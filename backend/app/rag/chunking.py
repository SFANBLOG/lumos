"""面向合同与制度文档的可追溯文本切分。

每个 chunk 保留文档 ID、序号、字符偏移和标题，便于检索命中后直接回链原文。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TextChunk:
    document_id: str
    chunk_id: str
    text: str
    index: int
    start_char: int
    end_char: int
    title: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def chunk_text(
    text: str,
    document_id: str,
    title: str = "",
    chunk_size: int = 700,
    overlap: int = 120,
) -> list[TextChunk]:
    """按段落优先、句子兜底切分中文文本，避免硬截断核心上下文。"""
    clean = re.sub(r"\r\n?", "\n", text).strip()
    if not clean:
        return []
    if chunk_size <= overlap or overlap < 0:
        raise ValueError("chunk_size 必须大于 overlap，且 overlap 不能为负")

    # 段落优先；超长段落再按中文句末和换行切分。
    units = [p.strip() for p in re.split(r"\n\s*\n+", clean) if p.strip()]
    pieces: list[str] = []
    for unit in units:
        if len(unit) <= chunk_size:
            pieces.append(unit)
        else:
            pieces.extend(s.strip() for s in re.split(r"(?<=[。！？；;])\s*|\n", unit) if s.strip())

    chunks: list[TextChunk] = []
    buffer = ""
    cursor = 0
    for piece in pieces:
        candidate = f"{buffer}\n{piece}".strip() if buffer else piece
        if buffer and len(candidate) > chunk_size:
            start = clean.find(buffer, cursor)
            start = cursor if start < 0 else start
            end = start + len(buffer)
            chunks.append(TextChunk(document_id, f"{document_id}:{len(chunks):04d}", buffer, len(chunks), start, end, title))
            cursor = end
            buffer = buffer[-overlap:] + "\n" + piece if overlap else piece
        else:
            buffer = candidate
    if buffer:
        start = clean.find(buffer, cursor)
        start = max(0, len(clean) - len(buffer)) if start < 0 else start
        chunks.append(TextChunk(document_id, f"{document_id}:{len(chunks):04d}", buffer, len(chunks), start, start + len(buffer), title))
    return chunks
