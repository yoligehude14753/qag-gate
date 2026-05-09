# qag-gate · 核心算法说明

> 版本：v1.0 · 日期：2026-05-08

本文档以**数学定义 + 伪代码**说明 QAG-Gate 的核心算法，作为论文方法章节的一手草稿。

---

## 1. 形式化定义

### 1.1 输入空间

任务 $t \in \mathcal{T}$（自然语言）；输出 $c \in \mathcal{C}$（自然语言或文件路径列表）；上下文 $x \in \mathcal{X}$（包含 `tools_used`, `tool_results`, `iteration`, `agent_state`, `total_tool_calls`）。

### 1.2 输出空间

$$
\text{EvalResult} = (s, V, H, R, \phi, d) \in [0,1] \times \mathcal{V}^* \times \mathcal{H}^* \times \mathcal{R}^* \times \Phi \times D
$$

其中：
- $s \in [0,1]$ 加权聚合分
- $V$ verdicts 序列
- $H$ hard failures 序列
- $R$ redline violations 序列
- $\phi \in \Phi = \{\text{planning, executing, delivering}\}$
- $d \in D = \{\text{fast, standard, deep}\}$

### 1.3 评估器

$$
E: \mathcal{T} \times \mathcal{C} \times \mathcal{X} \to \text{EvalResult}
$$

---

## 2. Phase 检测算法

```
function detect_phase(iteration, agent_state, tools_used, total_tool_calls):
    if agent_state == "reporting":
        return "delivering"
    if iteration ≤ 2 and total_tool_calls ≤ 3:
        return "planning"
    if total_tool_calls ≥ 5 and |tools_used| ≥ 2:
        return "delivering"
    return "executing"
```

**设计理由**：
- "reporting" 是 agent 显式宣告的最终状态，优先级最高
- 早期低工具调用 → 还在规划
- 大量工具调用 + 多种工具 → 已经在收尾
- 其他 → 执行阶段

**论文中的对比**：现有框架（RAGAS, OpenJudge）均无 phase 概念，所有 iteration 用同一套问题。QAG-Gate 的 phase 让评估器**只问当前阶段相关的问题**，避免"executing 阶段问交付物完整性"这类无效评估。

---

## 3. Depth 选择算法

```
function select_depth(phase, iteration, slope_tracker, tool_results):
    if phase == "delivering":
        return "deep"          # 交付决策必须深度评估
    if iteration ≤ 2:
        return "fast"          # 早期不浪费 LLM 调用
    if iteration ≥ 3 and slope_tracker.no_real_scores():
        return "standard"      # 防止一直 fast
    if slope_tracker.is_plateau() or slope_tracker.is_declining():
        return "deep"          # 停滞时升级评估
    if any tool failed:
        return "standard"
    if iteration % 5 == 0:
        return "standard"      # 周期性深检查
    return "fast"
```

**计算复杂度**：
- fast: O(1) — 仅规则
- standard: O(1) LLM 调用
- deep: O(k) LLM 调用，k ≤ 4（criteria + judge + claim + verify）

---

## 4. 三层问题组装

### 4.1 Layer 1: Baseline (universal, 6 questions)

不依赖任务类型，覆盖：意图匹配、可交付性、质量底线、可操作性、时间一致性、物理一致性。

### 4.2 Layer 2: Dynamic (LLM-generated, 5-12 questions)

```
function generate_dynamic_questions(task, phase, depth, context, content):
    output_type = detect_output_type(tool_results, content)
    domain_ctx = web_search_domain_standards(task) if depth == "deep" else ""
    prompt = build_criteria_prompt(task, phase, depth, output_type, domain_ctx, ...)
    response = llm_call(CRITERIA_SYSTEM_PROMPT, prompt, model="gpt-5.4-mini")
    questions = parse_json(response)["questions"]
    return [EvalQuestion(text=q.text, category=q.category, weight=q.weight)
            for q in questions]
```

**关键创新点**：`output_type` 决定 prompt：
- `file:video/pptx/docx/...` → 问"文件是否存在"、"是否符合规格"，**禁止问引用来源**
- `code` → 问"代码是否能跑"、"边界处理"
- `text` → 问"事实正确"、"分析深度"

### 4.3 Layer 3: Output-type Specific Override

```
if output_type starts with "file:" or output_type == "code":
    remove all questions with category == "factual_accuracy"
    add: "Did the tool execute and produce expected files?"
    add: "Were non-empty data files actually generated?"
```

