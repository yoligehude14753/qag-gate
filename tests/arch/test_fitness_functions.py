"""Fitness Functions — 架构约束自动化检测。

按 08-arch.mdc 规则：每条架构决策对应一个可运行测试。
"""

import ast
from pathlib import Path


SRC_ROOT = Path(__file__).parent.parent.parent / "src" / "qag_gate"


def _get_imports(filepath: Path) -> list[str]:
    """提取 Python 文件的所有 import 语句目标模块。"""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _get_all_py_files(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


# ── FF-01: domain 层不依赖 infrastructure ────────────────────────────────────


def test_ff01_domain_does_not_import_infrastructure():
    """domain 层禁止导入 infrastructure 或 openai/anthropic。"""
    forbidden = {"openai", "anthropic", "httpx", "qag_gate.infrastructure"}
    domain_files = _get_all_py_files(SRC_ROOT / "domain")

    for filepath in domain_files:
        imports = _get_imports(filepath)
        for imp in imports:
            for f in forbidden:
                assert not imp.startswith(f), (
                    f"架构违规 [FF-01]: {filepath.name} 不应导入 {imp}（forbidden: {f}）"
                )


# ── FF-02: domain 层不依赖 application ──────────────────────────────────────


def test_ff02_domain_does_not_import_application():
    """domain 层禁止导入 application 层。"""
    domain_files = _get_all_py_files(SRC_ROOT / "domain")
    for filepath in domain_files:
        imports = _get_imports(filepath)
        for imp in imports:
            assert not imp.startswith("qag_gate.application"), (
                f"架构违规 [FF-02]: {filepath.name} 不应导入 application 层: {imp}"
            )


# ── FF-03: checkers 层不依赖 infrastructure ──────────────────────────────────


def test_ff03_checkers_do_not_import_infra_directly():
    """checkers 层通过 LLMClient protocol 调用 LLM，禁止直接 import openai/anthropic。"""
    forbidden = {"openai", "anthropic"}
    checker_files = _get_all_py_files(SRC_ROOT / "checkers")

    for filepath in checker_files:
        imports = _get_imports(filepath)
        for imp in imports:
            for f in forbidden:
                assert not imp.startswith(f), (
                    f"架构违规 [FF-03]: {filepath.name} 直接导入 {imp}，应通过 LLMClient protocol"
                )


# ── FF-04: 公共接口只通过 __init__.py 暴露 ────────────────────────────────────


def test_ff04_public_api_defined_in_init():
    """__init__.py 必须包含 QAGEvaluator 和 EvalResult 的导出。"""
    init_file = SRC_ROOT / "__init__.py"
    assert init_file.exists(), "__init__.py 不存在"
    content = init_file.read_text(encoding="utf-8")
    assert "QAGEvaluator" in content, "__init__.py 未导出 QAGEvaluator"
    assert "EvalResult" in content, "__init__.py 未导出 EvalResult"


# ── FF-05: 每个模块有 __init__.py ────────────────────────────────────────────


def test_ff05_all_packages_have_init():
    """每个子包都必须有 __init__.py。"""
    for subdir in ["domain", "application", "infrastructure", "checkers"]:
        init = SRC_ROOT / subdir / "__init__.py"
        assert init.exists(), f"{subdir}/__init__.py 缺失"


# ── FF-06: MockLLMClient 实现 LLMClient protocol ─────────────────────────────


def test_ff06_mock_implements_llm_protocol():
    """MockLLMClient 必须是 LLMClient protocol 的实例。"""
    from qag_gate.domain.ports import LLMClient
    from qag_gate.infrastructure import MockLLMClient

    mock = MockLLMClient()
    assert isinstance(mock, LLMClient), (
        "MockLLMClient 未实现 LLMClient protocol（缺少 complete 或 complete_json 方法）"
    )
