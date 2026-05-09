"""内置问题库 — 三层架构的 Layer 1（baseline）与 output-type override。

Layer 1: BASELINE_QUESTIONS — 任务类型无关，始终存在（6 条）
Layer 2: 由 CriteriaGenerator（LLM）动态生成，见 criteria_generator.py
Layer 3: output-type-aware override，根据产物类型替换 factual_accuracy 类问题
"""

from __future__ import annotations

from typing import Dict, List

from qag_gate.domain.models import EvalQuestion

# ── Layer 1: 通用基线问题（始终存在）────────────────────────────────────

BASELINE_QUESTIONS: List[EvalQuestion] = [
    EvalQuestion(
        "Does the output directly address what the user asked for?",
        category="intent_match", weight=1.5,
    ),
    EvalQuestion(
        "Does the output contain a concrete, usable deliverable "
        "(text answer, file, code, data, etc.) rather than only describing what could be done?",
        category="deliverable", weight=1.5,
    ),
    EvalQuestion(
        "Is the output free of obvious errors, broken content, or incomplete artifacts?",
        category="quality_baseline", weight=1.0,
    ),
    EvalQuestion(
        "Can the user directly use this output without significant additional work?",
        category="actionability", weight=1.0,
    ),
    EvalQuestion(
        "Are all dates, time periods, and temporal references in the output consistent with "
        "the real current date (not based on stale training data)?",
        category="temporal_reality", weight=1.5,
    ),
    EvalQuestion(
        "Are all numbers, statistics, and data points in the output physically plausible "
        "and consistent with real-world constraints?",
        category="physical_consistency", weight=1.5,
    ),
]

BASELINE_WEIGHTS: Dict[str, float] = {
    "intent_match": 1.5,
    "deliverable": 1.5,
    "quality_baseline": 1.0,
    "actionability": 1.0,
    "temporal_reality": 1.5,
    "physical_consistency": 1.5,
}

# ── 文件/研究类任务附加问题 ────────────────────────────────────────────

STRUCTURAL_COMPLETENESS_QUESTIONS: List[EvalQuestion] = [
    EvalQuestion(
        "Are all generated charts/figures embedded in the output using image syntax?",
        category="structural_completeness", weight=1.2,
    ),
    EvalQuestion(
        "Does the output include a references/bibliography section with real citations?",
        category="structural_completeness", weight=1.0,
    ),
    EvalQuestion(
        "Does the output discuss and interpret data analysis results with specific numbers?",
        category="structural_completeness", weight=1.2,
    ),
]

# ── Layer 3: output-type override（code / file 类任务替换 factual_accuracy）────

CODE_FILE_OVERRIDE_QUESTIONS: List[EvalQuestion] = [
    EvalQuestion(
        "Did the code/tool execute successfully and produce the expected output files?",
        category="code_completeness", weight=1.5,
    ),
    EvalQuestion(
        "Were non-empty data files or artifacts actually generated?",
        category="data_quality", weight=1.0,
    ),
]

# ── output_type 检测 ───────────────────────────────────────────────────

def detect_output_type(tool_results: List[dict], content: str) -> str:
    """返回 text | code | file:pptx | file:docx | file:xlsx | file:image | file:other"""
    for r in (tool_results or []):
        if not isinstance(r, dict):
            continue
        # 检查是否产出了特定文件类型
        for key in ("path", "file_url", "filename"):
            val = r.get(key, "")
            if val:
                lower = str(val).lower()
                if lower.endswith(".pptx"):
                    return "file:pptx"
                if lower.endswith((".docx", ".doc")):
                    return "file:docx"
                if lower.endswith((".xlsx", ".xls", ".csv")):
                    return "file:xlsx"
                if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
                    return "file:image"
                if "." in lower.split("/")[-1]:
                    return "file:other"

        # 检查 output 里的文件路径
        output = str(r.get("output", ""))
        import re
        if re.search(r'/files/[\w\-./]+\.\w+', output):
            return "file:other"

    # 检查 content 里是否有代码块（>= 30 字符即算）
    import re
    if re.search(r'```[\w]*\n[\s\S]{30,}?```', content):
        return "code"

    return "text"
