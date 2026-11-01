"""提交内容的文档类型判定 (L1 规则 + L2 大模型兜底).

解决的问题: 扩展名白名单、`content-type` 只能说明"文件能不能打开", 不能说明
"内容是不是合同"。用户把简历、发票、新闻正文、小说贴进来, 旧链路会照样切成
"条款"并产出一份看起来正常的风险报告 —— 这是最危险的幻觉来源。

判定分两层, 与 ``agent/intent.py`` 同一套哲学: 规则优先、模型兜底、失败降级。

- L1 规则: 长度 / 中文字符占比 / 乱码率 / 合同要素 / 噪声特征, 确定性、零成本;
- L2 大模型: 仅当规则置信度不足时调用, 未配置密钥或任何异常都回退规则结果。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from app.core.config import get_settings


class DocType(str, Enum):
    """文档类型枚举 (比"是不是合同"更细, 便于给出精准提示)."""

    LABOR_CONTRACT = "labor_contract"  # 劳动合同
    SERVICE_AGREEMENT = "service_agreement"  # 服务/委托协议
    OTHER_CONTRACT = "other_contract"  # 其他合同、条款页面
    PRIVACY_POLICY = "privacy_policy"  # 隐私政策/用户协议
    NEWS_ARTICLE = "news_article"  # 新闻/资讯正文
    NOVEL = "novel"  # 小说/散文
    RESUME = "resume"  # 简历
    INVOICE = "invoice"  # 发票/票据
    SPREADSHEET = "spreadsheet"  # 表格
    PRESENTATION = "presentation"  # 演示文稿
    NON_CHINESE = "non_chinese"  # 非中文内容
    GARBAGE = "garbage"  # 乱码/过短/无意义
    UNKNOWN = "unknown"  # 无法判定


DOC_TYPE_LABELS: dict[DocType, str] = {
    DocType.LABOR_CONTRACT: "劳动合同",
    DocType.SERVICE_AGREEMENT: "服务/委托协议",
    DocType.OTHER_CONTRACT: "合同/协议",
    DocType.PRIVACY_POLICY: "隐私政策/用户协议",
    DocType.NEWS_ARTICLE: "新闻/资讯正文",
    DocType.NOVEL: "小说/散文",
    DocType.RESUME: "简历",
    DocType.INVOICE: "发票/票据",
    DocType.SPREADSHEET: "表格",
    DocType.PRESENTATION: "演示文稿",
    DocType.NON_CHINESE: "非中文内容",
    DocType.GARBAGE: "乱码或过短内容",
    DocType.UNKNOWN: "无法判定的内容",
}

#: 可进入合同审查的文档类型
CONTRACT_TYPES: frozenset[DocType] = frozenset(
    {DocType.LABOR_CONTRACT, DocType.SERVICE_AGREEMENT, DocType.OTHER_CONTRACT}
)

_MIN_CHARS = 80  # 少于该长度几乎不可能是一份完整合同
_MIN_CJK_RATIO = 0.15  # 中文字符占比下限
_MAX_BAD_RATIO = 0.15  # 乱码/不可打印字符占比上限
_MIN_CONF = 0.6  # 规则置信度达到该值即采纳, 不再调模型
_RULE_WINDOW = 20_000  # 规则只看前 2 万字, 避免长合同拖慢接口

_CONTRACT_PARTY = ("甲方", "乙方", "用人单位", "劳动者", "员工", "法定代表人", "职工", "雇主")
_CONTRACT_STRUCT = ("第一条", "第二条", "第三条", "鉴于", "本合同", "本协议", "条款", "约定", "附件")
_CONTRACT_SIGN = ("签字", "盖章", "签章", "签署日期", "签订日期", "签订地点", "生效日期")
_CONTRACT_OBLIGE = ("应当", "不得", "有权", "义务", "违约责任", "解除", "终止", "赔偿")

_LABOR_WORDS = (
    "劳动合同", "试用期", "工资", "薪", "岗位", "工作内容", "社保", "社会保险",
    "工作时间", "加班", "劳动报酬", "竞业", "年休假", "用人单位", "劳动者",
)
_SERVICE_WORDS = ("服务协议", "委托", "承揽", "技术服务", "咨询服务", "服务费", "甲方委托乙方")

_RESUME_WORDS = ("教育背景", "工作经历", "项目经验", "自我评价", "求职意向", "毕业院校", "专业技能", "简历")
_NEWS_WORDS = ("记者", "报道", "通讯员", "责任编辑", "原标题", "本报讯", "发布会", "网友", "采访", "消息")
_NOVEL_WORDS = ("他说", "她说", "说道", "心里", "眼睛", "笑了笑", "低声", "抬头", "那一刻")
_INVOICE_WORDS = ("发票代码", "发票号码", "价税合计", "税额", "开票日期", "购买方", "销售方", "增值税")
_PRIVACY_WORDS = ("隐私政策", "个人信息", "我们收集", "授权同意", "信息处理", "cookies")
_NOISE_WORDS = (
    "登录", "注册", "首页", "版权所有", "广告", "扫码", "下载APP", "点击",
    "分享到", "相关阅读", "评论区", "推荐阅读", "关注我们",
)

_LLM_SYSTEM = (
    "你是文档类型判定器。判断用户给出的文本属于哪种文档, 只输出 JSON, 不要任何多余文字:\n"
    '{"doc_type": "<labor_contract|service_agreement|other_contract|privacy_policy|news_article|'
    'novel|resume|invoice|spreadsheet|presentation|non_chinese|garbage|unknown>", '
    '"is_contract": <true|false>, "confidence": <0 到 1 之间的数>, "reason": "<不超过 30 字的中文理由>"}'
)


@dataclass
class DocCheckResult:
    """文档类型判定结果."""

    doc_type: DocType
    is_contract: bool
    confidence: float
    method: str  # rule | llm | ext
    reasons: list[str] = field(default_factory=list)
    notice: str | None = None  # 给用户看的提示; None 表示无需提示

    @property
    def label(self) -> str:
        return DOC_TYPE_LABELS.get(self.doc_type, "无法判定的内容")

    def to_dict(self) -> dict:
        """接口下发结构 (字段名与前端 ``DocCheck`` 对齐)."""
        return {
            "doc_type": self.doc_type.value,
            "doc_type_label": self.label,
            "is_contract": self.is_contract,
            "confidence": self.confidence,
            "method": self.method,
            "reasons": self.reasons,
            "notice": self.notice,
        }


def _hits(text_lower: str, words: tuple[str, ...]) -> list[str]:
    """统计词表命中项 (中文按子串匹配, 足够稳定且零依赖)."""
    return [w for w in words if w.lower() in text_lower]


def _bad_char_ratio(text: str) -> float:
    """乱码率: 替换符 + 控制字符占比."""
    if not text:
        return 0.0
    bad = sum(1 for ch in text if ch == "\ufffd" or (ord(ch) < 32 and ch not in "\n\r\t"))
    return bad / len(text)


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk / len(text)


def _build_notice(doc_type: DocType, is_contract: bool, confidence: float) -> str | None:
    """生成给用户看的一句话提示; 高置信合同不需要提示."""
    label = DOC_TYPE_LABELS.get(doc_type, "无法判定的内容")
    pct = round(confidence * 100)
    if is_contract:
        if confidence >= 0.8:
            return None
        return f"仅识别到部分合同要素（{label}，置信度 {pct}%），内容可能不完整，审查结论仅供参考"
    return f"识别为「{label}」（置信度 {pct}%），可能不是劳动合同；继续分析的结果可能不准确"


def _classify_by_rules(text: str) -> DocCheckResult:
    """纯规则判定 (无网络、无大模型, 可在单测中稳定复现)."""
    t = (text or "").strip()
    sample = t[:_RULE_WINDOW]
    n = len(sample)
    if n == 0:
        return DocCheckResult(
            DocType.GARBAGE, False, 0.95, "rule", ["内容为空"], "没有可分析的文字内容"
        )
    if n < _MIN_CHARS:
        return DocCheckResult(
            DocType.GARBAGE,
            False,
            0.9,
            "rule",
            [f"正文仅 {n} 字, 少于 {_MIN_CHARS} 字下限"],
            f"正文只有 {n} 字，不足以构成一份合同",
        )

    bad_ratio = _bad_char_ratio(sample)
    if bad_ratio > _MAX_BAD_RATIO:
        return DocCheckResult(
            DocType.GARBAGE,
            False,
            0.85,
            "rule",
            [f"乱码/不可打印字符占比 {bad_ratio:.0%}"],
            "内容包含大量乱码，无法识别为合同",
        )

    cjk = _cjk_ratio(sample)
    if cjk < _MIN_CJK_RATIO:
        return DocCheckResult(
            DocType.NON_CHINESE,
            False,
            0.75,
            "rule",
            [f"中文字符占比仅 {cjk:.0%}"],
            "内容几乎不含中文，暂不支持审查非中文文档",
        )

    low = sample.lower()
    party = _hits(low, _CONTRACT_PARTY)
    struct = _hits(low, _CONTRACT_STRUCT)
    sign = _hits(low, _CONTRACT_SIGN)
    oblige = _hits(low, _CONTRACT_OBLIGE)
    clause_no = len(re.findall(r"第[一二三四五六七八九十百]+条", sample)) + len(
        re.findall(r"^\s*\d+(?:\.\d+)+\s", sample, re.MULTILINE)
    )
    url_cnt = len(re.findall(r"https?://", low))

    labor = _hits(low, _LABOR_WORDS)
    service = _hits(low, _SERVICE_WORDS)
    resume = _hits(low, _RESUME_WORDS)
    news = _hits(low, _NEWS_WORDS)
    novel = _hits(low, _NOVEL_WORDS)
    invoice = _hits(low, _INVOICE_WORDS)
    privacy = _hits(low, _PRIVACY_WORDS)
    noise = _hits(low, _NOISE_WORDS)

    # ── 非合同类型的强特征 (无甲乙方时才采纳, 避免误杀含"发票"条款的合同) ──
    if len(resume) >= 3 and len(party) == 0:
        return DocCheckResult(
            DocType.RESUME,
            False,
            0.85,
            "rule",
            [f"命中简历特征: {', '.join(resume[:4])}"],
            _build_notice(DocType.RESUME, False, 0.85),
        )
    if len(invoice) >= 3 and len(party) == 0:
        return DocCheckResult(
            DocType.INVOICE,
            False,
            0.85,
            "rule",
            [f"命中票据特征: {', '.join(invoice[:4])}"],
            _build_notice(DocType.INVOICE, False, 0.85),
        )
    if len(privacy) >= 2 and len(party) == 0:
        return DocCheckResult(
            DocType.PRIVACY_POLICY,
            False,
            0.8,
            "rule",
            [f"命中隐私政策特征: {', '.join(privacy[:3])}"],
            _build_notice(DocType.PRIVACY_POLICY, False, 0.8),
        )
    if len(news) >= 3 or (len(news) >= 2 and url_cnt >= 3):
        return DocCheckResult(
            DocType.NEWS_ARTICLE,
            False,
            0.8,
            "rule",
            [f"命中新闻特征: {', '.join(news[:4])}"],
            _build_notice(DocType.NEWS_ARTICLE, False, 0.8),
        )
    if len(novel) >= 4 and len(party) == 0:
        return DocCheckResult(
            DocType.NOVEL,
            False,
            0.75,
            "rule",
            [f"命中叙事文本特征: {', '.join(novel[:4])}"],
            _build_notice(DocType.NOVEL, False, 0.75),
        )

    # ── 合同要素打分 ──
    score = 0
    score += min(len(party), 3) * 2  # 最多 6
    score += min(len(struct), 3)  # 最多 3
    score += min(len(sign), 2) * 2  # 最多 4
    score += min(len(oblige), 3)  # 最多 3
    score += min(clause_no, 5)  # 最多 5

    reasons = [f"合同要素评分 {score}"]
    if party:
        reasons.append(f"主体标识: {', '.join(party[:3])}")
    if clause_no:
        reasons.append(f"条款编号 {clause_no} 处")
    if sign:
        reasons.append(f"签署信息: {', '.join(sign[:2])}")

    if score >= 8 and party:
        if len(labor) >= 3:
            doc_type = DocType.LABOR_CONTRACT
        elif len(service) >= 2:
            doc_type = DocType.SERVICE_AGREEMENT
        else:
            doc_type = DocType.OTHER_CONTRACT
        confidence = min(0.98, 0.55 + score * 0.02)
        return DocCheckResult(
            doc_type, True, round(confidence, 2), "rule", reasons, _build_notice(doc_type, True, confidence)
        )

    if score >= 4 and party and (struct or clause_no or sign):
        doc_type = DocType.LABOR_CONTRACT if len(labor) >= 3 else DocType.OTHER_CONTRACT
        confidence = 0.55
        return DocCheckResult(
            doc_type,
            True,
            confidence,
            "rule",
            [*reasons, "合同要素不完整"],
            _build_notice(doc_type, True, confidence),
        )

    # ── 兜底: 没有合同要素 ──
    if len(noise) >= 5 or url_cnt >= 8:
        return DocCheckResult(
            DocType.NEWS_ARTICLE,
            False,
            0.7,
            "rule",
            [*reasons, f"导航/链接噪声: {len(noise)} 个导航词, {url_cnt} 条链接"],
            _build_notice(DocType.NEWS_ARTICLE, False, 0.7),
        )

    return DocCheckResult(
        DocType.UNKNOWN,
        False,
        0.4,
        "rule",
        [*reasons, "未识别到甲乙方主体与条款结构"],
        _build_notice(DocType.UNKNOWN, False, 0.4),
    )


async def _classify_by_llm(text: str) -> DocCheckResult | None:
    """大模型兜底判定; 未配置密钥或任何异常均返回 None."""
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
            max_tokens=96,
            streaming=False,
            request_timeout=20,
            max_retries=0,
        )
        sample = text[:1500] + ("\n……\n" + text[-500:] if len(text) > 2000 else "")
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": sample},
            ]
        )
        raw = (resp.content or "").strip() if isinstance(resp.content, str) else ""
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(raw[start : end + 1])
        doc_type = DocType(str(data.get("doc_type", "unknown")))
        is_contract = bool(data.get("is_contract"))
        if doc_type in CONTRACT_TYPES:
            is_contract = True
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.6))))
        reason = str(data.get("reason") or "").strip()
        reasons = [f"模型判定: {reason}"] if reason else ["模型判定"]
        return DocCheckResult(
            doc_type,
            is_contract,
            round(confidence, 2),
            "llm",
            reasons,
            _build_notice(doc_type, is_contract, confidence),
        )
    except Exception as exc:  # noqa: BLE001 - 兜底必须吞掉异常, 不能影响主流程
        logger.debug(f"[doc_check] LLM 判定失败, 降级规则: {exc}")
        return None


async def check_document(
    text: str,
    *,
    ext: str | None = None,
    use_llm: bool = True,
) -> DocCheckResult:
    """判定文本是否为可审查的合同.

    Args:
        text: 抽取/粘贴得到的正文.
        ext: 原始文件后缀 (可选), 用于对表格/演示文稿做确定性短路.
        use_llm: 规则低置信度时是否调用大模型兜底.
    """
    if ext in {"xlsx", "csv"}:
        return DocCheckResult(
            DocType.SPREADSHEET,
            False,
            0.95,
            "ext",
            [f".{ext} 表格文件"],
            _build_notice(DocType.SPREADSHEET, False, 0.95),
        )
    if ext == "pptx":
        return DocCheckResult(
            DocType.PRESENTATION,
            False,
            0.95,
            "ext",
            [".pptx 演示文稿"],
            _build_notice(DocType.PRESENTATION, False, 0.95),
        )

    rule_result = _classify_by_rules(text)
    if rule_result.confidence >= _MIN_CONF:
        return rule_result

    if use_llm:
        llm_result = await _classify_by_llm(text)
        if llm_result is not None:
            return llm_result

    return rule_result
