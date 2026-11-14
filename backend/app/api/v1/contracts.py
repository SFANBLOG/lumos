"""
合同分析路由.

核心业务接口:
- POST /contracts: 提交合同 → 启动 Agent 分析
- GET  /contracts/{id}/stream: SSE 流式接收分析过程
- GET  /contracts/{id}/report: 获取完整分析报告
- POST /contracts/{id}/resume: 人工复核通过后从检查点续跑
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import func
from sqlmodel import select

from app.agent.graph import get_checkpoint_state
from app.api.deps import AuthAny, DBSession
from app.models.analysis import AnalysisResult, RiskItem, RiskLevel
from app.models.contract import Contract, ContractStatus
from app.models.review import ContractFactItem, MissingClauseItem
from app.services import analysis_task
from app.services.audit import record_audit_event
from app.services.contract_guard import check_document
from app.schemas.analysis import AnalysisReportResponse, RiskItemResponse, SSEEventType
from app.schemas.review import ContractFactResponse, MissingClauseResponse
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
        "doc_type": contract.doc_type,
        "doc_check_note": contract.doc_check_note,
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
    http_request: Request,
) -> ContractSubmitResponse:
    """提交合同文本进行 AI 风险排查."""
    logger.info(
        f"📥 收到合同提交 | 来源: {request.source.value} | "
        f"字数: {len(request.text)}"
    )

    # 服务端重跑一次文档类型判定: 不能只依赖前端传参 (接口可被直接调用).
    # 非合同内容默认拦截, 用户二次确认后带 force=true 才放行, 并在报告里标注。
    doc_check = await check_document(request.text)
    if not doc_check.is_contract and not request.force:
        logger.warning(
            f"⛔ 内容判定为非合同, 已拦截 | 类型: {doc_check.doc_type.value} | "
            f"置信度: {doc_check.confidence}"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": doc_check.notice or "内容可能不是合同，无法进行合同风险审查",
                "doc_check": doc_check.to_dict(),
            },
        )

    # 创建合同记录
    contract = Contract(
        raw_text=request.text,
        source=request.source,
        status=ContractStatus.ANALYZING,
        page_count=request.page_count,
        char_count=len(request.text),
        device_id=request.device_id,
        doc_type=doc_check.doc_type.value,
        doc_confidence=doc_check.confidence,
        doc_check_method=doc_check.method,
        doc_check_note=doc_check.notice,
    )

    session.add(contract)
    await session.flush()  # 获取 ID
    await record_audit_event(
        session,
        action="contract.submitted",
        resource_type="contract",
        resource_id=contract.id,
        request_id=getattr(http_request.state, "request_id", None),
        ip_address=http_request.client.host if http_request.client else None,
        details={"source": request.source.value, "char_count": len(request.text)},
    )
    # 先提交落库, 再启动后台任务 (任务使用独立会话, 必须能读到该记录)
    await session.commit()

    analysis_task.start_analysis(
        contract.id, request.text, contract_type=request.contract_type
    )

    logger.info(f"✅ 合同记录已创建 | ID: {contract.id}")

    return ContractSubmitResponse(
        contract_id=contract.id,
        status=ContractStatus.ANALYZING,
        message="合同已受理, 正在进行 AI 风险排查…",
        stream_url=f"/api/v1/contracts/{contract.id}/stream",
    )


# ─── POST /contracts/{id}/resume (人工复核通过后续跑) ──────────


@router.post(
    "/{contract_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    summary="人工复核通过后从检查点续跑",
    description=(
        "CHECKPOINT_REVIEW_GATE 开启时, 高风险合同会挂起在复核门;"
        "复核通过后以同一 thread_id 从检查点继续, SSE 重连可看到完整进度。"
    ),
)
async def resume_contract(
    contract_id: str,
    session: DBSession,
    _auth: AuthAny,
) -> dict:
    """人工复核通过 → 从 LangGraph 检查点续跑."""
    if await session.get(Contract, contract_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"合同 {contract_id} 不存在",
        )
    state = await get_checkpoint_state(contract_id)
    if state is None or not state["pending_review"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该合同没有待复核的检查点, 无需续跑",
        )
    if not analysis_task.resume_analysis(contract_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="分析任务仍在运行, 请稍后重试",
        )
    return {
        "contract_id": contract_id,
        "status": "resuming",
        "checkpoint_id": state["checkpoint_id"],
    }


# ─── GET /contracts/{id}/stream (SSE) ──────────────────────────


@router.get(
    "/{contract_id}/stream",
    summary="SSE 流式接收分析过程",
    description="通过 Server-Sent Events 实时接收 Agent 的思考进度和风险发现。",
)
async def stream_analysis(
    contract_id: str,
    session: DBSession,
    _auth: AuthAny,
) -> StreamingResponse:
    """SSE 流式推送合同分析进度 (回放后台任务缓冲, 断线可重连)."""
    # 查找合同
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"合同 {contract_id} 不存在",
        )

    raw_text = contract.raw_text
    status_now = contract.status

    async def event_generator():
        """生成 SSE 事件流."""
        if not analysis_task.has_session(contract_id):
            # 无内存会话 (进程重启 / 缓冲已淘汰): 先看检查点, 避免重复分析
            try:
                checkpoint = await get_checkpoint_state(contract_id)
            except Exception:  # noqa: BLE001
                logger.exception(f"检查点查询失败 | 合同ID: {contract_id}")
                checkpoint = None
            if status_now == ContractStatus.ANALYZING:
                if checkpoint and checkpoint["pending_review"]:
                    data = json.dumps(
                        {"message": "该合同正在等待人工复核, 复核通过后自动续跑"},
                        ensure_ascii=False,
                    )
                    yield f"event: {SSEEventType.AWAITING_REVIEW.value}\ndata: {data}\n\n"
                    return
                if checkpoint and checkpoint["next"]:
                    analysis_task.start_resume(contract_id)
                else:
                    analysis_task.start_analysis(contract_id, raw_text)
            elif status_now == ContractStatus.COMPLETED:
                data = json.dumps({"message": "✨ 该合同已完成分析"}, ensure_ascii=False)
                yield f"event: complete\ndata: {data}\n\n"
                return
            else:
                data = json.dumps(
                    {"message": f"分析已结束, 当前状态: {status_now.value}, 请重新提交"},
                    ensure_ascii=False,
                )
                yield f"event: error\ndata: {data}\n\n"
                return

        async for event in analysis_task.stream_events(contract_id):
            # 格式化为 SSE 协议
            data = json.dumps(event.data, ensure_ascii=False)
            yield f"event: {event.event.value}\ndata: {data}\n\n"

            # 给前端一点渲染时间
            await asyncio.sleep(0.1)

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

    # 审查增强层: 要素核对表 + 缺失条款清单
    fact_stmt = (
        select(ContractFactItem)
        .where(ContractFactItem.analysis_id == analysis.id)
        .order_by(ContractFactItem.order)
    )
    facts = (await session.execute(fact_stmt)).scalars().all()
    missing_stmt = (
        select(MissingClauseItem)
        .where(MissingClauseItem.analysis_id == analysis.id)
        .order_by(MissingClauseItem.order)
    )
    missing = (await session.execute(missing_stmt)).scalars().all()
    required = [f for f in facts if f.required]
    coverage = (
        round(100 * sum(1 for f in required if f.status == "present") / len(required))
        if required
        else 100
    )

    return AnalysisReportResponse(
        contract_id=contract_id,
        overall_score=analysis.overall_score,
        overall_level=analysis.overall_level,
        summary=analysis.summary,
        risk_items=[
            RiskItemResponse(
                id=item.id,
                category=item.category,
                level=item.level,
                title=item.title,
                original_clause=item.original_clause,
                explanation=item.explanation,
                legal_basis=item.legal_basis,
                negotiation_tip=item.negotiation_tip,
                # 旧库通过 ALTER 补的列允许 NULL, 统一兜底成空串
                suggested_revision=item.suggested_revision or "",
                revision_reason=item.revision_reason or "",
                revision_diff=item.revision_diff or "",
                revision_method=item.revision_method or "",
                revision_confidence=item.revision_confidence or 0.0,
                score=item.score,
            )
            for item in risk_items
        ],
        contract_facts=[ContractFactResponse.model_validate(f) for f in facts],
        missing_clauses=[MissingClauseResponse.model_validate(m) for m in missing],
        coverage_score=coverage,
        content_notice=contract.doc_check_note,
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
