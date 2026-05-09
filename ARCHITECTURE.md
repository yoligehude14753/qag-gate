# qag-gate · ARCHITECTURE

> 版本：v1.0 · 日期：2026-05-08

---

## 一、统一哲学

**模块边界 = 用户视角的可观察单元**：每个模块对应论文中一个可独立讨论的章节、CLI 中一个可独立调用的子命令、benchmark 中一组可独立测量的指标。

---

## 二、业务域识别（三步法）

### 1. 业务名词提取

从 PRD 提取的核心名词：
- **Task** — 用户给 agent 的任务描述
- **Content** — agent 当前迭代的输出
- **Verdict** — 一个 binary 判定（question + answer + reason）
- **Question** — 评估问题（baseline / dynamic / structural）
- **Score** — 加权聚合分（0-1）
- **Phase** — 阶段（planning / executing / delivering）
- **Depth** — 深度（fast / standard / deep）
- **HardGate** — 硬性失败（不参与评分，但触发 retry）
- **RedLine** — 语义红线（推脱、伪造等）
- **DeliverableSpec** — 期望交付物的清单

### 2. 语言分歧检测

| 词 | 不同含义 | → 模块边界 |
|----|---------|----------|
| "Score" | 单题分（0/0.5/1）vs 加权总分（0-1） | `Verdict.score_value` vs `EvalResult.score` 必须分开 |
| "Question" | 静态库问题 vs LLM 动态生成 vs deliverable 派生 | 三种 question 来源各自独立模块 |
| "Phase" | agent 内部状态 vs 评估器看到的 phase | 评估器 phase 通过启发式从外部 metadata 推断，不依赖 agent 内部 |

### 3. 数据归属

| 数据 | 唯一写入方 |
|------|----------|
| `Verdict` | `BinaryJudge` 模块 |
| `Score` 聚合 | `aggregator` 模块 |
| `RedLine` violation | `RedLineChecker` 模块 |
| `HardGate` failure | `hard_gate` 模块 |
| `EvalResult` 最终 | `QAGEvaluator` Orchestrator（仅这一处） |

---

## 三、目录结构

```
qag-gate/
├── README.md
├── pyproject.toml
├── LICENSE                              # Apache 2.0
├── docs/
│   ├── ALGORITHM.md
│   ├── EXPERIMENTS.md
│   ├── TESTING.md
│   └── PAPER.md
├── src/
│   └── qag_gate/
│       ├── __init__.py                  # 唯一公共接口（EvalResult / QAGEvaluator）
│       ├── domain/                      # 领域模型，无外部依赖
│       │   ├── verdict.py               # Verdict, EvalQuestion 数据类
│       │   ├── result.py                # EvalResult 数据类
│       │   ├── phase.py                 # Phase, Depth 枚举
│       │   ├── redline.py               # RedLineResult, RedLineViolation
│       │   └── deliverable.py           # DeliverableSpec, DeliveryManifest
│       ├── application/                 # 用例编排
│       │   ├── evaluator.py             # QAGEvaluator 主类
│       │   ├── question_assembly.py     # 三层问题合并
│       │   ├── score_aggregation.py     # 加权聚合
│       │   └── output_type_detection.py # 文件/代码/文本检测
│       ├── infrastructure/              # 外部依赖
│       │   ├── llm/
│       │   │   ├── __init__.py          # LLMClient 协议
│       │   │   ├── openai_client.py     # OpenAI 适配器
│       │   │   ├── anthropic_client.py  # Anthropic 适配器
│       │   │   └── vllm_client.py       # 本地 vLLM 适配器
│       │   ├── search/
│       │   │   └── web_search.py        # 可选：claim 验证用
│       │   └── persistence/
│       │       └── runs.py              # 中间产物落盘（runs/<id>/）
│       ├── checkers/                    # 评估子系统
│       │   ├── binary_judge.py          # 主 BinaryJudge
│       │   ├── claim_extractor.py       # 事实抽取
│       │   ├── web_verifier.py          # 网络验证
│       │   ├── redline_checker.py       # 红线检测（规则+LLM）
│       │   ├── hard_gate.py             # 硬门槛扫描
│       │   ├── deliverable_coverage.py  # 交付物存在性确定性验证
│       │   └── question_generator.py    # 动态问题生成
│       ├── prompts/                     # 所有 prompts 独立文件，版本化
│       │   ├── criteria_system.txt
│       │   ├── judge_system.txt
│       │   ├── redline_system.txt
│       │   ├── claim_extract.txt
│       │   └── version.json             # prompt 版本号
│       ├── data/
│       │   └── baseline_questions.yaml  # 6 条基线问题
│       └── cli/
│           └── evaluate.py              # `qag-gate evaluate` 命令
├── tests/
│   ├── arch/                            # Fitness Functions
│   │   ├── test_dependency_direction.py # domain 不能 import infrastructure
│   │   ├── test_module_boundaries.py    # 跨模块只能通过 __init__
│   │   └── test_no_direct_llm_imports.py
│   ├── unit/                            # 单元测试
│   │   ├── test_score_aggregation.py
│   │   ├── test_phase_detection.py
│   │   ├── test_question_assembly.py
│   │   └── test_redline_rules.py
│   ├── integration/                     # 集成测试
│   │   ├── test_evaluator_e2e.py        # 用 mock LLM 跑完整流程
│   │   └── test_llm_adapter.py
│   ├── e2e/                             # 端到端（用真实 LLM API）
│   │   └── test_full_pipeline.py
│   └── acceptance/                      # 验收记录
│       └── README.md
├── benchmarks/
│   └── 2026-05-qag-vs-baselines/
│       ├── PLAN.md
│       ├── ENV.md
│       ├── run.sh
│       ├── data/
│       └── RESULT.md
├── examples/
│   ├── basic_usage.py
│   ├── with_openai.py
│   ├── with_anthropic.py
│   └── integrate_with_langchain.py
└── runs/                                # 中间产物落盘（gitignore）
```

