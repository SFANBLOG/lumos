"""
Supervisor Agent — 编排智能体.

负责调度子智能体、管理状态流转、发射 SSE 事件。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.base import BaseAgent
from app.agent.state import AgentState
from app.agent.sub_agents.extractor_agent import ExtractorAgent
from app.agent.sub_agents.retriever_agent import RetrieverAgent
from app.agent.sub_agents.reviewer_agent import ReviewerAgent
from app.agent.sub_agents.negotiator_agent import NegotiatorAgent
from app.models.analysis import AnalysisResult, RiskItem
from app.schemas.analysis import AgentNodeProgress, SSEEvent, SSEEventType


class SupervisorAgent:
    """编排所有子智能体，驱动完整合同分析流程."""

    def __init__(self) -> None:
        self._agents: list[BaseAgent] = [
            ExtractorAgent(),
            RetrieverAgent(),
            ReviewerAgent(),
            NegotiatorAgent(),
        ]

    async def run(
        self,
        contract_id: str,
        raw_text: str,
        session: AsyncSession | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """执行完整分析流程，异步产出 SSE 事件."""
        logger.info(f"🚀 Supervisor 启动 | 合同ID: {contract_id}")

        state = AgentState(contract_id=contract_id, raw_text=raw_text)
        total = len(self._agents)

        for idx, agent in enumerate(self._agents):
            progress = idx / total

            yield SSEEvent(
                event=SSEEventType.NODE_START,
                data=AgentNodeProgress(
                    node_name=agent.name,
                    description=agent.description,
                    progress=progress,
                ).model_dump(),
            )

            state = await agent(state)

            if state.errors:
                yield SSEEvent(
                    event=SSEEventType.THINKING,
                    data={"message": f"⚠️ {state.errors[-1]}，继续处理…"},
                )

            yield SSEEvent(
                event=SSEEventType.NODE_COMPLETE,
                data=AgentNodeProgress(
                    node_name=agent.name,
                    description=f"{agent.description.split('—')[0]}✅ 完成",
                    progress=(idx + 1) / total,
                ).model_dump(),
            )

            if agent.name == "reviewer":
                for assessment in state.risk_assessments:
                    yield SSEEvent(
                        event=SSEEventType.RISK_FOUND,
                        data=assessment.model_dump(),
                    )

        if session is not None:
            await self._persist(state, session)

        yield SSEEvent(
            event=SSEEventType.SUMMARY,
            data={
                "overall_score": state.overall_score,
                "overall_level": state.overall_level.value,
                "summary": state.summary,
                "total_clauses": len(state.extracted_clauses),
                "total_risks": len(state.risk_assessments),
                "legal_references_count": len(state.legal_references),
            },
        )

        yield SSEEvent(
            event=SSEEventType.COMPLETE,
            data={"message": "✨ 合同风险排查完成！"},
        )

        logger.info(
            f"🏁 Supervisor 完成 | 合同ID: {contract_id} | 评分: {state.overall_score}/100"
        )

    @staticmethod
    async def _persist(state: AgentState, session: AsyncSession) -> None:
        try:
            analysis = AnalysisResult(
                contract_id=state.contract_id,
                overall_score=state.overall_score,
                overall_level=state.overall_level,
                summary=state.summary,
            )
            session.add(analysis)
            await session.flush()

            for idx, assessment in enumerate(state.risk_assessments):
                session.add(
                    RiskItem(
                        analysis_id=analysis.id,
                        category=assessment.category,
                        level=assessment.level,
                        title=assessment.title,
                        original_clause=assessment.original_clause,
                        explanation=assessment.explanation,
                        legal_basis=assessment.legal_basis,
                        negotiation_tip=assessment.negotiation_tip,
                        score=assessment.score,
                        order=idx,
                    )
                )

            await session.commit()
            logger.info(
                f"💾 结果已持久化 | 合同ID: {state.contract_id} | "
                f"风险: {len(state.risk_assessments)} 条"
            )
        except Exception as e:
            logger.error(f"💾 持久化失败: {e}")
            await session.rollback()
