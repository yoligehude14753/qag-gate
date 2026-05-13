# Integrations

QAG-Gate plugs into any iterative agent loop that produces text outputs you want to score. The pattern is always the same: build a `QAGEvaluator` once, call `await evaluator.evaluate(task=..., content=..., context=...)` after each iteration / step / message, and use `result.score`, `result.verdicts`, `result.redline_violations` to decide what to do next.

All examples below assume:

```bash
pip install "qag-gate[openai]"
export OPENAI_API_KEY=sk-...
```

> Framework APIs change. Where an integration depends on an API that has been moving fast in 2025–2026, we pin a version and a date at the top of that section, and we deliberately stick to the smallest stable surface (e.g. a wrapper / callback rather than a private hook).

---

## 1. Self-Refine (Madaan et al. 2023)

Self-Refine is a loop pattern, not a library: generate → critique → refine. Use QAG-Gate's failed verdicts as the critique signal — they are concrete, category-tagged, and stable across iterations, which makes them more useful as feedback than free-form self-critiques.

```python
import asyncio, os
from openai import AsyncOpenAI
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

TASK = "Write a Python `is_leap_year(year)` with a docstring and 3 assert tests."

async def main() -> None:
    client = AsyncOpenAI()
    evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))
    answer, critique = "", "Start with a first draft."
    for i in range(4):
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": f"{TASK}\n\nPrev:\n{answer}\n\nFix: {critique}"}],
        )
        answer = resp.choices[0].message.content or ""
        r = await evaluator.evaluate(task=TASK, content=answer,
                                     context={"iteration": i, "agent_state": "executing"})
        print(f"iter={i} score={r.score:.3f} failed={len(r.failed_verdicts)}")
        if r.score >= 0.85 or not r.failed_verdicts:
            break
        critique = "; ".join(f"{v.category}: {v.reason}" for v in r.failed_verdicts[:3])

asyncio.run(main())
```

See `examples/02_self_refine_loop.py` in this repo for the full version.

---

## 2. Reflexion (Shinn et al. 2023)

Reflexion adds an episodic memory of past failures across attempts. QAG-Gate's `verdicts` (each with `category`, `question`, `is_positive`, `reason`) map cleanly to per-category memory slots — store the failing ones, replay them in the next system prompt.

```python
import asyncio, os
from openai import AsyncOpenAI
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

TASK = "Summarise a paper for a non-expert in 4 bullets, each <= 25 words."

async def main() -> None:
    client = AsyncOpenAI()
    evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))
    memory: list[str] = []
    answer = ""
    for trial in range(3):
        sys = "You revise drafts. Avoid these past failure modes:\n" + "\n".join(f"- {m}" for m in memory)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": f"{TASK}\n\nPrev draft:\n{answer}"}],
        )
        answer = resp.choices[0].message.content or ""
        r = await evaluator.evaluate(task=TASK, content=answer,
                                     context={"iteration": trial, "agent_state": "executing"})
        print(f"trial={trial} score={r.score:.3f}")
        if r.score >= 0.85:
            break
        memory.extend(f"[{v.category}] {v.reason}" for v in r.failed_verdicts[:3])

asyncio.run(main())
```

---

## 3. Claude Code SDK

*As of 2026-05 with `claude-code-sdk==0.0.x` (Anthropic Python SDK for the Claude Code agent). The SDK does not expose a stable "eval hook"; the supported pattern is to consume the message stream and score each assistant turn yourself.*

```python
import asyncio, os
from claude_code_sdk import query, ClaudeCodeOptions
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

TASK = "Add type hints to all public functions in src/utils.py"

async def main() -> None:
    evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))
    options = ClaudeCodeOptions(max_turns=5, allowed_tools=["Read", "Edit"])
    iteration = 0
    async for message in query(prompt=TASK, options=options):
        if getattr(message, "type", "") != "assistant":
            continue
        text = getattr(message, "text", "") or str(message)
        r = await evaluator.evaluate(task=TASK, content=text,
                                     context={"iteration": iteration, "agent_state": "executing"})
        iteration += 1
        print(f"turn={iteration} score={r.score:.3f} redlines={r.redline_violations}")
        if r.redline_violations or r.score < 0.4:
            print("warning: low-quality turn — log and review")

asyncio.run(main())
```

