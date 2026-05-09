"""ScoreAggregator — 三层权重合并，计算加权平均分。

权重优先级（从低到高）：
  category_weights (基础) → 动态问题权重 → weight_overrides (最高)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from qag_gate.domain.models import Verdict

_OVERRIDE_MAP: Dict[str, str] = {
    "multimodal": "deliverable",
    "file_content": "deliverable",
    "completeness": "deliverable",
    "relevance": "intent_match",
    "accuracy": "quality_baseline",
    "deflection": "quality_baseline",
}


def aggregate_scores(
    verdicts: List[Verdict],
    category_weights: Dict[str, float],
    weight_overrides: Optional[Dict[str, float]] = None,
) -> Tuple[float, Dict[str, float], List[Verdict]]:
    """返回 (total_score, category_scores, failed_verdicts)。"""
    merged_weights = dict(category_weights)
    if weight_overrides:
        for dim, w in weight_overrides.items():
            mapped = _OVERRIDE_MAP.get(dim, dim)
            if mapped in merged_weights:
                merged_weights[mapped] = max(merged_weights[mapped], w)
            else:
                merged_weights[mapped] = w

    by_cat: Dict[str, List[Verdict]] = {}
    for v in verdicts:
        by_cat.setdefault(v.category, []).append(v)

    cat_scores: Dict[str, float] = {}
    weighted_sum = 0.0
    total_weight = 0.0

    for cat, vs in by_cat.items():
        cat_weighted = sum(v.weight * v.score_value for v in vs)
        cat_total_w = sum(v.weight for v in vs)
        cat_score = cat_weighted / cat_total_w if cat_total_w > 0 else 0.5
        cat_scores[cat] = cat_score

        cat_weight = merged_weights.get(cat, 1.0)
        weighted_sum += cat_score * cat_weight
        total_weight += cat_weight

    total = weighted_sum / total_weight if total_weight > 0 else 0.5
    failed = [v for v in verdicts if not v.is_positive]
    return total, cat_scores, failed
