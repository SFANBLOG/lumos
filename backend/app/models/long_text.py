"""跨方言长文本类型.

MySQL 渲染为 MEDIUMTEXT, 其他方言 (PostgreSQL 等) 降级为 TEXT,
避免 str 默认 VARCHAR(255) 截断, 同时保证 DDL 在托管库可执行。
"""

from __future__ import annotations

from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.compiler import compiles


class LongText(MEDIUMTEXT):
    __visit_name__ = "lumos_long_text"


@compiles(LongText)
def _long_text_default(element, compiler, **kw):  # noqa: ARG001
    return "TEXT"


@compiles(LongText, "mysql")
def _long_text_mysql(element, compiler, **kw):  # noqa: ARG001
    return "MEDIUMTEXT"
