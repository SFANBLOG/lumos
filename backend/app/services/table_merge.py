"""
PDF 跨页表格检测与合并 (后处理, 不依赖额外模型).

背景: PDF 抽取是**逐页独立**的 (有文字层直取文字, 无文字层渲染位图走 OCR),
一张跨页表格会被切成「第 N 页尾部半张 + 第 N+1 页头部半张」, 且第 N+1 页
通常还会**重复一遍表头**。直接按页拼接会造成: 同一张表出现两个表头、列错位、
数据行语义断裂, 下游 Agent 读到的是两张"半张表"。

本模块在逐页文本之上做纯文本后处理, 分四步:

1. **行切分** ``split_row``: 把一行规范成单元格列表, 兼容三种列分隔形态——
   现有抽取链路的 `` | `` 约定、PDF 文字层/OCR 的连续空格对齐、制表符;
2. **块检测** ``TableBlock`` / ``_page_items``: 连续的"表格行"聚成一个块,
   要求 >=2 行且列数多数一致 (>=60% 行共享众数列数), 避免把正文误判成表;
3. **跨页判定** ``evaluate_merge``: 仅当 prev 块是第 N 页**最后一个**表、
   next 块是第 N+1 页**第一个**表时才评估, 依据四类信号加权打分——
   表头重复 / 列数一致性 / 上页末行截断 / 表题连续, 超过阈值才合并;
4. **合并** ``merge_cross_page_tables``: 去掉重复表头、按最大列数补齐
   (不丢数据), 支持 3 页及以上链式合并; 合并行挂在**前页**块上, 后页
   对应块标记为已消费, 输出时跳过, 保证拼接后文本仍连续。

已知边界 (诚实说明):
- 扫描版 PDF 的输入是 OCR **纯文本**, 没有字框坐标, 因此判定是启发式的
  (列数 + 表头相似 + 截断 + 表题), 不是几何级别的; 极端情况下两张列数相同、
  表头相同、表题都缺失的独立表可能被误合并——此时应调 ``merge_threshold``
  或关闭 ``pdf_cross_page_table_merge``;
- 若要做几何级判定, 需在 OCR 侧引入 TSV 字框 (pytesseract ``image_to_data``)
  或版面分析模型, 属于后续增强, 本模块不预支。

**版面几何信号 (信号 4, 可选)**: 若调用方传入了 ``layouts`` (见
``app/services/table_layout.py``), 会额外启用**版面 y 坐标连续性**判定——
上一页表格是否贴页尾、下一页表格是否贴页首、左右边界是否对齐。该信号
只在几何可用时叠加, 拿不到几何就自动退回四类纯文本信号, 不会让功能退化。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from loguru import logger

from app.services.table_layout import TableRegion, x_aligned

__all__ = [
    "TableBlock",
    "split_row",
    "evaluate_merge",
    "merge_cross_page_tables",
    "DEFAULT_MERGE_THRESHOLD",
]

#: 行内单元格分隔符 (与 DOCX/XLSX/PPTX 抽取链路的既有约定一致)
_CELL_SEP = "|"

#: 认定为表格的最小列数 / 最小行数
_MIN_COLS = 2
_MIN_ROWS = 2

#: 块内列数一致性下限: 共享众数列数的行占比需达到该值, 否则视为"伪表格"
_MIN_CONSISTENCY = 0.6

#: 默认合并阈值 (信号加权分)
DEFAULT_MERGE_THRESHOLD = 0.55

# 连续 2+ 空白或制表符视为列分隔 (PDF 文字层 / OCR 的常见对齐形态)
_WS_RUN = re.compile(r"[ \t　]{2,}|\t+")


# ── 数据结构 ───────────────────────────────────────────────────


@dataclass
class TableBlock:
    """一个表格块: 连续若干表格行 + 归属页码 + 紧邻上方的表题."""

    page: int
    rows: list[list[str]]
    title: str = ""
    #: 可选的版面几何 (贴页边 / 左右边界), 由 table_layout 提供; 无则 None
    region: TableRegion | None = None
    #: 该块已被并入更前面页的哪个块 (None 表示独立/根块)
    merged_into: "TableBlock | None" = None
    #: 合并后实际跨占的页码 (含自身), 仅根块有意义
    pages: list[int] = field(default_factory=list)

    @property
    def n_cols(self) -> int:
        """众数列数 (表格的"应有"列数)."""
        if not self.rows:
            return 0
        return Counter(len(r) for r in self.rows).most_common(1)[0][0]

    @property
    def is_truncated(self) -> bool:
        """末行非空单元格数少于众数列数 → 疑似在页尾被截断."""
        if not self.rows or self.n_cols == 0:
            return False
        return sum(1 for c in self.rows[-1] if c) < self.n_cols


# ── 步骤 1: 行 → 单元格 ────────────────────────────────────────


def split_row(line: str) -> list[str]:
    """把一行文本规范成单元格列表; 非表格行 (不足 2 列) 返回空列表.

    优先级: ``|`` 分隔 > 连续空白/制表符分隔。单一文本行 (如普通正文)
    只有 1 个单元格, 返回 ``[]`` —— 这是"正文不算表格行"的判据。
    """
    stripped = line.strip()
    if not stripped:
        return []

    if _CELL_SEP in stripped:
        raw = stripped.split(_CELL_SEP)
    else:
        raw = _WS_RUN.split(stripped)

    cells = [c.strip() for c in raw if c.strip()]
    return cells if len(cells) >= _MIN_COLS else []


def _is_table(rows: list[list[str]]) -> bool:
    """行组是否构成一张表: 行数达标且列数足够一致."""
    if len(rows) < _MIN_ROWS:
        return False
    counts = [len(r) for r in rows]
    modal = Counter(counts).most_common(1)[0][0]
    if modal < _MIN_COLS:
        return False
    consistent = sum(1 for c in counts if c == modal) / len(counts)
    return consistent >= _MIN_CONSISTENCY


# ── 步骤 2: 页 → 条目序列 ──────────────────────────────────────

#: 条目类型: ("text", 原始行) | ("table", TableBlock)
_Item = tuple[str, object]


def _page_items(text: str, page: int) -> list[_Item]:
    """把一页文本拆成有序条目: 非表格行原样保留, 连续表格行聚成块."""
    lines = text.split("\n")
    items: list[_Item] = []
    i, n = 0, len(lines)

    while i < n:
        if not split_row(lines[i]):
            items.append(("text", lines[i]))
            i += 1
            continue

        # 收集连续表格行
        j = i
        rows: list[list[str]] = []
        while j < n:
            cells = split_row(lines[j])
            if not cells:
                break
            rows.append(cells)
            j += 1

        if _is_table(rows):
            # 表题: 向前找最近的非空且非表格行
            title = ""
            k = i - 1
            while k >= 0 and not lines[k].strip():
                k -= 1
            if k >= 0 and not split_row(lines[k]):
                title = lines[k].strip()
            items.append(("table", TableBlock(page=page, rows=rows, title=title,
                                              pages=[page])))
        else:
            # 列数太散, 判为伪表格 → 原样输出, 不当表处理
            items.extend(("text", ln) for ln in lines[i:j])
        i = j

    return items


# ── 步骤 3: 跨页合并判定 ───────────────────────────────────────


def _norm(cells: list[str]) -> set[str]:
    """单元格归一化: 去空白, 用于集合相似度."""
    return {re.sub(r"\s+", "", c) for c in cells if c.strip()}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _text_sim(a: str, b: str) -> float:
    """整句相似度 (字符级), 用于表题比对."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def evaluate_merge(prev: TableBlock, nxt: TableBlock) -> tuple[float, bool, list[str]]:
    """评估 prev (第 N 页表) 与 nxt (第 N+1 页表) 是否应合并.

    Returns:
        (加权分, 是否检出重复表头, 命中信号说明)
    """
    score = 0.0
    reasons: list[str] = []

    # 信号 1: 表头重复 —— 跨页表最强的正向信号
    header_sim = _jaccard(_norm(prev.rows[0]), _norm(nxt.rows[0]))
    header_repeat = header_sim >= 0.6
    if header_repeat:
        score += 0.5
        reasons.append(f"表头重复(相似度{header_sim:.2f})")

    # 信号 2: 列数一致性
    pc, nc = prev.n_cols, nxt.n_cols
    if pc == nc:
        score += 0.25
        reasons.append(f"列数一致({pc})")
    elif abs(pc - nc) <= 1:
        score += 0.05
        reasons.append(f"列数接近({pc}→{nc})")
    else:
        score -= 0.35
        reasons.append(f"列数差异大({pc}→{nc})")

    # 信号 3: 上一页末行被截断 (列没填满)
    if prev.is_truncated:
        score += 0.3
        reasons.append(f"上页末行仅填满{sum(1 for c in prev.rows[-1] if c)}/{pc}列")

    # 信号 4: 版面 y 坐标连续性 (仅当两侧都拿到了表格区域几何时才参与)
    rp, rn = prev.region, nxt.region
    if rp is not None and rn is not None:
        if rp.touches_bottom and rn.touches_top:
            # 上页表顶到页尾 + 下页表从页首开始 → 跨页续表最直观的证据
            score += 0.2
            reasons.append("版面连续(上页贴页尾/下页贴页首)")
            if x_aligned(rp, rn):
                score += 0.15
                reasons.append("左右边界对齐")
        elif rp.page_height > 0 and rn.page_height > 0 and (
            rp.y1 < rp.page_height * 0.7 and rn.y0 > rn.page_height * 0.2
        ):
            # 两表都明显远离页边 (留了页边距) → 版面不连续, 更可能是各自完整的表。
            # 注意: 只在"明显"远离时才扣分——真实跨页表常带页边距, 不能仅因
            # 没贴到最边缘就误判。
            score -= 0.2
            reasons.append("版面明显不连续(两表均远离页边)")

    # 信号 5: 表题连续性 (两侧都有表题时才作为证据)
    if prev.title and nxt.title:
        if _text_sim(prev.title, nxt.title) >= 0.6:
            score += 0.15
            reasons.append("表题一致")
        else:
            # 两侧表题明显不同 → 更可能是两张独立表 (即使表头碰巧相同)
            score -= 0.25
            reasons.append("表题不一致")

    return score, header_repeat, reasons


