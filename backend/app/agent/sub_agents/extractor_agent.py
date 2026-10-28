"""
Extractor Agent — 文本抽取子智能体.

负责 OCR 文本纠错、结构化条款提取、初步风险分类。
"""

from __future__ import annotations

import json

from loguru import logger

from app.agent.base import BaseAgent
from app.agent.state import AgentState, ExtractedClause
from app.models.analysis import RiskCategory
from app.skills import get_skill

EXTRACTOR_SYSTEM_PROMPT = """\
你是一位专业的劳动合同分析助手。你的任务是将 OCR 识别出的劳动合同原始文本进行结构化处理。

## 你需要完成以下工作:

1. **纠错**: OCR 识别可能存在错别字、错误标点、段落断裂等问题，请修正这些错误。
2. **结构化提取**: 将合同文本拆分为独立的条款，每条包含标题和内容。
3. **初步分类**: 判断每条条款是否涉及以下 10 类风险，如果涉及请标注分类:
   - non_compete: 竞业禁止/竞业限制
   - probation_salary: 试用期薪资
   - probation_insurance: 试用期社保
   - salary_deduction: 扣薪/罚款条款
   - job_description: 岗位职责/工作内容
   - obedience_clause: 服从安排/无条件调岗
   - resignation: 离职/辞职条件
   - leave_rights: 休假/年假/病假
   - jurisdiction: 争议管辖/仲裁地
   - training_bond: 培训服务期/违约金

## 输出格式要求:
请严格以 JSON 数组的形式输出，每个元素包含:
- clause_index: 条款序号 (从 1 开始, 整数)
- title: 条款标题 (字符串)
- content: 条款完整内容 (已纠错, 字符串)
- category: 风险分类 (如果不涉及上述分类，设为 null)

只输出合法的 JSON 数组，不要添加 markdown 代码块标记或任何额外说明。
"""


class ExtractorAgent(BaseAgent):
    """文本抽取子智能体."""

    name = "extractor"
    description = "📝 结构化抽取 — 正在整理合同条款…"
    system_prompt = EXTRACTOR_SYSTEM_PROMPT
    skills = ["text_preprocessing"]

    async def run(self, state: AgentState) -> AgentState:
        preprocess = get_skill("text_preprocessing")
        cleaned = await preprocess.execute(text=state.raw_text)
        raw = cleaned["text"]

        try:
            content = await self.invoke_llm(
                f"请对以下劳动合同文本进行结构化提取:\n\n{raw}"
            )

            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()

            parsed = json.loads(content)

            clauses: list[ExtractedClause] = []
            for item in parsed:
                category = None
                if item.get("category"):
                    try:
                        category = RiskCategory(item["category"])
                    except ValueError:
                        logger.warning(f"  ⚠️ 未知分类: {item['category']}")
                clauses.append(
                    ExtractedClause(
                        clause_index=item["clause_index"],
                        title=item["title"],
                        content=item["content"],
                        category=category,
                    )
                )

            state.corrected_text = raw
            state.extracted_clauses = clauses
            logger.info(f"  提取完成 | 共 {len(clauses)} 条条款")

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"  LLM 提取失败: {e}，降级为段落分割")
            paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
            state.corrected_text = raw
            state.extracted_clauses = [
                ExtractedClause(
                    clause_index=i,
                    title=p.split("\n", 1)[0][:50],
                    content=p,
                    category=None,
                )
                for i, p in enumerate(paragraphs, 1)
            ]

        return state
