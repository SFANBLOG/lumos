"""
同页多栏(双栏/分栏)布局的栏感知抽取测试.

背景: 双栏排版的页面, 纯文本抽取会按 y 坐标把左栏与右栏逐行交错输出, 导致
同栏内的表格被另一栏正文行切断。``table_layout.detect_columns_from_blocks``
聚类栏边界, ``reorder_blocks_by_columns`` 按"先栏后 y"重组; ``text_extractor``
仅对"检测到多栏"的页用栏感知结果覆盖, 单栏/无 PyMuPDF 时完全走原路径。

覆盖:
- 栏检测: 双栏 → 2 列; 单栏 → 1 列;
- 重排: 左栏整体排在前、栏内按 y 保序;
- 端到端: fitz 构造双栏 PDF, ``extract_pdf`` 输出左栏连续 (不被交错);
- 回归: 单栏 PDF 开启/关闭开关输出一致 (不改动单栏文本)。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.services.table_layout import (
    detect_columns_from_blocks,
    reorder_blocks_by_columns,
)
from app.services.text_extractor import extract_pdf


# ─── 合成 blocks 数据 (fitz block 元组: x0,y0,x1,y1,text,block_no,block_type) ──

def _two_column_blocks() -> list:
    """左栏两行 + 右栏两行, x 故意交错插入, 模拟双栏页面."""
    return [
        (30, 100, 260, 120, "L1", 1, 0),
        (340, 110, 570, 130, "R1", 2, 0),
        (30, 200, 260, 220, "L2", 3, 0),
        (340, 210, 570, 230, "R2", 4, 0),
    ]


def _single_column_blocks() -> list:
    return [
        (30, 100, 260, 120, "S1", 1, 0),
        (30, 200, 260, 220, "S2", 2, 0),
        (30, 300, 260, 320, "S3", 3, 0),
    ]


class TestDetectColumns:
    def test_two_columns_detected(self) -> None:
        cols = detect_columns_from_blocks(_two_column_blocks(), page_width=600)
        assert len(cols) == 2

    def test_single_column_returns_one(self) -> None:
        cols = detect_columns_from_blocks(_single_column_blocks(), page_width=600)
        assert len(cols) == 1

    def test_empty_or_zero_width(self) -> None:
        assert detect_columns_from_blocks([], page_width=600) == [(0.0, 600)]
        assert detect_columns_from_blocks(_two_column_blocks(), page_width=0) == [(0.0, 0)]

    def test_columns_sorted_by_x(self) -> None:
        cols = detect_columns_from_blocks(_two_column_blocks(), page_width=600)
        assert cols[0][0] < cols[1][0]


class TestReorderByColumns:
    def test_left_column_grouped_before_right(self) -> None:
        blocks = _two_column_blocks()
        cols = detect_columns_from_blocks(blocks, page_width=600)
        reordered = reorder_blocks_by_columns(blocks, cols)
        # 左栏整体在前, 栏内按 y 保序
        assert reordered[:2] == ["L1", "L2"]
        assert reordered[2:] == ["R1", "R2"]

    def test_single_column_falls_back_to_y_order(self) -> None:
        blocks = _single_column_blocks()
        reordered = reorder_blocks_by_columns(blocks, [(0.0, 600)])
        assert reordered == ["S1", "S2", "S3"]

    def test_empty_blocks(self) -> None:
        assert reorder_blocks_by_columns([], [(0.0, 600)]) == []


# ─── 端到端: fitz 构造双栏/单栏 PDF ────────────────────────────

def _make_two_column_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((30, 100), "L1 左栏第一行")
    page.insert_text((30, 200), "L2 左栏第二行")
    page.insert_text((340, 110), "R1 右栏第一行")
    page.insert_text((340, 210), "R2 右栏第二行")
    return doc.tobytes()


def _make_single_column_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((30, 100), "S1 第一行")
    page.insert_text((30, 200), "S2 第二行")
    page.insert_text((30, 300), "S3 第三行")
    return doc.tobytes()


class TestExtractPdfColumnAware:
    def test_two_column_groups_left_before_right(self) -> None:
        text, _ = extract_pdf(_make_two_column_pdf())
        for token in ("L1", "L2", "R1", "R2"):
            assert token in text
        # 栏感知后: 左栏整体在右栏之前 (不被跨栏文本交错)
        assert text.index("L2") < text.index("R1")
        # 栏内顺序保持
        assert text.index("L1") < text.index("L2")
        assert text.index("R1") < text.index("R2")

    def test_single_column_unchanged_by_toggle(self, monkeypatch) -> None:
        data = _make_single_column_pdf()
        on, _ = extract_pdf(data)
        settings = get_settings()
        monkeypatch.setattr(settings, "pdf_column_aware_extract", False)
        off, _ = extract_pdf(data)
        # 单栏不触发栏感知覆盖, 开关不影响输出
        assert on == off
        assert "S1" in on and "S2" in on and "S3" in on
