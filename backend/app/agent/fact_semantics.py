"""合同要素的语义级增强.

把 v1 的「命中关键词就算已写明」升级为可解释的字段级判断:
- **矛盾表述识别**: 出现「自愿放弃社保」「离职需批准」这类反向约定时，
  不再误判为合规要素，而是标记 contradicted 并生成高危缺口;
- **字段级置信度**: 按捕获方式、证据长度、重现次数动态计算，不是固定 0.9/0.75;
- **按合同类型切换必备条款集**: 劳动合同 / 服务合同 / 保密与竞业协议各有规则集。
"""

from __future__ import annotations

import re

from app.agent.contract_facts import FACT_RULES, FactRule
from app.schemas.review import FACT_CONTRADICTED, FACT_PRESENT

#: 出现即说明「虽有表述但与法定要求冲突」的反向约定
CONTRADICTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "social_insurance": (
        r"自愿放弃(?:社保|社会保险|五险一金)",
        r"(?:不|不予|无需)(?:缴纳|办理)(?:社保|社会保险|五险一金)",
        r"(?:社保|社会保险).{0,10}(?:自行承担|以补贴代替|折现)",
    ),
    "salary": (
        r"工资.{0,12}(?:由|视)公司(?:决定|确定|另行通知)",
        r"(?:薪资|工资).{0,10}无(?:最低|下限)",
    ),
    "work_hours": (
        r"自愿放弃加班费", r"不计加班", r"无偿加班", r"加班.{0,8}不(?:另行)?支付",
    ),
    "termination": (
        r"离职需(?:经|公司|甲方)批准", r"未经批准不得离职", r"不得(?:主动)?(?:提出)?离职",
    ),
    "leave_rights": (r"不享受(?:带薪)?年休假", r"自愿放弃(?:休假|年假)"),
    "probation": (r"试用期.{0,10}(?:不缴|无工资|不发工资)",),
    "salary_payment_date": (r"发薪日.{0,10}(?:另行通知|由公司确定)",),
    "labor_protection": (r"劳动防护用品.{0,8}自理", r"职业危害.{0,8}自行承担"),
}

#: 服务合同必备要素（示例规则集，可按客户口径继续扩展）
SERVICE_RULE_SET: tuple[FactRule, ...] = (
    FactRule(
        "party_a", "委托方名称",
        (r"甲方[（(][^)）]{0,8}[)）]?\s*[：:]\s*([^\n，,；;]{2,40})", r"委托方\s*[：:]\s*([^\n，,；;]{2,40})"),
        True, "《中华人民共和国民法典》第四百七十条", "应写明委托方全称、住所与联系人。", "主体不明无法界定委托责任。",
    ),
    FactRule(
        "party_b", "受托方名称",
        (r"乙方\s*[：:]\s*([^\n，,；;]{2,40})", r"受托方\s*[：:]\s*([^\n，,；;]{2,40})"),
        True, "《中华人民共和国民法典》第四百七十条", "应写明受托方全称与资质信息。", "主体不明无法界定履约责任。",
    ),
    FactRule(
        "service_scope", "服务范围与交付物",
        (r"(?:服务(?:内容|范围)|交付物)\s*[：:]?\s*([^\n。；;]{2,80})",),
        True, "《中华人民共和国民法典》第四百七十条", "应列明服务范围、交付物清单与验收标准。", "范围不清是服务合同最常见的争议源。",
    ),
    FactRule(
        "contract_term", "服务期限",
        (r"(?:服务|合同)期限\s*[：:]?\s*([^\n。；;]{2,60})", r"自\s*20\d{2}\s*年"),
        True, "《中华人民共和国民法典》第四百七十条", "应写明起止日期与延期条件。", "期限不明无法判断逾期责任。",
    ),
    FactRule(
        "price", "价款与支付方式",
        (r"(?:价款|服务费|合同金额)\s*[：:]?\s*([^\n。；;]{2,60})", r"\d+(?:\.\d+)?\s*元"),
        True, "《中华人民共和国民法典》第四百七十条", "应写明总额、支付节点、发票与税费承担。", "价款不明无法结算。",
    ),
    FactRule(
        "liability", "违约责任",
        (r"违约责任|违约金|赔偿责任",),
        True, "《中华人民共和国民法典》第五百七十七条", "应约定违约情形、违约金计算与损失赔偿范围。", "无违约条款时救济困难。",
    ),
)

