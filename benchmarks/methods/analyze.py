"""Benchmark analysis: Spearman ρ, Pearson r, go/no-go judgment.

Usage:
    python analyze.py --results path/to/results.jsonl --phase p1
"""

import argparse
import json
import math
from pathlib import Path
from typing import Optional


# ── Pure statistics (no numpy required) ──────────────────────────────────────

def _rank(values: list[float]) -> list[float]:
    """Compute average ranks for Spearman (handles ties)."""
    n = len(values)
    sorted_idx = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and values[sorted_idx[j]] == values[sorted_idx[i]]:
            j += 1
        avg_rank = (i + j - 1) / 2.0 + 1
        for k in range(i, j):
            ranks[sorted_idx[k]] = avg_rank
        i = j
    return ranks


def spearman(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation coefficient."""
    assert len(x) == len(y) and len(x) >= 3, "Need ≥3 paired samples"
    rx = _rank(x)
    ry = _rank(y)
    return pearson(rx, ry)


def pearson(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(x)
    assert n >= 3
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def kendall_tau(x: list[float], y: list[float]) -> float:
    """Kendall's τ-b."""
    n = len(x)
    concordant = discordant = 0
    tied_x = tied_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            sx = x[i] - x[j]
            sy = y[i] - y[j]
            if sx == 0 and sy == 0:
                tied_x += 1; tied_y += 1
            elif sx == 0:
                tied_x += 1
            elif sy == 0:
                tied_y += 1
            elif sx * sy > 0:
                concordant += 1
            else:
                discordant += 1
    pairs = n * (n - 1) / 2
    denom = math.sqrt((pairs - tied_x) * (pairs - tied_y))
    if denom == 0:
        return 0.0
    return (concordant - discordant) / denom


def bootstrap_ci(x: list[float], y: list[float], metric_fn, n_boot: int = 1000, seed: int = 42) -> tuple[float, float]:
    """95% bootstrap CI via percentile method (no scipy needed)."""
    import random
    rng = random.Random(seed)
    n = len(x)
    boot_vals = []
    for _ in range(n_boot):
        idx = [rng.randint(0, n - 1) for _ in range(n)]
        bx = [x[i] for i in idx]
        by = [y[i] for i in idx]
        try:
            boot_vals.append(metric_fn(bx, by))
        except Exception:
            pass
    boot_vals.sort()
    lo = boot_vals[int(0.025 * len(boot_vals))]
    hi = boot_vals[int(0.975 * len(boot_vals))]
    return lo, hi


# ── Analysis runner ───────────────────────────────────────────────────────────

def analyze(results_path: Path, phase: str) -> dict:
    records = [json.loads(l) for l in results_path.read_text().splitlines() if l.strip()]

    # Collect paired scores
    qag_scores = [r["qag_score"] for r in records]
    geval_scores = [r.get("geval_score") for r in records]
    human_scores = [r["human_score"] for r in records]

    has_geval = all(s is not None for s in geval_scores)

    rho_qag = spearman(qag_scores, human_scores)
    r_qag = pearson(qag_scores, human_scores)
    tau_qag = kendall_tau(qag_scores, human_scores)
    ci_qag = bootstrap_ci(qag_scores, human_scores, spearman)

    result = {
        "phase": phase,
        "n": len(records),
        "qag": {"rho": rho_qag, "r": r_qag, "tau": tau_qag, "ci95": ci_qag},
    }

    if has_geval:
        rho_geval = spearman(geval_scores, human_scores)
        r_geval = pearson(geval_scores, human_scores)
        tau_geval = kendall_tau(geval_scores, human_scores)
        ci_geval = bootstrap_ci(geval_scores, human_scores, spearman)
        delta_rho = rho_qag - rho_geval

        result["geval"] = {"rho": rho_geval, "r": r_geval, "tau": tau_geval, "ci95": ci_geval}
        result["delta_rho"] = delta_rho

        # Go/No-Go for P1
        if phase == "p1":
            direction_ok = delta_rho >= 0
            result["go_nogo"] = {
                "direction_ok": direction_ok,
                "verdict": "GO → P2" if direction_ok else "NO-GO → 修算法后重跑 P1",
                "criteria": f"Δρ = {delta_rho:+.4f} (需 ≥ 0)"
            }
        # Go/No-Go for P2
        elif phase == "p2":
            h1_ok = delta_rho >= 0.05
            result["go_nogo"] = {
                "h1_supported": h1_ok,
                "verdict": "GO → P3" if h1_ok else "NO-GO → 分析原因",
                "criteria": f"Δρ = {delta_rho:+.4f} (需 ≥ 0.05 for H1 初步支持)"
            }

    return result


def print_report(analysis: dict, out_path: Optional[Path] = None) -> str:
    phase = analysis["phase"].upper()
    n = analysis["n"]
    qag = analysis["qag"]
    lines = [
        f"# QAG-Gate Benchmark — {phase} Analysis",
        f"",
        f"N = {n} samples",
        f"",
        f"## Correlation vs Human Scores",
        f"",
        f"| Method | Spearman ρ | 95% CI | Pearson r | Kendall τ |",
        f"|--------|-----------|--------|-----------|-----------|",
        f"| QAG-Gate | {qag['rho']:.4f} | [{qag['ci95'][0]:.3f}, {qag['ci95'][1]:.3f}] | {qag['r']:.4f} | {qag['tau']:.4f} |",
    ]
    if "geval" in analysis:
        geval = analysis["geval"]
        lines.append(
            f"| G-Eval | {geval['rho']:.4f} | [{geval['ci95'][0]:.3f}, {geval['ci95'][1]:.3f}] | {geval['r']:.4f} | {geval['tau']:.4f} |"
        )
        lines += [
            f"",
            f"**Δρ (QAG − G-Eval) = {analysis['delta_rho']:+.4f}**",
        ]

    if "go_nogo" in analysis:
        gng = analysis["go_nogo"]
        lines += [
            f"",
            f"## Go/No-Go",
            f"",
            f"- 条件：{gng['criteria']}",
            f"- 结论：**{gng['verdict']}**",
        ]

    report = "\n".join(lines)
    if out_path:
        out_path.write_text(report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--phase", default="p1")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    result = analyze(Path(args.results), args.phase)
    out_path = Path(args.out) if args.out else None
    report = print_report(result, out_path)
    print(report)
    print("\nRaw JSON:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
