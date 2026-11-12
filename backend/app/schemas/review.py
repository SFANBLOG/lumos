"""审查增强层共享数据结构.

补齐行业基线里的三项交付物: 合同要素表、缺失条款检测、风险条目级反馈。
这些类型同时被 Agent 状态、ORM 表与 API 响应复用，因此放在 schemas 层，
避免 ``app.agent`` 与 ``app.api`` 之间产生循环导入。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# 合同要素状态取值: present(已写明) / missing(未检出) / unclear(检出但取值不明确)
# / contradicted(检出但与法定要求冲突, 比缺失更危险)
FACT_PRESENT = "present"
FACT_MISSING = "missing"
FACT_UNCLEAR = "unclear"
FACT_CONTRADICTED = "contradicted"


class ContractFact(BaseModel):
    """一项合同要素及其原文定位.

    与旧的 ``AgentState.contract_facts`` (只有日期/金额/义务的正则结果) 不同,
    这里每项都带 label、evidence、confidence 与 required, 可直接渲染成核对表,
    也是缺失条款检测、模板比对、版本 diff 的共同输入。
    """

    key: str = Field(description="要素标识, 如 salary / work_location")
    label: str = Field(description="中文展示名")
    value: str = Field(default="", description="抽取到的要素值")
    evidence: str = Field(default="", description="命中的原文片段, 用于定位与复核")
    confidence: float = Field(default=0.0, ge=0, le=1, description="抽取置信度")
    status: str = Field(default=FACT_MISSING, description="present / missing / unclear")
    required: bool = Field(default=False, description="是否属于法定必备条款")
    legal_basis: str = Field(default="", description="缺失时援引的法条")
    matched_by: str = Field(default="", description="capture / keyword / negation / none")
    contradiction: str = Field(default="", description="命中的与法定要求冲突的原文片段")
    rule_set: str = Field(default="labor_contract", description="使用的必备条款规则集")


class MissingClause(BaseModel):
    """一项「该写却没写」的条款缺口."""

    key: str = Field(description="对应 ContractFact.key")
    label: str = Field(description="中文展示名")
    reason: str = Field(description="为什么必须有、缺失会有什么风险")
    legal_basis: str = Field(default="", description="法条依据")
    suggested_text: str = Field(default="", description="建议补充的条款措辞 (可直接提给 HR)")
    level: str = Field(default="medium", description="high / medium / low")
    score: int = Field(default=30, ge=0, le=100, description="缺失项单项评分")


class FeedbackVerdict(str, Enum):
    """用户对单条 AI 风险结论的判定."""

    ACCEPTED = "accepted"  # 认可: 确实有风险
    FALSE_POSITIVE = "false_positive"  # 误报: AI 判错了
    IGNORED = "ignored"  # 忽略: 有风险但不打算处理


class ContractFactResponse(ContractFact):
    """报告接口中的要素表行."""

    model_config = {"from_attributes": True}


class MissingClauseResponse(MissingClause):
    """报告接口中的缺失条款行."""

    model_config = {"from_attributes": True}


class RiskFeedbackCreate(BaseModel):
    """提交一条风险反馈 (同一用户对同一风险重复提交视为更新)."""

    risk_item_id: str
    contract_id: str
    verdict: FeedbackVerdict
    comment: str = Field(default="", max_length=1000)


class RiskFeedbackResponse(BaseModel):
    """风险反馈记录."""

    id: str
    risk_item_id: str
    contract_id: str
    verdict: FeedbackVerdict
    comment: str = ""
    user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReviewStatsResponse(BaseModel):
    """真实反馈闭环指标 (替换前端写死的「建议采纳率」)."""

    total: int = 0
    accepted: int = 0
    false_positive: int = 0
    ignored: int = 0
    adoption_rate: float = Field(default=0.0, ge=0, le=1, description="认可率")
    false_positive_rate: float = Field(default=0.0, ge=0, le=1, description="误报率")


class ShareCreateRequest(BaseModel):
    """创建报告分享链接."""

    ttl_hours: int = Field(default=72, ge=1, le=720, description="有效期 (小时)")
    allow_annotations: bool = Field(default=True, description="是否允许对方在线批注")


class ShareResponse(BaseModel):
    """分享链接创建结果; token 只在这里返回一次."""

    id: str
    token: str
    url: str
    expires_at: datetime
    allow_annotations: bool
    revoked: bool = False

    model_config = {"from_attributes": True}


class ShareListItem(BaseModel):
    """分享链接管理列表项 (不含 token)."""

    id: str
    contract_id: str
    expires_at: datetime
    created_at: datetime
    revoked: bool
    allow_annotations: bool
    annotation_count: int = 0

    model_config = {"from_attributes": True}


class AnnotationCreate(BaseModel):
    """提交一条在线批注 (分享链接持有者无需登录)."""

    risk_item_id: str = Field(default="", max_length=64)
    quote: str = Field(default="", max_length=2000, description="引用的原条款片段")
    comment: str = Field(min_length=1, max_length=2000)
    author: str = Field(default="匿名", max_length=64)


class AnnotationResponse(BaseModel):
    """在线批注."""

    id: str
    contract_id: str
    share_id: str
    risk_item_id: str = ""
    quote: str = ""
    comment: str
    author: str
    created_at: datetime

    model_config = {"from_attributes": True}