# ── 步骤 4: 合并执行 ───────────────────────────────────────────


def _root(block: TableBlock) -> TableBlock:
    """沿 merged_into 链找到根块 (链式合并时目标始终是根)."""
    seen: set[int] = set()
    while block.merged_into is not None and id(block) not in seen:
        seen.add(id(block))
        block = block.merged_into
    return block


def _has_text_after(items: list[_Item], idx: int) -> bool:
    """idx 之后是否还有非空正文行 (有 → 表格不在页尾, 不太可能被截断)."""
    return any(kind == "text" and str(obj).strip() for kind, obj in items[idx + 1:])


def _has_text_before(items: list[_Item], idx: int) -> bool:
    """idx 之前是否还有非空正文行 (有 → 表格不在页首, 更可能是新表)."""
    return any(kind == "text" and str(obj).strip() for kind, obj in items[:idx])


def _align(rows: list[list[str]], n_cols: int) -> list[list[str]]:
    """把行组补齐/对齐到 n_cols 列 (只补空列, 不截断, 避免丢数据)."""
    return [list(r) + [""] * (n_cols - len(r)) if len(r) < n_cols else list(r)
            for r in rows]


def _attach_regions(
    items_per_page: list[list[_Item]],
    layouts: dict[int, list[TableRegion]] | None,
) -> None:
    """按阅读顺序把版面几何区域挂到表格块上 (第 k 个区域 ↔ 第 k 个块).

    区域与块都按从上到下的顺序排列, 因此同序配对是合理近似; 数量不等时
    多出来的块不带几何, 自动退回纯文本判定, 不影响正确性。
    """
    if not layouts:
        return
    for pi, items in enumerate(items_per_page):
        regions = layouts.get(pi)
        if not regions:
            continue
        blocks = [obj for kind, obj in items
                  if kind == "table" and isinstance(obj, TableBlock)]
        for blk, region in zip(blocks, regions):
            blk.region = region