#: 保密与竞业协议必备要素
NDA_RULE_SET: tuple[FactRule, ...] = (
    FactRule(
        "party_a", "用人单位名称",
        (r"甲方\s*[：:]\s*([^\n，,；;]{2,40})", r"用人单位\s*[：:]\s*([^\n，,；;]{2,40})"),
        True, "《中华人民共和国劳动合同法》第二十三条", "应写明用人单位全称。", "主体不明无法界定保密义务相对方。",
    ),
    FactRule(
        "confidential_scope", "保密信息范围",
        (r"保密(?:信息|事项)(?:范围)?\s*[：:]?\s*([^\n。；;]{2,80})",),
        True, "《中华人民共和国劳动合同法》第二十三条", "应明确哪些信息属于保密范围，避免笼统覆盖全部工作信息。", "范围过宽易被认定无效。",
    ),
    FactRule(
        "non_compete", "竞业限制范围、期限与补偿",
        (r"竞业(?:限制|禁止)",),
        True, "《中华人民共和国劳动合同法》第二十四条", "期限不超过二年，范围限于同类竞争业务，离职后按月支付经济补偿。", "缺补偿约定时竞业条款对劳动者无约束力。",
    ),
    FactRule(
        "compensation", "竞业补偿标准",
        (r"(?:竞业)?补偿(?:金)?\s*[：:]?\s*([^\n。；;，,]{2,60})", r"每月.{0,8}补偿"),
        True, "《中华人民共和国劳动合同法》第二十三条", "应写明按月支付的补偿金额与计算方式，且不低于地方下限。", "补偿过低或只写一次性支付存在被调高的风险。",
    ),
    FactRule(
        "termination", "协议解除与终止",
        (r"(?:解除|终止)(?:本)?协议",),
        True, "《中华人民共和国劳动合同法》第二十四条", "应写明解除条件与竞业义务的解除方式。", "缺少退出机制时义务无期限。",
    ),
)

RULE_SETS: dict[str, tuple[FactRule, ...]] = {
    "labor_contract": FACT_RULES,
    "service_contract": SERVICE_RULE_SET,
    "nda": NDA_RULE_SET,
}


def rules_for(contract_type: str) -> tuple[FactRule, ...]:
    """按合同类型取规则集，未知类型回退劳动合同."""
    return RULE_SETS.get(contract_type, FACT_RULES)


def detect_contradiction(raw_text: str, key: str) -> str:
    """返回命中的反向约定原文片段."""
    patterns = CONTRADICTION_PATTERNS.get(key, ())
    if isinstance(patterns, str):  # 防止规则表漏写尾逗号被当成逐字符正则
        patterns = (patterns,)
    for pattern in patterns:
        match = re.search(pattern, raw_text)
        if match:
            return match.group(0)
    return ""


def dynamic_confidence(match: re.Match, evidence: str, raw_text: str) -> float:
    """字段级置信度：捕获方式 + 证据质量 + 全文重现度."""
    base = 0.9 if match.lastindex else 0.7
    if len(evidence) < 8:
        base *= 0.85
    if len(evidence) > 80:
        base *= 0.95
    if evidence and raw_text.count(evidence) > 1:
        base = min(0.98, base + 0.04)
    return round(max(0.3, min(0.98, base)), 2)


def refine_facts(raw_text: str, facts: list, contract_type: str) -> list:
    """补上规则集标识、命中方式，并把矛盾表述从 present 降级为 contradicted."""
    for fact in facts:
        fact.rule_set = contract_type
        if fact.status != FACT_PRESENT:
            fact.matched_by = fact.matched_by or "none"
            continue
        contradiction = fact.contradiction or detect_contradiction(raw_text, fact.key)
        if contradiction:
            fact.contradiction = contradiction
            fact.status = FACT_CONTRADICTED
            fact.matched_by = "negation"
            fact.confidence = max(fact.confidence, 0.92)
        else:
            fact.matched_by = fact.matched_by or "keyword"
    return facts


_LABOR_MARKERS = ("劳动合同", "劳动者", "用人单位", "试用期", "社会保险")
_NDA_MARKERS = ("保密协议", "竞业限制协议", "保密与竞业")
_SERVICE_MARKERS = ("委托方", "受托方", "服务费", "服务合同", "交付物")


def infer_contract_type(raw_text: str) -> str:
    """按标题/主体特征保守推断合同类型.

    只在前 200 字出现明确标识时才切换规则集: 劳动合同中常见的「竞业限制」
    条款不足以把整份合同判成 NDA, 避免误换规则集造成大面积误报。
    """
    head = (raw_text or "")[:200]
    if any(marker in head for marker in _LABOR_MARKERS):
        return "labor_contract"
    if any(marker in head for marker in _NDA_MARKERS):
        return "nda"
    if any(marker in head for marker in _SERVICE_MARKERS):
        return "service_contract"
    return "labor_contract"
