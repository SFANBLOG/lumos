"""
智能咨询路由.

- POST /consult/ask: 发起一轮问答 (SSE 流式推送思考步骤与最终回答)
- GET  /consult/sessions: 当前用户的历史会话
- GET  /consult/sessions/{id}/messages: 会话内消息
- DELETE /consult/sessions/{id}: 删除会话
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import func
from sqlmodel import select

from app.agent.sub_agents.consultant_agent import ConsultantAgent
from app.api.deps import DBSession, get_current_user
from app.models.analysis import AnalysisResult, RiskItem
from app.models.consult import ConsultMessage, ConsultSession
from app.models.contract import Contract, ContractStatus
from app.models.user import User
from app.schemas.consult import (
    ConsultAskRequest,
    ConsultEventType,
    ConsultMessageOut,
    ConsultSessionListResponse,
    ConsultSessionOut,
)

router = APIRouter(prefix="/consult", tags=["💬 智能咨询"])

_MAX_CONTEXT_RISKS = 6


def _sse(event: ConsultEventType, data: dict) -> str:
    """格式化一条 SSE 帧."""
    return f"event: {event.value}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _build_contract_context(
    session: DBSession, contract_id: str
) -> tuple[str, list[str]]:
    """组装关联报告的风险摘要与分类列表, 供回答引用."""
    contract = await session.get(Contract, contract_id)
    if not contract or contract.status != ContractStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="关联报告不存在或尚未分析完成",
        )
    stmt = select(AnalysisResult).where(AnalysisResult.contract_id == contract_id)
    analysis = (await session.execute(stmt)).scalar_one_or_none()
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分析结果不存在",
        )
    stmt = (
        select(RiskItem)
        .where(RiskItem.analysis_id == analysis.id)
        .order_by(RiskItem.order)
        .limit(_MAX_CONTEXT_RISKS)
    )
    risks = (await session.execute(stmt)).scalars().all()

    lines = [
        f"整体评分 {analysis.overall_score}/100 ({analysis.overall_level.value})",
        f"总结: {analysis.summary}",
    ]
    for item in risks:
        lines.append(
            f"- [{item.level.value}] {item.title} | 解读: {item.explanation}"
            f" | 依据: {item.legal_basis} | 谈判建议: {item.negotiation_tip}"
        )
    return "\n".join(lines), [r.category.value for r in risks]


# ─── POST /consult/ask (SSE 流) ────────────────────────────────


@router.post(
    "/ask",
    summary="发起智能咨询问答 (SSE 流式)",
    description="逐步推送思考过程与最终回答 (含法条引用与追问建议)。",
)
async def ask_question(
    request: ConsultAskRequest,
    session: DBSession,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """处理一轮问答, 以 SSE 推送结果."""
    # 前置校验与上下文准备 (在返回流之前完成, 错误走普通 JSON)
    contract_context: str | None = None
    report_categories: list[str] | None = None
    if request.contract_id:
        contract_context, report_categories = await _build_contract_context(
            session, request.contract_id
        )

    consult_session: ConsultSession | None = None
    if request.session_id:
        consult_session = await session.get(ConsultSession, request.session_id)
        if not consult_session or consult_session.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )
    else:
        consult_session = ConsultSession(
            user_id=current_user.id,
            title=request.question.strip()[:20] or "新对话",
            contract_id=request.contract_id,
        )
        session.add(consult_session)
        await session.flush()

    if request.contract_id is not None and consult_session.contract_id != request.contract_id:
        consult_session.contract_id = request.contract_id
        session.add(consult_session)

    # 落用户问题行
    next_seq = (
        await session.execute(
            select(func.max(ConsultMessage.seq)).where(
                ConsultMessage.session_id == consult_session.id
            )
        )
    ).scalar_one() or 0
    user_msg = ConsultMessage(
        session_id=consult_session.id,
        seq=next_seq + 1,
        role="user",
        content=request.question.strip(),
    )
    session.add(user_msg)
    await session.commit()

    agent = ConsultantAgent()
    answered = False

    async def event_generator():
        nonlocal answered
        try:
            yield _sse(
                ConsultEventType.SESSION, {"session_id": consult_session.id}
            )

            async for item in agent.answer(
                request.question,
                contract_context=contract_context,
                report_categories=report_categories,
            ):
                if item["type"] == "step":
                    yield _sse(ConsultEventType.STEP, {"message": item["message"]})
                else:
                    # final: 先落库再推送 (客户端收到即断连也不丢回答)
                    seq = (
                        await session.execute(
                            select(func.max(ConsultMessage.seq)).where(
                                ConsultMessage.session_id == consult_session.id
                            )
                        )
                    ).scalar_one() or 0
                    assistant_msg = ConsultMessage(
                        session_id=consult_session.id,
                        seq=seq + 1,
                        role="assistant",
                        content=item["content"],
                        refs_json=json.dumps(item["references"], ensure_ascii=False),
                        suggestions_json=json.dumps(
                            item["suggestions"], ensure_ascii=False
                        ),
                    )
                    consult_session.updated_at = datetime.now(UTC)
                    session.add(assistant_msg)
                    session.add(consult_session)
                    await session.commit()
                    answered = True

                    yield _sse(
                        ConsultEventType.ANSWER,
                        {
                            "message_id": assistant_msg.id,
                            "content": item["content"],
                            "references": item["references"],
                            "suggestions": item["suggestions"],
                        },
                    )

            yield _sse(
                ConsultEventType.COMPLETE, {"message": "✨ 回答完成"}
            )

        except asyncio.CancelledError:
            # 客户端断开: 问题行已落库, 补齐中断提示, 保证历史无"有问无答"
            logger.warning(f"咨询 SSE 连接中断 | 会话: {consult_session.id}")
            try:
                await _ensure_fallback_answer(session, consult_session.id, answered)
            except Exception:
                logger.exception("咨询中断后回补占位回答失败")
            raise

        except Exception as e:
            logger.exception(f"咨询回答失败 | 会话: {consult_session.id}")
            if not answered:
                try:
                    await _ensure_fallback_answer(
                        session, consult_session.id, answered, error=str(e)
                    )
                except Exception:
                    logger.exception("咨询失败后回补占位回答失败")
            yield _sse(
                ConsultEventType.ERROR, {"message": f"回答失败: {e}"}
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 禁用缓冲
        },
    )


async def _ensure_fallback_answer(
    session: DBSession,
    consult_session_id: str,
    answered: bool,
    *,
    error: str | None = None,
) -> None:
    """本轮无回答时补一条占位助手消息."""
    if answered:
        return
    seq = (
        await session.execute(
            select(func.max(ConsultMessage.seq)).where(
                ConsultMessage.session_id == consult_session_id
            )
        )
    ).scalar_one() or 0
    reason = f"（本轮回答失败：{error}）" if error else "（回答中断，请重试）"
    session.add(
        ConsultMessage(
            session_id=consult_session_id,
            seq=seq + 1,
            role="assistant",
            content=reason,
        )
    )
    await session.commit()


# ─── GET /consult/sessions ─────────────────────────────────────


@router.get(
    "/sessions",
    response_model=ConsultSessionListResponse,
    summary="历史咨询会话 (分页)",
)
async def list_sessions(
    session: DBSession,
    current_user: User = Depends(get_current_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConsultSessionListResponse:
    """当前用户会话列表 (按最后活跃时间倒序)."""
    total = (
        await session.execute(
            select(func.count())
            .select_from(ConsultSession)
            .where(ConsultSession.user_id == current_user.id)
        )
    ).scalar_one()

    stmt = (
        select(ConsultSession, func.count(ConsultMessage.id))
        .outerjoin(ConsultMessage, ConsultMessage.session_id == ConsultSession.id)
        .where(ConsultSession.user_id == current_user.id)
        .group_by(ConsultSession.id)
        .order_by(ConsultSession.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()

    items = [
        ConsultSessionOut(
            id=s.id,
            title=s.title,
            contract_id=s.contract_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=cnt,
        )
        for s, cnt in rows
    ]
    return ConsultSessionListResponse(
        total=total, page=page, page_size=page_size, items=items
    )


# ─── GET /consult/sessions/{id}/messages ───────────────────────


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ConsultMessageOut],
    summary="获取会话内全部消息",
)
async def list_messages(
    session_id: str,
    session: DBSession,
    current_user: User = Depends(get_current_user),
) -> list[ConsultMessageOut]:
    """会话内消息 (正序)."""
    consult_session = await session.get(ConsultSession, session_id)
    if not consult_session or consult_session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    stmt = (
        select(ConsultMessage)
        .where(ConsultMessage.session_id == session_id)
        .order_by(ConsultMessage.seq)
    )
    messages = (await session.execute(stmt)).scalars().all()

    return [
        ConsultMessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            references=_load_json(m.refs_json),
            suggestions=_load_json(m.suggestions_json),
            created_at=m.created_at,
        )
        for m in messages
    ]


def _load_json(raw: str) -> list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ─── DELETE /consult/sessions/{id} ─────────────────────────────


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除会话及其消息",
)
async def delete_session(
    session_id: str,
    session: DBSession,
    current_user: User = Depends(get_current_user),
) -> Response:
    """删除会话 (连带消息)."""
    consult_session = await session.get(ConsultSession, session_id)
    if not consult_session or consult_session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    await session.execute(
        ConsultMessage.__table__.delete().where(
            ConsultMessage.session_id == session_id
        )
    )
    await session.delete(consult_session)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
