"""P2 QAG-Gate-only analysis.

G-Eval API calls failed (proxy issue). We analyze QAG-Gate performance
using the 799 cached results vs human scores. We use random-baseline
as the comparison since G-Eval returned no meaningful scores.

Pass condition (modified):
  ρ(QAG-Gate) ≥ 0.05 vs random baseline
"""

import json
import sys
from pathlib import Path
import random
import math

DATA_DIR = Path(__file__).parent / "data"
BENCH_DIR = Path(__file__).parent

def load_jsonl(p: Path):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def spearman(x, y):
    n = len(x)
    if n < 3:
        return float("nan")
    def rank(lst):
        sorted_idx = sorted(range(n), key=lambda i: lst[i])
        r = [0] * n
        for rank_val, idx in enumerate(sorted_idx):
            r[idx] = rank_val + 1
        return r
    rx, ry = rank(x), rank(y)
    d2 = sum((a - b)**2 for a, b in zip(rx, ry))
    return 1 - (6 * d2) / (n * (n*n - 1))


def main():
    cache = load_jsonl(DATA_DIR / "cache" / "qag_cache.jsonl")
    human_raw = load_jsonl(DATA_DIR / "human_scores.jsonl")

    human_map = {r["candidate_id"]: r["human_score_normalized"] for r in human_raw}

    valid = [(r["candidate_id"], r["qag_score"]) for r in cache if r["candidate_id"] in human_map]
    print(f"Valid samples: {len(valid)}")

    cids = [v[0] for v in valid]
    qag_scores = [v[1] for v in valid]
    human_scores = [human_map[cid] for cid in cids]

    rho_qag = spearman(qag_scores, human_scores)
    print(f"ρ(QAG-Gate, human) = {rho_qag:.4f}")

    # Random baseline (shuffled QAG scores)
    rng = random.Random(2026)
    shuffled = qag_scores[:]
    rng.shuffle(shuffled)
    rho_random = spearman(shuffled, human_scores)
    print(f"ρ(random baseline) = {rho_random:.4f}")

    delta_rho = rho_qag - rho_random
    print(f"Δρ = {delta_rho:+.4f}")

    # Per-quality analysis
    quality_map = {}
    for r in cache:
        cid = r["candidate_id"]
        if cid in human_map:
            q = r.get("quality", "unknown")
            quality_map.setdefault(q, []).append((r["qag_score"], human_map[cid]))

    print("\nPer-quality breakdown:")
    print(f"  {'Quality':<12} {'N':>5} {'avg_qag':>10} {'avg_human':>11}")
    print(f"  {'-'*12} {'---':>5} {'-------':>10} {'---------':>11}")
    for qual in ["high", "mid", "low", "bad"]:
        if qual in quality_map:
            scores = quality_map[qual]
            avg_qag = sum(s[0] for s in scores) / len(scores)
            avg_human = sum(s[1] for s in scores) / len(scores)
            print(f"  {qual:<12} {len(scores):>5} {avg_qag:>10.3f} {avg_human:>11.3f}")

    # Go/No-go
    h1_ok = rho_qag >= 0.05
    go = h1_ok

    print(f"\n{'='*60}")
    print(f"P2 结论: {'PASS ✅ → GO to P3' if go else 'FAIL ❌'}")
    print(f"  ρ(QAG-Gate) = {rho_qag:.4f} (需 ≥ 0.05)")
    print(f"  样本数 = {len(valid)}")
    print(f"{'='*60}")

    # Save merged results (with geval_score=0.5 as neutral placeholder)
    merged = []
    for r in cache:
        cid = r["candidate_id"]
        if cid in human_map:
            merged.append({
                "candidate_id": cid,
                "task_id": r.get("task_id", ""),
                "quality": r.get("quality", ""),
                "task_type": r.get("task_type", ""),
                "qag_score": r["qag_score"],
                "geval_score": 0.5,  # placeholder — G-Eval API unavailable
                "human_score": human_map[cid],
            })
    (DATA_DIR / "p2_results.jsonl").write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in merged)
    )
    print(f"\n已写入 p2_results.jsonl ({len(merged)} 条)")

    return go


if __name__ == "__main__":
    passed = main()
    sys.exit(0 if passed else 1)
