"""
跨页表格合并测试 (app/services/table_merge.py) + 版面几何 (table_layout.py)
+ PDF 链路接入回归.

纯文本注入, 不依赖真实 PDF / OCR 引擎, 验证:
- 行切分对 ` | ` / 连续空格 / 制表符三种列分隔的兼容;
- 表格块识别 (行数、列数一致性门槛, 伪表格不当表处理);
- 跨页合并的判定信号: 表头重复 / 列数一致 / 末行截断 / 表题连续,
  以及**版面 y 坐标连续性** (贴页尾+贴页首+左右对齐, 与"明显远离页边"的扣分);
- 版面区域几何: 贴页边判定、左右边界对齐、Tesseract 词框聚成表格区域;
- 典型场景: 重复表头去重、3 页链式合并、列数不齐补齐、独立表不误合并;
- extract_pdf 接入后对既有用例零副作用 (无表格时输出逐字节不变)。
"""

from __future__ import annotations

import io
import sys
import types

import pytest

from app.services import text_extractor as te
from app.services.table_layout import TableRegion, regions_from_image, x_aligned
from app.services.table_merge import (
    TableBlock,
    evaluate_merge,
    merge_cross_page_tables,
    split_row,
)


# ─── 行切分 ────────────────────────────────────────────────────


class TestSplitRow:
    def test_pipe_separated(self) -> None:
        assert split_row("姓名 | 张三 | 男") == ["姓名", "张三", "男"]

    def test_multi_space_aligned(self) -> None:
        # PDF 文字层 / OCR 的常见对齐形态
        assert split_row("姓名    张三    男") == ["姓名", "张三", "男"]

    def test_tab_separated(self) -> None:
        assert split_row("姓名\t张三\t男") == ["姓名", "张三", "男"]

    def test_full_width_space_run(self) -> None:
        assert split_row("姓名　　张三　　男") == ["姓名", "张三", "男"]

    def test_single_cell_is_not_a_row(self) -> None:
        # 普通正文只有 1 个单元格 → 不是表格行
        assert split_row("甲方：星辰科技有限公司") == []

    def test_blank_line(self) -> None:
        assert split_row("   ") == []

    def test_pipe_with_empty_cells_dropped(self) -> None:
        assert split_row(" | 张三 |  | 男 | ") == ["张三", "男"]


# ─── 合并判定 ──────────────────────────────────────────────────


def _blk(page: int, rows: list[list[str]], title: str = "") -> TableBlock:
    return TableBlock(page=page, rows=rows, title=title, pages=[page])


HEADER = ["项目", "标准", "依据"]
P1_DATA = [
    HEADER,
    ["竞业限制", "不超过2年", "劳动合同法第23条"],
    ["试用期社保", "依法缴纳", "社会保险法"],
]
P2_DATA = [
    HEADER,
    ["培训服务期", "不得超过培训费分摊", "劳动合同法第22条"],
]


class TestEvaluateMerge:
    def test_repeated_header_and_same_columns_merges(self) -> None:
        score, repeat, _ = evaluate_merge(_blk(0, P1_DATA), _blk(1, P2_DATA))
        assert repeat is True
        assert score >= 0.55

    def test_column_mismatch_blocks_merge(self) -> None:
        wide = _blk(1, [["a", "b", "c", "d", "e"], ["f", "g", "h", "i", "j"]])
        score, _, reasons = evaluate_merge(_blk(0, P1_DATA), wide)
        assert score < 0.55
        assert any("列数差异大" in r for r in reasons)

    def test_same_header_but_different_titles_not_merged(self) -> None:
        """表头碰巧相同但表题不同 → 判为两张独立表 (防误合并)."""
        a = _blk(0, P1_DATA, title="表1 薪酬结构")
        b = _blk(1, P2_DATA, title="表2 福利待遇")
        score, _, reasons = evaluate_merge(a, b)
        assert score < 0.55
        assert any("表题不一致" in r for r in reasons)

    def test_truncated_last_row_adds_evidence(self) -> None:
        """上页末行缺列 (被页尾截断) 是正向信号."""
        full = _blk(0, P1_DATA)
        trunc = _blk(0, P1_DATA[:-1] + [["休假权益"]])  # 末行只有 1 列
        assert trunc.is_truncated is True
        assert full.is_truncated is False
        s_full, _, _ = evaluate_merge(full, _blk(1, P2_DATA))
        s_trunc, _, _ = evaluate_merge(trunc, _blk(1, P2_DATA))
        assert s_trunc > s_full

    def test_modal_columns(self) -> None:
        blk = _blk(0, [["a", "b", "c"], ["d", "e"], ["f", "g", "h"]])
        assert blk.n_cols == 3


