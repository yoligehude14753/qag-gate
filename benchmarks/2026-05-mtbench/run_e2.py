"""
E2：MT-Bench Pairwise 对齐验证

策略：
  对同一 MT-Bench 问题的两个模型回答，
  QAG-Gate 分高的模型是否=人类偏好模型。

  Accuracy = #{QAG 预测正确} / #{有明确获胜者的对}

门控：accuracy ≥ 65%（随机=50%）

数据：
  - mt_bench_questions.jsonl （80 题，取 writing+reasoning 共 ~40 题）
  - mt_bench_human.parquet   （3355 条 pairwise 人工评分）
  - 模型回答从 MT-Bench 问题的 conversation_a/b 中提取

用法：
  python run_e2.py
  python run_e2.py --dry-run   # 仅 20 对
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
WORKSPACE = ROOT.parents[4]   # /Desktop/all
sys.path.insert(0, str(WORKSPACE / "openall/projects/qag-gate/src"))

DATA_DIR    = ROOT / "data"
RESULTS_DIR = ROOT / "results"
CACHE_DIR   = ROOT / "cache"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

POC_DATA    = WORKSPACE / "openall/poc/data"

TARGET_CATEGORIES = {"writing", "reasoning", "roleplay", "stem"}


def load_api_config():
    env_file = WORKSPACE / "easychat/backend/.env"
    config = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                config[k.strip()] = v.strip()
    return (config.get("YUNWU_GPT_KEY") or config.get("OPENAI_API_KEY", ""),
            config.get("YUNWU_BASE_URL", "https://yunwu.ai/v1"))


def load_questions() -> dict[int, dict]:
    qfile = POC_DATA / "mt_bench_questions.jsonl"
    questions = {}
    with open(qfile) as f:
        for line in f:
            d = json.loads(line)
            questions[d["question_id"]] = d
    return questions


def extract_pairs(n_max: int | None = None) -> list[dict]:
    """从 MT-Bench human parquet 提取 (question, response_a, response_b, winner) 对。"""
    df = pd.read_parquet(POC_DATA / "mt_bench_human.parquet")
    questions = load_questions()

    # 只取 turn=1（第一轮），有明确获胜者
    df = df[df["turn"] == 1]
    df = df[df["winner"].isin(["model_a", "model_b"])]

    # 只取目标类别
    target_qids = {qid for qid, q in questions.items()
                   if q.get("category", "").lower() in TARGET_CATEGORIES}
    df = df[df["question_id"].isin(target_qids)]

    pairs = []
    for _, row in df.iterrows():
        qid = row["question_id"]
        q   = questions.get(qid, {})
        instruction = q.get("turns", [""])[0] if q.get("turns") else ""

        # 提取第一轮助手回答（parquet 可能返回 numpy array 或 list）
        def _to_list(conv):
            if conv is None:
                return []
            if isinstance(conv, list):
                return conv
            try:
                return list(conv)
            except Exception:
                return []

        conv_a = _to_list(row["conversation_a"])
        conv_b = _to_list(row["conversation_b"])
        resp_a = next((m["content"] for m in conv_a
                       if isinstance(m, dict) and m.get("role") == "assistant"), "")
        resp_b = next((m["content"] for m in conv_b
                       if isinstance(m, dict) and m.get("role") == "assistant"), "")

        if not resp_a.strip() or not resp_b.strip():
            continue

        pairs.append({
            "question_id":  qid,
            "instruction":  instruction,
            "response_a":   resp_a,
            "response_b":   resp_b,
            "model_a":      row["model_a"],
            "model_b":      row["model_b"],
            "human_winner": row["winner"],  # "model_a" or "model_b"
            "category":     q.get("category", ""),
        })

    # 去重：每对 (question_id, model_a, model_b) 取一条（多个评委取第一条）
    seen = set()
    deduped = []
    for p in pairs:
        key = (p["question_id"], p["model_a"], p["model_b"])
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    print(f"Extracted {len(deduped)} unique pairs "
          f"(from {len(pairs)} raw, categories: {TARGET_CATEGORIES})")
    return deduped[:n_max] if n_max else deduped


async def score_pair(pair: dict, evaluator, cache: dict, cache_fh) -> dict:
    """对一对回答都用 QAG-Gate 打分，返回 qag_winner。"""
    ctx = {"agent_state": "delivering", "iteration": 3}

    async def _score(response, key):
        if key in cache:
            return cache[key]
        try:
            r = await evaluator.evaluate(
                content=response, task=pair["instruction"], context=ctx)
            score = r.score
        except Exception as e:
            print(f"  ERROR {key}: {e}")
            score = None
        cache[key] = score
        if cache_fh:
            cache_fh.write(json.dumps({key: score}) + "\n")
            cache_fh.flush()
        return score

    key_a = f"qid{pair['question_id']}_{pair['model_a']}"
    key_b = f"qid{pair['question_id']}_{pair['model_b']}"
    score_a, score_b = await asyncio.gather(_score(pair["response_a"], key_a),
                                             _score(pair["response_b"], key_b))

    if score_a is None or score_b is None:
        qag_winner = None
    elif score_a > score_b + 0.02:
        qag_winner = "model_a"
    elif score_b > score_a + 0.02:
        qag_winner = "model_b"
    else:
        qag_winner = "tie"

    return {
        **pair,
        "score_a": score_a,
        "score_b": score_b,
        "qag_winner": qag_winner,
        "correct": (qag_winner == pair["human_winner"]) if qag_winner and qag_winner != "tie" else None,
    }


async def main(args):
    print("=== E2: MT-Bench Pairwise 对齐验证 ===\n")
    api_key, base_url = load_api_config()

    from qag_gate import QAGEvaluator
    from qag_gate.infrastructure import OpenAIAdapter
    llm = OpenAIAdapter(api_key=api_key, base_url=base_url, model="gpt-4o-mini")
    evaluator = QAGEvaluator(llm_client=llm)

    # 加载对
    n_max = 20 if args.dry_run else None
    pairs = extract_pairs(n_max)
    print(f"使用 {len(pairs)} 对\n")

    # 加载缓存
    suffix = "_dry" if args.dry_run else "_full"
    cache_file = CACHE_DIR / f"e2_scores{suffix}.jsonl"
    cache = {}
    if cache_file.exists():
        for line in cache_file.read_text().splitlines():
            if line.strip():
                cache.update(json.loads(line))
    print(f"缓存命中: {len(cache)} 分数\n")

    # 逐对评分（concurrency=4）
    sem   = asyncio.Semaphore(4)
    fh    = open(cache_file, "a")
    results = []

    async def _one(p):
        async with sem:
            await asyncio.sleep(0.3)
            return await score_pair(p, evaluator, cache, fh)

    done = 0
    for bs in range(0, len(pairs), 8):
        batch = pairs[bs:bs + 8]
        batch_results = await asyncio.gather(*[_one(p) for p in batch])
        results.extend(batch_results)
        done += len(batch)
        print(f"  {done}/{len(pairs)} ...", flush=True)

    fh.close()

    # 分析
    decisive  = [r for r in results if r.get("qag_winner") not in (None, "tie")]
    correct   = [r for r in decisive if r["correct"]]
    accuracy  = len(correct) / len(decisive) if decisive else 0.0

    # 按类别拆分
    cat_stats = {}
    for cat in TARGET_CATEGORIES:
        c_all  = [r for r in decisive if r["category"] == cat]
        c_corr = [r for r in c_all if r["correct"]]
        cat_stats[cat] = {"n": len(c_all), "correct": len(c_corr),
                          "accuracy": len(c_corr) / len(c_all) if c_all else None}

    go = accuracy >= 0.65

    print("\n" + "=" * 55)
    print("  E2 Results")
    print("=" * 55)
    print(f"  总对数        : {len(results)}")
    print(f"  决定性预测    : {len(decisive)}")
    print(f"  Accuracy      : {accuracy:.3f}  (需 ≥ 0.65)")
    print(f"\n  Per-category accuracy:")
    for cat, s in cat_stats.items():
        acc_s = f"{s['accuracy']:.3f}" if s["accuracy"] is not None else " N/A"
        print(f"    {cat:12s}: {s['correct']}/{s['n']}  = {acc_s}")
    verdict = "✅  GO" if go else "❌  NO-GO"
    print(f"\n  门控结论: {verdict}")
    print("=" * 55)

    # 保存
    out = {"accuracy": accuracy, "n_total": len(results),
           "n_decisive": len(decisive), "n_correct": len(correct),
           "cat_stats": cat_stats, "go": go}
    (RESULTS_DIR / f"e2_analysis{suffix}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    with open(RESULTS_DIR / f"e2_rows{suffix}.jsonl", "w") as f:
        for r in results:
            row = {k: v for k, v in r.items()
                   if k not in ("response_a", "response_b")}  # 省略长文本
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n[Results saved to {RESULTS_DIR}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args))
