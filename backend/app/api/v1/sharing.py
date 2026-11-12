"""报告分享链接与在线批注.

产品化要点:
- 明文 token 只在创建时返回一次, 库里只存 sha256; 链接可设有效期、可撤销;
- 分享访问无需登录, 但只能读该合同的报告与批注, 不能访问合同列表/原文全文;
- 批注可挂在具体风险条目上并附引用原文, 导出 md/docx/pdf 时一并带上;
- 撤销或过期后, 所有公开端点立即 404。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlmodel import select

from app.api.deps import AuthAny, DBSession
from app.api.v1.contracts import get_report
from app.api.v1.exports import _load, render_export
from app.models.contract import Contract, ContractStatus
from app.models.review import ReportAnnotation, ReportShare
from app.schemas.analysis import AnalysisReportResponse
from app.schemas.review import (
    AnnotationCreate,
    AnnotationResponse,
    ShareCreateRequest,
    ShareListItem,
    ShareResponse,
)

router = APIRouter(prefix="/contracts", tags=["🔗 报告分享"])
public_router = APIRouter(prefix="/shared", tags=["🔗 分享访问"])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _expired(expires_at: datetime, now: datetime) -> bool:
    """兼容 MySQL 返回 naive datetime 的情况."""
    value = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
    return value <= now


async def _resolve_share(session, token: str) -> ReportShare:
    row = (
        await session.execute(
            select(ReportShare).where(
                ReportShare.token_hash == hash_token(token),
                ReportShare.revoked.is_(False),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享链接无效或已撤销")
    if _expired(row.expires_at, datetime.now(UTC)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享链接已过期")
    return row


@router.post(
    "/{contract_id}/share",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建报告分享链接",
    description="明文 token 仅返回一次; 默认 72 小时有效, 可随时撤销。",
)
async def create_share(
    contract_id: str,
    body: ShareCreateRequest,
    session: DBSession,
    _auth: AuthAny,
) -> ShareResponse:
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"合同 {contract_id} 不存在")
    if contract.status != ContractStatus.COMPLETED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "合同尚未分析完成, 暂不能分享报告"
        )

    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    share = ReportShare(
        token_hash=hash_token(token),
        contract_id=contract_id,
        # AuthAny 只做校验不解析用户身份; 这里不落 JWT, 避免凭据入库
        created_by=None,
        expires_at=now + timedelta(hours=body.ttl_hours),
        allow_annotations=body.allow_annotations,
        created_at=now,
    )
    session.add(share)
    await session.commit()
    await session.refresh(share)
    return ShareResponse(
        id=share.id,
        token=token,
        url=f"/shared/{token}/report",
        expires_at=share.expires_at,
        allow_annotations=share.allow_annotations,
        revoked=share.revoked,
    )


@router.get(
    "/{contract_id}/shares",
    response_model=list[ShareListItem],
    summary="列出该合同的分享链接",
)
async def list_shares(
    contract_id: str,
    session: DBSession,
    _auth: AuthAny,
) -> list[ShareListItem]:
    shares = list(
        (
            await session.execute(
                select(ReportShare)
                .where(ReportShare.contract_id == contract_id)
                .order_by(ReportShare.created_at.desc())
            )
        ).scalars().all()
    )
    counts = dict(
        (
            await session.execute(
                select(ReportAnnotation.share_id, func.count())
                .where(ReportAnnotation.contract_id == contract_id)
                .group_by(ReportAnnotation.share_id)
            )
        ).all()
    )
    return [
        ShareListItem(
            id=row.id,
            contract_id=row.contract_id,
            expires_at=row.expires_at,
            created_at=row.created_at,
            revoked=row.revoked,
            allow_annotations=row.allow_annotations,
            annotation_count=int(counts.get(row.id, 0)),
        )
        for row in shares
    ]


@router.delete(
    "/{contract_id}/shares/{share_id}",
    summary="撤销分享链接",
)
async def revoke_share(
    contract_id: str,
    share_id: str,
    session: DBSession,
    _auth: AuthAny,
) -> dict:
    row = await session.get(ReportShare, share_id)
    if row is None or row.contract_id != contract_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分享链接不存在")
    row.revoked = True
    session.add(row)
    await session.commit()
    return {"revoked": True, "share_id": share_id}


@router.get(
    "/{contract_id}/annotations",
    response_model=list[AnnotationResponse],
    summary="查看该合同的在线批注",
)
async def list_annotations(
    contract_id: str,
    session: DBSession,
    _auth: AuthAny,
) -> list[ReportAnnotation]:
    return list(
        (
            await session.execute(
                select(ReportAnnotation)
                .where(ReportAnnotation.contract_id == contract_id)
                .order_by(ReportAnnotation.created_at)
            )
        ).scalars().all()
    )


@public_router.get(
    "/{token}/report",
    response_model=AnalysisReportResponse,
    summary="通过分享链接查看报告 (免登录)",
)
async def shared_report(
    token: str,
    session: DBSession,
) -> AnalysisReportResponse:
    share = await _resolve_share(session, token)
    return await get_report(contract_id=share.contract_id, session=session, _auth=None)


@public_router.get(
    "/{token}/report/export",
    summary="通过分享链接导出报告 (免登录)",
)
async def shared_export(
    token: str,
    session: DBSession,
    fmt: str = Query(default="md", alias="format"),
) -> Response:
    share = await _resolve_share(session, token)
    _contract, analysis, risks, facts, missing, annotations = await _load(
        session, share.contract_id
    )
    content, mime, filename = render_export(
        fmt, share.contract_id, analysis, risks, facts, missing, annotations
    )
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@public_router.get(
    "/{token}/annotations",
    response_model=list[AnnotationResponse],
    summary="查看分享链接上的批注",
)
async def shared_annotations(
    token: str,
    session: DBSession,
) -> list[ReportAnnotation]:
    share = await _resolve_share(session, token)
    return list(
        (
            await session.execute(
                select(ReportAnnotation)
                .where(ReportAnnotation.share_id == share.id)
                .order_by(ReportAnnotation.created_at)
            )
        ).scalars().all()
    )


@public_router.post(
    "/{token}/annotations",
    response_model=AnnotationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交在线批注 (免登录)",
)
async def create_annotation(
    token: str,
    body: AnnotationCreate,
    session: DBSession,
) -> ReportAnnotation:
    share = await _resolve_share(session, token)
    if not share.allow_annotations:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "该分享链接不允许批注")
    row = ReportAnnotation(
        contract_id=share.contract_id,
        share_id=share.id,
        risk_item_id=body.risk_item_id,
        quote=body.quote,
        comment=body.comment,
        author=body.author,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