# ─── 端到端合并 ────────────────────────────────────────────────


def _render(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(r) for r in rows)


class TestMergeCrossPageTables:
    def test_repeated_header_is_deduplicated(self) -> None:
        p1 = f"合同正文开头\n{_render(P1_DATA)}"
        p2 = f"{_render(P2_DATA)}\n合同正文结尾"
        out = merge_cross_page_tables([p1, p2])

        # 合并后整张表挂在前页, 后页只剩尾部正文
        assert out[0].endswith(_render(P1_DATA + P2_DATA[1:]))
        assert out[1] == "合同正文结尾"
        # 表头只出现一次
        assert out[0].count("项目 | 标准 | 依据") == 1

    def test_no_header_repeat_but_truncated_still_merges(self) -> None:
        """下页没有重复表头, 但上页末行缺列 (2/3) + 列数一致 → 仍应合并."""
        p1_rows = [HEADER,
                   ["竞业限制", "不超过2年", "劳动合同法第23条"],
                   ["试用期社保", "依法缴纳"]]          # 末行缺第 3 列
        p2_rows = [["第58条", "备注A", "x"],
                   ["年休假", "不少于5天", "第3条"]]
        out = merge_cross_page_tables([_render(p1_rows), _render(p2_rows)])
        assert len(out) == 2
        assert "试用期社保 | 依法缴纳 | " in out[0]      # 末行被补齐
        assert "第58条 | 备注A | x" in out[0]           # 下页首行接上

    def test_three_page_chain_merge(self) -> None:
        p1 = _render([HEADER, ["a", "1", "x"]])
        p2 = _render([HEADER, ["b", "2", "y"]])
        p3 = _render([HEADER, ["c", "3", "z"]])
        out = merge_cross_page_tables([p1, p2, p3])
        assert out[0] == _render([HEADER, ["a", "1", "x"], ["b", "2", "y"], ["c", "3", "z"]])
        assert out[1] == ""
        assert out[2] == ""

    def test_column_counts_are_padded_not_truncated(self) -> None:
        """列数不齐时补齐而非截断, 不丢数据 (前页行也被补到最大列数)."""
        p1 = "a | b\nc | d\ne | f"                   # 2 列
        p2 = "a | b\nx | y | z\np | q | r"            # 3 列
        out = merge_cross_page_tables([p1, p2])
        assert "x | y | z" in out[0]
        assert "p | q | r" in out[0]
        assert "a | b | " in out[0]                   # 前页行补齐到 3 列
        assert "e | f | " in out[0]

    def test_two_independent_tables_not_merged(self) -> None:
        """两张列数不同的独立表不应被合并."""
        p1 = _render([["a", "b"], ["c", "d"]])
        p2 = _render([["x", "y", "z"], ["u", "v", "w"]])
        out = merge_cross_page_tables([p1, p2])
        assert out == [p1, p2]

    def test_no_table_pages_are_identity(self) -> None:
        pages = ["第一页正文", "第二页正文", "第三页正文"]
        assert merge_cross_page_tables(pages) == pages

    def test_single_page_short_circuits(self) -> None:
        assert merge_cross_page_tables(["只有一页"]) == ["只有一页"]

    def test_high_threshold_suppresses_merge(self) -> None:
        out = merge_cross_page_tables(
            [_render(P1_DATA), _render(P2_DATA)], threshold=0.99
        )
        assert out[0] == _render(P1_DATA)
        assert out[1] == _render(P2_DATA)

    def test_table_not_at_page_boundary_is_not_merged(self) -> None:
        """上页的表不在页尾 (后面还有正文) → 不合并."""
        p1 = f"{_render(P1_DATA)}\n页尾补充说明"
        p2 = _render(P2_DATA)
        out = merge_cross_page_tables([p1, p2])
        assert out == [p1, p2]


# ─── 版面几何 (table_layout.py) ────────────────────────────────


def _fake_tesseract(words: list[tuple]) -> types.ModuleType:
    """构造假 pytesseract: image_to_data 返回指定词框 (left, top, w, h, text, line)."""
    mod = types.ModuleType("pytesseract")

    class _Output:
        DICT = "dict"

    mod.Output = _Output  # type: ignore[attr-defined]

    def _image_to_data(img, lang=None, output_type=None):  # noqa: ARG001
        return {
            "text": [w[4] for w in words],
            "left": [w[0] for w in words],
            "top": [w[1] for w in words],
            "width": [w[2] for w in words],
            "height": [w[3] for w in words],
            "block_num": [0] * len(words),
            "par_num": [0] * len(words),
            "line_num": [w[5] for w in words],
        }

    mod.image_to_data = _image_to_data  # type: ignore[attr-defined]
    return mod


