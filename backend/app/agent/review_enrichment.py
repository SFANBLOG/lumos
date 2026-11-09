"""审查增强层统一入口.

在 Negotiator 节点（图内最后一个节点）执行，一次补齐三项行业基线能力:
合同要素表 / 缺失条款检测 / 条款级 redline。刻意放在最后一节点是为了:
- 不新增图节点、不改 LangGraph 拓扑与线性回退路径;
- 不碰 Reviewer 的 LLM 输出契约，避免破坏已有 prompt 与测试;
- 即使 AI 降级，这三项确定性能力仍然产出，不会被模型可用性拖累。
"""

from __future__ import annotations

from loguru import logger

from app.agent.contract_facts import (
    coverage_score,
    detect_missing_clauses,
    extract_contract_facts,
)
from app.agent.redline import attach_redlines
from app.agent.state import AgentState


def enrich(state: AgentState) -> AgentState:
    """就地补全要素表、缺失条款与 redline，返回同一个 state."""
    facts = extract_contract_facts(state.raw_text)
    missing = detect_missing_clauses(facts)

    state.contract_fact_items = facts
    state.missing_clauses = missing
    state.coverage_score = coverage_score(facts)
    filled = attach_redlines(state.risk_assessments)

    logger.info(
        "  审查增强完成 | 要素 %d 项 (已写明 %d) | 缺失必备条款 %d 项 | "
        "覆盖率 %d%% | 补全 redline %d 条",
        len(facts),
        sum(1 for f in facts if f.status == "present"),
        len(missing),
        state.coverage_score,
        filled,
    )
    return state
