"""单元测试 — detect_output_type + output-type 问题覆盖。"""

import pytest

from qag_gate.checkers.questions import BASELINE_QUESTIONS, CODE_FILE_OVERRIDE_QUESTIONS, detect_output_type
from qag_gate.domain.models import EvalQuestion


# ── detect_output_type ────────────────────────────────────────────────────────

def test_default_text_type():
    assert detect_output_type([], "普通文本内容，没有代码块") == "text"


def test_pptx_file_detected():
    result = detect_output_type([{"path": "/output/report.pptx"}], "")
    assert result == "file:pptx"


def test_docx_file_detected():
    assert detect_output_type([{"file_url": "http://x.com/doc.docx"}], "") == "file:docx"
    assert detect_output_type([{"filename": "proposal.doc"}], "") == "file:docx"


def test_xlsx_csv_detected():
    assert detect_output_type([{"path": "/data/results.xlsx"}], "") == "file:xlsx"
    assert detect_output_type([{"path": "/data/report.csv"}], "") == "file:xlsx"


def test_image_detected():
    assert detect_output_type([{"path": "/out/chart.png"}], "") == "file:image"
    assert detect_output_type([{"path": "/out/logo.svg"}], "") == "file:image"


def test_other_file_detected():
    result = detect_output_type([{"path": "/out/report.pdf"}], "")
    assert result == "file:other"


def test_file_in_output_field_detected():
    result = detect_output_type([{"output": "Saved to /files/report-v2.pdf"}], "")
    assert result == "file:other"


def test_code_block_detected():
    code_content = "这是一个分析：\n```python\nimport pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.head())\n```"
    assert detect_output_type([], code_content) == "code"


def test_short_code_block_is_text():
    short = "```python\nx=1\n```"
    assert detect_output_type([], short) == "text"


def test_non_dict_tool_result_skipped():
    # Non-dict tool results should be skipped
    result = detect_output_type(["not a dict", 42], "normal text")
    assert result == "text"


# ── output-type 问题矩阵 ───────────────────────────────────────────────────────

def test_baseline_questions_exist():
    assert len(BASELINE_QUESTIONS) >= 3
    for q in BASELINE_QUESTIONS:
        assert isinstance(q, EvalQuestion)
        assert q.text  # EvalQuestion uses .text field


def test_code_file_override_questions_exist():
    assert len(CODE_FILE_OVERRIDE_QUESTIONS) > 0
    for q in CODE_FILE_OVERRIDE_QUESTIONS:
        assert isinstance(q, EvalQuestion)
        assert q.text
