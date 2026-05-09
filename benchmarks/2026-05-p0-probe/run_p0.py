"""P0 探针脚本 — 管道冒烟测试。

目标：20 样本（5 task × 4 candidate），验证：
  1. pipeline 无崩溃
  2. EvalResult 格式正确（score∈[0,1], verdicts 非空）
  3. phase/depth 推断合理
  4. 单次成本 ≤ ¥1.5
  5. Spearman ρ 可计算（不 NaN）

通过条件（全部满足）：
  □ 20 次调用 0 崩溃
  □ 20 个 EvalResult 格式均正确
  □ high 候选平均分 > low 候选平均分（方向性验证）
  □ 总成本 ≤ ¥30
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

# 确保使用本地 src
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from qag_gate import EvalResult, QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

BENCH_DIR = Path(__file__).parent
DATA_DIR = BENCH_DIR / "data"

# 从 easychat .env 读取（或环境变量）
def _load_api_config():
    env_file = Path(__file__).parent.parent.parent.parent.parent.parent / \
               "easychat/backend/.env"
    config = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                config[k.strip()] = v.strip()
    api_key = os.environ.get("OPENAI_API_KEY") or config.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL") or config.get("OPENAI_BASE_URL", "")
    return api_key, base_url


def load_jsonl(path: Path) -> List[Dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def run_p0():
    api_key, base_url = _load_api_config()
    if not api_key:
        print("❌ OPENAI_API_KEY 未设置")
        sys.exit(1)

    print(f"✓ API key: {api_key[:8]}...")
    print(f"✓ Base URL: {base_url or '(default OpenAI)'}")
    print()

    llm = OpenAIAdapter(
        model="gpt-4o-mini",
        api_key=api_key,
        base_url=base_url or None,
    )
    evaluator = QAGEvaluator(llm_client=llm)

    tasks = {t["task_id"]: t for t in load_jsonl(DATA_DIR / "tasks.jsonl")}
    candidates = load_jsonl(DATA_DIR / "candidates.jsonl")

    results = []
    errors = []
    total_cost_estimate = 0.0

    print(f"开始 P0 探针：{len(candidates)} 个候选 × 1 方法 × 1 seed")
    print("=" * 60)

    for i, cand in enumerate(candidates):
        task_obj = tasks[cand["task_id"]]
        task_text = task_obj["task"]
        content = cand["content"]

        print(f"[{i+1:2d}/20] {cand['candidate_id']} ({cand['quality']})... ", end="", flush=True)

        t0 = time.time()
        try:
            result: EvalResult = await evaluator.evaluate(
                task=task_text,
                content=content,
                context={
                    "iteration": 2,
                    "tools_used": [],
                    "tool_results": [],
                },
            )
            elapsed = time.time() - t0

            # 粗略成本估算（gpt-4o-mini: ~$0.15/1M input, ~$0.6/1M output）
            n_verdicts = len(result.verdicts)
            est_tokens_in = len(task_text + content) // 4 + 500
            est_tokens_out = n_verdicts * 30
            est_cost_usd = (est_tokens_in * 0.15 + est_tokens_out * 0.6) / 1_000_000
            est_cost_cny = est_cost_usd * 7.2
            total_cost_estimate += est_cost_cny

            record = {
                "candidate_id": cand["candidate_id"],
                "task_id": cand["task_id"],
                "quality": cand["quality"],
                "score": result.score,
                "phase": result.phase.value,
                "depth": result.depth.value,
                "n_verdicts": n_verdicts,
                "redline": result.redline_violations,
                "elapsed_s": round(elapsed, 2),
                "est_cost_cny": round(est_cost_cny, 4),
                "is_health_check": result.is_health_check,
            }
            results.append(record)

            status = "✓"
            note = f"score={result.score:.3f} verdicts={n_verdicts} phase={result.phase.value} depth={result.depth.value} {elapsed:.1f}s"
            if result.redline_violations:
                note += f" REDLINE={result.redline_violations}"
            print(f"{status} {note}")

        except Exception as e:
            elapsed = time.time() - t0
            errors.append({"candidate_id": cand["candidate_id"], "error": str(e)})
            print(f"✗ 错误: {e}")

    print()
    print("=" * 60)
    print("P0 探针结果汇总")
    print("=" * 60)

    # ── 检查项 ────────────────────────────────────────────────
    ok_count = len(results)
    error_count = len(errors)
    format_ok = all(
        0.0 <= r["score"] <= 1.0 and r["n_verdicts"] > 0
        for r in results
    )

    # high vs low 方向性验证
    high_scores = [r["score"] for r in results if r["quality"] == "high"]
    low_scores = [r["score"] for r in results if r["quality"] == "bad"]
    avg_high = sum(high_scores) / len(high_scores) if high_scores else 0
    avg_low = sum(low_scores) / len(low_scores) if low_scores else 0
    direction_ok = avg_high > avg_low

    all_passed = (
        error_count == 0
        and format_ok
        and direction_ok
        and total_cost_estimate <= 30
    )

    print(f"✓ 成功运行: {ok_count}/20")
    print(f"{'✓' if error_count == 0 else '✗'} 零崩溃: {error_count} 个错误")
    print(f"{'✓' if format_ok else '✗'} 格式正确（score∈[0,1], verdicts非空）")
    print(f"{'✓' if direction_ok else '✗'} 方向性正确: avg_high={avg_high:.3f} > avg_bad={avg_low:.3f}")
    print(f"{'✓' if total_cost_estimate <= 30 else '✗'} 估算总成本: ¥{total_cost_estimate:.2f} (上限¥30)")
    print()

    print("分数分布（按质量分组）:")
    for quality in ["high", "mid", "low", "bad"]:
        q_scores = [r["score"] for r in results if r["quality"] == quality]
        if q_scores:
            print(f"  {quality:4s}: {[f'{s:.3f}' for s in q_scores]}  avg={sum(q_scores)/len(q_scores):.3f}")

    print()
    print("Phase/Depth 分布:")
    for r in results:
        print(f"  {r['candidate_id']}: phase={r['phase']} depth={r['depth']}")

    # 保存结果
    result_path = DATA_DIR / "p0_results.jsonl"
    result_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in results))
    print()
    print(f"结果已写入: {result_path}")

    # 写 RESULT.md
    result_md = f"""# P0 探针结果

