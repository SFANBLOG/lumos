"""法规时效 / 生效范围 / 版本元数据.

原来的 14 个法条 JSON 只有 ``law_name/article/content/keywords/category/source``，
没有生效日期、失效日期、地区、版本与来源链接 —— 这是法律 AI 的硬伤:
法规废止后仍可能被检索并引用。本模块提供:
- 按法名维护的元数据基线表 (可被运维替换成外部法规库);
- ``attach_metadata`` 在语料加载时注入字段 (会改变 corpus_hash, 自动触发索引重建);
- ``is_effective`` / ``active_laws`` 按日期过滤失效法规。

⚠️ 下表的生效日期是**基线值**，用于演示时效过滤机制与建立回归用例；
正式上线前须按国家法律法规数据库逐条核对并补齐 ``source_url`` 到具体文本页。
本模块刻意不 import ``law_corpus``，避免循环导入。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

_OFFICIAL = "https://flk.npc.gov.cn/ (按法名检索现行有效文本)"


@dataclass(frozen=True)
class LawMeta:
    """一部法规的时效元数据."""

    effective_from: str = "1995-01-01"
    effective_until: str = ""  # 空表示现行有效
    region: str = "全国"
    version: str = "baseline-1.0"
    source_url: str = _OFFICIAL
    note: str = "基线值, 上线前须按官方发布核对"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


#: 语料中 14 部法律的名称 → 元数据。名称取自 app/rag/data/*.json 的 law_name。
LAW_META: dict[str, LawMeta] = {
    "劳动合同法": LawMeta(effective_from="2013-07-01", version="2012 修正"),
    "劳动法": LawMeta(effective_from="1995-01-01", version="2018 修正"),
    "社会保险法": LawMeta(effective_from="2011-07-01", version="2018 修正"),
    "劳动争议调解仲裁法": LawMeta(effective_from="2008-05-01"),
    "就业促进法": LawMeta(effective_from="2008-01-01", version="2015 修正"),
    "劳动合同法实施条例": LawMeta(effective_from="2008-09-18"),
    "职工带薪年休假条例": LawMeta(effective_from="2008-01-01"),
    "女职工劳动保护特别规定": LawMeta(effective_from="2012-04-28"),
    "工伤保险条例": LawMeta(effective_from="2011-01-01", version="2010 修订"),
    "劳动保障监察条例": LawMeta(effective_from="2004-12-01"),
    "工资支付暂行规定": LawMeta(effective_from="1995-01-01"),
    "最低工资规定": LawMeta(
        effective_from="2004-03-01",
        region="全国 (具体标准按省市)",
        note="最低工资标准按地区公布, 需接入地方口径",
    ),
    "国务院关于职工工作时间的规定": LawMeta(effective_from="1995-05-01"),
    "劳动争议司法解释二": LawMeta(
        effective_from="2025-09-01",
        note="基线值, 请按最高人民法院公告核对施行日期",
    ),
}

#: 扩展语料 (law_corpus_ext.py 中的民法典/个保法/医疗期/劳务派遣等) 的默认元数据
DEFAULT_META = LawMeta(note="扩展条文, 未逐部维护时效, 上线前须补齐")

#: 关键词 → 元数据, 用于扩展语料按法名子串匹配
_KEYWORD_META: tuple[tuple[str, LawMeta], ...] = (
    ("民法典", LawMeta(effective_from="2021-01-01")),
    ("个人信息保护法", LawMeta(effective_from="2021-11-01")),
    ("劳务派遣", LawMeta(effective_from="2014-03-01")),
    ("医疗期", LawMeta(effective_from="1995-01-01")),
)


def metadata_for(law_name: str) -> LawMeta:
    """按法名取元数据; 精确匹配优先, 其次关键词, 最后回退默认值."""
    if law_name in LAW_META:
        return LAW_META[law_name]
    for keyword, meta in _KEYWORD_META:
        if keyword in law_name:
            return meta
    return DEFAULT_META


def attach_metadata(law: dict) -> dict:
    """就地给法条字典补齐时效字段 (不覆盖语料里已有的显式声明)."""
    meta = metadata_for(str(law.get("law_name", ""))).as_dict()
    for key, value in meta.items():
        law.setdefault(key, value)
    return law


def _parse(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def is_effective(law: dict, as_of: date | None = None) -> bool:
    """判断某条法规在 ``as_of`` 当日是否生效且未失效.

    元数据缺失或日期非法时按「有效」处理，避免因为基线数据不全而误删语料。
    """
    today = as_of or date.today()
    start = _parse(str(law.get("effective_from", "")))
    end = _parse(str(law.get("effective_until", "")))
    if start is not None and start > today:
        return False
    if end is not None and end < today:
        return False
    return True


def active_laws(laws: list[dict], as_of: date | None = None) -> list[dict]:
    """过滤掉尚未生效或已经失效的法规."""
    return [law for law in laws if is_effective(law, as_of)]
