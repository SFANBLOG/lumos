"""
文本预处理技能.

提供 OCR 纠错、敏感信息脱敏、格式标准化能力。
"""

from __future__ import annotations

import re
from typing import Any

from app.skills.base import BaseSkill

_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_IDCARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_OCR_FIXES = {
    " labour ": " 劳动 ",
    "劳劝": "劳动",
    "竞业禁止": "竞业限制",
    "试用期工贤": "试用期工资",
}


class TextPreprocessingSkill(BaseSkill):
    """文本清洗: OCR 纠错 + 脱敏 + 标准化."""

    name = "text_preprocessing"
    description = "对原始合同文本进行 OCR 纠错、敏感信息脱敏和格式标准化"

    async def execute(self, *, text: str, mask_sensitive: bool = True, **kwargs: Any) -> dict[str, Any]:
        cleaned = text

        for wrong, correct in _OCR_FIXES.items():
            cleaned = cleaned.replace(wrong, correct)

        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)

        if mask_sensitive:
            cleaned = _PHONE_RE.sub("<手机号已脱敏>", cleaned)
            cleaned = _IDCARD_RE.sub("<身份证已脱敏>", cleaned)
            cleaned = _EMAIL_RE.sub("<邮箱已脱敏>", cleaned)

        return {
            "text": cleaned.strip(),
            "original_length": len(text),
            "cleaned_length": len(cleaned.strip()),
            "sensitive_masked": mask_sensitive,
        }
