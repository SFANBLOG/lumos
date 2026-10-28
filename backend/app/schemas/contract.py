"""
合同相关请求/响应 Schema.

定义 API 层的数据传输对象 (DTO)，与数据库模型解耦。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.contract import ContractSource, ContractStatus


# ─── 请求 ──────────────────────────────────────────────────────


class ContractCreateRequest(BaseModel):
    """提交合同进行分析的请求体."""

    text: str = Field(
        ...,
        min_length=10,
        max_length=100_000,
        description="已脱敏的合同文本内容",
    )
    source: ContractSource = Field(
        default=ContractSource.TEXT_PASTE,
        description="合同来源方式",
    )
    page_count: int | None = Field(
        default=None,
        ge=1,
        description="合同页数 (拍照模式时由客户端传入)",
    )
    device_id: str | None = Field(
        default=None,
        max_length=128,
        description="客户端设备标识 (可选)",
    )


# ─── 响应 ──────────────────────────────────────────────────────


class ContractResponse(BaseModel):
    """合同记录响应."""

    id: str
    source: ContractSource
    status: ContractStatus
    page_count: int | None
    char_count: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContractSubmitResponse(BaseModel):
    """提交合同后的立即响应 (分析将通过 SSE 流式推送)."""

    contract_id: str = Field(description="合同 ID, 用于后续查询和 SSE 订阅")
    status: ContractStatus = Field(default=ContractStatus.ANALYZING)
    message: str = Field(default="合同已受理, 正在进行 AI 风险排查…")
    stream_url: str = Field(description="SSE 流式分析结果订阅地址")


class ContractListItem(BaseModel):
    """合同列表项 (含正文预览)."""

    id: str
    source: ContractSource
    status: ContractStatus
    char_count: int | None
    created_at: datetime
    preview: str = Field(default="", description="正文前 80 字预览")


class ContractListResponse(BaseModel):
    """合同记录分页列表."""

    total: int
    page: int
    page_size: int
    items: list[ContractListItem]


class ContractStatsResponse(BaseModel):
    """看板统计汇总."""

    total: int = Field(description="合同分析总量")
    completed: int
    analyzing: int
    failed: int
    pending: int
    avg_overall_score: float | None = Field(description="平均安全分 (0-100, 无数据为 null)")
    high_risk_contracts: int = Field(description="高危合同数 (overall_level=high)")
    level_counts: dict[str, int] = Field(description="风险条目按等级计数 (high/medium/low/safe)")
    recent: list[ContractListItem] = Field(description="最近 5 条合同记录")
