"""
合同分析路由.

核心业务接口:
- POST /contracts: 提交合同 → 启动 Agent 分析
- GET  /contracts/{id}/stream: SSE 流式接收分析过程
- GET  /contracts/{id}/report: 获取完整分析报告
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import func
from sqlmodel import select

from app.agent.graph import run_contract_analysis
from app.api.deps import AuthAny, DBSession
from app.models.analysis import AnalysisResult, RiskItem, RiskLevel
from app.models.contract import Contract, ContractStatus
from app.schemas.analysis import AnalysisReportResponse, RiskItemResponse, SSEEventType
from app.schemas.contract import (
    ContractCreateRequest,
    ContractListResponse,
    ContractResponse,
    ContractStatsResponse,
    ContractSubmitResponse,
)

router = APIRouter(prefix="/contracts", tags=["📄 合同分析"])


async def _to_list_item(contract: Contract) -> dict:
    """合同记录 → 列表项 (含正文预览)."""
    return {
        "id": contract.id,
        "source": contract.source,
        "status": contract.status,
        "char_count": contract.char_count,
        "created_at": contract.created_at,
        "preview": (contract.raw_text or "")[:80],
    }


# ─── GET /contracts (列表, 须在 /{contract_id} 之前注册) ───────


@router.get(
    "",
    response_model=ContractListResponse,
    summary="合同记录列表 (分页)",
)
async def list_contracts(
    session: DBSession,
    _auth: AuthAny,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status_filter: ContractStatus | None = Query(default=None, alias="status"),
) -> ContractListResponse:
    """按时间倒序分页查询合同记录, 可按状态过滤."""
    where = [Contract.status == status_filter] if status_filter else []

    count_stmt = select(func.count()).select_from(Contract)
    if where:
        count_stmt = count_stmt.where(*where)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = select(Contract)
    if where:
        stmt = stmt.where(*where)
    stmt = stmt.order_by(Contract.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await session.execute(stmt)).scalars().all()

    return ContractListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[await _to_list_item(c) for c in items],
    )


# ─── GET /contracts/stats (看板统计, 须在 /{contract_id} 之前注册) ─


@router.get(
    "/stats",
    response_model=ContractStatsResponse,
    summary="看板统计汇总",
)
async def get_stats(
    session: DBSession,
    _auth: AuthAny,
) -> ContractStatsResponse:
    """返回分析总量、状态分布、平均分、风险等级计数与最近记录."""
    async def count_where(*conds) -> int:
        stmt = select(func.count()).select_from(Contract)
        if conds:
            stmt = stmt.where(*conds)
        return (await session.execute(stmt)).scalar_one()

    total = await count_where()
    completed = await count_where(Contract.status == ContractStatus.COMPLETED)
    analyzing = await count_where(Contract.status == ContractStatus.ANALYZING)
    failed = await count_where(Contract.status == ContractStatus.FAILED)
    pending = await count_where(Contract.status == ContractStatus.PENDING)

    avg_score = (
        await session.execute(
            select(func.avg(AnalysisResult.overall_score))
        )
    ).scalar_one()
    high_risk = (
        await session.execute(
            select(func.count())
            .select_from(AnalysisResult)
            .where(AnalysisResult.overall_level == RiskLevel.HIGH)
        )
    ).scalar_one()

    level_rows = (
        await session.execute(
            select(RiskItem.level, func.count()).group_by(RiskItem.level)
        )
    ).all()
    level_counts = {lv.value: 0 for lv in RiskLevel}
    for level, cnt in level_rows:
        if level is not None:
            level_counts[level.value] = cnt

    recent_stmt = select(Contract).order_by(Contract.created_at.desc()).limit(5)
    recent = (await session.execute(recent_stmt)).scalars().all()

    return ContractStatsResponse(
        total=total,
        completed=completed,
        analyzing=analyzing,
        failed=failed,
        pending=pending,
        avg_overall_score=round(avg_score, 1) if avg_score is not None else None,
        high_risk_contracts=high_risk,
        level_counts=level_counts,
        recent=[await _to_list_item(c) for c in recent],
    )


# ─── POST /contracts ───────────────────────────────────────────


@router.post(
    "",
    response_model=ContractSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交合同进行风险排查",
    description="接收脱敏后的合同文本，创建合同记录并启动 AI Agent 分析。"
    "分析结果通过 SSE 流式推送。",
)
async def submit_contract(
    request: ContractCreateRequest,
    session: DBSession,
    _auth: AuthAny,
) -> ContractSubmitResponse:
    """提交合同文本进行 AI 风险排查."""
    logger.info(
        f"📥 收到合同提交 | 来源: {request.source.value} | "
        f"字数: {len(request.text)}"
    )

    # 创建合同记录
    contract = Contract(
        raw_text=request.text,
        source=request.source,
        status=ContractStatus.ANALYZING,
        page_count=request.page_count,
        char_count=len(request.text),
        device_id=request.device_id,
    )

    session.add(contract)
    await session.flush()  # 获取 ID, 但不提交事务 (由 get_session 管理)

    logger.info(f"✅ 合同记录已创建 | ID: {contract.id}")

    return ContractSubmitResponse(
        contract_id=contract.id,
        status=ContractStatus.ANALYZING,
        message="合同已受理, 正在进行 AI 风险排查…",
        stream_url=f"/api/v1/contracts/{contract.id}/stream",
    )


# ─── GET /contracts/{id}/stream (SSE) ──────────────────────────


@router.get(
    "/{contract_id}/stream",
    summary="SSE 流式接收分析过程",
    description="通过 Server-Sent Events 实时接收 Agent 的思考进度和风险发现。",
)
async def stream_analysis(
    contract_id: str,
    session: DBSession,
) -> StreamingResponse:
    """SSE 流式推送合同分析进度."""
    # 查找合同
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"合同 {contract_id} 不存在",
        )

    async def event_generator():
        """生成 SSE 事件流."""
        try:
            async for event in run_contract_analysis(
                contract_id=contract_id,
                raw_text=contract.raw_text,
                session=session,
            ):
                # 在推送 complete 前先落库: 客户端收到后可能立即断开,
                # 若之后再提交状态, 生成器会被取消导致状态永远停留在 analyzing
                if event.event == SSEEventType.COMPLETE:
                    contract.status = ContractStatus.COMPLETED
                    contract.updated_at = datetime.now(UTC)
                    session.add(contract)
                    await session.commit()

                # 格式化为 SSE 协议
                data = json.dumps(event.data, ensure_ascii=False)
                yield f"event: {event.event.value}\ndata: {data}\n\n"

                # 给前端一点渲染时间
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            # 客户端提前断开 (如中途离开分析页): 数据已持久化则视为完成, 否则标记失败
            logger.warning(f"SSE 连接中断 | 合同ID: {contract_id}")
            try:
                persisted = (
                    await session.execute(
                        select(AnalysisResult).where(AnalysisResult.contract_id == contract_id)
                    )
                ).scalar_one_or_none()
                contract.status = (
                    ContractStatus.COMPLETED if persisted else ContractStatus.FAILED
                )
                contract.updated_at = datetime.now(UTC)
                session.add(contract)
                await session.commit()
            except Exception:
                logger.exception("SSE 连接中断后状态更新失败")
            raise

        except Exception as e:
            logger.exception(f"SSE 流异常 | 合同ID: {contract_id}")
            error_data = json.dumps(
                {"message": f"分析失败: {e}"},
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {error_data}\n\n"

            # 标记失败
            contract.status = ContractStatus.FAILED
            contract.updated_at = datetime.now(UTC)
            session.add(contract)
            await session.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 禁用缓冲
        },
    )


# ─── GET /contracts/{id}/report ────────────────────────────────


@router.get(
    "/{contract_id}/report",
    response_model=AnalysisReportResponse,
    summary="获取完整分析报告",
    description="获取指定合同的完整风险分析报告 (需分析完成后调用)。",
)
async def get_report(
    contract_id: str,
    session: DBSession,
    _auth: AuthAny,
) -> AnalysisReportResponse:
    """获取合同的完整风险分析报告."""
    # 查找合同
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"合同 {contract_id} 不存在",
        )

    if contract.status != ContractStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"合同尚未分析完成, 当前状态: {contract.status.value}",
        )

    # 查找分析结果
    stmt = select(AnalysisResult).where(AnalysisResult.contract_id == contract_id)
    result = await session.execute(stmt)
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分析结果不存在",
        )

    # 查找风险条目
    stmt = (
        select(RiskItem)
        .where(RiskItem.analysis_id == analysis.id)
        .order_by(RiskItem.order)
    )
    result = await session.execute(stmt)
    risk_items = result.scalars().all()

    return AnalysisReportResponse(
        contract_id=contract_id,
        overall_score=analysis.overall_score,
        overall_level=analysis.overall_level,
        summary=analysis.summary,
        risk_items=[RiskItemResponse.model_validate(item) for item in risk_items],
        analyzed_at=analysis.created_at,
    )


# ─── GET /contracts/{id} ──────────────────────────────────────


@router.get(
    "/{contract_id}",
    response_model=ContractResponse,
    summary="查询合同状态",
)
async def get_contract(
    contract_id: str,
    session: DBSession,
    _auth: AuthAny,
) -> ContractResponse:
    """查询合同记录与当前处理状态."""
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"合同 {contract_id} 不存在",
        )

    return ContractResponse.model_validate(contract)
