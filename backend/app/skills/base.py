"""
技能抽象基类.

所有技能必须实现 execute 方法，供子智能体调用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    """可复用的能力单元."""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """执行技能，接受并返回任意数据."""
        ...
