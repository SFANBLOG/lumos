"""
A2A (Agent2Agent Protocol) 数据模型.

遵循 A2A 规范 (https://github.com/google/A2A) 定义的最小可用子集：
AgentCard 自描述、JSON-RPC 2.0 消息信封、Task/Artifact 数据模型
以及流式 SSE 事件。Lumos 借此可被任意 A2A 客户端/其他 Agent 发现并调用。

本模块为协议层，不依赖任何第三方 A2A SDK，纯 Pydantic 建模，便于
在受限/离线环境中部署。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, Field


# ─── Part (消息/产物的最小载体) ─────────────────────────────────
# A2A 2025-06 规范以 ``kind`` 字段区分 part 类型 (旧版用 ``type``)。


class TextPart(BaseModel):
    """文本片段, 承载合同原文或结论文本."""

    kind: Literal["text"] = "text"
    text: str
    metadata: dict[str, Any] | None = None


class FilePart(BaseModel):
    """文件片段, 如上传的合同 PDF/图片 (bytes 为 base64 / uri 二选一)."""

    kind: Literal["file"] = "file"
    file: dict[str, Any] = Field(description="{'name'?, 'mimeType'?, 'bytes'|'uri'}")
    metadata: dict[str, Any] | None = None


class DataPart(BaseModel):
    """结构化数据片段, 如风险清单 JSON."""

    kind: Literal["data"] = "data"
    data: dict[str, Any]
    metadata: dict[str, Any] | None = None


Part = Union[TextPart, FilePart, DataPart]


# ─── Message (Agent 间传递的语义单元) ──────────────────────────


class Message(BaseModel):
    role: Literal["user", "agent"]
    parts: list[Part]
    metadata: dict[str, Any] | None = None


# ─── Task & Artifact ───────────────────────────────────────────


class TaskState(str, Enum):
    """A2A 任务状态机."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    UNKNOWN = "unknown"


class TaskStatus(BaseModel):
    state: TaskState
    message: Message | None = None
    timestamp: str | None = None


class Artifact(BaseModel):
    """任务产物, 如风险清单、完整报告."""

    artifactId: str
    name: str | None = None
    description: str | None = None
    parts: list[Part]
    index: int | None = None
    append: bool | None = None
    last: bool | None = None
    metadata: dict[str, Any] | None = None


class Task(BaseModel):
    id: str
    contextId: str
    kind: Literal["task"] = "task"
    status: TaskStatus
    artifacts: list[Artifact] | None = None
    history: list[Message] | None = None
    metadata: dict[str, Any] | None = None


# ─── 流式 SSE 事件 (message/stream 推送) ───────────────────────


class TaskStatusUpdateEvent(BaseModel):
    kind: Literal["status-update"] = "status-update"
    taskId: str
    contextId: str
    status: TaskStatus
    final: bool = False


class TaskArtifactUpdateEvent(BaseModel):
    kind: Literal["artifact-update"] = "artifact-update"
    taskId: str
    contextId: str
    artifact: Artifact
    append: bool = False
    lastChunk: bool = False


# ─── JSON-RPC 2.0 信封 ─────────────────────────────────────────


class JSONRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Any = None


class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any = None
    error: JSONRPCError | None = None


# ─── TaskSendParams (message/send 入参) ────────────────────────


class TaskSendParams(BaseModel):
    id: str | None = None
    contextId: str | None = None
    message: Message
    historyLength: int | None = None
    metadata: dict[str, Any] | None = None


# ─── Agent Card (自描述能力声明) ───────────────────────────────


class AgentCapabilities(BaseModel):
    streaming: bool = True
    pushNotifications: bool = False
    stateTransitionHistory: bool = False


class AgentSkill(BaseModel):
    """单个可被发现的能力."""

    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    inputModes: list[str] = Field(default_factory=lambda: ["text/plain"])
    outputModes: list[str] = Field(default_factory=lambda: ["text/plain", "application/json"])


class AgentCard(BaseModel):
    protocolVersion: str
    name: str
    description: str
    url: str
    provider: dict[str, Any] | None = None
    version: str
    capabilities: AgentCapabilities
    skills: list[AgentSkill]
    defaultInputModes: list[str] = Field(default_factory=lambda: ["text/plain"])
    defaultOutputModes: list[str] = Field(default_factory=lambda: ["text/plain", "application/json"])


# ─── JSON-RPC 错误码 (与规范保持一致) ──────────────────────────


class A2AErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
