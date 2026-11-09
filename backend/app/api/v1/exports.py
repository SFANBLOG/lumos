"""带批注审查报告导出 (Markdown / Word).

原项目只有前端 CSV / 纯文本导出, 无法把「原文 + 风险解读 + 建议改为」
一起带走在维权或送审场景使用。本模块在后端生成带批注报告:
- ``md``: 零依赖, 随时可用;
- ``docx``: 用已在依赖清单里的 python-docx 生成可编辑的 Word 文档。

导出内容包含合同要素核对表、缺失条款清单，以及每条风险的原句、
法条依据、条款级修改建议 (redline) 与谈判话术。
"""

from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from sqlmodel import select

from app.api.deps import AuthAny, DBSession
from app.models.analysis import AnalysisResult, RiskItem
from app.models.contract import Contract, ContractStatus
from app.models.review import ContractFactItem, MissingClauseItem

router = APIRouter(prefix="/contracts", tags=["📤 报告导出"])

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


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
    return contract, analysis, risks, facts, missing


def _level(value) -> str:
    return getattr(value, "value", str(value))


def _coverage(facts) -> int:
    required = [f for f in facts if f.required]
    if not required:
        return 100
    return round(100 * sum(1 for f in required if f.status == "present") / len(required))


def _markdown(contract_id: str, analysis, risks, facts, missing) -> str:
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
    for f in facts:
        mark = "✅ 已写明" if f.status == "present" else "❌ 缺失"
        value = (f.value or "—").replace("|", "\\|")
        evidence = (f.evidence or "—").replace("|", "\\|")[:60]
        lines.append(f"| {f.label} | {mark} | {value} | {evidence} | {f.confidence:.2f} |")

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
            f"- **沟通话术**：{risk.negotiation_tip or '—'}",
            "",
        ]
    lines += [
        "---",
        "",
        "本报告由 AI 辅助生成，仅供风险排查参考，不构成具有法定效力的专业法律意见。",
        "",
    ]
    return "\n".join(lines)


def _docx_bytes(contract_id: str, analysis, risks, facts, missing) -> bytes:
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
        cells[1].text = "已写明" if f.status == "present" else "缺失"
        cells[2].text = f.value or "—"
        cells[3].text = (f.evidence or "—")[:80]

    doc.add_heading("二、缺失条款与建议补充措辞", level=1)
    if not missing:
        doc.add_paragraph("未检出必备条款缺失。")
    for item in missing:
        doc.add_heading(f"{item.label}（{item.level}）", level=2)
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
        doc.add_paragraph(f"沟通话术：{risk.negotiation_tip or '—'}")

    doc.add_paragraph(
        "本报告由 AI 辅助生成，仅供风险排查参考，不构成具有法定效力的专业法律意见。"
    )
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@router.get(
    "/{contract_id}/report/export",
    summary="导出带批注审查报告",
    description="format=md (默认) 或 docx; 返回带原文、法条、redline 与话术的可下载文件。",
)
async def export_report(
    contract_id: str,
    session: DBSession,
    _auth: AuthAny,
    fmt: str = Query(default="md", alias="format"),
):
    contract, analysis, risks, facts, missing = await _load(session, contract_id)
    short_id = contract_id[:8]

    if fmt == "docx":
        content = _docx_bytes(contract_id, analysis, risks, facts, missing)
        mime = _DOCX_MIME
        filename = f"lumos-report-{short_id}.docx"
    elif fmt == "md":
        content = _markdown(contract_id, analysis, risks, facts, missing).encode("utf-8")
        mime = "text/markdown; charset=utf-8"
        filename = f"lumos-report-{short_id}.md"
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "不支持的导出格式, 仅支持 md / docx",
        )

    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
