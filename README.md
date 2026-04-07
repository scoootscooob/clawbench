# ClawBench

Rigorous benchmark for AI models as [OpenClaw](https://github.com/openclaw/openclaw) agents. Runs entirely on [Hugging Face Spaces](https://huggingface.co/spaces).

## How it works

1. **You submit a model** via the Gradio UI (or API)
2. **The HF Space evaluates it** — gateway, harness, and scoring all run inside the container
3. **Results appear on the leaderboard** with three-axis scores and pass^k reliability

No local setup required. Everything runs on HF infrastructure.

## Architecture

```
┌─────────────────────── HF Docker Space ───────────────────────┐
│                                                                │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────┐   │
│  │  Gradio   │    │  Job Queue   │    │  OpenClaw Gateway  │   │
│  │  Frontend │───>│  (async)     │───>│  (Node.js)         │   │
│  │  :7860    │    │              │    │  :18789 internal    │   │
│  └──────────┘    └──────┬───────┘    └─────────┬──────────┘   │
│                         │                       │              │
│                   ┌─────▼───────┐    ┌─────────▼──────────┐   │
│                   │  Eval Worker │    │  WebSocket Proto v3 │   │
│                   │  (Python)    │───>│  sessions.create    │   │
│                   │              │    │  sessions.send      │   │
│                   └──────┬───────┘    │  chat.history       │   │
│                          │            └────────────────────┘   │
│                   ┌──────▼───────┐                             │
│                   │  Three-Axis   │                             │
│                   │  Scorer       │                             │
│                   │  S + T + B    │                             │
│                   └──────┬───────┘                             │
│                          │                                     │
│              ┌───────────▼────────────┐                        │
│              │  /data/ (persistent)   │                        │
│              │  + HF Dataset push     │                        │
│              └────────────────────────┘                        │
└────────────────────────────────────────────────────────────────┘
```

## Three evaluation axes

### Axis 1: Environment State (~50% weight)
After the agent finishes, we query the actual world:
- **Filesystem**: Does the file exist with correct content?
- **Memory**: Was the fact stored in agent memory? (gateway query)
- **Gateway state**: Cron jobs, session model, raw protocol assertions

We **never** trust the agent's claims. We verify the world changed.

### Axis 2: Trajectory (~30% weight)
Compare actual tool call sequence against reference:
- **Precision**: fraction of calls that were relevant
- **Recall**: fraction of required calls that were made
- **Order**: LIS-based sequence correctness
- **Efficiency**: within call budget?
- **Forbidden**: tools that must NOT be called

### Axis 3: Behavior (~20% weight)
LLM judge scoped to subjective quality only — explicitly does NOT score completion or efficiency.

## pass^k: The production metric

`pass^k = p^k`. Primary leaderboard sort.

| pass@1 | pass^5 | pass^8 |
|--------|--------|--------|
| 90% | 59% | 43% |
| 95% | 77% | 66% |
| 99% | 95% | 92% |

## 14 tasks across 3 categories

### General (6)
tool_selection, multi_turn_context, coding_file_ops, research_synthesis, instruction_following, error_recovery

### OpenClaw (5)
memory_store_recall, model_switch_continuity, subagent_handoff, cron_scheduling, skill_invocation

### Adversarial (3)
impossible_request, contradiction, hallucination_trap

## Deploy to HF Spaces

1. Create a new Space with SDK: Docker
2. Copy `SPACE_README.md` content to the Space's `README.md`
3. Push this repo to the Space
4. Set secrets: `HF_TOKEN`, `ANTHROPIC_API_KEY`, `OPENCLAW_GATEWAY_TOKEN`

## Local development

```bash
# Run locally (mimics HF Space)
docker compose up

# Or without Docker:
pip install -e .
# Start openclaw gateway separately, then:
clawbench run -m anthropic/claude-sonnet-4-6 --judge-api-key $ANTHROPIC_API_KEY
```

## File structure

```
app.py                  # HF Space entry: Gradio + background worker
clawbench/
  queue.py              # Job queue (HF Dataset-backed persistence)
  worker.py             # Background eval worker (starts gateway, runs harness)
  harness.py            # POMDP conversation loop + three-axis scoring
  environment.py        # Axis 1: State verification (filesystem, memory, gateway)
  trajectory.py         # Axis 2: Tool call precision/recall/F1
  simulated_user.py     # Static, adaptive (LLM), adversarial user modes
  scorer.py             # Combines axes + LLM judge for Axis 3
  client.py             # Gateway WebSocket protocol v3 client
  schemas.py            # Pydantic models (GoalState, ReferenceTrajectory, etc.)
  stats.py              # Bootstrap CI, pass^k
  upload.py             # HF Dataset push
  cli.py                # Local CLI
tasks/
  general/              # 6 general agent tasks
  openclaw/             # 5 OpenClaw-specific tasks
  adversarial/          # 3 adversarial tasks
  assets/               # Workspace files
Dockerfile              # HF Docker Space (gateway + Python + Gradio)
SPACE_README.md         # HF Space metadata (copy to README.md when deploying)
```

## Based on

- [TAU-bench](https://github.com/sierra-research/tau-bench) — POMDP, pass^k, database state verification
- [SWE-bench](https://www.swebench.com/) — deterministic test-based verification
- [WebArena](https://webarena.dev/) — programmatic environment state assertions
- [Open LLM Leaderboard](https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard) — HF Space submission queue architecture
- [Anthropic: Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — three-tier evaluation
- [Anthropic: Infrastructure noise](https://www.anthropic.com/engineering/infrastructure-noise) — statistical rigor
- [ABC checklist](https://arxiv.org/html/2507.02825v1) — anti-gaming, task/outcome validity

## License

MIT
