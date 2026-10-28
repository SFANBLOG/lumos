"""将已下载的《劳动合同法（2012修正）》政府公开 HTML 转为离线 RAG 语料。

示例：python scripts/import_labor_contract_law.py <source.html>
输出：app/rag/data/labor_contract_law_2012.json
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "app" / "rag" / "data" / "labor_contract_law_2012.json"
# 仅匹配 HTML 块转换后的行首正式条号；正文中的“本法第×条”不应拆段。
ARTICLE = re.compile(r"(?:^|\n)[　 ]*第([一二三四五六七八九十百零〇]+)条(?:　|\s)*(?:【[^】]+】)?(.*?)(?=\n[　 ]*第[一二三四五六七八九十百零〇]+条|$)", re.S)


def category_of(text: str) -> str:
    rules = [
        ("non_compete", ("竞业限制", "保密")), ("probation_salary", ("试用期", "工资")),
        ("probation_insurance", ("社会保险", "社保")), ("training_bond", ("培训", "服务期")),
        ("leave_rights", ("工作时间", "休息", "休假", "加班")), ("jurisdiction", ("仲裁", "争议")),
        ("resignation", ("解除", "终止", "裁员", "经济补偿", "辞职")),
        ("salary_deduction", ("劳动报酬", "工资", "违约金")), ("job_description", ("工作内容", "工作地点", "劳动合同")),
    ]
    return next((category for category, terms in rules if any(term in text for term in terms)), "general")


def main(source: Path) -> None:
    raw = source.read_text(encoding="utf-8", errors="ignore")
    plain = html.unescape(re.sub(r"<[^>]+>", "\n", raw)).replace("\xa0", " ")
    plain = re.sub(r"[ \t\r\f\v]+", "", plain)
    plain = re.sub(r"\n+", "\n", plain)
    start = plain.find("第一条")
    end = plain.find("第九十八条")
    if start < 0 or end < 0:
        raise RuntimeError("未找到第一条或第九十八条，请确认来源为劳动合同法全文")
    text = plain[start:]
    rows = []
    for number, content in ARTICLE.findall(text):
        content = re.sub(r"\s+", "", content).strip()
        if not content:
            continue
        article = f"第{number}条"
        category = category_of(content)
        rows.append({
            "law_name": "劳动合同法",
            "article": article,
            "content": content,
            "keywords": [article, category, "劳动合同法"],
            "category": category,
            "source": "政府公开文本：劳动合同法（2012修正）",
        })
    if len(rows) != 98:
        raise RuntimeError(f"解析结果应为98条，实际为{len(rows)}条；已停止写入")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {TARGET}，共 {len(rows)} 条。")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法：python scripts/import_labor_contract_law.py <source.html>")
    main(Path(sys.argv[1]))
