"""
E1 数据准备：从 FLASK chatgpt_review.jsonl 过滤 + 分层采样

过滤策略（基于 POC 发现 1）：
  排除以 commonsense_understanding / logical_correctness 为主维度的
  knowledge-intensive 样本（这类任务 QAG-Gate 无法评估事实正确性）。

  保留 readability / completeness / user_alignment 主导的
  instruction-following 样本。

分层采样：
  - Low  : flask_avg ≤ 2.0   → 100 条
  - Mid  : 2.0 < flask_avg < 4.0 → 100 条
  - High : flask_avg ≥ 4.0   → 100 条
  共 300 条，保证质量分布均匀。

输出：
  data/e1_samples.jsonl  （每条含 question_id, instruction, response,
                           flask_avg, flask_score_raw, quality_tier）
  data/e1_stats.json     （过滤统计）
"""

import json
import random
from collections import Counter
from pathlib import Path

BENCH_DIR = Path(__file__).parent
FLASK_REVIEW = BENCH_DIR.parents[3] / "poc/data/flask_chatgpt_review.jsonl"
OUT_DIR = BENCH_DIR / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 知识密集型技能（主要出现意味着该任务不适合 QAG-Gate 评估）
KNOWLEDGE_SKILLS = {
    "commonsense understanding",
    "logical correctness",
    "logical robustness",
    "mathematical correctness",
    "factual correctness",
}

# 目标技能（QAG-Gate 设计覆盖的维度）
TARGET_SKILLS = {
    "readability",
    "completeness",
    "user_alignment",
    "understandability",
    "appropriate_tone",
    "insight",
    "metacognition",
}

RANDOM_SEED = 42
N_PER_TIER  = 100


def is_suitable(record: dict) -> bool:
    """判断该样本是否适合 QAG-Gate 验证。"""
    # 过滤空回答
    if not record.get("target_txt", "").strip():
        return False

    score_dict = record.get("score", {})
    if not score_dict:
        return False

    # 排除分数全为 N/A 的
    numeric = [v for v in score_dict.values() if isinstance(v, (int, float))]
    if not numeric:
        return False

    # 技能维度分析
    skills_in_record = {k.lower().strip() for k in score_dict.keys()}

    # 排除"主要维度是知识密集型"的样本：知识维度占比 > 50%
    knowledge_count = len(skills_in_record & KNOWLEDGE_SKILLS)
    if len(skills_in_record) > 0 and knowledge_count / len(skills_in_record) > 0.5:
        return False

    return True


def load_and_filter() -> list[dict]:
    records = []
    total = 0
    with open(FLASK_REVIEW) as f:
        for line in f:
            total += 1
            d = json.loads(line)
            if not is_suitable(d):
                continue
            score_dict = d["score"]
            nums = [v for v in score_dict.values() if isinstance(v, (int, float))]
            avg = sum(nums) / len(nums)
            records.append({
                "question_id": d["question_id"],
                "instruction": d["text"],
                "response": d["target_txt"],
                "flask_avg": avg,
                "flask_score_raw": score_dict,
                "task": d.get("task", ""),
                "skills": d.get("metrics", list(score_dict.keys())),
            })
    print(f"Total records: {total}  |  After filter: {len(records)} "
          f"({len(records)/total*100:.1f}%)")
    return records


def stratified_sample(records: list[dict], n_per_tier: int, seed: int) -> list[dict]:
    rng = random.Random(seed)

    low  = [r for r in records if r["flask_avg"] <= 2.0]
    mid  = [r for r in records if 2.0 < r["flask_avg"] < 4.0]
    high = [r for r in records if r["flask_avg"] >= 4.0]

    print(f"  Low  (≤2.0): {len(low):4d} candidates → sample {min(n_per_tier, len(low))}")
    print(f"  Mid  (2-4) : {len(mid):4d} candidates → sample {min(n_per_tier, len(mid))}")
    print(f"  High (≥4.0): {len(high):4d} candidates → sample {min(n_per_tier, len(high))}")

    def _sample(pool, n):
        n = min(n, len(pool))
        return rng.sample(pool, n)

    sampled = (
        [dict(r, quality_tier="low")  for r in _sample(low,  n_per_tier)]
        + [dict(r, quality_tier="mid")  for r in _sample(mid,  n_per_tier)]
        + [dict(r, quality_tier="high") for r in _sample(high, n_per_tier)]
    )
    rng.shuffle(sampled)
    return sampled


def main():
    print("=== E1 数据准备 ===\n")

    print("[1] 加载 + 过滤 FLASK 数据 ...")
    records = load_and_filter()

    print("\n[2] 分层采样 ...")
    sampled = stratified_sample(records, N_PER_TIER, RANDOM_SEED)
    print(f"\n  最终样本: {len(sampled)} 条")

    # 统计
    tier_counts = Counter(r["quality_tier"] for r in sampled)
    avg_scores  = {tier: sum(r["flask_avg"] for r in sampled if r["quality_tier"] == tier)
                   / tier_counts[tier]
                   for tier in tier_counts}

    print(f"\n  分布统计:")
    for tier in ["low", "mid", "high"]:
        print(f"    {tier:4s}: n={tier_counts[tier]}  avg_flask={avg_scores[tier]:.3f}")

    # 保存
    out_file = OUT_DIR / "e1_samples.jsonl"
    with open(out_file, "w") as f:
        for r in sampled:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n[✓] 保存到 {out_file}")

    stats = {
        "total_flask_records": 1700,
        "after_filter": len(records),
        "filter_rate": f"{len(records)/1700*100:.1f}%",
        "sampled": len(sampled),
        "tier_counts": dict(tier_counts),
        "avg_flask_per_tier": avg_scores,
        "random_seed": RANDOM_SEED,
    }
    stats_file = OUT_DIR / "e1_stats.json"
    stats_file.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"[✓] 统计保存到 {stats_file}")


if __name__ == "__main__":
    main()
