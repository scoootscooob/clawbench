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

Rigorous benchmark for AI models as OpenClaw agents.

Submit a model and it gets evaluated on HF infrastructure with three-axis scoring:
- **Environment State**: Did the world actually change?
- **Trajectory**: Was the tool call sequence correct?
- **Behavior**: How did the agent handle edge cases?

Primary metric: **pass^k** (all runs must succeed).