---

## 四、跨模块边界规则（Fitness Function）

```python
# tests/arch/test_dependency_direction.py
import ast
from pathlib import Path

def test_domain_has_no_external_deps():
    """domain/ 不能 import infrastructure/ 或 application/"""
    for f in Path("src/qag_gate/domain").rglob("*.py"):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = node.module if hasattr(node, 'module') else None
                assert "infrastructure" not in (module or "")
                assert "application" not in (module or "")

# tests/arch/test_no_direct_llm_imports.py
def test_no_direct_openai_in_business_logic():
    """checkers/ 和 application/ 不能直接 import openai"""
    for layer in ["checkers", "application"]:
        for f in Path(f"src/qag_gate/{layer}").rglob("*.py"):
            content = f.read_text()
            assert "import openai" not in content
            assert "import anthropic" not in content
            # 必须通过 infrastructure.llm
```

---

## 五、技术选型与 ADR

### ADR-2026-05-09-llm-adapter

**决策**：LLM 调用统一通过 `LLMClient` 协议（Python `Protocol`），具体实现放 `infrastructure/llm/`，业务层只依赖协议。

**理由**：
- 实证数据：本地实验 OpenAI / Anthropic / 本地 vLLM 在同一个 prompt 上的 response_time P50 分别为 1.2s / 1.5s / 0.4s（见 `experiments/2026-05-llm-latency-comparison`）
- 用户安装 qag-gate 后只想填一个 API key 就用，不想改代码

**Fitness Function**：`test_no_direct_llm_imports.py`

### ADR-2026-05-10-no-langchain

**决策**：不依赖 langchain / llamaindex，自己实现最小化的 LLM 客户端封装。

**理由**：
- langchain 引入大量传递依赖，安装包变大 ~50MB
- 用户社区在 langchain 之外也很大（OpenAI 直接用户）
- 自己的封装只需 ~200 行，可读性更好

**Fitness Function**：`test_no_langchain_dep.py`

### ADR-2026-05-11-prompts-versioned

**决策**：所有 prompts 放 `prompts/` 目录，独立文本文件，`version.json` 维护版本号。

**理由**：
- 防止 prompt 散落代码里
- benchmark 跑分时必须记录用的是哪个 prompt 版本
- 方便做 prompt A/B 实验

---

## 六、数据流（端到端）

```
User → QAGEvaluator.evaluate(task, content, context)
                    │
                    ▼
        ┌───────────────────────────┐
        │ application/evaluator.py  │
        │ ─────────────────────────  │
        │ 1. detect_phase(context)  │ ← domain/phase.py
        │ 2. select_depth(...)      │
        │ 3. hard_gate.scan(...)    │ ← checkers/hard_gate.py
        │ 4. assemble_questions(...)│ ← application/question_assembly.py
        │    ├── load baseline      │ ← data/baseline_questions.yaml
        │    ├── (LLM) gen dynamic  │ ← checkers/question_generator.py
        │    └── infer output_type  │ ← application/output_type_detection.py
        │ 5. BinaryJudge.judge(...) │ ← checkers/binary_judge.py
        │    └── (LLM) batch eval  │
        │ 6. (deep) WebVerifier     │ ← checkers/web_verifier.py
        │ 7. DeliverableCoverage    │ ← checkers/deliverable_coverage.py
        │ 8. aggregate_scores(...)  │ ← application/score_aggregation.py
        │ 9. RedLineChecker.check   │ ← checkers/redline_checker.py
        └───────────┬───────────────┘
                    │
                    ▼
                EvalResult ← domain/result.py
                    │
                    └── 落盘到 runs/<run_id>/{input,output,meta}.json
```

每个 LLM 调用都通过 `infrastructure/llm/` 走，记录 trace_id / token / latency 到 `runs/`。

---

## 七、对外公共接口（src/qag_gate/__init__.py）

```python
# 仅暴露这些
from qag_gate.application.evaluator import QAGEvaluator
from qag_gate.domain.result import EvalResult
from qag_gate.domain.verdict import Verdict, EvalQuestion
from qag_gate.domain.redline import RedLineResult
from qag_gate.infrastructure.llm import LLMClient, OpenAIClient, AnthropicClient

__version__ = "0.1.0"
__all__ = [
    "QAGEvaluator", "EvalResult", "Verdict", "EvalQuestion", 
    "RedLineResult", "LLMClient", "OpenAIClient", "AnthropicClient",
]
```

外部用户**只能**从 `qag_gate` 顶级导入，不能 `from qag_gate.checkers.binary_judge import ...`。Fitness Function 检查这一点。

---

## 八、与 SlopeNav 的契约

QAG-Gate 输出的 `EvalResult` 是 SlopeNav 的标准输入。两者通过 `domain/result.py` 解耦：

```python
# domain/result.py
@dataclass(frozen=True)
class EvalResult:
    score: float                    # SlopeNav 主要消费这个
    verdicts: tuple[Verdict, ...]   # SlopeNav 用于 verdict-level analysis
    hard_failures: tuple[HardFail, ...]
    redline_violations: tuple[str, ...]
    phase: str
    depth: str
    metadata: dict                  # token / latency / cost
```

`SlopeNav` 不 import `qag_gate`；它只接受**实现了相同接口的任何对象**（Python duck typing 或定义为 Protocol）。这样两个项目可独立维护。
