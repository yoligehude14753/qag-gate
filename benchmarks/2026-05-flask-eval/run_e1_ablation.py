"""
E1 消融实验：验证 QAG-Gate 各组件的贡献

5 个配置（每次去掉一个组件）：
  A: QAG-Gate full         （基准）
  B: - Phase-aware          → 全部当 EXECUTING phase（去掉 phase 感知）
  C: - Dynamic questions    → 置 `_skip_dynamic`，评估器内跳过 Layer 2 动态题
  D: - RedLine              → 关闭 RedLine checker（不做硬门控）
  E: - Depth-adaptive       → 固定 STANDARD depth（`_force_depth=standard`）

目标：每个组件去掉后 ρ 变化可观测。

用法：
  python run_e1_ablation.py               # 全量 5 配置
  python run_e1_ablation.py --dry-run     # 30 条
  python run_e1_ablation.py --only C_no_dynamic   # 只重跑指定配置（合并进 e1_ablation_*.json）

注意：重跑 C 前建议删除对应 cache 行文件，或用 --only 配合删 cache：`rm cache/ablation_C_no_dynamic_full.jsonl`
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from scipy.stats import spearmanr

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parents[2] / "src"))

from qag_gate import QAGEvaluator
from qag_gate.application.evaluator import QAGEvaluator as _QAGEval
from qag_gate.checkers.depth_selector import select_depth
from qag_gate.checkers.phase_detector import detect_phase
from qag_gate.domain.models import EvalDepth, EvalPhase
from qag_gate.infrastructure import OpenAIAdapter

BENCH_DIR   = ROOT
DATA_FILE   = BENCH_DIR / "data/e1_samples.jsonl"
CACHE_DIR   = BENCH_DIR / "cache"
RESULTS_DIR = BENCH_DIR / "results"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def load_api_config():
    env_file = ROOT.parents[4] / "easychat/backend/.env"
    config = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                config[k.strip()] = v.strip()
    return (config.get("YUNWU_GPT_KEY") or config.get("OPENAI_API_KEY", ""),
            config.get("YUNWU_BASE_URL", "https://yunwu.ai/v1"))


# ── 各消融 context 配置 ────────────────────────────────────────────────────────
ABLATION_CONFIGS = {
    "A_full":        {"agent_state": "delivering", "iteration": 3},
    "B_no_phase":    {"agent_state": "executing",  "iteration": 3},  # PLANNING/DELIVERING 消失
    "C_no_dynamic":  {"agent_state": "delivering", "iteration": 3, "_no_dynamic": True},
    "D_no_redline":  {"agent_state": "delivering", "iteration": 3, "_no_redline": True},
    "E_fixed_depth": {"agent_state": "delivering", "iteration": 3, "_force_standard": True},
}


async def run_ablation_config(
    samples: list[dict],
    evaluator: QAGEvaluator,
    config_name: str,
    ctx_base: dict,
    cache_file: Path,
    concurrency: int = 4,
    delay: float = 0.3,
) -> dict[int, float]:
    """运行单个消融配置，返回 {question_id: score}。"""
    cache = {}
    if cache_file.exists():
        for line in cache_file.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                cache[r["question_id"]] = r["score"]

    todo = [s for s in samples if s["question_id"] not in cache]
    if not todo:
        print(f"    [{config_name}] all cached ({len(cache)})")
        return cache

    # 内部标志（消融逻辑通过 context 传递）
    no_dynamic    = ctx_base.pop("_no_dynamic",   False)
    no_redline    = ctx_base.pop("_no_redline",   False)
    force_std     = ctx_base.pop("_force_standard", False)

    sem = asyncio.Semaphore(concurrency)
    fh  = open(cache_file, "a")

    async def _one(s: dict):
        async with sem:
            await asyncio.sleep(delay)
            ctx = dict(ctx_base)

            try:
                if no_redline:
                    # Monkey-patch: 临时禁用 RedLine
                    orig_check = evaluator._redline.check
                    evaluator._redline.check = lambda c, x: type(
                        "R", (), {"violations": [], "action": None}
                    )()
                    r = await evaluator.evaluate(
                        content=s["response"], task=s["instruction"], context=ctx)
                    evaluator._redline.check = orig_check
                elif no_dynamic:
                    # 通过 context 标记跳过动态问题
                    ctx["_skip_dynamic"] = True
                    r = await evaluator.evaluate(
                        content=s["response"], task=s["instruction"], context=ctx)
                elif force_std:
                    # 强制 STANDARD depth
                    ctx["_force_depth"] = "standard"
                    r = await evaluator.evaluate(
                        content=s["response"], task=s["instruction"], context=ctx)
                else:
                    r = await evaluator.evaluate(
                        content=s["response"], task=s["instruction"], context=ctx)
                score = r.score
            except Exception as e:
                print(f"      ERROR qid={s['question_id']}: {e}")
                score = None

            result = {"question_id": s["question_id"], "score": score}
            fh.write(json.dumps(result) + "\n")
            fh.flush()
            cache[s["question_id"]] = score
            return result

    print(f"    [{config_name}] running {len(todo)} samples ...")
    done = 0
    for bs in range(0, len(todo), 10):
        batch = todo[bs:bs + 10]
        await asyncio.gather(*[_one(s) for s in batch])
        done += len(batch)
        print(f"      {done}/{len(todo)} ...", flush=True)

    fh.close()
    return cache


def compute_corr(samples, score_cache):
    pairs = [(((r["flask_avg"] - 1) / 4.0), score_cache.get(r["question_id"]))
             for r in samples]
    valid = [(flask, qag) for flask, qag in pairs if qag is not None]
    if len(valid) < 5:
        return None, len(valid)
    flask_v, qag_v = zip(*valid)
    rho, p = spearmanr(flask_v, qag_v)
    return float(rho), len(valid)


async def main(args):
    print("=== E1 消融实验 ===\n")
    api_key, base_url = load_api_config()

    samples = []
    with open(DATA_FILE) as f:
        for line in f:
            samples.append(json.loads(line))
    if args.dry_run:
        samples = samples[:30]
        print("[DRY-RUN] 30 条\n")

    llm = OpenAIAdapter(api_key=api_key, base_url=base_url, model="gpt-4o-mini")
    evaluator = QAGEvaluator(llm_client=llm)

    suffix = "_dry" if args.dry_run else "_full"
    only = [x.strip() for x in args.only.split(",")] if args.only else None
    if only:
        bad = set(only) - set(ABLATION_CONFIGS.keys())
        if bad:
            raise SystemExit(f"未知配置名: {bad}，可选: {list(ABLATION_CONFIGS.keys())}")
        print(f"[--only] 仅运行: {only}\n")

    configs_iter = (
        [(n, ABLATION_CONFIGS[n]) for n in only]
        if only
        else list(ABLATION_CONFIGS.items())
    )

    results = {}
    for config_name, ctx in configs_iter:
        print(f"\n[{config_name}]")
        t0 = time.time()
        cache = await run_ablation_config(
            samples, evaluator, config_name,
            dict(ctx),  # copy（pop 修改原 dict 的防护）
            CACHE_DIR / f"ablation_{config_name}{suffix}.jsonl",
        )
        rho, n = compute_corr(samples, cache)
        elapsed = time.time() - t0
        results[config_name] = {"rho": rho, "n": n, "elapsed_s": round(elapsed, 1)}
        print(f"    ρ={rho:.4f}  n={n}  ({elapsed:.1f}s)" if rho is not None else
              f"    ρ=N/A  n={n}")

    out_path = RESULTS_DIR / f"e1_ablation{suffix}.json"
    if only:
        if not out_path.exists():
            raise SystemExit(
                f"缺少 {out_path}，请先不带 --only 跑完全量以生成合并基准，或从备份恢复该文件。"
            )
        merged = json.loads(out_path.read_text())
        merged.update(results)
        results = merged

    # 打印对比（按标准配置顺序）
    print("\n" + "=" * 55)
    print("  E1 Ablation Summary")
    print("=" * 55)
    base_rho = results.get("A_full", {}).get("rho")
    print(f"  {'Config':<22} {'ρ':>7}  {'Δρ vs A':>9}  {'n':>5}")
    print(f"  {'-'*48}")
    for name in ABLATION_CONFIGS:
        r = results.get(name)
        if not r:
            continue
        rho_s = f"{r['rho']:.4f}" if r.get("rho") is not None else "  N/A "
        if base_rho is not None and r.get("rho") is not None:
            delta = r["rho"] - base_rho
            delta_s = f"{delta:+.4f}"
        else:
            delta_s = "   N/A"
        print(f"  {name:<22} {rho_s:>7}  {delta_s:>9}  {r['n']:>5}")
    print("=" * 55)

    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n[Results saved to {out_path}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only",
        type=str,
        default="",
        metavar="NAME",
        help="逗号分隔，仅重跑部分配置，如 C_no_dynamic 或 A_full,C_no_dynamic",
    )
    args = parser.parse_args()
    asyncio.run(main(args))
