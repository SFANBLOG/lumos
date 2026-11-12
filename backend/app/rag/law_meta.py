"""法规时效 / 生效范围 / 版本元数据 (可核验版).

原来的 14 个法条 JSON 只有 ``law_name/article/content/keywords/category/source``，
没有生效日期、失效日期、地区、版本与来源链接 —— 这是法律 AI 的硬伤:
法规废止后仍可能被检索并引用。本模块提供:

- 按法名维护的元数据基线表, 可被运维用**外部覆盖文件**逐条替换
  (``LUMOS_LAW_META_PATH``, 见 ``app/rag/data/law_meta_overrides.example.json``);
- ``attach_metadata`` 在语料加载时注入字段 (会改变 corpus_hash, 自动触发索引重建);
- ``is_effective`` / ``active_laws`` 按日期与地区过滤失效法规;
- ``verify_laws`` 输出可核验报告: 来源链接是否具体到文本页、是否人工核对过、
  核对日期是否过期、生效日期是否合法、法规是否已废止;
- ``metadata_diff`` 对比两份语料的元数据快照, 给出变更清单;
- ``python -m app.rag.law_meta --strict`` 作为 CI / 上线前的检查门禁。

⚠️ 内置生效日期是**基线值**，仅用于演示时效过滤与建立回归用例；
正式上线前须按国家法律法规数据库逐条核对，通过外部覆盖文件补齐
``source_url``（具体文本页）、``checked_at``（核对日期）与 ``version``。
本模块刻意不 import ``law_corpus``，避免循环导入。
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, fields, replace
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

_OFFICIAL = "https://flk.npc.gov.cn/ (按法名检索现行有效文本)"
_GENERIC_URL_PREFIX = "https://flk.npc.gov.cn/ ("

#: 外部覆盖文件默认位置; 不存在时静默使用基线表, 便于开箱即用。
_DEFAULT_OVERRIDE_FILE = Path(__file__).with_name("data") / "law_meta_overrides.json"

#: 核验报告的阻断级问题 (出现任意一条即不允许放行)
_BLOCKING = frozenset(
    {
        "source_not_verified",
        "never_checked",
        "stale",
        "not_effective",
        "invalid_date",
    }
)


@dataclass(frozen=True)
class LawMeta:
    """一部法规的时效元数据."""

    effective_from: str = "1995-01-01"
    effective_until: str = ""  # 空表示现行有效
    region: str = "全国"
    version: str = "baseline-1.0"
    source_url: str = _OFFICIAL
    checked_at: str = ""  # 最近一次人工核对日期 (ISO), 空表示从未核对
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

_META_FIELDS = frozenset(f.name for f in fields(LawMeta))


def override_path() -> Path:
    """外部覆盖文件路径 (环境变量优先)."""
    return Path(os.getenv("LUMOS_LAW_META_PATH") or _DEFAULT_OVERRIDE_FILE)


def _clean_override(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {k: str(v) for k, v in raw.items() if k in _META_FIELDS}


@lru_cache(maxsize=8)
def _load_overrides(path: str) -> dict[str, dict[str, str]]:
    """读取外部覆盖表; 文件缺失/格式错误时降级为空, 绝不拖垮语料加载."""
    file = Path(path)
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(name): _clean_override(value)
        for name, value in payload.items()
        if _clean_override(value)
    }


def reload_overrides() -> None:
    """运维更新覆盖文件后清空缓存 (API / 长驻进程热加载)."""
    _load_overrides.cache_clear()


def _base_meta(law_name: str) -> LawMeta:
    if law_name in LAW_META:
        return LAW_META[law_name]
    for keyword, meta in _KEYWORD_META:
        if keyword in law_name:
            return meta
    return DEFAULT_META


def _override_for(law_name: str, region: str = "") -> dict[str, str]:
    """取该法名 (及地区) 的外部覆盖字段."""
    overrides = _load_overrides(str(override_path()))
    patch = overrides.get(f"{law_name}@{region}") if region else None
    return patch or overrides.get(law_name) or {}


def metadata_for(law_name: str, region: str = "") -> LawMeta:
    """按法名 (及可选地区) 取元数据.

    外部覆盖支持 ``"法名"`` 与 ``"法名@地区"`` 两种键, 后者优先,
    用于「最低工资规定」这类中央立法 + 地方标准的场景。
    """
    key = str(law_name or "")
    base = _base_meta(key)
    patch = _override_for(key, region)
    return replace(base, **patch) if patch else base


def attach_metadata(law: dict, region: str = "") -> dict:
    """就地注入元数据: 语料显式声明的字段保留, 外部覆盖字段强制生效."""
    name = str(law.get("law_name", ""))
    meta = metadata_for(name, region).as_dict()
    patch = _override_for(name, region)
    for key, value in meta.items():
        if key in patch:
            law[key] = value
        else:
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


def _region_matches(law_region: str, region: str) -> bool:
    """全国性法规始终适用; 地方性法规只在其标注地区适用."""
    if not region:
        return True
    value = str(law_region or "全国")
    if value.startswith("全国") or value == "全国":
        return True
    return region in value or value in region


def active_laws(
    laws: list[dict], as_of: date | None = None, region: str = ""
) -> list[dict]:
    """过滤掉尚未生效、已经失效或不适用本地区的法规."""
    return [
        law
        for law in laws
        if is_effective(law, as_of)
        and _region_matches(str(law.get("region", "")), region)
    ]


_META_KEYS = tuple(f.name for f in fields(LawMeta))


def verify_laws(
    laws: list[dict],
    as_of: date | None = None,
    stale_days: int = 180,
) -> dict[str, Any]:
    """生成可核验报告: 逐部法规列出缺失/过期的核验证据.

    基线表刻意保持「未核验」状态, 因此默认报告会给出待办清单;
    只有外部覆盖文件补齐 ``source_url`` 与 ``checked_at`` 后,
    ``ok`` 才会变为 True, 可直接作为上线门禁。
    """
    today = as_of or date.today()
    by_name: dict[str, dict] = {}
    for law in laws:
        name = str(law.get("law_name", "") or "")
        by_name.setdefault(name, law)

    issues: list[dict[str, str]] = []
    for name in sorted(by_name):
        law = by_name[name]
        url = str(law.get("source_url", "") or "")
        if not url or url.startswith(_GENERIC_URL_PREFIX) or "example.invalid" in url:
            issues.append(
                {"law_name": name, "code": "source_not_verified", "detail": "来源链接不是具体文本页"}
            )
        checked = _parse(str(law.get("checked_at", "") or ""))
        if checked is None:
            issues.append(
                {"law_name": name, "code": "never_checked", "detail": "没有人工核对日期"}
            )
        elif (today - checked).days > stale_days:
            issues.append(
                {
                    "law_name": name,
                    "code": "stale",
                    "detail": f"上次核对 {checked.isoformat()}, 已超过 {stale_days} 天",
                }
            )
        start = _parse(str(law.get("effective_from", "") or ""))
        if start is None:
            issues.append(
                {"law_name": name, "code": "invalid_date", "detail": "effective_from 不是合法 ISO 日期"}
            )
        if not is_effective(law, today):
            issues.append(
                {"law_name": name, "code": "not_effective", "detail": "法规在核验日未生效或已废止"}
            )
        if "基线" in str(law.get("note", "") or ""):
            issues.append(
                {"law_name": name, "code": "baseline_value", "detail": "仍在使用基线值, 需按官方文本替换"}
            )

    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    return {
        "as_of": today.isoformat(),
        "stale_days": stale_days,
        "override_file": str(override_path()),
        "law_count": len(by_name),
        "issue_count": len(issues),
        "blocking_issues": sum(1 for i in issues if i["code"] in _BLOCKING),
        "by_code": counts,
        "issues": issues,
        "ok": not any(i["code"] in _BLOCKING for i in issues),
    }


def snapshot(laws: list[dict]) -> dict[str, dict[str, str]]:
    """导出按法名的元数据快照, 供版本留痕与变更检查."""
    return {
        str(law.get("law_name", "")): {
            key: str(law.get(key, "") or "") for key in _META_KEYS
        }
        for law in laws
        if law.get("law_name")
    }


def metadata_diff(
    previous: dict[str, dict[str, str]],
    current: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """对比两份元数据快照, 输出新增/删除/字段变更清单."""
    changes: list[dict[str, str]] = []
    for name in sorted(set(previous) | set(current)):
        if name not in previous:
            changes.append({"law_name": name, "change": "added", "field": "", "old": "", "new": ""})
            continue
        if name not in current:
            changes.append({"law_name": name, "change": "removed", "field": "", "old": "", "new": ""})
            continue
        for field in _META_KEYS:
            old = str(previous[name].get(field, "") or "")
            new = str(current[name].get(field, "") or "")
            if old != new:
                changes.append(
                    {"law_name": name, "change": "changed", "field": field, "old": old, "new": new}
                )
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="法规时效元数据核验与变更检查")
    parser.add_argument("--strict", action="store_true", help="存在阻断级问题时返回非零退出码")
    parser.add_argument("--stale-days", type=int, default=180)
    parser.add_argument("--as-of", type=str, default="", help="核验基准日 YYYY-MM-DD")
    parser.add_argument("--diff", type=Path, default=None, help="与指定快照 JSON 对比变更")
    parser.add_argument("--out", type=Path, default=None, help="将报告写入文件")
    args = parser.parse_args(argv)

    from app.rag.law_corpus import ALL_LAWS

    as_of = _parse(args.as_of) or date.today()
    report = verify_laws(ALL_LAWS, as_of=as_of, stale_days=args.stale_days)
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    if args.diff:
        try:
            previous = json.loads(args.diff.read_text(encoding="utf-8"))
            changes = metadata_diff(previous, snapshot(ALL_LAWS))
            report["changes"] = changes
            report["change_count"] = len(changes)
        except (OSError, json.JSONDecodeError) as exc:
            report["changes"] = []
            report["change_error"] = str(exc)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
