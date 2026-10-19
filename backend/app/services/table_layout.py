"""
PDF 版面几何提取 — 为跨页表格判定提供 y 坐标连续性证据.

背景: ``table_merge.py`` 的合并判定原先只有三类**纯文本**信号 (表头重复 /
列数一致 / 末行截断 / 表题一致), 缺少最直观的**版面连续性**证据——
上一页表格是否顶到页尾、下一页表格是否从页首开始、左右边界是否对齐。

难点在于扫描版 PDF 走 OCR 后只拿到纯文本, 没有字框坐标。本模块的取法:

- **有文字层的页**: 用 PyMuPDF 的 ``page.find_tables()`` 直接拿表格线框
  bbox (真实矢量几何, 最准); 老版本 PyMuPDF 没有该 API 时静默跳过;
- **无文字层的页 (扫描件)**: 渲染出的位图再跑一趟 Tesseract
  ``image_to_data`` 拿词框, 按 y 聚类成行, 再把"连续多行都呈多列排布"
  的行段聚成表格区域, 区域 bbox 取并集。

设计要点: 本模块只产出**区域级**几何 (bbox + 是否贴页边 + 左右边界),
不产出行级坐标, 因此**不需要**与 OCR 文本逐行对齐——跨页判定只需要
"上页表贴页尾 / 下页表贴页首 / 左右对齐"这三个事实。这样它就能作为
一个**可缺省的附加信号**叠加到纯文本判定之上, 拿不到几何时自动退回
原有三类信号, 不会让功能退化。

成本说明: 扫描页需要额外一趟 Tesseract (不重复渲染, 复用已渲染的位图),
且只对"OCR 文本里确实有表格行"的页执行, 正文页零开销。
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from loguru import logger

__all__ = [
    "TableRegion",
    "x_aligned",
    "extract_pdf_layout",
    "regions_from_image",
    "detect_columns_from_blocks",
    "reorder_blocks_by_columns",
]

#: 距页边多少比例以内算"贴页边" (用于判定表是否顶到页尾/页首)
_EDGE_RATIO = 0.08

#: 左右边界对齐容差 (占表格宽度的比例)
_X_ALIGN_TOL_RATIO = 0.12

#: Tesseract 词框判定"多列"的最小列间空隙 (占图像宽度比例)
_MIN_COL_GAP_RATIO = 0.03

#: 连续多少行多列排布才认定为一个表格区域
_MIN_REGION_LINES = 3


@dataclass
class TableRegion:
    """一页上的一个表格区域 (版面几何)."""

    page: int
    x0: float  # 左边界
    y0: float  # 上边界
    x1: float  # 右边界
    y1: float  # 下边界
    page_width: float
    page_height: float
    n_rows: int = 0
    #: 几何来源: pymupdf (矢量线框) | tesseract (OCR 词框)
    source: str = ""

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def touches_top(self) -> bool:
        """区域是否贴近页首 (下一页表格从页首开始 → 跨页续表的强证据)."""
        if self.page_height <= 0:
            return False
        return self.y0 <= self.page_height * _EDGE_RATIO

    @property
    def touches_bottom(self) -> bool:
        """区域是否贴近页尾 (上一页表格顶到页尾 → 跨页续表的强证据)."""
        if self.page_height <= 0:
            return False
        return self.y1 >= self.page_height * (1 - _EDGE_RATIO)

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return (
            f"TableRegion(page={self.page}, bbox=({self.x0:.0f},{self.y0:.0f})"
            f"-({self.x1:.0f},{self.y1:.0f}), source={self.source or '-'})"
        )


def x_aligned(a: TableRegion | None, b: TableRegion | None) -> bool:
    """两个表格区域的左右边界是否对齐 (容差为较宽者宽度的 12%)."""
    if a is None or b is None:
        return False
    tol = max(a.width, b.width) * _X_ALIGN_TOL_RATIO
    return abs(a.x0 - b.x0) <= tol and abs(a.x1 - b.x1) <= tol


# ─── 有文字层的页: PyMuPDF 矢量线框 ────────────────────────────


def _regions_from_fitz_page(page: object, page_index: int) -> list[TableRegion]:
    """用 ``page.find_tables()`` 提取表格 bbox; 不支持时返回空列表."""
    find_tables = getattr(page, "find_tables", None)
    if find_tables is None:
        return []

    rect = getattr(page, "rect", None)
    page_width = float(getattr(rect, "width", 0) or 0)
    page_height = float(getattr(rect, "height", 0) or 0)

    try:
        finder = find_tables()
    except Exception as e:  # 版面分析失败不应中断抽取主链路
        logger.debug(f"版面分析失败 | 第{page_index + 1}页 | {e}")
        return []

    regions: list[TableRegion] = []
    for table in getattr(finder, "tables", []) or []:
        bbox = getattr(table, "bbox", None)
        if not bbox or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = (float(v) for v in bbox)
        rows = getattr(table, "rows", []) or []
        regions.append(
            TableRegion(
                page=page_index,
                x0=x0, y0=y0, x1=x1, y1=y1,
                page_width=page_width,
                page_height=page_height,
                n_rows=len(rows),
                source="pymupdf",
            )
        )
    return regions


# ─── 无文字层的页: Tesseract 词框聚类 ──────────────────────────


def regions_from_image(png_bytes: bytes, page_index: int = 0,
                       lang: str = "chi_sim+eng") -> list[TableRegion]:
    """
    从已渲染的页面位图提取表格区域 (Tesseract 词框 → 行 → 表格区域).

    步骤: 词框按 (block, par, line) 聚成文本行 → 按 y 排序 → 找出"词间存在
    明显横向空隙"的多列行 → 连续 >=3 行多列排布即认定为一个表格区域。

    Tesseract 不可用或识别不出结构时返回空列表 (交由纯文本信号兜底)。
    """
    try:
        from PIL import Image
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return []

    try:
        img = Image.open(io.BytesIO(png_bytes))
        data = pytesseract.image_to_data(img, lang=lang, output_type=Output.DICT)
    except Exception as e:
        logger.debug(f"版面几何: OCR 词框获取失败 | 第{page_index + 1}页 | {e}")
        return []

    img_w, img_h = img.size
    if not img_w or not img_h:
        return []

    # 1) 词框 → 文本行 (按 block/par/line 分组)
    texts = data.get("text") or []
    if not texts:
        return []

    lines: dict[tuple, dict] = {}
    for i, raw in enumerate(texts):
        word = (raw or "").strip()
        if not word:
            continue
        try:
            left = float(data["left"][i])
            top = float(data["top"][i])
            width = float(data["width"][i])
            height = float(data["height"][i])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        key = (data.get("block_num", [0] * len(texts))[i],
               data.get("par_num", [0] * len(texts))[i],
               data.get("line_num", [0] * len(texts))[i])
        bucket = lines.setdefault(
            key, {"x0": left, "y0": top, "x1": left + width, "y1": top + height,
                  "words": []}
        )
        bucket["x0"] = min(bucket["x0"], left)
        bucket["y0"] = min(bucket["y0"], top)
        bucket["x1"] = max(bucket["x1"], left + width)
        bucket["y1"] = max(bucket["y1"], top + height)
        bucket["words"].append((left, left + width))

    ordered = sorted(lines.values(), key=lambda b: (b["y0"], b["x0"]))

    # 2) 判定每行是否"多列": 词间最大空隙超过图宽 3% 即视为分列
    min_gap = img_w * _MIN_COL_GAP_RATIO
    multi_col: list[bool] = []
    for line in ordered:
        words = sorted(line["words"])
        if len(words) < 2:
            multi_col.append(False)
            continue
        max_gap = max(words[k + 1][0] - words[k][1] for k in range(len(words) - 1))
        multi_col.append(max_gap >= min_gap)

    # 3) 连续多列行聚成区域 (允许中间断 1 行)
    regions: list[TableRegion] = []
    run: list[dict] = []
    gap_budget = 0

    def _flush() -> None:
        nonlocal run, gap_budget
        if len(run) >= _MIN_REGION_LINES:
            regions.append(
                TableRegion(
                    page=page_index,
                    x0=min(b["x0"] for b in run),
                    y0=min(b["y0"] for b in run),
                    x1=max(b["x1"] for b in run),
                    y1=max(b["y1"] for b in run),
                    page_width=float(img_w),
                    page_height=float(img_h),
                    n_rows=len(run),
                    source="tesseract",
                )
            )
        run = []
        gap_budget = 0

    for line, is_multi in zip(ordered, multi_col):
        if is_multi:
            run.append(line)
            gap_budget = 0
        elif run:
            gap_budget += 1
            if gap_budget > 1:
                _flush()
    _flush()

    return regions


# ─── 统一入口 ──────────────────────────────────────────────────


def extract_pdf_layout(
    data: bytes,
    blank_idx: list[int],
    ocr_renderer: object | None = None,
) -> dict[int, list[TableRegion]]:
    """
    提取 PDF 各页的表格区域几何.

    Args:
        data: PDF 原始字节.
        blank_idx: 无文字层 (需 OCR) 的页索引.
        ocr_renderer: 可选回调 ``(page_index) -> png_bytes | None``, 用于复用
            已渲染的位图, 避免重复渲染; 未提供时扫描页跳过几何提取。

    Returns:
        {页索引: [TableRegion, ...]}, 按 y0 升序。拿不到几何的页不出现在结果里。
    """
    layout: dict[int, list[TableRegion]] = {}
    if not data:
        return layout

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.debug("版面几何: pymupdf 不可用, 跳过")
        return layout

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        logger.debug(f"版面几何: PDF 打开失败 | {e}")
        return layout

    try:
        blank_set = set(blank_idx)
        for idx in range(doc.page_count):
            try:
                if idx in blank_set:
                    # 扫描页: 复用已渲染位图跑 Tesseract 词框
                    if ocr_renderer is None:
                        continue
                    png = ocr_renderer(idx)
                    if not png:
                        continue
                    regions = regions_from_image(png, page_index=idx)
                else:
                    regions = _regions_from_fitz_page(doc[idx], idx)
            except Exception as e:
                logger.debug(f"版面几何: 第{idx + 1}页提取失败 | {e}")
                continue
            if regions:
                regions.sort(key=lambda r: r.y0)
                layout[idx] = regions
    finally:
        doc.close()

    return layout


# ─── 同页多栏 (双栏/分栏) 检测与重排 ──────────────────────────
#
# 双栏/分栏排版的页面, 纯文本抽取 (pypdf / Tesseract 默认顺序) 会按 y 坐标把
# 左栏与右栏的文本逐行交错输出, 导致"同栏内的表格"被另一栏的正文行切断、
# 表格行不再连续。解决办法: 先检测栏边界, 再按"先栏后 y"的顺序重组文本块。
#
# 这里只依赖文本块的 bbox (x0/x1/y0 与文本), 不依赖 OCR 逐行对齐, 因此
# 可同时服务于"有文字层页 (PyMuPDF blocks)"与"扫描页 (Tesseract 词框聚合
# 出的行块)"两种来源 —— 调用方把各自的 (x0,y0,x1,y1,text) 块喂进来即可。


#: 判定"栏间空档"的最小宽度 (占子区间宽度比例)
_MIN_GAP_RATIO = 0.08

#: 过滤掉过窄的列 (占子区间宽度比例), 避免把单栏内的局部空隙误切成多列
_MIN_COL_RATIO = 0.10

#: 最多切分出的栏数 (防止噪声把页面切成碎列)
_MAX_COLS = 4


def detect_columns_from_blocks(
    text_blocks: list,
    page_width: float,
    max_cols: int = _MAX_COLS,
) -> list[tuple[float, float]]:
    """
    从文本块 (fitz block 元组: (x0,y0,x1,y1,text,block_no,block_type)) 聚类出
    栏边界 ``[(x0,x1), ...]`` (按 x 升序).

    算法: 把块的 x 跨度投影到一维, 在"覆盖为空"的最大空档处切一刀, 递归切分
    直到无足够大的空档或达到 max_cols。单栏页面返回 ``[(0, page_width)]``。
    """
    if not text_blocks or page_width <= 0:
        return [(0.0, page_width)]

    def _rec(blocks: list, lo: float, hi: float, depth: int) -> list[tuple[float, float]]:
        width = hi - lo
        if width <= 0 or len(blocks) < 2 or depth >= max_cols - 1:
            return [(lo, hi)]

        spans = [(max(lo, b[0]), min(hi, b[2])) for b in blocks]
        nbins = max(20, int(width / page_width * 200))
        cov = [0] * nbins
        for x0, x1 in spans:
            a = max(0, min(nbins - 1, int((x0 - lo) / width * nbins)))
            b_ = max(a, min(nbins - 1, int((x1 - lo) / width * nbins)))
            for k in range(a, b_ + 1):
                cov[k] += 1

        # 找最大空档
        best = None
        i = 0
        while i < nbins:
            if cov[i] == 0:
                j = i
                while j < nbins and cov[j] == 0:
                    j += 1
                gap_len = (j - i) / nbins
                if best is None or gap_len > best[2]:
                    best = (i, j, gap_len)
                i = j
            else:
                i += 1

        if best is None or best[2] < _MIN_GAP_RATIO:
            return [(lo, hi)]

        gi, gj, _ = best
        cut = lo + (gi + gj) / 2 / nbins * width
        left = [b for b in blocks if (b[0] + b[2]) / 2 <= cut]
        right = [b for b in blocks if (b[0] + b[2]) / 2 > cut]
        if not left or not right:
            return [(lo, hi)]

        cols = _rec(left, lo, cut, depth + 1) + _rec(right, cut, hi, depth + 1)
        cols = [(c0, c1) for c0, c1 in cols if (c1 - c0) >= _MIN_COL_RATIO * width]
        if len(cols) <= 1:
            return [(lo, hi)]
        cols.sort()
        return cols

    return _rec(text_blocks, 0.0, page_width, 0)


def reorder_blocks_by_columns(
    text_blocks: list,
    columns: list[tuple[float, float]],
) -> list[str]:
    """
    按"先栏后 y (再 x)"的顺序重排文本块, 返回重排后的文本列表.

    ``text_blocks`` 元素同 ``detect_columns_from_blocks``; ``columns`` 为其输出。
    单栏 (len(columns) <= 1) 时退化为按 (y, x) 排序, 不改变原有阅读顺序。
    """
    if not text_blocks:
        return []

    if len(columns) <= 1:
        ordered = sorted(text_blocks, key=lambda b: (b[1], b[0]))
        return [b[4] for b in ordered]

    def _col_of(block: object) -> int:
        cx = (block[0] + block[2]) / 2
        for idx, (c0, c1) in enumerate(columns):
            if c0 <= cx <= c1:
                return idx
        # 不在任何列中心区间内 → 取最近列
        return min(
            range(len(columns)),
            key=lambda i: abs((columns[i][0] + columns[i][1]) / 2 - cx),
        )

    ordered = sorted(text_blocks, key=lambda b: (_col_of(b), b[1], b[0]))
    return [b[4] for b in ordered]
