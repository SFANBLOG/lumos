"""
Lumos A2A Agent Executor.

将 A2A 入站 ``Message`` 转交现有 LangGraph 合同审查工作流
(``app.agent.graph.run_contract_analysis``) 执行, 并把产出的 SSE 事件
流映射为 A2A 的 ``Task`` / ``Artifact`` 与流式 ``Task*UpdateEvent``。

设计原则: 不改动现有工作流代码, 仅在其事件流之上做协议适配层。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from loguru import logger

from app.a2a.models import (
    Artifact,
    DataPart,
    Message,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from app.agent.graph import run_contract_analysis
from app.schemas.analysis import SSEEventType


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_contract_text(message: Message) -> str:
    """从 A2A Message 中提取合同正文文本 (优先 TextPart, 兼容 DataPart)."""
    texts: list[str] = []
    for part in message.parts:
        if isinstance(part, TextPart):
            texts.append(part.text)
        elif isinstance(part, DataPart):
            for key in ("raw_text", "text", "contract_text"):
                if key in part.data and isinstance(part.data[key], str):
                    texts.append(part.data[key])
                    break
    return "\n".join(t.strip() for t in texts if t and t.strip())


def _build_report(summary: dict, risks: list[dict]) -> str:
    """将审查结果渲染为可读的 Markdown 报告."""
    lines: list[str] = ["# 劳动合同风险排查报告", ""]
    score = summary.get("overall_score", "—")
    level = summary.get("overall_level", "—")
    lines.append(f"**总体评分**: {score}/100　**风险等级**: {level}")
    if summary.get("summary"):
        lines.append(f"**一句话总结**: {summary['summary']}")
    lines.append("")
    lines.append(f"共发现 **{len(risks)}** 项风险：")
    for i, r in enumerate(risks, 1):
        lines.append(f"\n## {i}. {r.get('title', '未命名风险')} 〔{r.get('level', '—')}〕")
        if r.get("original_clause"):
            lines.append(f"- **原条款**：{r['original_clause']}")
        if r.get("explanation"):
            lines.append(f"- **大白话解读**：{r['explanation']}")
        if r.get("legal_basis"):
            lines.append(f"- **法律依据**：{r['legal_basis']}")
        if r.get("negotiation_tip"):
            lines.append(f"- **谈判话术**：{r['negotiation_tip']}")
        if r.get("score") is not None:
            lines.append(f"- **单项评分**：{r['score']}/100")
    return "\n".join(lines)


class LumosAgentExecutor:
    """A2A 执行器: 把协议事件适配到 Lumos 合同审查工作流."""

    async def execute_task(self, task_id: str, context_id: str, message: Message) -> Task:
        """同步模式: 跑完整工作流, 返回处于终态 (completed/failed) 的 Task."""
        text = _extract_contract_text(message)
        if not text:
            return Task(
                id=task_id,
                contextId=context_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="未提供合同文本, 请在 Message 中附带合同正文。")],
                    ),
                    timestamp=_now(),
                ),
            )

        risks: list[dict] = []
        summary: dict = {}
        try:
            async for event in run_contract_analysis(
                contract_id=task_id, raw_text=text, session=None
            ):
                if event.event == SSEEventType.RISK_FOUND:
                    risks.append(event.data)
                elif event.event == SSEEventType.SUMMARY:
                    summary = event.data
                elif event.event == SSEEventType.ERROR:
                    return Task(
                        id=task_id,
                        contextId=context_id,
                        status=TaskStatus(
                            state=TaskState.FAILED,
                            message=Message(
                                role="agent",
                                parts=[TextPart(text=event.data.get("message", "分析失败"))],
                            ),
                            timestamp=_now(),
                        ),
                    )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"A2A 工作流执行异常 | task={task_id}")
            return Task(
                id=task_id,
                contextId=context_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(role="agent", parts=[TextPart(text=f"分析引擎异常: {e}")]),
                    timestamp=_now(),
                ),
            )

        report = _build_report(summary, risks)
        artifacts = [
            Artifact(
                artifactId=f"{task_id}-risks",
                name="risk_assessments",
                description="结构化风险清单 (JSON)",
                parts=[DataPart(data={"summary": summary, "risks": risks})],
            ),
            Artifact(
                artifactId=f"{task_id}-report",
                name="report",
                description="人类可读的 Markdown 风险报告",
                parts=[TextPart(text=report)],
            ),
        ]
        return Task(
            id=task_id,
            contextId=context_id,
            status=TaskStatus(
                state=TaskState.COMPLETED,
                message=Message(
                    role="agent",
                    parts=[TextPart(text=summary.get("summary", "✨ 合同风险排查完成！"))],
                ),
                timestamp=_now(),
            ),
            artifacts=artifacts,
        )

    async def stream_task(self, task_id: str, context_id: str, message: Message):
        """流式模式: 逐步 yield ``TaskStatusUpdateEvent`` / ``TaskArtifactUpdateEvent``."""
        text = _extract_contract_text(message)
        if not text:
            yield TaskStatusUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[TextPart(text="未提供合同文本, 请在 Message 中附带合同正文。")],
                    ),
                    timestamp=_now(),
                ),
                final=True,
            )
            return

        # 提交 & 处理中
        yield TaskStatusUpdateEvent(
            taskId=task_id,
            contextId=context_id,
            status=TaskStatus(
                state=TaskState.WORKING,
                message=Message(role="agent", parts=[TextPart(text="🔍 已接收合同, 开始风险排查…")]),
                timestamp=_now(),
            ),
        )

        risks: list[dict] = []
        summary: dict = {}
        try:
            async for event in run_contract_analysis(
                contract_id=task_id, raw_text=text, session=None
            ):
                if event.event == SSEEventType.NODE_START:
                    desc = (event.data or {}).get("description", "")
                    yield TaskStatusUpdateEvent(
                        taskId=task_id,
                        contextId=context_id,
                        status=TaskStatus(
                            state=TaskState.WORKING,
                            message=Message(role="agent", parts=[TextPart(text=desc)]),
                            timestamp=_now(),
                        ),
                    )
                elif event.event == SSEEventType.THINKING:
                    yield TaskStatusUpdateEvent(
                        taskId=task_id,
                        contextId=context_id,
                        status=TaskStatus(
                            state=TaskState.WORKING,
                            message=Message(
                                role="agent",
                                parts=[TextPart(text=event.data.get("message", ""))],
                            ),
                            timestamp=_now(),
                        ),
                    )
                elif event.event == SSEEventType.RISK_FOUND:
                    risks.append(event.data)
                elif event.event == SSEEventType.SUMMARY:
                    summary = event.data
                elif event.event == SSEEventType.ERROR:
                    yield TaskStatusUpdateEvent(
                        taskId=task_id,
                        contextId=context_id,
                        status=TaskStatus(
                            state=TaskState.FAILED,
                            message=Message(
                                role="agent",
                                parts=[TextPart(text=event.data.get("message", "分析失败"))],
                            ),
                            timestamp=_now(),
                        ),
                        final=True,
                    )
                    return
        except Exception as e:  # noqa: BLE001
            logger.exception(f"A2A 流式工作流异常 | task={task_id}")
            yield TaskStatusUpdateEvent(
                taskId=task_id,
                contextId=context_id,
                status=TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(role="agent", parts=[TextPart(text=f"分析引擎异常: {e}")]),
                    timestamp=_now(),
                ),
                final=True,
            )
            return

        # 推送产物 (一次性完整 artifact)
        report = _build_report(summary, risks)
        yield TaskArtifactUpdateEvent(
            taskId=task_id,
            contextId=context_id,
            artifact=Artifact(
                artifactId=f"{task_id}-risks",
                name="risk_assessments",
                parts=[DataPart(data={"summary": summary, "risks": risks})],
            ),
            append=False,
            lastChunk=True,
        )
        yield TaskArtifactUpdateEvent(
            taskId=task_id,
            contextId=context_id,
            artifact=Artifact(
                artifactId=f"{task_id}-report",
                name="report",
                parts=[TextPart(text=report)],
            ),
            append=False,
            lastChunk=True,
        )

        # 终态
        yield TaskStatusUpdateEvent(
            taskId=task_id,
            contextId=context_id,
            status=TaskStatus(
                state=TaskState.COMPLETED,
                message=Message(
                    role="agent",
                    parts=[TextPart(text=summary.get("summary", "✨ 合同风险排查完成！"))],
                ),
                timestamp=_now(),
            ),
            final=True,
        )
