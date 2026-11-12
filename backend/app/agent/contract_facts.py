"""合同要素抽取与缺失条款检测 (确定性规则层).

对标市面智能体合同审查系统的 coverage gap / 合同要素表能力:
- ``extract_contract_facts`` 产出带原文定位与置信度的结构化要素表;
- ``detect_missing_clauses`` 检查《劳动合同法》第十七条必备条款与劳动者侧
  应有保护条款，输出「该写却没写」的缺口及可直接使用的补充措辞;
- ``coverage_score`` 给出必备条款覆盖率。

设计上刻意不调用 LLM: 漏填检测应该是可复现、可回归测试的确定性规则，
也不能因为 AI 不可用而漏报。不依赖 Milvus / MySQL / 大模型，便于单测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.review import (
    FACT_CONTRADICTED,
    FACT_MISSING,
    FACT_PRESENT,
    ContractFact,
    MissingClause,
)

_ARTICLE_17 = "《中华人民共和国劳动合同法》第十七条"


@dataclass(frozen=True)
class FactRule:
    """一条要素的抽取规则."""

    key: str
    label: str
    patterns: tuple[str, ...]
    required: bool = False
    legal_basis: str = ""
    suggested_text: str = ""
    reason: str = ""


#: 必备条款以《劳动合同法》第十七条为主，另补劳动者侧高频维权缺口。
#: patterns 中带捕获组时优先取 group(1) 作为要素值，否则取整段命中文本。
FACT_RULES: tuple[FactRule, ...] = (
    FactRule(
        key="party_a",
        label="用人单位名称与住所",
        patterns=(
            r"甲方[（(][^)）]{0,8}[)）]?\s*[：:]\s*([^\n，,；;]{2,40})",
            r"用人单位(?:名称)?\s*[：:]\s*([^\n，,；;]{2,40})",
            r"甲方\s*[：:]\s*([^\n，,；;]{2,40})",
        ),
        required=True,
        legal_basis=_ARTICLE_17,
        suggested_text="应完整写明用人单位全称、住所与法定代表人（或主要负责人），并与盖章主体一致。",
        reason="主体不明会影响劳动关系认定与后续维权对象确认。",
    ),
    FactRule(
        key="party_b",
        label="劳动者姓名与身份信息",
        patterns=(
            r"乙方(?:姓名)?\s*[：:]\s*([^\n，,；;]{2,30})",
            r"劳动者(?:姓名)?\s*[：:]\s*([^\n，,；;]{2,30})",
            r"身份证(?:号|号码)?\s*[：:]?\s*[\dXx]{15,18}",
        ),
        required=True,
        legal_basis=_ARTICLE_17,
        suggested_text="应写明劳动者姓名、住址及居民身份证或其他有效身份证件号码。",
        reason="缺少劳动者身份信息属于法定必备条款缺项。",
    ),
    FactRule(
        key="contract_term",
        label="劳动合同期限",
        patterns=(
            r"合同期限\s*[：:]?\s*([^\n。；;]{2,60})",
            r"(?:无固定期限|固定期限|以完成一定工作任务为期限)劳动合同",
            r"自\s*20\d{2}\s*年[^\n]{0,30}至\s*20\d{2}\s*年",
        ),
        required=True,
        legal_basis=_ARTICLE_17,
        suggested_text="应明确合同类型为固定期限 / 无固定期限 / 以完成一定工作任务为期限，并写明起止日期。",
        reason="期限不明会直接影响试用期上限、经济补偿与续约争议的判断。",
    ),
    FactRule(
        key="job_position",
        label="工作内容与岗位",
        patterns=(
            r"(?:担任|岗位(?:为|是)?|职位(?:为|是)?|工作内容(?:为|是)?)\s*[：:]?\s*([^\n。；;，,]{2,40})",
            r"工作内容\s*[：:]\s*([^\n。；;]{2,60})",
        ),
        required=True,
        legal_basis=_ARTICLE_17,
        suggested_text="应写明具体岗位、职责范围与考核标准，避免仅写「服从公司安排」。",
        reason="岗位模糊是用人单位单方调岗、降薪的常见依据。",
    ),
    FactRule(
        key="work_location",
        label="工作地点",
        patterns=(
            r"工作地点\s*[：:]?\s*([^\n。；;，,]{2,40})",
            r"工作地\s*[：:]\s*([^\n。；;，,]{2,40})",
        ),
        required=True,
        legal_basis=_ARTICLE_17,
        suggested_text="应写明具体城市与办公地址；跨市调动须经双方协商一致并书面变更。",
        reason="未约定工作地点，异地调岗时劳动者难以主张拒绝。",
    ),
    FactRule(
        key="work_hours",
        label="工作时间与休息休假",
        patterns=(
            r"(?:工作时间|工时制度|每日工作|每周工作)\s*[：:]?\s*([^\n。；;，,]{2,40})",
            r"标准工时|综合计算工时|不定时工作制",
            r"休息休假|带薪年休假",
        ),
        required=True,
        legal_basis=_ARTICLE_17 + "；《中华人民共和国劳动法》第三十六条",
        suggested_text="应写明执行标准工时（每日不超过 8 小时、每周不超过 44 小时）、加班费计算方式与带薪年休假安排。",
        reason="工时与休假未约定，加班费和超时用工争议中举证困难。",
    ),
    FactRule(
        key="salary",
        label="劳动报酬数额与构成",
        patterns=(
            r"(?:劳动报酬|工资标准|月薪|月工资|基本工资)\s*[：:]?\s*([^\n。；;，,]{2,60})",
            r"\d+(?:\.\d+)?\s*元\s*/\s*月",
            r"税前(?:月薪|工资)[^\n。；;，,]{0,30}",
        ),
        required=True,
        legal_basis=_ARTICLE_17 + "；《中华人民共和国劳动合同法》第十一条",
        suggested_text="应明确税前月薪数额、构成（基本工资 / 绩效 / 补贴）及调整机制，且不低于当地最低工资标准。",
        reason="只写「按公司制度执行」或只写比例，无法核算加班费与经济补偿基数。",
    ),
    FactRule(
        key="salary_payment_date",
        label="工资支付日期",
        patterns=(
            r"(?:每月|次月)\s*\d{1,2}\s*日[^\n]{0,20}(?:支付|发放|发薪)",
            r"工资[^\n]{0,16}支付日[^\n]{0,16}",
            r"发薪日\s*[：:]?\s*([^\n。；;，,]{2,20})",
        ),
        required=True,
        legal_basis="《工资支付暂行规定》第七条",
        suggested_text="应写明每月固定发薪日、支付方式与银行代发账户；遇节假日应提前发放。",
        reason="未约定支付日，拖欠工资时难以界定逾期起点。",
    ),
    FactRule(
        key="social_insurance",
        label="社会保险",
        patterns=(
            r"社会保险|五险一金|社保缴纳",
            r"养老保险|医疗保险|失业保险|工伤保险|生育保险|住房公积金",
        ),
        required=True,
        legal_basis="《中华人民共和国社会保险法》第五十八条；《中华人民共和国劳动合同法》第十七条",
        suggested_text="应写明自用工之日起依法办理社保登记并足额缴纳五险，不得以试用期、自愿放弃或现金补贴替代。",
        reason="约定「自愿放弃社保」或试用期不缴社保属无效条款，且影响工伤与生育待遇。",
    ),
    FactRule(
        key="labor_protection",
        label="劳动保护、劳动条件与职业危害防护",
        patterns=(
            r"劳动保护|劳动条件|职业危害|职业病",
            r"劳动防护用品|安全培训",
        ),
        required=True,
        legal_basis=_ARTICLE_17,
        suggested_text="应写明劳动安全卫生条件、防护用品与职业危害告知；存在职业危害岗位须如实告知并提供防护。",
        reason="属于第十七条列明的必备条款，缺失时工伤责任与告知义务难以界定。",
    ),
    FactRule(
        key="termination",
        label="合同解除与终止条件",
        patterns=(
            r"(?:解除|终止)(?:本)?合同(?:的)?条件",
            r"合同(?:的)?(?:解除|终止)",
            r"提前\s*\d+\s*日(?:以)?书面通知",
        ),
        required=True,
        legal_basis="《中华人民共和国劳动合同法》第三十六条至第四十四条",
        suggested_text="应写明双方解除/终止的法定情形、提前通知期、经济补偿计算方式与离职交接流程。",
        reason="缺失时常见「离职需审批」「未经批准不得离职」等限制劳动者解除权的表述。",
    ),
    FactRule(
        key="probation",
        label="试用期约定",
        patterns=(r"试用期\s*[：:]?\s*([^\n。；;，,]{2,40})", r"试用期"),
        required=False,
        legal_basis="《中华人民共和国劳动合同法》第十九条",
        suggested_text="试用期长度须与合同期限匹配且不得超过六个月，试用期工资不得低于本单位同岗最低档工资或约定工资的 80%。",
        reason="",
    ),
    FactRule(
        key="non_compete",
        label="竞业限制范围、期限与补偿",
        patterns=(r"竞业(?:限制|禁止)", r"竞业补偿"),
        required=False,
        legal_basis="《中华人民共和国劳动合同法》第二十三条、第二十四条",
        suggested_text="竞业限制期限不得超过二年，人员限于高级管理/技术/负有保密义务人员，离职后须按月支付经济补偿。",
        reason="",
    ),
    FactRule(
        key="dispute_jurisdiction",
        label="争议解决与管辖",
        patterns=(r"劳动争议|管辖(?:法院|地)|仲裁委员会|提起诉讼", r"争议解决"),
        required=False,
        legal_basis="《中华人民共和国劳动争议调解仲裁法》第二十一条",
        suggested_text="建议约定劳动合同履行地或用人单位所在地有管辖权的劳动争议仲裁委员会 / 人民法院。",
        reason="",
    ),
)


def _first_match(text: str, patterns: tuple[str, ...]) -> re.Match[str] | None:
    for pattern in patterns:
        try:
            match = re.search(pattern, text)
        except re.error:  # 规则库写错时不应拖垮审查主链
            continue
        if match is not None:
            return match
    return None


def extract_contract_facts(
    raw_text: str,
    contract_type: str = "labor_contract",
    *,
    rules: tuple[FactRule, ...] | None = None,
) -> list[ContractFact]:
    """从合同原文抽取结构化要素表.

    ``contract_type`` 决定使用哪套必备条款规则集 (劳动合同 / 服务合同 / NDA)。
    命中即 ``present`` 并保留原文片段作为 evidence; 检出但与法定要求冲突的
    反向约定标为 ``contradicted``; 未命中且为必备条款则标为 ``missing``。
    置信度按捕获方式、证据长度与全文重现度动态计算, 不再是固定 0.9 / 0.75。
    """
    # 局部 import 打破 contract_facts ↔ fact_semantics 的模块级循环依赖
    from app.agent.fact_semantics import (
        detect_contradiction,
        dynamic_confidence,
        refine_facts,
        rules_for,
    )

    text = raw_text or ""
    selected = rules if rules is not None else rules_for(contract_type)
    facts: list[ContractFact] = []
    for rule in selected:
        match = _first_match(text, rule.patterns)
        if match is None:
            facts.append(
                ContractFact(
                    key=rule.key,
                    label=rule.label,
                    status=FACT_MISSING,
                    required=rule.required,
                    legal_basis=rule.legal_basis,
                    matched_by="none",
                    rule_set=contract_type,
                )
            )
            continue
        evidence = match.group(0).strip()
        value = match.group(1).strip() if match.lastindex else evidence
        facts.append(
            ContractFact(
                key=rule.key,
                label=rule.label,
                value=value[:120],
                evidence=evidence[:200],
                confidence=dynamic_confidence(match, evidence, text),
                status=FACT_PRESENT,
                required=rule.required,
                legal_basis=rule.legal_basis,
                matched_by="capture" if match.lastindex else "keyword",
                contradiction=detect_contradiction(text, rule.key),
                rule_set=contract_type,
            )
        )
    return refine_facts(text, facts, contract_type)


def detect_missing_clauses(
    facts: list[ContractFact],
    *,
    rules: tuple[FactRule, ...] | None = None,
    contract_type: str = "",
) -> list[MissingClause]:
    """必备条款缺失或与法定要求冲突时生成缺口清单 (确定性, 不依赖 LLM)."""
    from app.agent.fact_semantics import rules_for

    selected = rules if rules is not None else rules_for(
        contract_type or (facts[0].rule_set if facts else "labor_contract")
    )
    by_key = {rule.key: rule for rule in selected}
    high = {"party_a", "party_b", "salary", "social_insurance"}
    missing: list[MissingClause] = []
    for fact in facts:
        contradicted = fact.status == FACT_CONTRADICTED
        if not fact.required or (fact.status != FACT_MISSING and not contradicted):
            continue
        rule = by_key.get(fact.key)
        reason = rule.reason if rule else "法定必备条款未见约定。"
        if contradicted:
            reason = (
                f"检出反向约定「{fact.contradiction}」，该表述无效且须整条改写。{reason}"
            )
        level = "high" if contradicted or fact.key in high else "medium"
        score = 10 if contradicted else (20 if fact.key in high else 30)
        missing.append(
            MissingClause(
                key=fact.key,
                label=fact.label,
                reason=reason,
                legal_basis=fact.legal_basis,
                suggested_text=rule.suggested_text if rule else "建议补充该项约定。",
                level=level,
                score=score,
            )
        )
    return missing


def coverage_score(facts: list[ContractFact]) -> int:
    """必备条款覆盖率 (0-100); contradicted 不计入「已写明」."""
    required = [fact for fact in facts if fact.required]
    if not required:
        return 100
    present = sum(1 for fact in required if fact.status == FACT_PRESENT)
    return round(100 * present / len(required))
