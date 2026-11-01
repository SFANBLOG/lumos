"""意图识别单测 (纯规则, 不依赖网络 / 大模型)."""

from __future__ import annotations

import asyncio

import pytest

from app.agent.intent import Intent, _classify_by_rules, recognize_intent


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("竞业限制有没有补偿，法律怎么规定的？", Intent.LAW_QUERY),
        ("这份合同有什么风险和坑？", Intent.RISK_ANALYSIS),
        ("老板让我签竞业协议，我该怎么谈？", Intent.NEGOTIATION),
        ("竞业限制是什么意思？", Intent.CLAUSE_EXPLAIN),
        ("公司不发工资我该怎么办，流程是什么？", Intent.PROCEDURE),
        ("你好", Intent.CHITCHAT),
        ("今天天气不错", Intent.UNKNOWN),
    ],
)
def test_rule_classification(question: str, expected: Intent) -> None:
    result = _classify_by_rules(question)
    assert result.intent is expected
    assert 0.0 <= result.confidence <= 1.0


def test_chitchat_wins_only_when_no_substantive_hit() -> None:
    # 寒暄 + 实质问题时应识别为实质意图, 而不是闲聊
    result = _classify_by_rules("你好，竞业限制法律规定要给补偿吗？")
    assert result.intent is Intent.LAW_QUERY


def test_recognize_intent_rules_only() -> None:
    # use_llm=False 确保不触发任何网络调用
    result = asyncio.run(recognize_intent("公司拖欠工资怎么仲裁？", use_llm=False))
    assert result.intent is Intent.PROCEDURE
    assert result.method == "rule"


def test_empty_question_is_unknown() -> None:
    result = asyncio.run(recognize_intent("   ", use_llm=False))
    assert result.intent is Intent.UNKNOWN
    assert result.confidence == 0.0


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("工伤赔偿标准是多少？", Intent.LAW_QUERY),
        ("加班费怎么算？", Intent.LAW_QUERY),
        ("被裁员有经济补偿吗？", Intent.LAW_QUERY),
        ("公司拖欠工资怎么办？", Intent.PROCEDURE),
        ("这份合同的霸王条款有什么风险？", Intent.RISK_ANALYSIS),
        ("劳动仲裁要准备什么证据？", Intent.PROCEDURE),
    ],
)
def test_business_terms(question: str, expected: Intent) -> None:
    assert _classify_by_rules(question).intent is expected
