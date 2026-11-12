"""风险条目级反馈闭环 API.

补齐市面合同审查产品的 accept / reject 反馈层: 原项目只有合同级审批队列
(ApprovalTask), 决策不回写风险结论, 前端「建议采纳率」是写死的 mock。
这里让每条 AI 风险都可被判定为「认可 / 误报 / 忽略」，落库后:
- ``/feedback/stats`` 提供真实采纳率与误报率, 替换前端演示数据;
- 误报样本可直接作为端到端评测集与 prompt/规则调优依据;
- 每次提交写审计事件, 满足人工复核留痕要求。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import select

from app.api.deps import DBSession, get_current_user
from app.models.analysis import RiskItem
from app.models.review import RiskFeedback
from app.models.user import User
from app.services.feedback_insights import build_eval_cases, rule_tuning_suggestions
from app.schemas.review import (
    RiskFeedbackCreate,
    RiskFeedbackResponse,
    ReviewStatsResponse,
)
from app.services.audit import record_audit_event

router = APIRouter(prefix="/feedback", tags=["💬 风险反馈"])


@router.post(
    "",
    response_model=RiskFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交风险反馈",
    description="对单条 AI 风险结论标记认可 / 误报 / 忽略; 同一用户重复提交视为更新。",
)
async def submit_feedback(
    body: RiskFeedbackCreate,
    session: DBSession,
    user: User = Depends(get_current_user),
) -> RiskFeedback:
    user_id = getattr(user, "id", None)
    stmt = select(RiskFeedback).where(
        RiskFeedback.risk_item_id == body.risk_item_id,
        RiskFeedback.user_id == user_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    now = datetime.now(UTC)

    if row is None:
        row = RiskFeedback(
            risk_item_id=body.risk_item_id,
            contract_id=body.contract_id,
            verdict=body.verdict.value,
            comment=body.comment,
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
    else:
        row.verdict = body.verdict.value
        row.comment = body.comment
        row.contract_id = body.contract_id
        row.updated_at = now

    session.add(row)
    await record_audit_event(
        session,
        action=f"risk_feedback.{body.verdict.value}",
        resource_type="risk_item",
        resource_id=body.risk_item_id,
        actor_id=user_id,
    )
    await session.commit()
    await session.refresh(row)
    return row


@router.get(
    "/contracts/{contract_id}",
    response_model=list[RiskFeedbackResponse],
    summary="查询某合同的风险反馈",
)
async def list_feedback(
    contract_id: str,
    session: DBSession,
    _user: User = Depends(get_current_user),
) -> list[RiskFeedback]:
    stmt = (
        select(RiskFeedback)
        .where(RiskFeedback.contract_id == contract_id)
        .order_by(RiskFeedback.updated_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get(
    "/stats",
    response_model=ReviewStatsResponse,
    summary="真实采纳率与误报率",
    description="基于 risk_feedback 表统计, 供 Dashboard 替换演示数据。",
)
async def feedback_stats(
    session: DBSession,
    _user: User = Depends(get_current_user),
) -> ReviewStatsResponse:
    rows = list((await session.execute(select(RiskFeedback))).scalars().all())
    total = len(rows)
    accepted = sum(1 for r in rows if r.verdict == "accepted")
    false_positive = sum(1 for r in rows if r.verdict == "false_positive")
    ignored = sum(1 for r in rows if r.verdict == "ignored")
    return ReviewStatsResponse(
        total=total,
        accepted=accepted,
        false_positive=false_positive,
        ignored=ignored,
        adoption_rate=round(accepted / total, 4) if total else 0.0,
        false_positive_rate=round(false_positive / total, 4) if total else 0.0,
    )


async def _load_feedback_and_risks(session, limit: int):
    """读取最近的反馈及其对应风险条目 (只查用到的行, 避免全表扫描)."""
    feedback = list(
        (
            await session.execute(
                select(RiskFeedback)
                .order_by(RiskFeedback.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )
    risk_ids = [row.risk_item_id for row in feedback]
    risks: list[RiskItem] = []
    if risk_ids:
        risks = list(
            (
                await session.execute(
                    select(RiskItem).where(RiskItem.id.in_(risk_ids))
                )
            ).scalars().all()
        )
    return feedback, risks


@router.get(
    "/eval-cases",
    summary="导出反馈回流评测集",
    description="认可的结论导出为可并入 review_golden.json 的正例; 误报原文导出为「期望无风险」反例集。",
)
async def eval_cases(
    session: DBSession,
    _user: User = Depends(get_current_user),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict:
    feedback, risks = await _load_feedback_and_risks(session, limit)
    return build_eval_cases(feedback, risks)


@router.get(
    "/tuning-suggestions",
    summary="按风险类别生成规则调优建议",
    description="误报率达到阈值时给出 prompt / 规则 / 置信度阈值与回归用例的具体动作。",
)
async def tuning_suggestions(
    session: DBSession,
    _user: User = Depends(get_current_user),
    limit: int = Query(default=500, ge=1, le=5000),
    min_samples: int = Query(default=3, ge=1, le=100),
    fp_threshold: float = Query(default=0.3, ge=0.0, le=1.0),
) -> dict:
    feedback, risks = await _load_feedback_and_risks(session, limit)
    return rule_tuning_suggestions(
        feedback,
        risks,
        min_samples=min_samples,
        fp_threshold=fp_threshold,
    )
