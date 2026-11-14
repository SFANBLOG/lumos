"""
Agent 记忆管理.

三层记忆:

- **工作记忆**: ``AgentState`` + 有界追加归并器 (``reducers.py``), 单次任务内有效;
- **短期记忆**: LangGraph checkpointer 的 thread 级状态快照 (``checkpoint.py``),
  支持断点续跑; 由 ``prune_expired_checkpoints`` 按 TTL / 容量清理;
- **长期记忆**: 跨任务的审查经验与用户反馈, 存于 ``BaseStore``, 按命名空间隔离。
  只保存结构化摘要 (类别 / 评分 / 计数), 绝不写合同原文或条款正文。

默认 Store 是进程内 ``InMemoryStore``; 多机部署只需把 ``get_memory_store``
换成 PostgresStore, 上层读写接口不变。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from loguru import logger

from app.agent.checkpoint import get_checkpointer, graph_config
from app.core.config import get_settings

NAMESPACE_ROOT = "agent"

#: 清理节流 (秒), 避免每次分析结束都全量扫描 saver
_PRUNE_INTERVAL = 600.0
_last_prune_at: float = 0.0


def _ns(*parts: str) -> tuple[str, ...]:
    """命名空间: agent / <scope> / <subject>, 天然隔离用户与合同类型."""
    return (NAMESPACE_ROOT, *parts)


@lru_cache(maxsize=1)
def get_memory_store() -> BaseStore:
    """长期记忆 Store 单例."""
    return InMemoryStore()


def reset_memory_store() -> None:
    """清空 Store 单例 (测试隔离 / 配置切换)."""
    get_memory_store.cache_clear()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _expired(value: dict[str, Any]) -> bool:
    raw = value.get("_expires_at")
    if not raw:
        return False
    try:
        return datetime.fromisoformat(str(raw)) < datetime.now(UTC)
    except ValueError:
        return False


def _public(value: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in value.items() if not k.startswith("_")}


# ─── 长期记忆 CRUD ─────────────────────────────────────────────


def put_memory(
    namespace: tuple[str, ...],
    key: str,
    value: dict[str, Any],
    *,
    ttl_hours: float | None = None,
) -> None:
    """写入一条记忆, 带有效期与命名空间容量上限."""
    if not get_settings().memory_enabled:
        return
    store = get_memory_store()
    record = {**_public(value), "_updated_at": _now_iso()}
    ttl = ttl_hours if ttl_hours is not None else get_settings().memory_ttl_hours
    if ttl > 0:
        record["_expires_at"] = (datetime.now(UTC) + timedelta(hours=ttl)).isoformat()
    store.put(namespace, key, record)
    _evict_namespace(store, namespace)


def _evict_namespace(store: BaseStore, namespace: tuple[str, ...]) -> None:
    limit = max(1, get_settings().memory_max_items_per_namespace)
    items = store.search(namespace, limit=limit * 4)
    if len(items) <= limit:
        return
    ordered = sorted(items, key=lambda i: str(i.value.get("_updated_at", "")))
    for item in ordered[: len(items) - limit]:
        store.delete(tuple(item.namespace), item.key)


def get_memory(namespace: tuple[str, ...], key: str) -> dict[str, Any] | None:
    """读取一条有效记忆; 过期则顺手删除."""
    store = get_memory_store()
    item = store.get(namespace, key)
    if item is None:
        return None
    value = dict(item.value)
    if _expired(value):
        store.delete(namespace, key)
        return None
    return _public(value)


def search_memories(
    namespace_prefix: tuple[str, ...], *, limit: int = 20
) -> list[dict[str, Any]]:
    """列出命名空间前缀下的有效记忆 (顺带清理过期项)."""
    store = get_memory_store()
    out: list[dict[str, Any]] = []
    for item in store.search(namespace_prefix, limit=limit * 3):
        value = dict(item.value)
        if _expired(value):
            store.delete(tuple(item.namespace), item.key)
            continue
        out.append(
            {
                "namespace": tuple(item.namespace),
                "key": item.key,
                **_public(value),
            }
        )
    return out[:limit]


def delete_memory(namespace: tuple[str, ...], key: str) -> None:
    """遗忘: 显式删除一条记忆."""
    get_memory_store().delete(namespace, key)


def prune_expired_memories() -> int:
    """主动删除过期记忆, 并按容量淘汰最旧的 thread 级记忆命名空间.

    ``InMemoryStore`` 不支持 TTL, 惰性删除 (读时才删) 会让长期无人读取的
    条目一直占内存; 另外每份合同一个 thread namespace, 也需要容量上限。
    """
    store = get_memory_store()
    items = store.search((NAMESPACE_ROOT,), limit=10000)
    removed = 0
    kept: list[Any] = []
    for item in items:
        if _expired(dict(item.value)):
            store.delete(tuple(item.namespace), item.key)
            removed += 1
        else:
            kept.append(item)

    thread_items = [
        item
        for item in kept
        if len(item.namespace) == 3 and item.namespace[1] == "thread"
    ]
    overflow = len(thread_items) - max(1, get_settings().memory_max_threads)
    if overflow > 0:
        ordered = sorted(thread_items, key=lambda i: str(i.value.get("_updated_at", "")))
        for item in ordered[:overflow]:
            store.delete(tuple(item.namespace), item.key)
            removed += 1
    return removed


# ─── 经验沉淀与召回 ───────────────────────────────────────────


def record_experience(state: Any, *, user_id: str = "") -> None:
    """审查完成后沉淀经验; 只写结构化摘要, 不写合同原文 / 条款正文."""
    if not get_settings().memory_enabled:
        return
    ctype = str(state.contract_type or "unknown").strip() or "unknown"
    ns = _ns("experience", ctype)
    prev = get_memory(ns, "summary") or {}

    counts = dict(prev.get("category_counts", {}))
    for risk in state.risk_assessments:
        category = str(getattr(risk.category, "value", risk.category))
        counts[category] = int(counts.get(category, 0)) + 1

    total = int(prev.get("count", 0)) + 1
    avg_score = round(
        (float(prev.get("avg_score", 0)) * (total - 1) + int(state.overall_score)) / total, 2
    )
    put_memory(
        ns,
        "summary",
        {
            "contract_type": ctype,
            "count": total,
            "avg_score": avg_score,
            "avg_review_rounds": round(
                (float(prev.get("avg_review_rounds", 0)) * (total - 1) + int(state.review_rounds))
                / total,
                2,
            ),
            "category_counts": counts,
        },
    )
    put_memory(
        _ns("thread", str(state.contract_id)),
        "last_run",
        {
            "overall_score": int(state.overall_score),
            "overall_level": str(getattr(state.overall_level, "value", state.overall_level)),
            "risk_count": len(state.risk_assessments),
            "event_count": int(state.event_count),
            "review_decision": str(state.review_decision or ""),
        },
    )
    if user_id:
        put_memory(_ns("profile", user_id), "last_contract_type", {"contract_type": ctype})


def record_feedback(category: str, verdict: str, *, user_id: str = "") -> None:
    """用户风险反馈 → 长期记忆; 误报统计用于下次审查时抑制同类误判."""
    if not get_settings().memory_enabled or not category or verdict == "ignored":
        return
    ns = _ns("feedback", category)
    prev = get_memory(ns, "stats") or {}
    stats = {
        "category": category,
        "false_positive": int(prev.get("false_positive", 0)),
        "accepted": int(prev.get("accepted", 0)),
    }
    if verdict in ("false_positive", "accepted"):
        stats[verdict] += 1
    put_memory(ns, "stats", stats)


def build_recall(contract_type: str = "", *, user_id: str = "") -> list[str]:
    """新任务开始时召回相关长期记忆, 转成可注入状态的审查提示."""
    if not get_settings().memory_enabled:
        return []
    hints: list[str] = []
    ctype = str(contract_type or "unknown").strip() or "unknown"

    exp = get_memory(_ns("experience", ctype), "summary")
    if exp and int(exp.get("count", 0)) >= 2:
        top = sorted(exp.get("category_counts", {}).items(), key=lambda kv: -int(kv[1]))[:3]
        if top:
            hints.append("历史同类合同高频风险类别：" + "、".join(f"{k}({v})" for k, v in top))
        hints.append(f"历史同类合同平均评分 {exp.get('avg_score')}/100，样本 {exp.get('count')} 份")

    for item in search_memories(_ns("feedback"), limit=20):
        fp = int(item.get("false_positive", 0))
        total = fp + int(item.get("accepted", 0))
        if total >= 3 and fp / total >= 0.3:
            hints.append(
                f"历史反馈：{item.get('category')} 类别误报率偏高，"
                "请严格核对法定构成要件后再下结论"
            )

    if user_id:
        profile = get_memory(_ns("profile", user_id), "last_contract_type")
        if profile:
            hints.append(f"该用户上次审查的合同类型：{profile.get('contract_type')}")

    return hints[:8]


# ─── 短期记忆 (检查点) 清理 ───────────────────────────────────


def _checkpoint_time(tup: Any) -> datetime | None:
    raw = (tup.checkpoint or {}).get("ts") or (tup.metadata or {}).get("created_at")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


async def prune_expired_checkpoints(*, force: bool = False) -> dict[str, int]:
    """统一记忆清理入口 (带节流).

    - 长期记忆: 删除过期条目, 按容量淘汰最旧的 thread 命名空间;
    - 短期记忆: 按 TTL / 最大 thread 数清理检查点, 但保留在途任务的快照。
    """
    global _last_prune_at
    if not force and time.monotonic() - _last_prune_at < _PRUNE_INTERVAL:
        return {"scanned": 0, "deleted": 0, "kept": 0, "memories_deleted": 0, "skipped": 1}

    memories_deleted = prune_expired_memories()
    _last_prune_at = time.monotonic()

    saver = get_checkpointer()
    if saver is None:
        return {"scanned": 0, "deleted": 0, "kept": 0, "memories_deleted": memories_deleted}

    settings = get_settings()
    ttl_seconds = settings.memory_checkpoint_ttl_hours * 3600
    now = datetime.now(UTC)
    latest: dict[str, datetime] = {}
    scanned = 0
    async for tup in saver.alist(None, limit=5000):
        scanned += 1
        thread_id = str((tup.config.get("configurable") or {}).get("thread_id", ""))
        stamp = _checkpoint_time(tup)
        if not thread_id or stamp is None:
            continue
        if thread_id not in latest or stamp > latest[thread_id]:
            latest[thread_id] = stamp

    expired = {
        thread_id
        for thread_id, stamp in latest.items()
        if (now - stamp).total_seconds() > ttl_seconds
    }
    overflow = max(0, len(latest) - max(1, settings.memory_max_threads))
    if overflow:
        expired.update(thread_id for thread_id, _ in sorted(latest.items(), key=lambda kv: kv[1])[:overflow])

    # 在途任务 (还有 next 节点, 或挂在人工复核门) 一律保留:
    # 检查点最该保住的正是这些「未完成」状态。函数内导入避免与 graph 循环依赖。
    from app.agent.graph import _pending_interrupt, build_contract_graph

    graph = build_contract_graph()
    for thread_id in list(expired):
        try:
            snapshot = await graph.aget_state(graph_config(thread_id))
        except Exception:  # noqa: BLE001
            expired.discard(thread_id)  # 读不出来就保守保留
            continue
        if snapshot is not None and (
            snapshot.next or _pending_interrupt(snapshot) is not None
        ):
            expired.discard(thread_id)

    for thread_id in expired:
        await saver.adelete_thread(thread_id)
    if expired:
        logger.info(f"🧹 检查点清理 | 扫描 {scanned} 份, 删除 {len(expired)} 个 thread")
    return {
        "scanned": scanned,
        "deleted": len(expired),
        "kept": len(latest) - len(expired),
        "memories_deleted": memories_deleted,
    }


def get_memory_stats() -> dict[str, Any]:
    """当前记忆占用概览, 供健康检查 / 运维排查."""
    saver = get_checkpointer()
    items = search_memories((NAMESPACE_ROOT,), limit=1000)
    return {
        "enabled": get_settings().memory_enabled,
        "store_backend": type(get_memory_store()).__name__,
        "checkpoint_backend": type(saver).__name__ if saver is not None else "off",
        "long_term_items": len(items),
        "namespaces": sorted({"/".join(item["namespace"]) for item in items}),
    }
