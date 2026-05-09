# Contributing to QAG-Gate

Thank you for considering contributing to QAG-Gate! This document explains how to set up your development environment and contribute effectively.

## Development Setup

```bash
git clone https://github.com/[org]/qag-gate.git
cd qag-gate
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
# Unit + arch tests (no API calls)
pytest tests/unit/ tests/arch/ -v

# E2E tests with mock LLM
pytest tests/e2e/ -v

# All tests
pytest tests/ -v --cov=qag_gate
```

## Code Style

We use `ruff` for linting and formatting:

```bash
pip install ruff
ruff check src/ tests/   # lint
ruff format src/ tests/  # format
```

## Making Changes

### Architecture Principles

QAG-Gate follows a layered architecture (Outside-In TDD):

```
domain/     ← Pure models, no external dependencies
checkers/   ← Business logic, depends only on domain
application/← Orchestration, depends on checkers
infrastructure/← External adapters (LLM APIs)
```

**Rules:**
- `domain/` must not import from any other layer
- `checkers/` must not directly import `openai`, `anthropic`, etc.
- All public interfaces use the `LLMClient` protocol (defined in `domain/ports.py`)

### Adding a New Checker

1. Define the data model in `domain/models.py` if needed
2. Implement in `checkers/your_checker.py`
3. Write unit tests in `tests/unit/test_your_checker.py` first (TDD)
4. Export from `checkers/__init__.py`
5. Wire into `application/evaluator.py`
6. Update architecture fitness test in `tests/arch/test_fitness_functions.py`

### Adding a New LLM Adapter

1. Implement the `LLMClient` protocol in `infrastructure/`
2. Write unit tests with `MockLLMClient`
3. Export from `infrastructure/__init__.py`

## Commit Convention

```
feat: add phase detection for multi-step agents
fix: handle empty response in RedLineChecker
test: add property tests for score aggregation
docs: update ADR-001 with P1 results
bench: add P2 core experiment results
```

## Opening a PR

1. Fork + branch from `main`
2. Make changes with tests
3. Ensure all tests pass: `pytest tests/ -v`
4. Submit PR with description of what changes and why

## Reporting Issues

For bugs, please include:
- Python version
- `pip show qag-gate` output
- Minimal reproducible example
- Expected vs actual behavior

For benchmark/evaluation questions, reference the relevant ADR in `docs/adr/`.