If you are embedding the Claude Code SDK in a CI job, treat QAG-Gate's output as an additional gate before accepting the patch.

---

## 4. Cursor Composer / OpenAI Codex CLI

These are CLI tools without a stable Python embedding API. The recommended pattern is to capture their stdout (or read the file they edited) and score it as a one-shot:

```python
import asyncio, subprocess
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

TASK = "Refactor src/utils.py to use dataclasses"

async def main() -> None:
    out = subprocess.check_output(["codex", "exec", TASK], text=True)
    evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))
    r = await evaluator.evaluate(task=TASK, content=out,
                                 context={"iteration": 0, "agent_state": "delivering"})
    print(f"score={r.score:.3f} verdicts_failed={len(r.failed_verdicts)}")
    if r.redline_violations:
        raise SystemExit(f"redline tripped: {r.redline_violations}")

asyncio.run(main())
```

Same shape works for `cursor-agent` CLI invocations or any other command-line agent — feed the captured output into `evaluate()` and treat redline violations as CI failures.

---

## 5. Aider

*As of 2026-05 with `aider-chat>=0.60`. Aider exposes `Coder` programmatically; there is no stable hook system, but `Coder.run()` returns the assistant message and you can score it directly.*

```python
import asyncio, os
from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

TASK = "Add a 'reverse' method to src/utils/list_helpers.py with a unit test"

async def main() -> None:
    coder = Coder.create(main_model=Model("gpt-4o-mini"),
                         io=InputOutput(yes=True), fnames=["src/utils/list_helpers.py"])
    evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))
    for i in range(3):
        message = coder.run(with_message=TASK if i == 0 else "address the critique below")
        r = await evaluator.evaluate(task=TASK, content=message or "",
                                     context={"iteration": i, "agent_state": "executing"})
        print(f"iter={i} score={r.score:.3f} failed={len(r.failed_verdicts)}")
        if r.score >= 0.85 or r.redline_violations:
            break
        TASK = "Address: " + "; ".join(v.reason for v in r.failed_verdicts[:3])

asyncio.run(main())
```

---

## 6. AutoGen

*As of 2026-05 with `autogen-agentchat>=0.4` (the redesigned, event-driven AutoGen). The clean integration point is to consume the `TaskResult.messages` stream and score the final assistant message; for finer control wrap a per-message callback.*

```python
import asyncio, os
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

TASK = "Draft a 3-paragraph release note for v0.2.0 emphasising the new phase classifier."

async def main() -> None:
    agent = AssistantAgent(name="writer",
                           model_client=OpenAIChatCompletionClient(model="gpt-4o-mini"))
    evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))
    result = await agent.run(task=TASK)
    last = result.messages[-1].content if result.messages else ""
    r = await evaluator.evaluate(task=TASK, content=str(last),
                                 context={"iteration": 0, "agent_state": "delivering"})
    print(f"score={r.score:.3f} phase={r.phase.value} redlines={r.redline_violations}")

asyncio.run(main())
```

---

## 7. CrewAI

*As of 2026-05 with `crewai>=0.50`. `Task` accepts a `callback=` argument that receives a `TaskOutput` object after the task completes — that's the right place to score.*

```python
import asyncio, os
from crewai import Agent, Task, Crew
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))

def score_task_output(output) -> None:
    text = getattr(output, "raw", str(output))
    r = asyncio.run(evaluator.evaluate(task=output.description, content=text,
                                       context={"iteration": 0, "agent_state": "delivering"}))
    print(f"[QAG] score={r.score:.3f} redlines={r.redline_violations}")

writer = Agent(role="Writer", goal="Draft concise release notes", backstory="Senior tech writer.",
               llm="gpt-4o-mini")
task = Task(description="Write a one-paragraph release note for v0.2.0.",
            expected_output="A single paragraph, plain text.",
            agent=writer, callback=score_task_output)

Crew(agents=[writer], tasks=[task]).kickoff()
```

