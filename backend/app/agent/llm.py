"""
LLM 客户端工厂.

统一管理大模型客户端的创建与配置，
支持 OpenAI 兼容接口 (DeepSeek / Claude / 通义千问 等)。
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


def get_chat_llm(temperature: float | None = None) -> ChatOpenAI:
    """获取聊天大模型客户端.

    Args:
        temperature: 覆盖默认温度 (None 使用默认 0.1).
    """
    settings = get_settings()

    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model_name,
        temperature=temperature if temperature is not None else 0.1,
        max_tokens=4096,
        streaming=True,
    )


def get_vision_llm(temperature: float = 0.0) -> ChatOpenAI:
    """获取多模态(视觉)大模型客户端, 用于图片/扫描件文字抽取.

    走 OpenAI 兼容接口 (默认通义千问 VL), 非流式单次返回。
    """
    settings = get_settings()

    return ChatOpenAI(
        api_key=settings.llm_vision_api_key,
        base_url=settings.llm_vision_base_url,
        model=settings.llm_vision_model_name,
        temperature=temperature,
        max_tokens=4096,
        streaming=False,
    )
