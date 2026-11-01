"""
合同数据模型.

存储用户上传的合同文本与基本元数据。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from app.models.long_text import LongText


class ContractSource(str, Enum):
    """合同来源类型."""

    CAMERA_OCR = "camera_ocr"  # 拍照 OCR
    PDF_UPLOAD = "pdf_upload"  # PDF 上传
    WORD_UPLOAD = "word_upload"  # Word 上传
    TEXT_PASTE = "text_paste"  # 文本粘贴
    FILE_UPLOAD = "file_upload"  # 文件上传 (智能导入抽取文本)
    URL_ANALYSIS = "url_analysis"  # 网页链接分析


class ContractStatus(str, Enum):
    """合同处理状态."""

    PENDING = "pending"  # 等待分析
    ANALYZING = "analyzing"  # 分析中
    COMPLETED = "completed"  # 分析完成
    FAILED = "failed"  # 分析失败


class Contract(SQLModel, table=True):
    """合同记录表."""

    __tablename__ = "contracts"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="合同唯一标识",
    )

    # ---- 合同内容 ----
    raw_text: str = Field(
        sa_column=Column(
            "raw_text",
            LongText(),
            nullable=False,
        ),
        description="OCR/上传后的原始文本（已脱敏）",
    )
    source: ContractSource = Field(
        default=ContractSource.TEXT_PASTE,
        description="合同来源方式",
    )

    # ---- 状态 ----
    status: ContractStatus = Field(
        default=ContractStatus.PENDING,
        description="当前处理状态",
    )

    # ---- 元数据 ----
    page_count: int | None = Field(default=None, description="合同页数")
    char_count: int | None = Field(default=None, description="字符数")
    device_id: str | None = Field(default=None, description="来源设备标识")

    # ---- 内容体检 (提交时判定文档类型, 非合同内容也能留痕) ----
    doc_type: str | None = Field(
        default=None,
        max_length=32,
        description="判定出的文档类型 (labor_contract/news_article/...)",
    )
    doc_confidence: float | None = Field(
        default=None,
        description="文档类型判定置信度 (0~1)",
    )
    doc_check_method: str | None = Field(
        default=None,
        max_length=16,
        description="判定方式: rule/llm/ext",
    )
    doc_check_note: str | None = Field(
        default=None,
        max_length=255,
        description="内容提示文案 (空表示无需提示), 会写进分析报告",
    )

    # ---- 时间 ----
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="创建时间",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="更新时间",
    )