The callback is synchronous, so we wrap the async `evaluate()` with `asyncio.run`. For a long-lived crew, build a small dispatcher that re-uses one event loop instead.

---

## 8. Letta (formerly MemGPT)

*As of 2026-05 with `letta-client>=0.5`. Letta does not expose a per-step hook in the public client; the supported pattern is to call `agent.messages.create()` (or `agents.messages.create`) and score the assistant reply yourself.*

```python
import asyncio, os
from letta_client import Letta
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

async def main() -> None:
    letta = Letta(base_url=os.environ.get("LETTA_BASE_URL", "http://localhost:8283"))
    agent = letta.agents.create(name="writer", model="openai/gpt-4o-mini",
                                embedding="openai/text-embedding-3-small")
    evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))
    task = "Summarise this paper in 4 bullets."
    response = letta.agents.messages.create(
        agent_id=agent.id, messages=[{"role": "user", "content": task}])
    text = "\n".join(getattr(m, "content", "") for m in response.messages
                     if getattr(m, "message_type", "") == "assistant_message")
    r = await evaluator.evaluate(task=task, content=text,
                                 context={"iteration": 0, "agent_state": "delivering"})
    print(f"score={r.score:.3f} verdicts_failed={len(r.failed_verdicts)}")

asyncio.run(main())
```

Field names on Letta messages have changed across versions — guard with `getattr` and pin the version you target.

---

## 9. LangGraph

*As of 2026-05 with `langgraph>=0.2`. The natural place to integrate is a regular `StateGraph` node that calls `evaluator.evaluate()` and writes the result back into the graph state.*

```python
import asyncio, os
from typing import TypedDict
from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI
from qag_gate import QAGEvaluator
from qag_gate.infrastructure import OpenAIAdapter

class S(TypedDict):
    task: str; draft: str; score: float; iteration: int

client = AsyncOpenAI()
evaluator = QAGEvaluator(OpenAIAdapter(model="gpt-4o-mini"))

async def write(state: S) -> S:
    resp = await client.chat.completions.create(model="gpt-4o-mini",
        messages=[{"role": "user", "content": state["task"]}])
    return {"draft": resp.choices[0].message.content or "", "iteration": state["iteration"] + 1}

async def score(state: S) -> S:
    r = await evaluator.evaluate(task=state["task"], content=state["draft"],
                                 context={"iteration": state["iteration"], "agent_state": "executing"})
    print(f"iter={state['iteration']} score={r.score:.3f}")
    return {"score": r.score}

g = StateGraph(S)
g.add_node("write", write); g.add_node("score", score)
g.set_entry_point("write"); g.add_edge("write", "score")
g.add_conditional_edges("score", lambda s: END if s["score"] >= 0.85 or s["iteration"] >= 4 else "write")

asyncio.run(g.compile().ainvoke({"task": "Explain RAG in 3 bullets.", "draft": "", "score": 0.0, "iteration": 0}))
```

---

## 10. YOLI

Built-in. YOLI's evaluation framework already wires QAG-Gate as the default scorer for long-running agent loops — see `docs/EVAL.md` in the [`yoli`](https://github.com/yoligehude14753/yoli) repo for setup, configuration, and the recommended pairing with [SlopeNav](https://github.com/yoligehude14753/slopenav) as the stopping criterion.

---

## Cookbook

- **Pair with a stopping criterion.** QAG-Gate emits per-iteration scores; [SlopeNav](https://github.com/yoligehude14753/slopenav) consumes them and decides `continue` / `pivot` / `deliver`. Use them together for budget-aware loops.
- **Use redlines as hard CI gates.** `result.redline_violations` is deterministic and free (no LLM call) — fail the build whenever it is non-empty.
- **Pass `context["iteration"]` and `context["agent_state"]`.** The phase classifier uses both; without them every iteration falls back to `EXECUTING` and you lose the planning / delivering specialisations.
- **Cap concurrency.** For high-throughput pipelines wrap the evaluator behind an `asyncio.Semaphore` keyed to your LLM provider's rate limit.