避免对生成 PPT 的任务问"引用是否真实"——这是错位评估。

---

## 5. BinaryJudge 算法

```
function judge(questions, content, task, context):
    content_eval = truncate_smart(content, 16000)
    q_list = format_numbered(questions)
    prompt = build_judge_prompt(task, tool_summary, content_eval, q_list)
    
    response = llm_call(JUDGE_SYSTEM_PROMPT, prompt, model="gpt-5.4")
    answers = parse_json(response)["answers"]
    
    verdicts = []
    for i, q in enumerate(questions):
        raw = answers[i].answer  # "yes" | "partial" | "no"
        score = SCORE_MAP[raw]    # 1.0 | 0.5 | 0.0
        if not q.positive_answer:
            score = 1.0 - score
        verdicts.append(Verdict(
            question=q.text, category=q.category,
            answer=score >= 0.5, is_positive=score >= 0.5,
            reason=answers[i].reason, weight=q.weight, score_value=score,
        ))
    return verdicts
```

**关键设计**：所有问题打包为单次 LLM 调用，而非每问题一次。
- 成本节省：O(N) → O(1)
- 一致性提高：模型在同一 context 评所有问题，避免跨调用的标准漂移

**Yes/Partial/No 三档**：比纯 binary 更细，但仍可量化为 {0, 0.5, 1}。

---

## 6. 加权聚合算法

```
function aggregate_scores(verdicts, category_weights, weight_overrides):
    merged_weights = merge(category_weights, weight_overrides, override_map)
    
    by_cat = group_by(verdicts, key=lambda v: v.category)
    
    total_weighted, total_weight = 0, 0
    cat_scores = {}
    for cat, vs in by_cat.items():
        cat_score = sum(v.weight * v.score_value for v in vs) /
                    sum(v.weight for v in vs)
        cat_scores[cat] = cat_score
        cw = merged_weights[cat]
        total_weighted += cat_score * cw
        total_weight += cw
    
    total = total_weighted / total_weight
    failed = [v for v in verdicts if not v.is_positive]
    return total, cat_scores, failed
```

**三层权重合并**：
$$
w_\text{cat} = \max\left(w_\text{baseline}[cat],\; w_\text{dynamic}[cat],\; w_\text{override}[cat]\right)
$$

`override` 优先级最高（用户传入）；`dynamic` 次之（LLM 生成的权重）；`baseline` 兜底。

---

## 7. RedLine 检测算法

### 7.1 规则层（无 LLM）

```
function check_rules(content, context):
    violations = []
    
    # 1. 空回答
    if len(content.strip()) < 10:
        violations.append("empty_response")
    
    # 2. 推脱（DEFLECTION_PHRASES 命中 ≥ 3 次）
    if count_deflection_phrases(content) ≥ 3:
        violations.append("deflection")
    
    # 3. 工具失败道歉式交付
    if any APOLOGY_PHRASE in content:
        violations.append("tool_failure_apology_delivery")
    
    # 4. 工具失败率 > 50% + 短交付
    if tool_fail_rate > 0.5 and len(content) < 500:
        violations.append("unhandled_tool_error")
    
    # 5. 段落重复（前 50 字符指纹相同 ≥ 3 个）
    if duplicate_paragraph_count ≥ 3:
        violations.append("content_duplication")
    
    # 6. 数据伪造（声称爬取但未用爬取工具）
    if data_acquisition_pattern_in_task and no_fetch_tool_used:
        violations.append("data_fabrication")
    
    return violations
```

### 7.2 LLM 验证层（交叉验证）

```
function check_with_llm(content, context):
    rule_result = check_rules(content, context)
    llm_result = llm_call(REDLINE_SYSTEM_PROMPT, content)
    
    # 交叉验证：LLM 报告的 violation 必须被规则确认 OR severity ≥ 3
    validated = []
    for v in llm_result.violations:
        if v in rule_result or (v in HARD_VIOLATIONS and v.severity ≥ 3):
            validated.append(v)
    return validated
```

**设计动机（防 LLM 幻觉）**：纯 LLM 红线检测会假阳性（LLM 总倾向"挑刺"）。交叉验证后只保留规则确认的 + LLM 标 severity ≥ 3 的硬违规，假阳性率可降至 < 5%（实证待验证）。

---

## 8. Hard Gate 扫描算法

