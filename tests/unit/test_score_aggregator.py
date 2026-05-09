"""单元测试 — ScoreAggregator 权重聚合。"""

import pytest

from qag_gate.checkers.score_aggregator import aggregate_scores
from qag_gate.domain.models import Verdict


def _v(category: str, score: float, weight: float = 1.0, is_positive: bool = None) -> Verdict:
    if is_positive is None:
        is_positive = score >= 0.5
    return Verdict(
        question="test?", category=category,
        answer=score >= 0.5, is_positive=is_positive,
        score_value=score, weight=weight,
    )


def test_all_yes_returns_high_score():
    verdicts = [_v("intent_match", 1.0, 1.5), _v("deliverable", 1.0, 1.5)]
    total, cats, failed = aggregate_scores(verdicts, {"intent_match": 1.5, "deliverable": 1.5})
    assert total == pytest.approx(1.0)
    assert failed == []


def test_all_no_returns_zero():
    verdicts = [_v("intent_match", 0.0, 1.0, is_positive=False)]
    total, cats, failed = aggregate_scores(verdicts, {"intent_match": 1.0})
    assert total == pytest.approx(0.0)
    assert len(failed) == 1


def test_mixed_verdicts_weighted_correctly():
    verdicts = [
        _v("intent_match", 1.0, weight=2.0),  # 高权重，yes
        _v("quality", 0.0, weight=1.0, is_positive=False),  # 低权重，no
    ]
    weights = {"intent_match": 2.0, "quality": 1.0}
    total, cats, failed = aggregate_scores(verdicts, weights)
    # intent_match: score=1.0, category_weight=2.0 → 贡献 2.0
    # quality: score=0.0, category_weight=1.0 → 贡献 0.0
    # total = 2.0 / 3.0 ≈ 0.667
    assert 0.6 < total < 0.7


def test_weight_overrides_merge_correctly():
    verdicts = [_v("deliverable", 0.8, 1.0)]
    total_no_override, _, _ = aggregate_scores(verdicts, {"deliverable": 1.0})
    total_with_override, _, _ = aggregate_scores(
        verdicts, {"deliverable": 1.0}, weight_overrides={"deliverable": 3.0}
    )
    # 权重增大但只有一个类别，结果不变（只有单类别时权重不影响归一化比例）
    assert total_no_override == pytest.approx(total_with_override)


def test_empty_verdicts_returns_half():
    total, cats, failed = aggregate_scores([], {"intent_match": 1.0})
    assert total == pytest.approx(0.5)
    assert failed == []


def test_partial_score_is_half():
    verdicts = [_v("intent_match", 0.5, 1.0)]
    total, cats, _ = aggregate_scores(verdicts, {"intent_match": 1.0})
    assert total == pytest.approx(0.5)
