"""
Retriever Agent — 法规检索子智能体.

对每条合同条款进行 RAG 语义检索，查找最相关的劳动法条文。
"""

from __future__ import annotations

from loguru import logger

from app.agent.base import BaseAgent
from app.agent.state import AgentState, LegalReference
from app.mcp.client import MCPClient


class RetrieverAgent(BaseAgent):
    """法规检索子智能体，通过 MCP 调用法律检索工具."""

    name = "retriever"
    description = "⚖️ 法规检索 — 正在查询相关劳动法条文…"
    system_prompt = ""
    skills = ["legal_analysis"]

    async def run(self, state: AgentState) -> AgentState:
        mcp = MCPClient()
        all_refs: list[LegalReference] = []
        seen: set[str] = set()

        for clause in state.extracted_clauses:
            query = f"{clause.title} {clause.content[:200]}"
            category = clause.category.value if clause.category else None

            result = await mcp.call(
                "law_search",
                query=query,
                top_k=3,
                category=category,
            )

            for match in result.get("results", []):
                key = f"{match['law_name']}_{match['article']}"
                if key in seen:
                    continue
                seen.add(key)
                all_refs.append(
                    LegalReference(
                        law_name=match["law_name"],
                        article=match["article"],
                        content=match["content"],
                        relevance_score=match["similarity"],
                    )
                )

            if len(result.get("results", [])) < 2 and category:
                fallback = await mcp.call("law_search", query=query, top_k=3)
                for match in fallback.get("results", []):
                    key = f"{match['law_name']}_{match['article']}"
                    if key not in seen:
                        seen.add(key)
                        all_refs.append(
                            LegalReference(
                                law_name=match["law_name"],
                                article=match["article"],
                                content=match["content"],
                                relevance_score=match["similarity"],
                            )
                        )

        all_refs.sort(key=lambda r: r.relevance_score, reverse=True)
        state.legal_references = all_refs
        logger.info(f"  检索完成 | 找到 {len(all_refs)} 条相关法条")
        return state
