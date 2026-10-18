"""
风险类别一致性守卫测试.

新增一类风险需要改: 枚举 / 抽取提示词 / 审查提示词 / 分类关键词 /
谈判话术 / 追问语料 / 法条语料 / 前端标签。**漏掉任何一处都不会报错,
只会静默降级**——例如 obedience_clause 曾长期在法条库里 0 条, 导致该
类别检索命中恒为 0, 但没有任何测试失败。

本测试把这些"静默失败"变成显式失败。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.sub_agents import extractor_agent, reviewer_agent
from app.models.analysis import RiskCategory
from app.rag import law_corpus
from app.skills import followup_suggestion, legal_analysis, negotiation

ALL_CATEGORIES: list[str] = [c.value for c in RiskCategory]

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ── 法条语料覆盖 ────────────────────────────────────────────────


def _corpus_category_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for law in law_corpus.ALL_LAWS:
        cat = law.get("category")
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    return counts


def test_every_category_has_corpus_entries() -> None:
    """每个类别在法条库里至少要有 1 条条文, 否则该类检索命中恒为 0."""
    counts = _corpus_category_counts()
    missing = {c: counts.get(c, 0) for c in ALL_CATEGORIES if counts.get(c, 0) == 0}
    assert not missing, f"以下类别在法条库中没有条文, 检索命中恒为 0: {missing}"


def test_expanded_categories_have_multiple_provisions() -> None:
    """扩充的 6 类仲裁高发案由至少各有 2 条条文 (单条不足以支撑分类)."""
    counts = _corpus_category_counts()
    expanded = [
        "unlawful_termination", "severance_pay", "no_written_contract",
        "overtime_pay", "illegal_penalty", "deposit_guarantee",
    ]
    thin = {c: counts.get(c, 0) for c in expanded if counts.get(c, 0) < 2}
    assert not thin, f"以下扩充类别条文过少: {thin}"


# ── 技能层覆盖 ──────────────────────────────────────────────────


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_legal_analysis_keywords_cover_all_categories(category: str) -> None:
    assert category in legal_analysis._CATEGORY_KEYWORDS, (
        f"{category} 缺少分类关键词, 规则分类永远命中不了"
    )


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_negotiation_templates_cover_all_categories(category: str) -> None:
    assert category in negotiation._TEMPLATES, (
        f"{category} 缺少谈判话术, 会静默落到默认模板"
    )


@pytest.mark.parametrize("category", ALL_CATEGORIES)
def test_followups_cover_all_categories(category: str) -> None:
    assert RiskCategory(category) in followup_suggestion._FOLLOWUPS, (
        f"{category} 缺少追问语料, 会静默落到兜底话术"
    )


# ── 提示词覆盖 ──────────────────────────────────────────────────


def test_extractor_prompt_lists_all_categories() -> None:
    prompt = extractor_agent.EXTRACTOR_SYSTEM_PROMPT
    missing = [c for c in ALL_CATEGORIES if f"- {c}:" not in prompt]
    assert not missing, f"抽取提示词缺少类别: {missing}"
    assert f"{len(ALL_CATEGORIES)} 类风险" in prompt, (
        "抽取提示词里的类别总数与实际枚举数不一致"
    )


def test_reviewer_prompt_lists_all_categories() -> None:
    prompt = reviewer_agent.REVIEWER_SYSTEM_PROMPT
    section = prompt.split("## 风险分类")[1].split("##")[0]
    missing = [c for c in ALL_CATEGORIES if c not in section]
    assert not missing, f"审查提示词缺少类别: {missing}"


# ── 前端标签覆盖 ────────────────────────────────────────────────


def test_frontend_category_labels_cover_all_categories() -> None:
    ts = _REPO_ROOT / "front" / "src" / "utils" / "contractMeta.ts"
    if not ts.exists():
        pytest.skip("前端源码不在当前检出中")
    text = ts.read_text(encoding="utf-8")
    missing = [c for c in ALL_CATEGORIES if f"{c}:" not in text]
    assert not missing, f"front/src/utils/contractMeta.ts 缺少中文标签: {missing}"


def test_mcp_view_labels_cover_all_categories() -> None:
    """MCPView.vue 里独立重复维护了一份类别集合, 新增时最容易漏改."""
    vue = _REPO_ROOT / "front" / "src" / "views" / "MCPView.vue"
    if not vue.exists():
        pytest.skip("前端源码不在当前检出中")
    text = vue.read_text(encoding="utf-8")
    missing = [c for c in ALL_CATEGORIES if f"'{c}'" not in text]
    assert not missing, f"MCPView.vue 缺少类别: {missing}"


# ── 基本约束 ────────────────────────────────────────────────────


def test_category_values_are_unique() -> None:
    assert len(set(ALL_CATEGORIES)) == len(ALL_CATEGORIES)


def test_eval_category_dirs_are_valid_categories() -> None:
    """评测集映射的目标必须是合法类别 (否则金标准永远命中不了)."""
    from eval.retrieval_eval import _CATEGORY_DIRS

    invalid = {k: v for k, v in _CATEGORY_DIRS.items() if v not in ALL_CATEGORIES}
    assert not invalid, f"评测映射指向了非法的类别: {invalid}"
