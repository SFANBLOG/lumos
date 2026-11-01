"""
用户提问意图识别.

用于智能咨询链路的路由与回答定制:
- 规则/关键词快速识别 (确定性、零成本、可解释);
- 规则不确定时, 可选调用大模型兜底 (仅低置信度才调, 省 token)。

设计原则: 规则优先、模型兜底、失败降级为 UNKNOWN, 任何异常都不影响主流程。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from app.core.config import get_settings


class Intent(str, Enum):
    """用户提问意图枚举."""

    LAW_QUERY = "law_query"  # 法条查询/依据
    RISK_ANALYSIS = "risk_analysis"  # 风险/合同分析
    NEGOTIATION = "negotiation"  # 谈判/沟通建议
    CLAUSE_EXPLAIN = "clause_explain"  # 条款/名词解释
    PROCEDURE = "procedure"  # 维权流程/怎么办
    CHITCHAT = "chitchat"  # 寒暄/无关
    UNKNOWN = "unknown"  # 无法判定


_LABELS: dict[Intent, str] = {
    Intent.LAW_QUERY: "法条查询",
    Intent.RISK_ANALYSIS: "风险分析",
    Intent.NEGOTIATION: "谈判建议",
    Intent.CLAUSE_EXPLAIN: "条款解释",
    Intent.PROCEDURE: "维权流程",
    Intent.CHITCHAT: "闲聊",
    Intent.UNKNOWN: "其他",
}


@dataclass
class IntentResult:
    """意图识别结果."""

    intent: Intent
    confidence: float
    method: str  # rule | llm | fallback
    matched: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return _LABELS.get(self.intent, "其他")


# 关键词规则表: 命中关键词越多, 置信度越高.
# 顺序有意义: 并列时靠前的实质意图优先于末尾的 CHITCHAT.
# 已按劳动法实际业务扩展: 工伤/加班费/经济补偿/社保/试用期/裁员/仲裁/诉讼等.
# 注意: 避免放入互为子串的词 (如"工伤"与"工伤认定"), 否则会重复计分虚高置信度.
_RULES: dict[Intent, tuple[str, ...]] = {
    Intent.LAW_QUERY: (
        "法条", "第几条", "哪条", "规定", "依据", "法律", "劳动合同法", "劳动法",
        "条款", "条文", "违法", "合法",
        # 业务术语: 权益 / 法律依据类
        "工伤", "职业病", "加班费", "加班工资", "经济补偿", "赔偿金", "双倍工资",
        "社保", "五险一金", "试用期", "竞业限制", "竞业补偿", "年休假", "年假",
        "产假", "病假", "医疗期", "裁员", "最低工资", "违约金", "押金", "工时",
        "法定节假日", "离职证明", "失业保险", "生育津贴",
    ),
    Intent.RISK_ANALYSIS: (
        "风险", "有什么坑", "坑", "危险", "隐患", "审查", "评估", "问题", "合规",
        # 业务术语: 风险 / 审查类
        "漏洞", "陷阱", "霸王条款", "不利", "争议", "纠纷", "无效条款", "单方解除",
    ),
    Intent.NEGOTIATION: (
        "谈判", "怎么谈", "怎么沟通", "怎么拒绝", "怎么回", "话术", "协商", "争取",
        # 业务术语: 谈判 / 沟通类
        "讨价还价", "谈补偿", "谈判筹码", "辞退谈判",
    ),
    Intent.CLAUSE_EXPLAIN: (
        "什么意思", "怎么理解", "解释", "含义", "指的是", "是什么", "啥意思",
        # 业务术语: 解释 / 释义类
        "释义", "怎么解读", "定义",
    ),
    Intent.PROCEDURE: (
        "怎么办", "流程", "步骤", "怎么维权", "投诉", "仲裁", "起诉", "举报", "找谁",
        # 业务术语: 维权流程 / 机构类
        "劳动监察", "劳动局", "人社局", "法院", "诉讼", "申诉", "复议", "举证",
        "证据", "时效", "申报",
    ),
    Intent.CHITCHAT: (
        "你好", "您好", "谢谢", "在吗", "再见", "拜拜", "hello", "hi", "早上好", "晚上好",
    ),
}

_MIN_CONF = 0.5  # 规则置信度达到该值即直接采纳, 不再调模型
_CHITCHAT_SKIP = 0.6  # 闲聊置信度达到该值则跳过法条检索

_INTENT_SYSTEM = (
    "你是意图分类器。把用户问题归到下列意图之一, 只输出 JSON, 不要任何多余文字:\n"
    '{"intent": "<law_query|risk_analysis|negotiation|clause_explain|procedure|chitchat|unknown>", '
    '"confidence": <0 到 1 之间的数>}'
)


def _hit(keyword: str, text: str) -> bool:
    """关键词命中判断: 英文按词边界, 中文按子串 (避免 hi 命中 which 这类误判)."""
    if keyword.isascii():
        return re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE) is not None
    return keyword in text


def _classify_by_rules(text: str) -> IntentResult:
    """纯规则分类: 按命中关键词数打分, 取最高分意图."""
    if not text:
        return IntentResult(Intent.UNKNOWN, 0.0, "rule", [])

    scores: dict[Intent, list[str]] = {}
    for intent, keywords in _RULES.items():
        hits = [kw for kw in keywords if _hit(kw, text)]
        if hits:
            scores[intent] = hits

    if not scores:
        return IntentResult(Intent.UNKNOWN, 0.0, "rule", [])

    # 命中数最多者胜; 数量相同按 _RULES 顺序 (实质意图优先于 CHITCHAT).
    best_intent = max(scores, key=lambda i: len(scores[i]))
    best_hits = scores[best_intent]
    confidence = min(1.0, 0.45 + 0.2 * len(best_hits))  # 1 个→0.65, 2 个→0.85, 3+→1.0
    return IntentResult(best_intent, round(confidence, 2), "rule", best_hits)


async def _classify_by_llm(text: str) -> IntentResult | None:
    """大模型兜底分类; 未配置密钥或任何异常均返回 None, 交回规则结果."""
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model_name,
            temperature=0,
            max_tokens=64,
            streaming=False,
            request_timeout=20,
            max_retries=0,
        )
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user", "content": text[:500]},
            ]
        )
        raw = (resp.content or "").strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(raw[start : end + 1])
        intent = Intent(str(data.get("intent", "unknown")))
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.6))))
        return IntentResult(intent, round(confidence, 2), "llm", [])
    except Exception as exc:  # noqa: BLE001 - 兜底必须吞掉异常
        logger.debug(f"[intent] LLM 分类失败, 降级规则: {exc}")
        return None


async def recognize_intent(question: str, *, use_llm: bool = True) -> IntentResult:
    """识别用户提问意图.

    规则优先: 置信度达标直接用; 否则 (可选) 调大模型兜底, 模型不可用时回退规则结果.
    """
    text = (question or "").strip()
    if not text:
        return IntentResult(Intent.UNKNOWN, 0.0, "rule", [])

    rule_result = _classify_by_rules(text)
    if rule_result.intent is not Intent.UNKNOWN and rule_result.confidence >= _MIN_CONF:
        return rule_result

    if use_llm:
        llm_result = await _classify_by_llm(text)
        if llm_result is not None:
            return llm_result

    return rule_result
