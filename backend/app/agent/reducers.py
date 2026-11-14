"""
LangGraph 状态归并器 (Reducer).

只对「天然追加」的字段启用累加语义: 错误信息、执行轨迹、智能体消息、SSE 事件。
条款 / 法条 / 风险 / 要素表等结论型列表由单个节点整体产出, 返工时应该覆盖旧结论
而不是累加, 因此仍使用 LangGraph 默认的 LastValue (覆盖) 语义。

启用归并器后, 节点必须返回「本次新增的增量」而不是完整状态快照,
否则历史条目会被归并器重复累加 (同一条消息/事件出现两遍)。

工作记忆有界: 每个追加字段只保留最近 N 条, 避免长合同 / 多轮返工让单个
checkpoint 无限膨胀。SSE 回放改用 ``AgentState.event_count`` 单调游标,
不再依赖列表长度, 因此裁剪事件列表不会丢帧。
"""

from __future__ import annotations

from typing import Any, TypeVar

from app.core.config import get_settings

T = TypeVar("T")

#: 使用追加归并器的状态字段 (与 ``AgentState`` 的 Annotated 注解一一对应)
APPEND_FIELDS: frozenset[str] = frozenset(
    {"errors", "agent_trace", "agent_messages", "events"}
)


def bounded_append(left: list[T] | None, right: list[T] | None, limit: int) -> list[T]:
    """追加后只保留最后 ``limit`` 条 (limit <= 0 表示不限制)."""
    merged = [*(left or []), *(right or [])]
    if limit > 0 and len(merged) > limit:
        return merged[-limit:]
    return merged


def append_list(left: list[T] | None, right: list[T] | None) -> list[T]:
    """无界追加 (兼容旧调用与单测), 生产字段请使用下面的有界版本."""
    return bounded_append(left, right, 0)


def append_events(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    """SSE 事件: 只留最近的窗口, 回放由 event_count 游标保证不丢帧."""
    return bounded_append(left, right, get_settings().memory_max_events)


def append_messages(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    """智能体消息总线."""
    return bounded_append(left, right, get_settings().memory_max_messages)


def append_trace(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    """执行轨迹 (含返工重复执行)."""
    return bounded_append(left, right, get_settings().memory_max_trace)


def append_errors(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    """错误信息收集."""
    return bounded_append(left, right, get_settings().memory_max_errors)


def state_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """把节点执行前/后的完整状态快照转成「增量更新」字典.

    - 追加字段: 只取新增的尾部条目, 交给归并器累加;
    - 其余字段: 只返回发生变化的值, 由框架按覆盖语义写回 (未变化字段不写);
    - ``events`` / ``event_count`` 由调用方覆写 (事件不在 state.events 里)。
    """
    delta: dict[str, Any] = {
        key: value
        for key, value in after.items()
        if key not in APPEND_FIELDS and value != before.get(key)
    }
    for field in APPEND_FIELDS:
        old = before.get(field) or []
        new = after.get(field) or []
        delta[field] = new[len(old) :]
    return delta
