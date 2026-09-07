"""
Consultant Agent — 智能咨询子智能体.

以劳动者视角解答劳动法问题: 清洗问题 → RAG 检索法条 → (可选) 结合关联报告风险项
→ LLM 组织回答 (以 [n] 引用检索法条) → 生成追问建议。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger

from app.agent.base import BaseAgent
from app.mcp.client import MCPClient
from app.skills import get_skill

_SYSTEM_PROMPT = """你是 Lumos 的劳动法律顾问，站在劳动者（打工人）立场解答劳动法问题。
要求：
1. 用大白话说人话，先给结论再讲道理，分点表述，中文回复；
2. 若提供了法条素材，必须用 [1][2] 这样的编号标注引用到对应素材；
3. 素材中找不到直接依据时，要明说"未找到直接适用的法条"，并建议向当地劳动监察大队或工会求助，不要编造法条；
4. 涉及维权路径时给出可执行步骤（协商 → 劳动监察投诉 → 劳动仲裁），不要承诺结果；
5. 若提供了关联合同报告的上下文，结合其中的风险项作答。"""


class ConsultantAgent(BaseAgent):
    """智能咨询子智能体（不参与合同分析状态流）."""

    name = "consultant"
    description = "🤖 智能咨询 — 正在检索法条并组织回答…"
    system_prompt = _SYSTEM_PROMPT
    skills = ["followup_suggestion"]

    async def answer(
        self,
        question: str,
        *,
        contract_context: str | None = None,
        report_categories: list[str] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """多步咨询作答，逐步产出 step / final 事件 dict."""
        yield {"type": "step", "message": "正在理解你的问题…"}

        cleaned = question.strip()
        try:
            result = await get_skill("text_preprocessing").execute(text=cleaned)
            cleaned = (result.get("text") or cleaned).strip() or cleaned
        except Exception as e:  # 技能失败不影响主流程
            logger.debug(f"[consultant] 文本清洗失败: {e}")

        # 1. RAG 检索
        yield {"type": "step", "message": "正在检索《劳动合同法》《劳动法》等条文…"}
        laws: list[dict[str, Any]] = []
        try:
            res = await MCPClient().call("law_search", query=cleaned, top_k=4)
            seen: set[tuple[str, str]] = set()
            for match in res.get("results", []):
                key = (match.get("law_name", ""), match.get("article", ""))
                if key in seen or not key[0]:
                    continue
                seen.add(key)
                laws.append(
                    {
                        "law_name": match["law_name"],
                        "article": match["article"],
                        "content": match.get("content", ""),
                        "similarity": float(match.get("similarity", 0.0)),
                    }
                )
                if len(laws) >= 4:
                    break
            laws.sort(key=lambda r: r["similarity"], reverse=True)
        except Exception as e:
            logger.warning(f"[consultant] 法条检索失败: {e}")
            yield {"type": "step", "message": "⚠️ 法条库暂不可用，将尽力为你作答"}

        if laws:
            yield {
                "type": "step",
                "message": f"已检索到 {len(laws)} 条相关法条，正在核对依据…",
            }

        # 2. 组织 prompt
        material: list[str] = []
        for i, law in enumerate(laws, start=1):
            material.append(
                f"[{i}] {law['law_name']} {law['article']}\n{law['content']}"
            )
        prompt_parts = [f"问题：{cleaned}"]
        if material:
            prompt_parts.append("可引用的法条素材：\n" + "\n\n".join(material))
        if contract_context:
            prompt_parts.append("关联合同的风险报告摘要：\n" + contract_context)
            yield {"type": "step", "message": "已结合你关联报告中的风险项…"}
        prompt_parts.append(
            "请作答（引用素材时使用 [n] 编号标注；没有直接依据请如实说明）。"
        )

        # 3. LLM 作答
        yield {"type": "step", "message": "正在组织回答…"}
        content = await self.invoke_llm("\n\n".join(prompt_parts), temperature=0.3)
        if not content:
            content = "抱歉，本次没能生成有效回答，请换个问法再试一次。"

        # 4. 追问建议
        suggestions: list[str] = []
        try:
            sugg = await get_skill("followup_suggestion").execute(
                categories=report_categories
            )
            suggestions = sugg.get("suggestions", [])
        except Exception as e:
            logger.debug(f"[consultant] 追问建议生成失败: {e}")

        logger.info(f"[consultant] 回答完成 | 引用 {len(laws)} 条法条")
        yield {
            "type": "final",
            "content": content,
            "references": laws,
            "suggestions": suggestions,
        }
