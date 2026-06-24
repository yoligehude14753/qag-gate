# EMNLP 2026 System Demonstration Package

Official call: https://2026.emnlp.org/calls/demos/

Deadline: 2026-07-10, 23:59 AoE.

## Proposed Title

QAG-Gate: A Phase-Aware Binary Evaluation System for Long-Running Coding Agents

## Short Abstract

QAG-Gate is an open-source evaluation system for long-running LLM coding agents. Unlike generic LLM-as-a-judge prompts or static rubrics, QAG-Gate first detects the agent's execution phase, then selects binary evaluation questions appropriate to planning, execution, or delivery. It combines baseline quality gates, dynamically generated task-specific criteria, output-type overrides for code and file artifacts, and deterministic RedLine checks for common production failure modes. The demo will show QAG-Gate scoring agent trajectories, surfacing failing criteria, and producing a programmable signal that can stop, continue, or escalate iterative agent loops. Public validation includes MT-Bench human pairwise preference agreement and FLASK-Eval correlation, with ablations for phase routing, dynamic questions, and RedLine checks.

## Demo Story

1. User starts an agent task, such as "write a Python data-cleaning script and report."
2. The agent emits planning, execution, and delivery-stage outputs.
3. QAG-Gate detects the phase and selects the evaluation depth.
4. The UI/CLI shows binary verdicts, weighted score, and RedLine violations.
5. The operator can decide whether to continue, pivot, or ship.

## System Contributions

- Phase-aware evaluation for planning / executing / delivering states.
- Depth-adaptive binary criteria selection.
- Three-layer question stack:
  - baseline gates,
  - task-specific dynamic questions,
  - output-type overrides.
- Deterministic RedLine hard gate for failures such as empty output, deflection, fabricated data, duplicate content, and temporal incoherence.
- Python package for integration into Self-Refine, Reflexion, AutoGen, CrewAI, Letta, Claude Code SDK wrappers, Codex CLI wrappers, and custom agent loops.

## Submission Work Remaining

- Convert the technical report into the official ACL/EMNLP demo format.
- Keep within the demo track page limit.
- Add a system architecture figure.
- Add one screenshot or terminal transcript.
- Confirm whether the demo track is anonymized.
- Register / restore OpenReview account before submission.
- Upload PDF and metadata before 2026-07-10.

## Metadata Draft

- Authors: Yuli Gao
- Code: https://github.com/yoligehude14753/qag-gate
- License: Apache 2.0
- Keywords: LLM evaluation, coding agents, LLM-as-a-judge, agent observability, binary evaluation

## Status

Blocked on OpenReview registration. The user chose not to register OpenReview yet on 2026-06-25.
