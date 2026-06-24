# arXiv Submission Metadata

## Title

QAG-Gate: Phase-Aware Binary Evaluation for Long-Running Coding Agents

## Authors

Yuli Gao

## Primary Category

cs.CL - Computation and Language

Alternative if moderation recommends a broader fit:

- cs.AI - Artificial Intelligence
- cs.SE - Software Engineering
- cs.LG - Machine Learning

## License

arXiv.org perpetual, non-exclusive license

## Abstract

Tools like Claude Code, OpenAI Codex CLI, Cursor Composer and similar long-running coding agents now routinely run unattended for minutes to hours, producing planning text, partial code, files, and final deliverables in the same loop. Two questions become operational: is the agent's current output good for its current stage, and is it good enough to ship. Off-the-shelf judges answer neither well: static rubrics ignore which stage the agent is in, and generic LLM-as-a-judge scoring treats a Python script and a planning bullet list as the same kind of text.

We present QAG-Gate, an open-source framework that scores agent outputs through a phase classifier, a depth-adaptive selector, a three-layer stack of binary evaluation questions, and a deterministic RedLine hard gate for common production failure patterns. On MT-Bench human pairwise preferences, QAG-Gate matches the human-preferred answer on 263/380 = 69.2% of decisive pairs. On FLASK-Eval, QAG-Gate correlates with FLASK's GPT-4 aggregate skill scores at Spearman rho = 0.226, compared with 0.487 for G-Eval; we interpret the gap as evidence that QAG-Gate measures agent-output suitability rather than generic instruction-following style. Ablations show small but consistent contributions from phase-aware depth, dynamic task-specific questions, and RedLine checks.

Code is released under Apache 2.0 at https://github.com/yoligehude14753/qag-gate.

## Comments

10 pages. Code: https://github.com/yoligehude14753/qag-gate

## Journal Reference

None.

## DOI

None for the initial arXiv submission.
