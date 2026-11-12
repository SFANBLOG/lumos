"""法规时效元数据核验接口.

把 ``app.rag.law_meta`` 的核验能力暴露给运维/管理员:
- ``GET /laws/metadata``: 当前语料的元数据快照 (可作为版本基线存档);
- ``GET /laws/metadata/verify``: 逐部法规的待核验项与 ok 标志 (上线门禁);
- ``POST /laws/metadata/reload``: 热加载外部覆盖文件;
- ``POST /laws/metadata/diff``: 与历史快照对比, 输出字段级变更。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import AuthAny
from app.rag.law_corpus import ALL_LAWS
from app.rag.law_meta import (
    metadata_diff,
    override_path,
    reload_overrides,
    snapshot,
    verify_laws,
)

router = APIRouter(prefix="/laws", tags=["⚖️ 法规元数据"])


class SnapshotDiffRequest(BaseModel):
    """历史元数据快照 (``GET /laws/metadata`` 的返回值)."""

    previous: dict[str, dict[str, Any]] = Field(default_factory=dict)


@router.get("/metadata", summary="导出法规元数据快照")
async def metadata_snapshot(_auth: AuthAny) -> dict[str, dict[str, str]]:
    return snapshot(ALL_LAWS)


@router.get("/metadata/verify", summary="核验法规时效、来源与核对日期")
async def verify_metadata(
    _auth: AuthAny,
    stale_days: int = Query(default=180, ge=1, le=3650),
) -> dict:
    report = verify_laws(ALL_LAWS, stale_days=stale_days)
    report["corpus_law_count"] = len({str(l.get("law_name", "")) for l in ALL_LAWS})
    return report


@router.post("/metadata/reload", summary="热加载外部覆盖文件")
async def reload_metadata(_auth: AuthAny) -> dict:
    reload_overrides()
    return {
        "reloaded": True,
        "override_file": str(override_path()),
        "notice": "覆盖文件已重载；重启服务后语料会重新注入元数据，corpus_hash 变化将触发索引重建。",
    }


@router.post("/metadata/diff", summary="对比历史快照与当前元数据")
async def diff_metadata(body: SnapshotDiffRequest, _auth: AuthAny) -> dict:
    changes = metadata_diff(body.previous, snapshot(ALL_LAWS))
    return {"change_count": len(changes), "changes": changes}