def merge_cross_page_tables(
    page_texts: list[str],
    threshold: float = DEFAULT_MERGE_THRESHOLD,
    layouts: dict[int, list[TableRegion]] | None = None,
) -> list[str]:
    """对逐页文本做跨页表格合并, 返回与输入等长的页文本列表.

    Args:
        page_texts: 逐页文本 (与 PDF 页一一对应).
        threshold: 合并判定阈值, 调高更保守 (少合并), 调低更激进.
        layouts: 可选的版面几何 ``{页索引: [TableRegion]}``, 由
            ``table_layout.extract_pdf_layout`` 提供。传入后启用"版面 y 坐标
            连续性"信号; 不传则完全退回纯文本判定 (与旧行为一致)。

    Note:
        无表格或页数 < 2 时原样返回, 输出与非表格 PDF 完全一致 (回归安全)。
    """
    if len(page_texts) < 2:
        return list(page_texts)

    items_per_page = [_page_items(t, i) for i, t in enumerate(page_texts)]
    _attach_regions(items_per_page, layouts)

    def _table_ids(pi: int) -> list[int]:
        return [k for k, (kind, _) in enumerate(items_per_page[pi]) if kind == "table"]

    merged_count = 0
    for pi in range(len(items_per_page) - 1):
        prev_ids = _table_ids(pi)
        next_ids = _table_ids(pi + 1)
        if not prev_ids or not next_ids:
            continue

        prev_blk = items_per_page[pi][prev_ids[-1]][1]
        nxt_blk = items_per_page[pi + 1][next_ids[0]][1]
        assert isinstance(prev_blk, TableBlock) and isinstance(nxt_blk, TableBlock)

        # 位置守卫: 只有"上页表格贴页尾、下页表格贴页首"才可能是同一张跨页表。
        # 上页表格后还有正文 → 该表大概率已完整; 下页表格前还有正文 → 更可能是新表。
        if _has_text_after(items_per_page[pi], prev_ids[-1]):
            continue
        if _has_text_before(items_per_page[pi + 1], next_ids[0]):
            continue

        score, header_repeat, reasons = evaluate_merge(prev_blk, nxt_blk)
        if score < threshold:
            continue

        root = _root(prev_blk)
        rows = list(nxt_blk.rows)
        if header_repeat and rows:
            rows = rows[1:]  # 丢掉被重复的表头行

        n_cols = max([len(r) for r in root.rows] + [len(r) for r in rows] + [_MIN_COLS])
        root.rows = _align(root.rows, n_cols)
        root.rows.extend(_align(rows, n_cols))
        root.pages.append(nxt_blk.page)
        nxt_blk.merged_into = root
        merged_count += 1
        reason_text = "; ".join(reasons)
        logger.info(
            f"🔗 跨页表格合并 | 第{root.page + 1}页 ↔ 第{nxt_blk.page + 1}页 | 信号: {reason_text} | 合并后 {len(root.rows)} 行"
        )

    out: list[str] = []
    for pi in range(len(items_per_page)):
        lines: list[str] = []
        for kind, obj in items_per_page[pi]:
            if kind == "text":
                lines.append(str(obj))
            elif isinstance(obj, TableBlock) and obj.merged_into is None:
                lines.extend(" | ".join(r) for r in obj.rows)
            # merged_into 非空的块已被并入前页, 输出时跳过
        out.append("\n".join(lines))

    if merged_count:
        logger.info(f"✅ 跨页表格合并完成 | 共合并 {merged_count} 处")
    return out