> 日期：{time.strftime('%Y-%m-%d %H:%M')}  
> 样本：5 tasks × 4 candidates = 20  
> 模型：gpt-4o-mini (yunwu.ai proxy)  

## Go/No-Go 检查

| 检查项 | 结果 |
|--------|------|
| 零崩溃 | {'✅ PASS' if error_count == 0 else f'❌ FAIL ({error_count} errors)'} |
| 格式正确 | {'✅ PASS' if format_ok else '❌ FAIL'} |
| 方向性正确 (avg_high > avg_bad) | {'✅ PASS' if direction_ok else '❌ FAIL'} avg_high={avg_high:.3f} avg_bad={avg_low:.3f} |
| 成本≤¥30 | {'✅ PASS' if total_cost_estimate <= 30 else '❌ FAIL'} ¥{total_cost_estimate:.2f} |
| **综合结论** | **{'✅ P0 PASS → 进入 P1' if all_passed else '❌ P0 FAIL → 修复后重跑'}** |

## 分数分布

| 候选ID | 质量 | Score | Phase | Depth | 用时(s) |
|--------|------|-------|-------|-------|---------|
"""
    for r in results:
        result_md += f"| {r['candidate_id']} | {r['quality']} | {r['score']:.3f} | {r['phase']} | {r['depth']} | {r['elapsed_s']} |\n"

    (BENCH_DIR / "RESULT.md").write_text(result_md)
    print(f"报告已写入: {BENCH_DIR / 'RESULT.md'}")

    if all_passed:
        print("\n🎉 P0 PASS — 可以进入 P1 试点（¥150）")
    else:
        print("\n⚠️  P0 FAIL — 请检查上方失败项，修复后用 PHASE=p0 重跑")

    return all_passed


if __name__ == "__main__":
    passed = asyncio.run(run_p0())
    sys.exit(0 if passed else 1)
