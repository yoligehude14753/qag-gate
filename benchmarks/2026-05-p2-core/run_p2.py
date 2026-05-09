"""P2 核心实验：200 任务 × 4 候选 × 2 方法 (QAG-Gate + G-Eval)。

通过条件（H1 初步验证）：
  □ Δρ = ρ(QAG) - ρ(G-Eval) ≥ 0.05
  □ ρ(QAG) ≥ 0.45（绝对值有意义）
  □ 成本 ≤ ¥800（预计实际约 ¥2-5）

支持恢复：已完成的样本会跳过，支持断点续传。
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter
from methods.geval import run_geval_batch
from methods.analyze import analyze, print_report

BENCH_DIR = Path(__file__).parent
DATA_DIR = BENCH_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_api_config():
    env_file = Path(__file__).parents[5] / "easychat/backend/.env"
    config = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                config[k.strip()] = v.strip()
    return (
        os.environ.get("OPENAI_API_KEY") or config.get("OPENAI_API_KEY", ""),
        os.environ.get("OPENAI_BASE_URL") or config.get("OPENAI_BASE_URL", ""),
    )


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def load_cache(cache_file: Path) -> dict:
    """Load previously computed scores to support resumption."""
    if cache_file.exists():
        return {r["candidate_id"]: r for r in load_jsonl(cache_file)}
    return {}


def save_cache(cache_file: Path, records: list[dict]):
    cache_file.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records))


async def run_qag_batch(
    candidates: list[dict],
    tasks: dict,
    evaluator: QAGEvaluator,
    cache: dict,
    concurrency: int = 4,
) -> list[dict]:
    """Run QAG-Gate on all candidates with concurrency and cache."""
    sem = asyncio.Semaphore(concurrency)
    results = []
    skipped = 0

    async def _one(cand):
        cid = cand["candidate_id"]
        if cid in cache:
            return {**cand, "qag_score": cache[cid]["qag_score"], "qag_cached": True}

        task_obj = tasks[cand["task_id"]]
        async with sem:
            t0 = time.time()
            for attempt in range(3):
                try:
                    result = await evaluator.evaluate(
                        task=task_obj["task"],
                        content=cand["content"],
                        context={"iteration": 2, "tools_used": [], "tool_results": []},
                    )
                    return {**cand, "qag_score": result.score, "qag_elapsed": round(time.time() - t0, 2), "qag_cached": False}
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return {**cand, "qag_score": 0.5, "qag_elapsed": round(time.time() - t0, 2), "qag_error": str(e), "qag_cached": False}

    all_tasks = [_one(c) for c in candidates]

    # Process in chunks to show progress
    chunk_size = 20
    for i in range(0, len(all_tasks), chunk_size):
        chunk = await asyncio.gather(*all_tasks[i:i + chunk_size])
        results.extend(chunk)
        done = i + len(chunk)
        cached = sum(1 for r in results if r.get("qag_cached"))
        errors = sum(1 for r in results if r.get("qag_error"))
        print(f"  QAG [{done:3d}/{len(candidates)}] cached={cached} errors={errors} ...", flush=True)
        # Save progress
        save_cache(CACHE_DIR / "qag_cache.jsonl", [r for r in results if not r.get("qag_error")])

    return results


async def run_p2():
    t_start = time.time()
    api_key, base_url = _load_api_config()
    if not api_key:
        print("❌ OPENAI_API_KEY 未设置")
        sys.exit(1)

    tasks = {t["task_id"]: t for t in load_jsonl(DATA_DIR / "tasks.jsonl")}
    candidates = load_jsonl(DATA_DIR / "candidates.jsonl")
    human_scores = {h["candidate_id"]: h["human_score_normalized"]
                    for h in load_jsonl(DATA_DIR / "human_scores.jsonl")}

    print(f"P2 核心实验：{len(candidates)} 候选 × 2 方法 (QAG-Gate + G-Eval)")
    print(f"任务分布：{len(tasks)} 任务 × 4 质量等级")
    print("=" * 70)

    llm = OpenAIAdapter(model="gpt-4o-mini", api_key=api_key, base_url=base_url or None)
    evaluator = QAGEvaluator(llm_client=llm)

    # ── QAG-Gate ──────────────────────────────────────────────────────────
    qag_cache = load_cache(CACHE_DIR / "qag_cache.jsonl")
    print(f"\n[Phase A] QAG-Gate ({len(qag_cache)} cached, {len(candidates)-len(qag_cache)} to run)")
    qag_results = await run_qag_batch(candidates, tasks, evaluator, qag_cache, concurrency=5)
    qag_map = {r["candidate_id"]: r["qag_score"] for r in qag_results}

    # ── G-Eval ────────────────────────────────────────────────────────────
    geval_cache = load_cache(CACHE_DIR / "geval_cache.jsonl")
    to_eval_geval = [c for c in candidates if c["candidate_id"] not in geval_cache]
    print(f"\n[Phase B] G-Eval ({len(geval_cache)} cached, {len(to_eval_geval)} to run, concurrency=2)")

    geval_map = {k: v["geval_score"] for k, v in geval_cache.items()}
    if to_eval_geval:
        samples = [{"task": tasks[c["task_id"]]["task"], "content": c["content"], **c}
                   for c in to_eval_geval]
        geval_raw = await run_geval_batch(samples, llm, concurrency=2, inter_batch_delay=1.5)
        for r in geval_raw:
            geval_map[r["candidate_id"]] = r["geval_score"]
        # Save G-Eval cache
        all_geval = [{**c, "geval_score": geval_map.get(c["candidate_id"], 0.5)}
                     for c in candidates]
        save_cache(CACHE_DIR / "geval_cache.jsonl", all_geval)

    print(f"  G-Eval 完成：{len(geval_map)} 条")

    # ── Merge ─────────────────────────────────────────────────────────────
    merged = []
    for cand in candidates:
        cid = cand["candidate_id"]
        merged.append({
            "candidate_id": cid,
            "task_id": cand["task_id"],
            "quality": cand["quality"],
            "task_type": cand.get("task_type", ""),
            "qag_score": qag_map.get(cid, 0.5),
            "geval_score": geval_map.get(cid, 0.5),
            "human_score": human_scores[cid],
        })

    results_path = DATA_DIR / "p2_results.jsonl"
    results_path.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in merged))

    # ── Analysis ──────────────────────────────────────────────────────────
    elapsed = time.time() - t_start
    print(f"\n{'='*70}")
    print(f"P2 分析 (耗时 {elapsed:.0f}s)")
    print("=" * 70)

    analysis = analyze(results_path, phase="p2")
    report = print_report(analysis, out_path=BENCH_DIR / "RESULT.md")
    print(report)

    # Per-task-type breakdown
    print("\n## 按任务类型分析 (QAG-Gate ρ)")
    task_types = list(set(m["task_type"] for m in merged))
    for ttype in sorted(task_types):
        subset = [m for m in merged if m["task_type"] == ttype]
        if len(subset) >= 5:
            from methods.analyze import spearman
            rho = spearman([m["qag_score"] for m in subset], [m["human_score"] for m in subset])
            print(f"  {ttype:20s}: ρ={rho:.3f}  n={len(subset)}")

    go_nogo = analysis.get("go_nogo", {})
    if go_nogo.get("h1_supported"):
        print(f"\n🎉 P2 PASS → 进入 P3 完整实验（¥2500）")
        return True
    else:
        print(f"\n⚠️  P2 NO-GO — Δρ = {analysis.get('delta_rho', 0):+.4f}（需 ≥ 0.05）")
        return False


if __name__ == "__main__":
    passed = asyncio.run(run_p2())
    sys.exit(0 if passed else 1)
