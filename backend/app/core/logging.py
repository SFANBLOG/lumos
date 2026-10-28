"""
日志配置模块.

使用 loguru 记录应用日志, 同时把标准库 logging 中较“话痨”的日志器
(sqlalchemy 引擎 SQL 回显等) 收敛到 WARNING 以上, 保证控制台干净。

输出:
- 控制台 (stderr, 带颜色)
- 文件 ``backend/logs/lumos_<日期>.log``: 开发与生产均启用, 每天零点轮转,
  保留 30 天并 gz 压缩。日志目录以文件位置锚定, 不依赖启动 CWD。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

from app.core.config import BASE_DIR, get_settings

#: 标准库中默认收敛的“话痨”日志器 (SQLAlchemy 引擎/连接池 SQL 回显等)
_QUIET_STDLIB_LOGGERS = (
    "sqlalchemy",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.dialects",
)


def _tune_stdlib_loggers(echo: bool) -> None:
    """调节标准库 logging 日志器级别, 避免 SQL/ORM 内部日志刷屏。

    - 默认 (echo=False): 收到 WARNING, ``SELECT ...`` 等 INFO 日志不再产生;
    - 显式开启 ``DATABASE_ECHO=true`` 调试 SQL 时: 放开到 INFO。
    """
    level = logging.INFO if echo else logging.WARNING
    for name in _QUIET_STDLIB_LOGGERS:
        logging.getLogger(name).setLevel(level)


def setup_logging() -> None:
    """配置全局日志."""
    settings = get_settings()

    # 1) 收敛标准库日志器 (须在任何 SQL 执行前生效)
    _tune_stdlib_loggers(settings.database_echo)

    # 2) 移除默认 handler
    logger.remove()

    # 3) 日志目录 = backend/logs (以文件位置锚定, 不依赖启动 CWD)
    log_dir = Path(BASE_DIR) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 控制台输出 (带颜色; SQL 回显已被收敛, 不再刷屏)
    logger.add(
        sys.stderr,
        format=log_format,
        level=settings.log_level,
        colorize=True,
        backtrace=settings.is_development,
        diagnose=settings.is_development,
    )

    # 文件输出 (开发/生产均启用): 每天零点轮转, 保留 30 天, gz 压缩
    logger.add(
        str(log_dir / "lumos_{time:YYYY-MM-DD}.log"),
        encoding="utf-8",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        enqueue=True,  # 异步线程安全写入
        level="INFO",
        format=log_format,
    )

    logger.info(f"📋 日志级别: {settings.log_level} | 环境: {settings.app_env.value}")
    logger.info(
        f"📄 日志文件: {log_dir / 'lumos_*.log'} | "
        f"database_echo={settings.database_echo}"
    )
