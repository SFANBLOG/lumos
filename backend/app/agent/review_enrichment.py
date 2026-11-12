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
from app.agent.fact_semantics import RULE_SETS, infer_contract_type, rules_for
from app.agent.redline_engine import attach_rewrites
from app.agent.state import AgentState
from app.schemas.review import FACT_CONTRADICTED


def resolve_contract_type(state: AgentState) -> str:
    """确定生效的规则集: 显式指定优先, auto/空/非法值按原文保守推断."""
    requested = (getattr(state, "contract_type", "") or "").strip().lower()
    if requested in ("", "auto"):
        requested = infer_contract_type(state.raw_text)
    if requested not in RULE_SETS:
        requested = "labor_contract"
    state.contract_type = requested
    return requested


def enrich(state: AgentState) -> AgentState:
    """就地补全要素表、缺失条款与逐条改写，返回同一个 state."""
    contract_type = resolve_contract_type(state)
    rules = rules_for(contract_type)
    facts = extract_contract_facts(
        state.raw_text, contract_type=contract_type, rules=rules
    )
    missing = detect_missing_clauses(facts, rules=rules)

    state.contract_fact_items = facts
    state.missing_clauses = missing
    state.coverage_score = coverage_score(facts)
    llm_count, rule_count = attach_rewrites(state.risk_assessments)
    contradictions = sum(1 for f in facts if f.status == FACT_CONTRADICTED)

    logger.info(
        "  审查增强完成 | 类型 %s | 要素 %d 项 (已写明 %d / 反向约定 %d) | "
        "缺口 %d 项 | 覆盖率 %d%% | 改写 LLM %d 条 / 规则兜底 %d 条",
        contract_type,
        len(facts),
        sum(1 for f in facts if f.status == "present"),
        contradictions,
        len(missing),
        state.coverage_score,
        llm_count,
        rule_count,
    )
    return state
