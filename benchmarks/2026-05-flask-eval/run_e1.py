"""
E1 主实验：QAG-Gate × FLASK 外部验证

比较三种方法对 FLASK GPT-4 分数的 Spearman ρ：
  - QAG-Gate (full)
  - G-Eval (GPT-4o-mini)
  - Static Rubric (5 条硬编码标准，零 LLM)

门控：ρ(QAG-Gate) ≥ 0.50 且 Δρ(QAG - G-Eval) ≥ 0.05 → PASS

用法：
  python run_e1.py              # 全量 279 条
  python run_e1.py --dry-run    # 仅跑前 30 条验证管道
  python run_e1.py --method qag # 单独跑某方法（断点续传）
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import kendalltau, spearmanr

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parents[2] / "src"))
sys.path.insert(0, str(ROOT.parent / "methods"))

from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter
from geval import geval_score

BENCH_DIR   = ROOT
DATA_FILE   = BENCH_DIR / "data/e1_samples.jsonl"
CACHE_DIR   = BENCH_DIR / "cache"
RESULTS_DIR = BENCH_DIR / "results"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

QAG_CONTEXT = {"agent_state": "delivering", "iteration": 3}

# ── API 配置 ───────────────────────────────────────────────────────────────────
def load_api_config() -> tuple[str, str]:
    env_file = ROOT.parents[4] / "easychat/backend/.env"
    config = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                config[k.strip()] = v.strip()
    api_key  = config.get("YUNWU_GPT_KEY") or config.get("OPENAI_API_KEY", "")
    base_url = config.get("YUNWU_BASE_URL", "https://yunwu.ai/v1")
    return api_key, base_url


# ── Static Rubric（零 LLM 基线）──────────────────────────────────────────────
_RUBRIC_KEYWORDS = {
    "complete":    ["complete", "comprehensive", "thorough", "all", "fully"],
    "clear":       ["clear", "concise", "readable", "well-structured", "organized"],
    "relevant":    ["relevant", "appropriate", "addresses", "task", "question"],
    "accurate":    ["accurate", "correct", "precise", "exact"],
    "helpful":     ["helpful", "useful", "informative", "practical"],
}

def static_rubric_score(content: str) -> float:
    """Heuristic: score based on length + keyword presence (no LLM)."""
    if not content or len(content.strip()) < 20:
        return 0.0
    text = content.lower()
    words = set(text.split())
    matched = sum(
        1 for kw_list in _RUBRIC_KEYWORDS.values()
        if any(kw in text for kw in kw_list)
    )
    # Length score: 50-500 chars = good; too short or too long = penalty
    length = len(content.strip())
    length_score = min(1.0, length / 300) if length < 300 else max(0.5, 1.0 - (length - 300) / 2000)
    keyword_score = matched / len(_RUBRIC_KEYWORDS)
    return round(0.4 * length_score + 0.6 * keyword_score, 4)


# ── QAG-Gate 评分 ─────────────────────────────────────────────────────────────
async def run_qag_batch(
    samples: list[dict],
    evaluator: QAGEvaluator,
    cache_file: Path,
    concurrency: int = 3,
    delay: float = 0.5,
) -> dict[int, float]:
    """返回 {question_id: score}，支持断点续传。"""
    cache = {}
    if cache_file.exists():
        for line in cache_file.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                cache[r["question_id"]] = r["qag_score"]
    print(f"  [QAG-Gate] cache hits: {len(cache)}/{len(samples)}")

    todo = [s for s in samples if s["question_id"] not in cache]
    if not todo:
        return cache

    sem = asyncio.Semaphore(concurrency)
    fh  = open(cache_file, "a")

    async def _one(s: dict):
        async with sem:
            await asyncio.sleep(delay)
            try:
                r = await evaluator.evaluate(
                    content=s["response"],
                    task=s["instruction"],
                    context=QAG_CONTEXT,
                )
                score = r.score
            except Exception as e:
                print(f"    QAG ERROR qid={s['question_id']}: {e}")
                score = None
            result = {"question_id": s["question_id"], "qag_score": score}
            fh.write(json.dumps(result) + "\n")
            fh.flush()
            cache[s["question_id"]] = score
            return result

    done = 0
    for batch_start in range(0, len(todo), 10):
        batch = todo[batch_start:batch_start + 10]
        await asyncio.gather(*[_one(s) for s in batch])
        done += len(batch)
        print(f"  [QAG-Gate] {done}/{len(todo)} done "
              f"(+{len(cache)} cached) ...", flush=True)

    fh.close()
    return cache


# ── G-Eval 评分 ───────────────────────────────────────────────────────────────
async def run_geval_batch_e1(
    samples: list[dict],
    llm,
    cache_file: Path,
    concurrency: int = 2,
    delay: float = 1.2,
) -> dict[int, float]:
    """返回 {question_id: score}，支持断点续传。"""
    cache = {}
    if cache_file.exists():
        for line in cache_file.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                cache[r["question_id"]] = r["geval_score"]
    print(f"  [G-Eval] cache hits: {len(cache)}/{len(samples)}")

    todo = [s for s in samples if s["question_id"] not in cache]
    if not todo:
        return cache

    sem = asyncio.Semaphore(concurrency)
    fh  = open(cache_file, "a")

    async def _one(s: dict):
        async with sem:
            await asyncio.sleep(delay)
            r = await geval_score(s["instruction"], s["response"], llm)
            score = r.get("score", 0.5)
            result = {"question_id": s["question_id"], "geval_score": score,
                      "geval_error": r.get("error")}
            fh.write(json.dumps(result) + "\n")
            fh.flush()
            cache[s["question_id"]] = score
            return result

    done = 0
    for batch_start in range(0, len(todo), 6):
        batch = todo[batch_start:batch_start + 6]
        await asyncio.gather(*[_one(s) for s in batch])
        done += len(batch)
        print(f"  [G-Eval] {done}/{len(todo)} done "
              f"(+{len(cache)} cached) ...", flush=True)

    fh.close()
    return cache


# ── 分析 & 报告 ────────────────────────────────────────────────────────────────
def analyze(samples: list[dict],
            qag_cache: dict, geval_cache: dict) -> dict:
    rows = []
    for s in samples:
        qag   = qag_cache.get(s["question_id"])
        geval = geval_cache.get(s["question_id"])
        rows.append({
            **s,
            "qag_score":   qag,
            "geval_score": geval,
            "rubric_score": static_rubric_score(s["response"]),
            "flask_norm":  (s["flask_avg"] - 1) / 4.0,  # 1-5 → 0-1
        })

    valid_qag   = [(r["flask_norm"], r["qag_score"])   for r in rows if r["qag_score"] is not None]
    valid_geval = [(r["flask_norm"], r["geval_score"])  for r in rows if r["geval_score"] is not None]
    valid_rub   = [(r["flask_norm"], r["rubric_score"]) for r in rows]

    def _corr(pairs):
        if len(pairs) < 5:
            return {"rho": None, "tau": None, "n": len(pairs)}
        x, y = zip(*pairs)
        rho, p_rho = spearmanr(x, y)
        tau, p_tau = kendalltau(x, y)
        return {"rho": float(rho), "p_rho": float(p_rho),
                "tau": float(tau), "p_tau": float(p_tau), "n": len(pairs)}

    qag_corr   = _corr(valid_qag)
    geval_corr = _corr(valid_geval)
    rub_corr   = _corr(valid_rub)

    rho_qag  = qag_corr.get("rho")
    rho_gev  = geval_corr.get("rho")
    delta_rho = (rho_qag - rho_gev) if (rho_qag is not None and rho_gev is not None) else None

    # Per-tier breakdown
    tier_stats = {}
    for tier in ["low", "mid", "high"]:
        t_pairs = [(r["flask_norm"], r["qag_score"])
                   for r in rows
                   if r["quality_tier"] == tier and r["qag_score"] is not None]
        tier_stats[tier] = _corr(t_pairs)

    go = (rho_qag is not None and rho_qag >= 0.50 and
          delta_rho is not None and delta_rho >= 0.05)

    return {
        "qag_corr":   qag_corr,
        "geval_corr": geval_corr,
        "rubric_corr": rub_corr,
        "delta_rho":  delta_rho,
        "tier_stats": tier_stats,
        "go":         go,
        "rows":       rows,
    }


def print_report(result: dict, is_dry_run: bool = False):
    note = " [DRY-RUN 30条]" if is_dry_run else ""
    print("\n" + "=" * 65)
    print(f"  E1 Results{note}")
    print("=" * 65)

    qag  = result["qag_corr"]
    gev  = result["geval_corr"]
    rub  = result["rubric_corr"]
    delt = result["delta_rho"]

    print(f"  {'Method':<20} {'ρ':>7}  {'p':>7}  {'τ':>7}  {'n':>5}")
    print(f"  {'-'*50}")
    for name, c in [("QAG-Gate (full)", qag), ("G-Eval", gev), ("Static Rubric", rub)]:
        rho_s = f"{c['rho']:.4f}" if c.get("rho") is not None else "  N/A "
        p_s   = f"{c['p_rho']:.4f}" if c.get("p_rho") is not None else "  N/A "
        tau_s = f"{c['tau']:.4f}" if c.get("tau") is not None else "  N/A "
        print(f"  {name:<20} {rho_s:>7}  {p_s:>7}  {tau_s:>7}  {c['n']:>5}")

    print(f"\n  Δρ (QAG - G-Eval) = {delt:.4f}" if delt is not None else "\n  Δρ = N/A")

    print(f"\n  Per-tier ρ(QAG-Gate):")
    for tier in ["low", "mid", "high"]:
        ts = result["tier_stats"].get(tier, {})
        rho_s = f"{ts['rho']:.4f}" if ts.get("rho") is not None else "N/A"
        print(f"    {tier:5s}: ρ={rho_s}  n={ts.get('n','?')}")

    verdict = "✅  GO  → 进入 E2 + E3 + E4" if result["go"] else "❌  NO-GO → 分析失败原因，调整后重跑"
    print(f"\n  门控结论: {verdict}")
    print("=" * 65)


# ── Main ─────────────────────────────────────────────────────────────────────
async def main(args):
    print("=== E1: QAG-Gate × FLASK 外部验证 ===\n")

    api_key, base_url = load_api_config()
    print(f"API: {base_url}  key={api_key[:8]}...\n")

    # 加载数据
    samples = []
    with open(DATA_FILE) as f:
        for line in f:
            samples.append(json.loads(line))

    if args.dry_run:
        samples = samples[:30]
        print(f"[DRY-RUN] 使用前 30 条样本\n")

    print(f"样本数: {len(samples)}\n")

    llm = OpenAIAdapter(api_key=api_key, base_url=base_url, model="gpt-4o-mini")
    evaluator = QAGEvaluator(llm_client=llm)

    run_qag   = args.method in ("all", "qag")
    run_geval = args.method in ("all", "geval")

    suffix = "_dry" if args.dry_run else ""

    # ── QAG-Gate ──
    if run_qag:
        print("[1/3] QAG-Gate ...")
        t0 = time.time()
        qag_cache = await run_qag_batch(
            samples, evaluator,
            CACHE_DIR / f"qag_cache{suffix}.jsonl",
            concurrency=4,
            delay=0.3,
        )
        print(f"  完成: {time.time()-t0:.1f}s\n")
    else:
        qag_cache = {}
        cache_f = CACHE_DIR / f"qag_cache{suffix}.jsonl"
        if cache_f.exists():
            for line in cache_f.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    qag_cache[r["question_id"]] = r["qag_score"]
        print(f"[1/3] QAG-Gate: 跳过，加载缓存 {len(qag_cache)} 条\n")

    # ── G-Eval ──
    if run_geval:
        print("[2/3] G-Eval ...")
        t0 = time.time()
        geval_cache = await run_geval_batch_e1(
            samples, llm,
            CACHE_DIR / f"geval_cache{suffix}.jsonl",
            concurrency=3,
            delay=0.8,
        )
        print(f"  完成: {time.time()-t0:.1f}s\n")
    else:
        geval_cache = {}
        cache_f = CACHE_DIR / f"geval_cache{suffix}.jsonl"
        if cache_f.exists():
            for line in cache_f.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    geval_cache[r["question_id"]] = r["geval_score"]
        print(f"[2/3] G-Eval: 跳过，加载缓存 {len(geval_cache)} 条\n")

    # ── Static Rubric ──（同步，无需 API）
    print("[3/3] Static Rubric ... (sync, no LLM)\n")

    # ── 分析 ──
    print("[4/4] 分析 ...")
    result = analyze(samples, qag_cache, geval_cache)

    # 保存结果
    result_rows = result.pop("rows")
    suffix_out = "_dry" if args.dry_run else "_full"
    (RESULTS_DIR / f"e1_analysis{suffix_out}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    with open(RESULTS_DIR / f"e1_rows{suffix_out}.jsonl", "w") as f:
        for row in result_rows:
            # flask_score_raw 可能含字符串，简单序列化
            row_out = {k: v for k, v in row.items() if k != "flask_score_raw"}
            row_out["flask_score_raw"] = str(row.get("flask_score_raw", ""))
            f.write(json.dumps(row_out, ensure_ascii=False) + "\n")

    print_report(result, is_dry_run=args.dry_run)
    print(f"\n[Results saved to {RESULTS_DIR}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Only run first 30 samples to validate pipeline")
    parser.add_argument("--method", choices=["all", "qag", "geval"], default="all",
                        help="Which method(s) to run (default: all)")
    args = parser.parse_args()
    asyncio.run(main(args))
