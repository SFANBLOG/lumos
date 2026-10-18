"""
法条语料风险分类修正脚本 (可重复执行).

背景
----
风险类别从 10 类扩充到 16 类 (新增 6 类劳动仲裁高发案由) 后, 新增类别
在 ``ALL_LAWS`` 里条文数为 0——经查证, 这些案由对应的条文**早已存在于
data/*.json 中**, 只是当初的 ``category`` 标注不准, 例如:

- 劳动合同法第87条 (违法解除二倍赔偿金) 被标成 ``resignation``
- 劳动合同法第47条 (经济补偿计算标准)  被标成 ``probation_salary``
- 劳动合同法第9条  (禁止扣押证件/押金) 被标成 ``general``

同时 ``obedience_clause`` 在 659 条语料里一条都没有, 导致该类别检索
命中恒为 0。

为什么不写在 law_corpus_ext.py 里
---------------------------------
``_load_full_corpus()`` 按 ``(law_name, article)`` 去重且**保留首次出现**,
而 ``EXTENDED_RULES`` 是追加在 JSON 之后的, 所以凡与 JSON 重复的扩展条目
都会被静默丢弃。因此修正分类必须落在 JSON 上。

用法
----
    cd backend && python -m scripts.recategorize_laws          # 预览改动
    cd backend && python -m scripts.recategorize_laws --write  # 落盘

脚本保持幂等: 对已修正的条目重复执行不再产生改动。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "rag" / "data"
_REPO_ROOT = DATA_DIR.parents[3]

#: (法律名, 条文号) → (新分类, 补充关键词)
_CATEGORY_FIXES: dict[tuple[str, str], tuple[str, list[str]]] = {
    # ── unlawful_termination: 违法解除/终止 (2N 赔偿金) ──
    ("劳动合同法", "第三十九条"): ("unlawful_termination", ["过失性辞退", "严重违反规章制度", "不符合录用条件"]),
    ("劳动合同法", "第四十条"): ("unlawful_termination", ["无过失性辞退", "不能胜任工作", "代通知金", "提前三十日"]),
    ("劳动合同法", "第四十二条"): ("unlawful_termination", ["不得解除", "孕期", "产期", "哺乳期", "医疗期"]),
    ("劳动合同法", "第四十三条"): ("unlawful_termination", ["通知工会", "单方解除程序"]),
    ("劳动合同法", "第四十八条"): ("unlawful_termination", ["违法解除", "继续履行", "赔偿金"]),
    ("劳动合同法", "第八十七条"): ("unlawful_termination", ["二倍赔偿金", "2N", "违法解除赔偿"]),
    # ── severance_pay: 经济补偿金 (N) ──
    ("劳动合同法", "第四十六条"): ("severance_pay", ["经济补偿", "支付情形", "协商一致解除"]),
    ("劳动合同法", "第四十七条"): ("severance_pay", ["经济补偿计算", "每满一年一个月工资", "N+1", "月平均工资"]),
    ("劳动合同法", "第八十五条"): ("severance_pay", ["未支付经济补偿", "加付赔偿金", "责令限期支付"]),
    # ── no_written_contract: 未签书面合同 (二倍工资) ──
    ("劳动合同法", "第十条"): ("no_written_contract", ["书面劳动合同", "用工之日起一个月内"]),
    ("劳动合同法", "第十四条"): ("no_written_contract", ["无固定期限劳动合同", "连续工作满十年"]),
    ("劳动合同法", "第八十二条"): ("no_written_contract", ["二倍工资", "双倍工资", "未订立书面合同"]),
    ("劳动保障监察条例", "第二十四条"): ("no_written_contract", ["不依法订立劳动合同", "责令改正"]),
    # ── overtime_pay: 加班费与工时上限 ──
    ("劳动合同法", "第三十一条"): ("overtime_pay", ["不得强迫加班", "变相强迫", "支付加班费"]),
    ("劳动法", "第三十六条"): ("overtime_pay", ["工时制度", "每日八小时", "每周四十四小时"]),
    ("劳动法", "第四十一条"): ("overtime_pay", ["延长工作时间", "每月不得超过三十六小时", "加班上限"]),
    ("劳动法", "第四十四条"): ("overtime_pay", ["加班费", "百分之一百五十", "百分之二百", "百分之三百", "补休"]),
    ("工资支付暂行规定", "第十三条"): ("overtime_pay", ["加班工资", "计件工资加班", "综合计算工时", "150%", "200%", "300%"]),
    ("劳动保障监察条例", "第二十五条"): ("overtime_pay", ["延长工作时间", "罚款", "责令限期改正"]),
    ("国务院关于职工工作时间的规定", "第六条"): ("overtime_pay", ["不得擅自延长", "延长职工工作时间"]),
    # ── illegal_penalty: 违法约定违约金 ──
    ("劳动合同法", "第二十五条"): ("illegal_penalty", ["违约金", "不得约定", "劳动者承担"]),
    ("劳动合同法", "第二十六条"): ("illegal_penalty", ["合同无效", "免除法定责任", "排除劳动者权利"]),
    # ── deposit_guarantee: 押金 / 扣押证件 / 担保 ──
    ("劳动合同法", "第九条"): ("deposit_guarantee", ["扣押证件", "居民身份证", "担保", "收取财物", "押金"]),
    ("劳动合同法", "第八十四条"): ("deposit_guarantee", ["责令退还", "扣押档案", "罚款"]),
    # ── obedience_clause: 原先 0 条, 补齐 ──
    ("劳动合同法", "第三十五条"): ("obedience_clause", ["变更劳动合同", "协商一致", "书面形式", "调岗"]),
    ("劳动合同法", "第三十二条"): ("obedience_clause", ["违章指挥", "强令冒险作业", "不视为违反合同"]),
}


def _apply(rows: list[dict]) -> list[str]:
    """就地修改 rows, 返回变更说明列表."""
    changes: list[str] = []
    for row in rows:
        fix = _CATEGORY_FIXES.get((row.get("law_name", ""), row.get("article", "")))
        if not fix:
            continue
        new_cat, extra_keywords = fix
        old_cat = row.get("category")
        if old_cat != new_cat:
            changes.append(
                f"  {row['law_name']}{row['article']}: {old_cat} → {new_cat}"
            )
            row["category"] = new_cat
        keywords = row.setdefault("keywords", [])
        for kw in extra_keywords:
            if kw not in keywords:
                keywords.append(kw)
    return changes


# 各文件 keywords 数组原有排版不一致 (有的内联、有的多行), 序列化时需保留
# 原风格, 否则一次修正会产生大量与语义无关的 diff 噪声。
_KW_BLOCK = re.compile(r'"keywords": \[(.*?)\]', re.DOTALL)
_KW_ITEM = re.compile(r'"(?:[^"\\]|\\.)*"')


def _compact_keywords(text: str) -> str:
    """把多行 keywords 数组折叠成内联 (原文件为内联风格时使用)."""
    def repl(match: re.Match) -> str:
        items = _KW_ITEM.findall(match.group(1))
        return '"keywords": [' + ", ".join(items) + "]"

    return _KW_BLOCK.sub(repl, text)


def _dump(rows: list[dict], reference: str) -> str:
    """按参考文本 (通常是 git HEAD 原稿) 的风格序列化.

    保持缩进 2 / keywords 内联与否 / 末尾换行三项与原稿一致, 使一次分类
    修正不产生与语义无关的 diff 噪声。
    """
    text = json.dumps(rows, ensure_ascii=False, indent=2)
    if '"keywords": ["' in reference:
        text = _compact_keywords(text)
    if reference.endswith("\n"):
        text += "\n"
    return text


def _head_version(path: Path) -> str | None:
    """取 git HEAD 版本, 用于判断原稿排版风格; 不可用 (首次执行/非仓库) 返回 None."""
    try:
        rel = path.relative_to(_REPO_ROOT).as_posix()
        proc = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (ValueError, OSError):
        return None
    return proc.stdout or None if proc.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description="修正法条语料的风险分类标注")
    parser.add_argument("--write", action="store_true", help="落盘 (默认仅预览)")
    args = parser.parse_args()

    if not DATA_DIR.is_dir():
        print(f"[ERR] 未找到语料目录: {DATA_DIR}")
        return 1

    total = rewritten = 0
    for path in sorted(DATA_DIR.glob("*.json")):
        original = path.read_text(encoding="utf-8")
        rows = json.loads(original)
        changes = _apply(rows)
        # 用 git HEAD 原稿判断排版风格, 避免读到已被本脚本改写过的版本
        reference = _head_version(path) or original
        new_text = _dump(rows, reference)
        if not changes and new_text == original:
            continue
        if changes:
            print(f"[FILE] {path.name}")
            for line in changes:
                print(line)
            total += len(changes)
        elif new_text != original:
            print(f"[FILE] {path.name} (仅排版归一化)")
        if args.write and new_text != original:
            path.write_text(new_text, encoding="utf-8")
            rewritten += 1

    if not total and not rewritten:
        print("[OK] 无待修正条目 (语料已是最新分类)")
    elif args.write:
        print(f"\n[OK] 已落盘: 分类修正 {total} 条, 重写文件 {rewritten} 个")
    else:
        print(f"\n[INFO] 分类修正 {total} 条, 待重写 {rewritten} 个文件, 加 --write 落盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
