"""P1 试点：QAG-Gate vs G-Eval，50 样本，验证方向性 Δρ ≥ 0。

通过条件：
  □ ρ(QAG-Gate, human) ≥ ρ(G-Eval, human)  → 方向正确
  □ 成本 ≤ ¥150
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


async def run_p1():
    api_key, base_url = _load_api_config()
    if not api_key:
        print("❌ OPENAI_API_KEY 未设置")
        sys.exit(1)

    tasks = {t["task_id"]: t for t in load_jsonl(DATA_DIR / "tasks.jsonl")}
    candidates = load_jsonl(DATA_DIR / "candidates.jsonl")
    human_scores = {h["candidate_id"]: h["human_score_normalized"] for h in load_jsonl(DATA_DIR / "human_scores.jsonl")}

    llm = OpenAIAdapter(model="gpt-4o-mini", api_key=api_key, base_url=base_url or None)
    evaluator = QAGEvaluator(llm_client=llm)

    print(f"P1 试点：{len(candidates)} 候选 × 2 方法 (QAG-Gate + G-Eval)")
    print("=" * 70)

    # ── Phase A: QAG-Gate ─────────────────────────────────────────────────
    print("\n[Phase A] QAG-Gate 评分...")
    qag_results = []
    sem = asyncio.Semaphore(3)

    async def _eval_qag(cand: dict):
        task_obj = tasks[cand["task_id"]]
        async with sem:
            t0 = time.time()
            try:
                result = await evaluator.evaluate(
                    task=task_obj["task"],
                    content=cand["content"],
                    context={"iteration": 2, "tools_used": [], "tool_results": []},
                )
                elapsed = time.time() - t0
                return {**cand, "qag_score": result.score, "qag_elapsed": round(elapsed, 2), "qag_error": None}
            except Exception as e:
                elapsed = time.time() - t0
                return {**cand, "qag_score": 0.5, "qag_elapsed": round(elapsed, 2), "qag_error": str(e)}

    qag_results = await asyncio.gather(*[_eval_qag(c) for c in candidates])
    for r in qag_results:
        status = "✓" if not r.get("qag_error") else "✗"
        print(f"  {status} {r['candidate_id']:12s} QAG={r['qag_score']:.3f} ({r['qag_elapsed']:.1f}s)")

    # ── Phase B: G-Eval ───────────────────────────────────────────────────
    print("\n[Phase B] G-Eval 评分 (concurrency=3)...")
    geval_samples = [{"task": tasks[c["task_id"]]["task"], "content": c["content"], **c} for c in candidates]
    geval_raw = await run_geval_batch(geval_samples, llm, concurrency=3)
    geval_map = {r["candidate_id"]: r["geval_score"] for r in geval_raw}

    for r in geval_raw:
        status = "✓" if not r.get("geval_error") else "✗"
        print(f"  {status} {r['candidate_id']:12s} G-Eval={r['geval_score']:.3f}")

    # ── Merge results ─────────────────────────────────────────────────────
    merged = []
    for r in qag_results:
        cid = r["candidate_id"]
        merged.append({
            "candidate_id": cid,
            "task_id": r["task_id"],
            "quality": r["quality"],
            "qag_score": r["qag_score"],
            "geval_score": geval_map.get(cid, 0.5),
            "human_score": human_scores[cid],
        })

    results_path = DATA_DIR / "p1_results.jsonl"
    results_path.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in merged))

    # ── Analysis ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("P1 分析")
    print("=" * 70)

    analysis = analyze(results_path, phase="p1")
    report = print_report(analysis, out_path=BENCH_DIR / "RESULT.md")
    print(report)

    # Cost estimate
    n = len(candidates)
    est_tokens = n * 1500  # QAG + G-Eval per sample
    est_cost_usd = est_tokens * 0.15 / 1_000_000 * 2  # rough estimate
    est_cost_cny = est_cost_usd * 7.2
    print(f"\n估算成本：约 ¥{est_cost_cny:.2f}（上限 ¥150）")

    go_nogo = analysis.get("go_nogo", {})
    if go_nogo.get("direction_ok"):
        print("\n🎉 P1 PASS — 可以进入 P2 核心实验（¥800）")
        return True
    else:
        print(f"\n⚠️  P1 NO-GO — {go_nogo.get('criteria', '')}")
        return False


if __name__ == "__main__":
    passed = asyncio.run(run_p1())
    sys.exit(0 if passed else 1)