def _blank_png(width: int = 1000, height: int = 1400) -> bytes:
    """生成一张真实白底 PNG (供 PIL 解码)."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return buf.getvalue()


class TestTableRegionGeometry:
    def test_touches_top_and_bottom(self) -> None:
        bottom = TableRegion(0, 50, 1200, 550, 1380, 600, 1400)
        assert bottom.touches_bottom is True
        assert bottom.touches_top is False

        top = TableRegion(1, 50, 10, 550, 200, 600, 1400)
        assert top.touches_top is True
        assert top.touches_bottom is False

    def test_x_aligned(self) -> None:
        a = TableRegion(0, 50, 1200, 550, 1380, 600, 1400)
        b = TableRegion(1, 50, 10, 550, 200, 600, 1400)
        assert x_aligned(a, b) is True  # 左右边界完全重合

        shifted = TableRegion(1, 300, 10, 800, 200, 600, 1400)
        assert x_aligned(a, shifted) is False  # 左边界偏移 250px > 容差 60px
        assert x_aligned(a, None) is False


class TestRegionsFromImage:
    def test_multi_column_lines_form_region(self, monkeypatch) -> None:
        """4 行 × 2 列、列间空隙 320px → 聚成一个表格区域."""
        words = []
        for i in range(4):
            y = 100 + i * 30
            words.append((100, y, 80, 20, f"a{i}", i))
            words.append((500, y, 80, 20, f"b{i}", i))
        monkeypatch.setitem(sys.modules, "pytesseract", _fake_tesseract(words))

        regions = regions_from_image(_blank_png(), page_index=0)
        assert len(regions) == 1
        r = regions[0]
        assert r.source == "tesseract"
        assert (r.x0, r.x1) == (100, 580)
        assert r.n_rows == 4
        assert r.touches_top is True       # y0=100 <= 1400*0.08=112
        assert r.touches_bottom is False

    def test_single_column_prose_forms_no_region(self, monkeypatch) -> None:
        """每行只有一个词 (正文) → 不构成多列, 无表格区域."""
        words = [(100, 100 + i * 30, 300, 20, f"正文第{i}行", i) for i in range(6)]
        monkeypatch.setitem(sys.modules, "pytesseract", _fake_tesseract(words))

        assert regions_from_image(_blank_png(), page_index=0) == []

    def test_missing_tesseract_returns_empty(self, monkeypatch) -> None:
        """Tesseract 不可用时静默返回空 (交由纯文本信号兜底)."""
        monkeypatch.setitem(sys.modules, "pytesseract", None)
        assert regions_from_image(_blank_png(), page_index=0) == []


class TestLayoutGeometrySignal:
    def test_geometry_confirms_continuation(self) -> None:
        """上页贴页尾 + 下页贴页首 + 左右对齐 → 加分."""
        prev, nxt = _blk(0, P1_DATA), _blk(1, P2_DATA)
        base, _, _ = evaluate_merge(prev, nxt)

        prev.region = TableRegion(0, 50, 1200, 550, 1390, 600, 1400)
        nxt.region = TableRegion(1, 50, 5, 550, 150, 600, 1400)
        boosted, _, reasons = evaluate_merge(prev, nxt)

        assert boosted > base
        assert any("版面连续" in r for r in reasons)
        assert any("左右边界对齐" in r for r in reasons)

    def test_geometry_penalizes_mid_page_tables(self) -> None:
        """两表都在页面中部 (远离页边) → 版面不连续, 扣分."""
        prev, nxt = _blk(0, P1_DATA), _blk(1, P2_DATA)
        base, _, _ = evaluate_merge(prev, nxt)

        prev.region = TableRegion(0, 50, 300, 550, 500, 600, 1400)   # 35% 处结束
        nxt.region = TableRegion(1, 50, 600, 550, 800, 600, 1400)    # 43% 处开始
        penalized, _, reasons = evaluate_merge(prev, nxt)

        assert penalized < base
        assert any("版面明显不连续" in r for r in reasons)

    def test_geometry_alone_can_trigger_merge(self) -> None:
        """无表头重复、无截断、无表题时, 仅靠版面连续性也能判定合并."""
        p1 = _render([["a", "b", "c"], ["d", "e", "f"]])
        p2 = _render([["x", "y", "z"], ["u", "v", "w"]])
        # 纯文本只有"列数一致" 0.25 分, 不够阈值 → 不合并
        assert merge_cross_page_tables([p1, p2]) == [p1, p2]

        layouts = {
            0: [TableRegion(0, 50, 1200, 550, 1390, 600, 1400)],
            1: [TableRegion(1, 50, 5, 550, 150, 600, 1400)],
        }
        out = merge_cross_page_tables([p1, p2], layouts=layouts)
        assert "x | y | z" in out[0]

    def test_no_geometry_keeps_pure_text_behavior(self) -> None:
        """不传几何时行为与旧版完全一致 (可缺省, 不退化)."""
        p1, p2 = _render(P1_DATA), _render(P2_DATA)
        assert merge_cross_page_tables([p1, p2], layouts=None) == \
            merge_cross_page_tables([p1, p2])


# ─── extract_pdf 接入回归 ──────────────────────────────────────


def _fake_pypdf(page_texts: list[str]) -> types.ModuleType:
    mod = types.ModuleType("pypdf")

    class _Page:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class _Reader:
        def __init__(self, _data: object) -> None:
            self.pages = [_Page(t) for t in page_texts]

    mod.PdfReader = _Reader  # type: ignore[attr-defined]
    return mod


def _fake_fitz(page_count: int) -> types.ModuleType:
    mod = types.ModuleType("fitz")

    class _Pixmap:
        def tobytes(self, _fmt: str) -> bytes:
            return b"PNGDUMMY"

    class _Page:
        def get_pixmap(self, matrix: object = None) -> _Pixmap:  # noqa: ARG002
            return _Pixmap()

    class _Doc:
        def __init__(self, *_a: object, **_k: object) -> None:
            self._pages = [_Page() for _ in range(page_count)]
            self.page_count = page_count

        def __getitem__(self, idx: int) -> _Page:
            return self._pages[idx]

        def close(self) -> None:
            pass

    mod.open = lambda **_kw: _Doc()  # type: ignore[attr-defined]
    mod.Matrix = lambda *a: a  # type: ignore[attr-defined]
    return mod


class TestExtractPdfCrossPageTable:
    def test_scanned_pdf_cross_page_table_is_merged(self, monkeypatch) -> None:
        """扫描版 PDF: 两页 OCR 出的半张表被拼回一张 (表头去重)."""
        page1 = "费用明细\n项目    标准    依据\n竞业限制    不超过2年    第23条"
        page2 = "项目    标准    依据\n培训服务期    分摊    第22条"
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf(["", ""]))
        monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(page_count=2))

        ocr_texts = iter([page1, page2])
        monkeypatch.setattr(te, "extract_image", lambda _d: (next(ocr_texts), True))

        text, scanned = te.extract_pdf(b"%PDF-1.4 fake")
        assert scanned is True
        # 合并后表头只出现一次, 且输出统一为 ` | ` 分隔
        assert text.count("项目 | 标准 | 依据") == 1
        assert "培训服务期 | 分摊 | 第22条" in text

    def test_text_layer_pdf_cross_page_table_is_merged(self, monkeypatch) -> None:
        """有文字层的 PDF 同样做跨页表格合并."""
        page1 = "项目 | 标准 | 依据\n竞业限制 | 不超过2年 | 第23条"
        page2 = "项目 | 标准 | 依据\n培训服务期 | 分摊 | 第22条"
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf([page1, page2]))

        text, scanned = te.extract_pdf(b"%PDF-1.4 fake")
        assert scanned is False
        assert text.count("项目 | 标准 | 依据") == 1
        assert "培训服务期 | 分摊 | 第22条" in text

    def test_merge_can_be_disabled_by_config(self, monkeypatch) -> None:
        """关闭开关后恢复逐页独立抽取 (跨页表仍被切成两张)."""
        page1 = "项目 | 标准 | 依据\n竞业限制 | 不超过2年 | 第23条"
        page2 = "项目 | 标准 | 依据\n培训服务期 | 分摊 | 第22条"
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf([page1, page2]))
        monkeypatch.setattr(
            "app.core.config.get_settings",
            lambda: types.SimpleNamespace(
                pdf_cross_page_table_merge=False, pdf_layout_geometry=False
            ),
        )

        text, _ = te.extract_pdf(b"%PDF-1.4 fake")
        assert text.count("项目 | 标准 | 依据") == 2

    def test_no_table_output_unchanged(self, monkeypatch) -> None:
        """回归: 无表格内容时输出与改造前逐字节一致."""
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf(["第一条正文", "", "第三条正文"]))
        monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(page_count=3))
        monkeypatch.setattr(te, "extract_image", lambda _d: ("第二条OCR文本", True))

        text, scanned = te.extract_pdf(b"%PDF-1.4 fake")
        assert scanned is False
        assert text == "第一条正文\n\n第二条OCR文本\n\n第三条正文"
