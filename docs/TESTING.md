# qag-gate · 测试 Plan

> 版本：v1.0 · 日期：2026-05-08 · 遵循 `12-testing.mdc`、`19-quality-detail.mdc`

---

## 一、测试金字塔

```
        ┌──────────────────┐
        │   E2E (~5 个)    │   真实 LLM API，整条管线
        ├──────────────────┤
        │ Integration ~15  │   mock LLM，模块协作
        ├──────────────────┤
        │   Arch (~10 个)  │   Fitness Functions
        ├──────────────────┤
        │   Unit (~50 个)  │   纯函数、领域规则
        └──────────────────┘
```

---

## 二、业务目标三问

### 主路径
> 用户 `pip install qag-gate`，写 5 行代码调用 `QAGEvaluator.evaluate(task, content, context)`，能拿到一个语义合理的 `EvalResult`（score 在 [0,1]，verdicts 非空，phase/depth 正确推断）。

### 失败路径
- LLM API 不可用 → 降级到 baseline questions + 默认评分，**不抛异常**
- LLM 返回非法 JSON → 触发 fallback verdicts（全部 `is_positive=False, reason="parser failed"`）
- content 为空 → 立即返回 `redline_violations=["empty_response"]`，跳过 LLM 调用
- task 含敏感字符 → prompt 安全注入防御（见 14-security.mdc）

### 完整状态
- 三种 phase × 三种 depth = 9 种组合都有覆盖
- 五种 output_type（text / code / file:* / image / video）都有覆盖
- 六种红线类型都有 happy + sad 测试

---

## 三、功能完整性清单

```markdown
## 功能完整性清单：QAG-Gate Evaluate

### 主流程（Happy Path）
- [ ] 输入合法 task + content + context → 输出 EvalResult
- [ ] EvalResult.score ∈ [0, 1]
- [ ] EvalResult.verdicts 至少包含 BASELINE_QUESTIONS 数量的条目
- [ ] EvalResult.phase ∈ {planning, executing, delivering}
- [ ] EvalResult.depth ∈ {fast, standard, deep}
- [ ] 每次调用 runs/ 下产生新目录，含 input/prompt/output/meta

### 失败路径
- [ ] LLM 超时 → 降级到 baseline + warning log，不抛异常
- [ ] LLM 返回非 JSON → fallback verdicts，每条 reason 含 "parser failed"
- [ ] content == "" → redline=["empty_response"]，无 LLM 调用
- [ ] tool_results 缺失 → DeliverableCoverage 跳过，无错误
- [ ] context 缺 iteration → 默认 iteration=0，不崩溃
- [ ] 网络断开（deep 模式）→ web_verifier 跳过，记录到 metadata

### 边界场景
- [ ] content 长度 > 16000 → 自动智能截断，按章节分配预算
- [ ] task 长度 > 800 → 截断 + warning
- [ ] questions 为 0（极端情况）→ score = 0.5, reason 注明
- [ ] tool_results 中 100% 失败 → unhandled_tool_error 红线触发
- [ ] 多语言 content（中英混合）→ 评估器正确处理

### 状态集
- [ ] is_health_check=True 时（depth=fast）→ 仅返回 hard_failures，不跑 LLM
- [ ] phase=delivering 强制 depth=deep
- [ ] phase=planning + iteration ≤ 2 → depth=fast

### 细节
- [ ] runs/ 目录有标准结构（plan.json / node-XX/）
- [ ] 每个 LLM 调用 meta 含 token、latency、cost
- [ ] prompt 版本号写入 metadata
- [ ] 标准日志格式：`[QAG-Gate] phase=X depth=Y score=Z`
```

---

## 四、单元测试设计（~50 个）

### 4.1 `domain/`（10 个）
- `test_verdict_serialization` — Verdict ↔ dict 互转
- `test_evalresult_immutable` — frozen dataclass 验证
- `test_phase_enum_completeness` — 所有 phase 值可枚举
- `test_redline_violation_types`
- `test_deliverable_spec_min_size_default`

### 4.2 `application/`（15 个）
- `test_phase_detection_planning` — iteration=0, no tools → planning
- `test_phase_detection_delivering_explicit` — agent_state="reporting" → delivering
- `test_phase_detection_executing_default`
- `test_depth_selection_fast` — early iter, no tools
- `test_depth_selection_standard_periodic` — iteration % 5 == 0
- `test_depth_selection_deep_on_plateau`
- `test_depth_selection_deep_on_decline`
- `test_score_aggregation_simple` — 1 cat, 3 verdicts, 验证加权
- `test_score_aggregation_with_overrides` — override_map 转换正确
- `test_score_aggregation_empty` — 0 verdicts → 0.5 默认
- `test_question_assembly_baseline_only` — 没 LLM 时
- `test_question_assembly_with_dynamic`
- `test_question_assembly_output_type_override` — file 类型移除 factual_accuracy
- `test_output_type_detection_video`
- `test_output_type_detection_code` — 含 ``` 块

### 4.3 `checkers/`（20 个）
- `test_redline_empty_response`
- `test_redline_deflection_3plus`
- `test_redline_deflection_below_threshold` — < 3 不触发
- `test_redline_apology_phrase`
- `test_redline_unhandled_tool_error`
- `test_redline_duplication`
- `test_redline_data_fabrication`
- `test_redline_cross_validation` — LLM 标 violation 但规则不确认 → 丢弃
- `test_hard_gate_tool_failure`
- `test_hard_gate_infra_error_classification` — 403 vs ModuleNotFoundError
- `test_hard_gate_code_all_failing`
- `test_hard_gate_no_file_produced`
- `test_binary_judge_yes_partial_no_mapping`
- `test_binary_judge_negative_question` — positive_answer=False 反转
- `test_binary_judge_fallback_on_llm_fail`
- `test_claim_extractor_top_k`
- `test_web_verifier_max_checks`
- `test_deliverable_coverage_present`
- `test_deliverable_coverage_undersized`
- `test_deliverable_coverage_no_spec` — 返回空 list

### 4.4 `infrastructure/`（5 个）
- `test_openai_client_protocol`
- `test_anthropic_client_protocol`
- `test_runs_persistence_structure`
- `test_prompt_version_loading`
- `test_llm_client_retry`

---

## 五、Fitness Functions（~10 个）

```python
# tests/arch/test_dependency_direction.py
def test_domain_no_external_deps()
def test_application_no_infrastructure_deps()  # except via Protocol

