"""带批注审查报告导出 (Markdown / Word / PDF).

原项目只有前端 CSV / 纯文本导出, 无法把「原文 + 风险解读 + 建议改为」
一起带走在维权或送审场景使用。本模块在后端生成带批注报告:
- ``md``: 零依赖, 随时可用;
- ``docx``: 用 python-docx 生成可编辑的 Word 文档;
- ``pdf``: 用 reportlab 内置 CJK 字体生成可直接发送的 PDF (无需外部字体文件)。

导出内容包含合同要素核对表、缺失条款清单、每条风险的原句/法条依据/
逐条改写 (含理由、来源、diff、置信度) 与谈判话术，以及分享链接上的在线批注。
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from sqlmodel import select

from app.api.deps import AuthAny, DBSession
from app.models.analysis import AnalysisResult, RiskItem
from app.models.contract import Contract, ContractStatus
from app.models.review import ContractFactItem, MissingClauseItem, ReportAnnotation

router = APIRouter(prefix="/contracts", tags=["📤 报告导出"])

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_PDF_MIME = "application/pdf"


def _attr(obj, name: str, default=""):
    """兼容 ORM 行与测试里的 SimpleNamespace (老数据可能没有新列)."""
    return getattr(obj, name, default) or default


async def _load(session, contract_id: str):
    contract = await session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"合同 {contract_id} 不存在")
    if contract.status != ContractStatus.COMPLETED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"合同尚未分析完成, 当前状态: {contract.status.value}",
        )
    analysis = (
        await session.execute(
            select(AnalysisResult).where(AnalysisResult.contract_id == contract_id)
        )
    ).scalar_one_or_none()
    if not analysis:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分析结果不存在")

    risks = list(
        (
            await session.execute(
                select(RiskItem)
                .where(RiskItem.analysis_id == analysis.id)
                .order_by(RiskItem.order)
            )
        ).scalars().all()
    )
    facts = list(
        (
            await session.execute(
                select(ContractFactItem)
                .where(ContractFactItem.analysis_id == analysis.id)
                .order_by(ContractFactItem.order)
            )
        ).scalars().all()
    )
    missing = list(
        (
            await session.execute(
                select(MissingClauseItem)
                .where(MissingClauseItem.analysis_id == analysis.id)
                .order_by(MissingClauseItem.order)
            )
        ).scalars().all()
    )
    annotations = list(
        (
            await session.execute(
                select(ReportAnnotation)
                .where(ReportAnnotation.contract_id == contract_id)
                .order_by(ReportAnnotation.created_at)
            )
        ).scalars().all()
    )
    return contract, analysis, risks, facts, missing, annotations


def _level(value) -> str:
    return getattr(value, "value", str(value))


def _coverage(facts) -> int:
    required = [f for f in facts if f.required]
    if not required:
        return 100
    return round(100 * sum(1 for f in required if f.status == "present") / len(required))


def _annotation_lines(annotations) -> list[str]:
    rows = list(annotations or [])
    if not rows:
        return []
    lines = ["", "## 四、在线批注", ""]
    for item in rows:
        lines.append(f"- **{_attr(item, 'author', '匿名')}**：{_attr(item, 'comment')}")
        quote = _attr(item, "quote")
        if quote:
            lines.append(f"  - 引用原文：{quote}")
    lines.append("")
    return lines


def _markdown(contract_id: str, analysis, risks, facts, missing, annotations=None) -> str:
    lines = [
        "# 劳动合同风险审查报告",
        "",
        f"- 合同 ID：`{contract_id}`",
        f"- 合同安全总评分：**{analysis.overall_score}/100**（{_level(analysis.overall_level)}）",
        f"- 必备条款覆盖率：**{_coverage(facts)}%**",
        f"- 分析时间：{analysis.created_at.isoformat()}",
        "",
        f"> {analysis.summary}",
        "",
        "## 一、合同要素核对表",
        "",
        "| 要素 | 状态 | 抽取值 | 原文依据 | 置信度 |",
        "|---|---|---|---|---|",
    ]
    status_map = {
        "present": "✅ 已写明",
        "missing": "❌ 缺失",
        "contradicted": "⚠️ 反向约定",
    }
    for f in facts:
        mark = status_map.get(f.status, "❓ 待确认")
        value = (f.value or "—").replace("|", "\\|")
        evidence = (f.evidence or "—").replace("|", "\\|")[:60]
        lines.append(f"| {f.label} | {mark} | {value} | {evidence} | {f.confidence:.2f} |")
        if _attr(f, "contradiction"):
            lines.append(f"| ↳ 冲突原文 | | {_attr(f, 'contradiction')[:60]} | | |")

    lines += ["", "## 二、缺失条款与建议补充措辞", ""]
    if not missing:
        lines.append("未检出必备条款缺失。")
    for item in missing:
        lines += [
            f"### {item.label}（{_level(item.level)}）",
            "",
            f"- 风险：{item.reason}",
            f"- 依据：{item.legal_basis}",
            f"- **建议补充**：{item.suggested_text}",
            "",
        ]

    lines += ["", "## 三、逐条风险与条款级修改建议", ""]
    if not risks:
        lines.append("未检出条款级风险。")
    for idx, risk in enumerate(risks, 1):
        lines += [
            f"### {idx}. {risk.title}（{_level(risk.level)}，{risk.score}/100）",
            "",
            f"- **原合同条款**：{risk.original_clause or '—'}",
            f"- **风险解读**：{risk.explanation}",
            f"- **法律依据**：{risk.legal_basis or '—'}",
            f"- **建议改为**：{risk.suggested_revision or '—'}",
            f"- **改写理由**：{_attr(risk, 'revision_reason') or '—'}",
            (
                f"- **改写来源**：{_attr(risk, 'revision_method') or '—'}"
                f" ｜ 置信度 {_attr(risk, 'revision_confidence', 0.0)}"
            ),
            f"- **沟通话术**：{risk.negotiation_tip or '—'}",
            "",
        ]
        diff = _attr(risk, "revision_diff")
        if diff:
            lines += ["<details><summary>原条款 → 建议条款 diff</summary>", "", "```diff", diff, "```", "", "</details>", ""]
    lines += _annotation_lines(annotations)
    lines += [
        "---",
        "",
        "本报告由 AI 辅助生成，仅供风险排查参考，不构成具有法定效力的专业法律意见。",
        "",
    ]
    return "\n".join(lines)


def _docx_bytes(contract_id: str, analysis, risks, facts, missing, annotations=None) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("劳动合同风险审查报告", 0)
    doc.add_paragraph(f"合同 ID：{contract_id}")
    doc.add_paragraph(
        f"合同安全总评分：{analysis.overall_score}/100（{_level(analysis.overall_level)}）"
    )
    doc.add_paragraph(f"必备条款覆盖率：{_coverage(facts)}%")
    doc.add_paragraph(f"分析时间：{analysis.created_at.isoformat()}")
    doc.add_paragraph(analysis.summary)

    doc.add_heading("一、合同要素核对表", level=1)
    fact_table = doc.add_table(rows=1, cols=4)
    fact_table.style = "Light Grid Accent 1"
    for cell, text in zip(fact_table.rows[0].cells, ["要素", "状态", "抽取值", "原文依据"]):
        cell.text = text
    for f in facts:
        cells = fact_table.add_row().cells
        cells[0].text = f.label
        cells[1].text = "已写明" if f.status == "present" else ("反向约定" if f.status == "contradicted" else "缺失")
        cells[2].text = f.value or "—"
        cells[3].text = (f.evidence or "—")[:80]

    doc.add_heading("二、缺失条款与建议补充措辞", level=1)
    if not missing:
        doc.add_paragraph("未检出必备条款缺失。")
    for item in missing:
        doc.add_heading(f"{item.label}（{_level(item.level)}）", level=2)
        doc.add_paragraph(f"风险：{item.reason}")
        doc.add_paragraph(f"依据：{item.legal_basis}")
        doc.add_paragraph(f"建议补充：{item.suggested_text}")

    doc.add_heading("三、逐条风险与条款级修改建议", level=1)
    if not risks:
        doc.add_paragraph("未检出条款级风险。")
    for idx, risk in enumerate(risks, 1):
        doc.add_heading(f"{idx}. {risk.title}（{_level(risk.level)}）", level=2)
        doc.add_paragraph(f"原合同条款：{risk.original_clause or '—'}")
        doc.add_paragraph(f"风险解读：{risk.explanation}")
        doc.add_paragraph(f"法律依据：{risk.legal_basis or '—'}")
        doc.add_paragraph(f"建议改为：{risk.suggested_revision or '—'}")
        doc.add_paragraph(f"改写理由：{_attr(risk, 'revision_reason') or '—'}")
        doc.add_paragraph(
            f"改写来源：{_attr(risk, 'revision_method') or '—'}"
            f"｜置信度 {_attr(risk, 'revision_confidence', 0.0)}"
        )
        doc.add_paragraph(f"沟通话术：{risk.negotiation_tip or '—'}")
        diff = _attr(risk, "revision_diff")
        if diff:
            doc.add_paragraph("原条款 → 建议条款 diff：")
            doc.add_paragraph(diff)

    rows = list(annotations or [])
    if rows:
        doc.add_heading("四、在线批注", level=1)
        for item in rows:
            doc.add_paragraph(f"{_attr(item, 'author', '匿名')}：{_attr(item, 'comment')}")
            if _attr(item, "quote"):
                doc.add_paragraph(f"引用原文：{_attr(item, 'quote')}")

    doc.add_paragraph(
        "本报告由 AI 辅助生成，仅供风险排查参考，不构成具有法定效力的专业法律意见。"
    )
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _pdf_bytes(contract_id: str, analysis, risks, facts, missing, annotations=None) -> bytes:
    """用 reportlab 内置 STSong-Light CJK 字体生成中文 PDF (无外部字体依赖)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    font = "STSong-Light"
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("cjk-title", parent=base["Title"], fontName=font, fontSize=18, leading=24),
        "h1": ParagraphStyle("cjk-h1", parent=base["Heading1"], fontName=font, fontSize=13, leading=18, spaceBefore=10),
        "h2": ParagraphStyle("cjk-h2", parent=base["Heading2"], fontName=font, fontSize=11, leading=16, spaceBefore=6),
        "body": ParagraphStyle("cjk-body", parent=base["BodyText"], fontName=font, fontSize=9, leading=14),
        "cell": ParagraphStyle("cjk-cell", parent=base["BodyText"], fontName=font, fontSize=8, leading=11),
    }

    def p(text, style="body"):
        return Paragraph(xml_escape(str(text if text is not None else "")), styles[style])

    story = [
        p("劳动合同风险审查报告", "title"),
        p(f"合同 ID：{contract_id}"),
        p(f"合同安全总评分：{analysis.overall_score}/100（{_level(analysis.overall_level)}）"),
        p(f"必备条款覆盖率：{_coverage(facts)}%"),
        p(f"分析时间：{analysis.created_at.isoformat()}"),
        p(analysis.summary),
        Spacer(1, 4 * mm),
        p("一、合同要素核对表", "h1"),
    ]
    table_data = [[p(x, "cell") for x in ("要素", "状态", "抽取值", "原文依据")]]
    for f in facts:
        table_data.append(
            [
                p(f.label, "cell"),
                p("已写明" if f.status == "present" else ("反向约定" if f.status == "contradicted" else "缺失"), "cell"),
                p(f.value or "—", "cell"),
                p((f.evidence or "—")[:60], "cell"),
            ]
        )
    table = Table(table_data, colWidths=[35 * mm, 22 * mm, 50 * mm, 65 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story += [table, Spacer(1, 4 * mm), p("二、缺失条款与建议补充措辞", "h1")]
    if not missing:
        story.append(p("未检出必备条款缺失。"))
    for item in missing:
        story += [
            p(f"{item.label}（{_level(item.level)}）", "h2"),
            p(f"风险：{item.reason}"),
            p(f"依据：{item.legal_basis}"),
            p(f"建议补充：{item.suggested_text}"),
        ]

    story.append(p("三、逐条风险与条款级修改建议", "h1"))
    if not risks:
        story.append(p("未检出条款级风险。"))
    for idx, risk in enumerate(risks, 1):
        story += [
            p(f"{idx}. {risk.title}（{_level(risk.level)}，{risk.score}/100）", "h2"),
            p(f"原合同条款：{risk.original_clause or '—'}"),
            p(f"风险解读：{risk.explanation}"),
            p(f"法律依据：{risk.legal_basis or '—'}"),
            p(f"建议改为：{risk.suggested_revision or '—'}"),
            p(f"改写理由：{_attr(risk, 'revision_reason') or '—'}"),
            p(
                f"改写来源：{_attr(risk, 'revision_method') or '—'}"
                f"｜置信度 {_attr(risk, 'revision_confidence', 0.0)}"
            ),
            p(f"沟通话术：{risk.negotiation_tip or '—'}"),
        ]
        diff = _attr(risk, "revision_diff")
        if diff:
            story.append(p("原条款 → 建议条款 diff："))
            story.append(p(diff.replace("\n", "<br/>")))

    rows = list(annotations or [])
    if rows:
        story.append(p("四、在线批注", "h1"))
        for item in rows:
            story.append(p(f"{_attr(item, 'author', '匿名')}：{_attr(item, 'comment')}"))
            if _attr(item, "quote"):
                story.append(p(f"引用原文：{_attr(item, 'quote')}"))

    story += [
        Spacer(1, 6 * mm),
        p("本报告由 AI 辅助生成，仅供风险排查参考，不构成具有法定效力的专业法律意见。"),
    ]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Lumos 合同审查报告 {contract_id[:8]}",
    )
    doc.build(story)
    return buffer.getvalue()


def render_export(fmt: str, contract_id: str, analysis, risks, facts, missing, annotations=None):
    """统一的导出渲染入口, 供登录态导出与分享链接导出共用."""
    short_id = contract_id[:8]
    if fmt == "docx":
        return (
            _docx_bytes(contract_id, analysis, risks, facts, missing, annotations),
            _DOCX_MIME,
            f"lumos-report-{short_id}.docx",
        )
    if fmt == "pdf":
        return (
            _pdf_bytes(contract_id, analysis, risks, facts, missing, annotations),
            _PDF_MIME,
            f"lumos-report-{short_id}.pdf",
        )
    if fmt == "md":
        return (
            _markdown(contract_id, analysis, risks, facts, missing, annotations).encode("utf-8"),
            "text/markdown; charset=utf-8",
            f"lumos-report-{short_id}.md",
        )
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "不支持的导出格式, 仅支持 md / docx / pdf",
    )


@router.get(
    "/{contract_id}/report/export",
    summary="导出带批注审查报告",
    description="format=md (默认) / docx / pdf; 返回带原文、法条、逐条改写与在线批注的可下载文件。",
)
async def export_report(
    contract_id: str,
    session: DBSession,
    _auth: AuthAny,
    fmt: str = Query(default="md", alias="format"),
):
    _contract, analysis, risks, facts, missing, annotations = await _load(session, contract_id)
    content, mime, filename = render_export(
        fmt, contract_id, analysis, risks, facts, missing, annotations
    )
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
