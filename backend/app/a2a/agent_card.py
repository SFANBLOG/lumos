"""
Lumos A2A Agent Card 构建.

Agent Card 是 A2A 的「自我声明」文件, 通常托管于
``/.well-known/agent.json``。其他 A2A 客户端读取它即可发现 Lumos
的能力 (合同风险排查)、输入输出模态与 A2A 端点地址。
"""

from __future__ import annotations

from app.a2a.models import AgentCapabilities, AgentCard, AgentSkill
from app.core.config import get_settings

#: A2A 协议版本 (与 google/A2A 规范 0.3.x 对齐)
A2A_PROTOCOL_VERSION = "0.3.0"


def _build_public_url() -> str:
    """推断对外暴露的 A2A 端点基址.

    容器内 ``app_host`` 常为 0.0.0.0 (不可路由), 因此优先使用
    显式配置的 ``a2a_public_url``; 缺省则回退到 host:port。
    """
    settings = get_settings()
    base = (settings.a2a_public_url or "").rstrip("/")
    if not base:
        base = f"http://{settings.app_host}:{settings.app_port}"
    return f"{base}{settings.a2a_base_path}"


def get_agent_card() -> AgentCard:
    """构造 Lumos 的 A2A Agent Card."""
    settings = get_settings()
    endpoint = _build_public_url()
    return AgentCard(
        protocolVersion=A2A_PROTOCOL_VERSION,
        name="Lumos · 契光鉴微",
        description=(
            "开源 AI 劳动合同风险排查助手。站在劳动者视角, 基于中国劳动法对"
            "劳动合同进行结构化抽取、法规检索(RAG)、风险审查与谈判话术生成, "
            "输出十大坑点风险清单与总评分。"
        ),
        url=endpoint,
        provider={
            "organization": "Lumos Contributors",
            "url": "https://gitee.com/BLOGSFan/lumos",
        },
        version=settings.app_version,
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            stateTransitionHistory=False,
        ),
        skills=[
            AgentSkill(
                id="contract-risk-review",
                name="劳动合同风险排查",
                description=(
                    "输入劳动合同正文文本, 执行 抽取→检索→审查→谈判 四阶段工作流, "
                    "返回风险清单 (含法律依据与谈判话术) 与总体安全评分。"
                ),
                tags=["legal", "contract", "labor-law", "risk-review", "rag"],
                examples=[
                    "请审查这份劳动合同:\n<劳动合同全文>",
                    "帮我看看这份竞业禁止条款有没有坑。",
                ],
                inputModes=["text/plain"],
                outputModes=["text/plain", "application/json"],
            )
        ],
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain", "application/json"],
    )