# tests/arch/test_module_boundaries.py
def test_external_imports_only_from_init()    # 跨模块只能从 __init__
def test_no_relative_import_outside_package()

# tests/arch/test_no_direct_llm_imports.py
def test_no_openai_in_business_layer()
def test_no_anthropic_in_business_layer()
def test_no_langchain_anywhere()

# tests/arch/test_prompt_versioning.py
def test_all_prompts_have_version_entry()
def test_prompts_are_separate_files()  # 不允许 prompt 字符串散落代码

# tests/arch/test_runs_persistence.py
def test_every_llm_call_has_runs_record()  # mock 后验证
```

---

## 六、集成测试（~15 个）

每个用 mock LLM（fixture 返回固定 response），覆盖模块协作：

- `test_evaluator_full_pipeline_text_task`
- `test_evaluator_full_pipeline_code_task`
- `test_evaluator_full_pipeline_pptx_task`
- `test_evaluator_full_pipeline_with_redline_violation`
- `test_evaluator_full_pipeline_with_hard_gate`
- `test_evaluator_phase_planning_uses_baseline_only`
- `test_evaluator_phase_delivering_forces_deep`
- `test_evaluator_with_deliverable_spec`
- `test_evaluator_with_weight_overrides`
- `test_evaluator_health_check_returns_immediately`
- `test_evaluator_consistent_across_runs` — 同输入 5 次跑，verdict 高度一致
- `test_evaluator_handles_llm_failure_gracefully`
- `test_evaluator_runs_dir_creation`
- `test_evaluator_metadata_completeness`
- `test_llm_adapter_swap` — 切换 OpenAI ↔ Anthropic 行为一致

---

## 七、E2E 测试（~5 个，用真实 LLM API）

仅在 CI 的 nightly job 跑（避免每次 PR 烧钱）：

```python
# tests/e2e/test_full_pipeline.py

def test_e2e_text_analysis_high_quality():
    """
    Given: 一个高质量 research 任务的 candidate output
    When: 调用 QAGEvaluator.evaluate()
    Then: score ≥ 0.8，无红线，phase=delivering
    """

def test_e2e_text_analysis_with_data_fabrication():
    """
    Given: 任务要求爬取数据但 candidate 未用爬取工具
    When: 调用 evaluate()
    Then: redline_violations 含 'data_fabrication'
    """

def test_e2e_pptx_generation_correct_questions():
    """
    Given: 生成 PPT 任务的 candidate（含文件路径）
    When: 调用 evaluate()
    Then: verdicts 中无 factual_accuracy 类问题（被 override 移除），
          有 deliverable_coverage 问题
    """

def test_e2e_iteration_loop_three_rounds():
    """
    Given: 模拟三轮 iteration 输入
    When: 顺序调用 evaluate()
    Then: 第 1 轮 phase=planning depth=fast，
          第 2 轮 executing standard，
          第 3 轮 delivering deep
    """

def test_e2e_with_anthropic_backend():
    """同样的输入，切换 Anthropic backend，行为一致"""
```

---

## 八、验收测试记录（acceptance/）

每次主流程 E2E 通过后，在 `tests/acceptance/<date>.md` 记录：

```markdown
## 2026-MM-DD QAG-Gate Acceptance

### 验收条件清单
- [x] 主路径：text/code/pptx 三种任务均能跑通
- [x] 失败路径：LLM 超时降级
- [x] 状态：phase × depth 9 种组合
- [x] 红线：6 种 violation 全部触发过

### 环境
- Python 3.12
- qag-gate v0.1.0
- LLM: gpt-5.4-mini

### 通过样本
（链接到 runs/<id>/）
```

---

## 九、Flaky 测试管理

LLM 调用本身是不确定的。规则：

- **集成测试**：用 mock LLM，**不允许 Flaky**
- **E2E**：允许偶尔 Flaky，但单测试 3 次重跑必有一次成功（CI 设 retry=3）
- 所有标记为 Flaky 的测试登记到 `tests/FLAKY.md`，含症状、根因猜测、恢复条件

---

## 十、测试名称规范（可读为文档）

```
# 不可读
test_eval_1
test_redline

# 可作文档
test_evaluator_returns_redline_violation_when_content_only_describes_what_could_be_done
test_redline_does_not_trigger_deflection_when_phrase_count_is_below_three
test_phase_detection_returns_delivering_when_agent_state_is_reporting
```