```
function scan_hard_gates(tools_used, tool_results):
    failures = []
    
    # 1. 工具失败
    for r in tool_results:
        if r.success is False:
            failures.append({
                type: "tool_failure",
                error: r.error[:300],
                is_infra: is_infra_error(r.error),
            })
    
    # 2. 代码工具连续 3 次失败
    if any code_tool used:
        last_3 = tool_results[-3:]
        if all not r.success for r in last_3:
            failures.append({type: "code_all_failing"})
    
    # 3. 文件工具但无文件产出
    if any file_tool used:
        if no path/file_url/filename in tool_results:
            failures.append({type: "no_file_produced"})
    
    return failures
```

**`is_infra_error` 判定**：
匹配 `PermissionError`, `403`, `401`, `CAPTCHA`, `cloudflare`, `ConnectionRefused`, `GPU not available`, `No space left` 等。
**重要排除**：`ModuleNotFoundError` 和 `FileNotFoundError` 不算 infra（这些是 agent 可以自己改导入/路径修复的代码 bug）。

---

## 9. Deliverable Coverage（确定性验证）

```
function build_deliverable_coverage(context):
    spec = SpecStore.load(task_id, session_id)
    if spec is None:
        return []
    
    manifest = build_manifest(delivery_dir)
    verdicts = []
    for d in spec.deliverables:
        entry = manifest.find(d.filename)
        present = entry is not None
        passes_size = entry.size_bytes ≥ d.min_size_bytes if entry else False
        verdicts.append(Verdict(
            question=f"Required '{d.filename}' present and ≥ {d.min_size_bytes}B?",
            category="deliverable_coverage",
            answer=present and passes_size,
            weight=2.0 if d.required else 0.5,
            score_value=1.0 if (present and passes_size) else 0.0,
            reason=f"present={present} size={entry.size_bytes if entry else 0}",
        ))
    return verdicts
```

**关键差异化**：这部分**完全确定性**，不依赖 LLM。
- LLM 评分可能因为内容看起来"完整"就给高分；但实际文件不存在
- Deliverable Coverage 用文件系统作为 ground truth
- 高权重（2.0）确保有 LLM 错评时仍被这个否决

---

## 10. 端到端伪代码

```
function evaluate(task, content, context):
    phase = detect_phase(context)
    depth = select_depth(phase, context.iteration, slope_tracker, tool_results)
    
    hard_failures = scan_hard_gates(context.tools_used, context.tool_results)
    
    if depth == "fast":
        return EvalResult(score=0.0, verdicts=[], hard_failures=hard_failures,
                          phase=phase, depth=depth, is_health_check=True)
    
    questions = list(BASELINE_QUESTIONS)
    if has_files(content) or is_research_task(task):
        questions.extend(STRUCTURAL_COMPLETENESS_QUESTIONS)
    
    dynamic_qs = generate_dynamic_questions(task, phase, depth, context, content)
    questions.extend(dynamic_qs)
    
    output_type = detect_output_type(context.tool_results, content)
    questions = override_for_output_type(questions, output_type)
    
    extra_verdicts = []
    if depth == "deep" and output_type.is_textual:
        claims = extract_claims(content)
        extra_verdicts = web_verify(claims, max_checks=3)
    
    extra_verdicts.extend(build_deliverable_coverage(context))
    
    eval_content = augment_with_file_artifacts(content, context.tool_results)
    verdicts = BinaryJudge.judge(questions, eval_content, task, context)
    verdicts.extend(extra_verdicts)
    
    cat_weights = merge_weights(BASELINE_WEIGHTS, dynamic_qs, context.weight_overrides)
    score, cat_scores, failed = aggregate_scores(verdicts, cat_weights)
    
    redline = RedLineChecker.check(content, context)
    
    return EvalResult(score, verdicts, hard_failures, redline.violations,
                      phase, depth, metadata)
```

---

## 11. 论文中的核心创新声明

我们将主张以下贡献是当前文献中**首次提出的组合**（待 related work 章节确认）：

1. **Phase × Depth 自适应矩阵**：3 phase × 3 depth = 9 种评估策略，按运行时上下文动态选择。
2. **Output-type-aware 问题改写**：根据输出类型（file/code/text）动态删除/添加问题，避免类型错位评估。
3. **三层权重合并机制**：baseline → dynamic → override 单调递增，保证用户优先级始终有效。
4. **规则 + LLM 交叉验证的红线**：而非纯规则或纯 LLM，假阳性可控。
5. **确定性 deliverable coverage 作为评分组件**：而非仅作为后置 sanity check。

详细 related work 对比见 `docs/PAPER.md`。
