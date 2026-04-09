---
title: ClawBench
emoji: 🦞
colorFrom: red
colorTo: yellow
sdk: docker
app_port: 7860
pinned: true
license: mit
---

# ClawBench

Rigorous benchmark for AI models acting as OpenClaw agents.

Submit a model and it gets evaluated on HF infrastructure with deterministic, execution-first scoring:
- **Completion**: Did the workspace, tests, services, or gateway state actually satisfy the task?
- **Trajectory**: Did the agent explore, recover, and use tools well?
- **Behavior**: Did the transcript show planning, progress updates, and safe handling of blockers?
- **Reliability**: How stable was performance across repeated runs?

Official score formula:
- normalized per-run weighted average of `0.4 completion + 0.3 trajectory + 0.2 behavior`
- per-task aggregate of `0.9 * mean_run_score + 0.1 * reliability_score`

Primary metric: **pass^k** (all repeated runs must succeed).

ClawBench v0.4 includes:
- 20 tasks across `tier1` through `tier5`
- realistic multi-file Python, Node, shell, browser, and multi-phase tasks
- deterministic local browser tasks backed by task-owned HTTP services
- scripted user turns instead of LLM-based user simulation
- execution-based verification instead of file-exists-only checks
- dataset-backed scenario coverage metadata
- `clear` and `ambiguous` prompt variants for query robustness slices
- pass/partial/fail delivery buckets plus weighted query-score side surfaces
- optional advisory LLM judging on selected high-ambiguity tasks for nuanced artifact/transcript quality checks

The official benchmark score still stays deterministic. Optional judge results are reported as a sidecar signal and do not replace execution-based verification.

The benchmark does not require a separate scorer or user-simulation API key. It uses the model-under-test auth already configured for OpenClaw, and the same auth path can be reused if you enable the optional judge model.
