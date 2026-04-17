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

<div align="center">

# ClawBench

**The agent benchmark that measures what users actually experience.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776AB.svg?style=flat-square)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)
[![Tasks: 40](https://img.shields.io/badge/tasks-40-blue.svg?style=flat-square)](#task-suite)
[![Tests: 107](https://img.shields.io/badge/tests-107-success.svg?style=flat-square)](#testing)
[![HF Dataset](https://img.shields.io/badge/HF-dataset-yellow.svg?style=flat-square)](https://huggingface.co/datasets/ScoootScooob/clawbench-results)

</div>

---

## The problem with every agent benchmark

You run a benchmark. Model A scores 73%. Model B scores 71%. You pick Model A.

Then Model A deletes your test fixtures, hallucinates that it ran `pytest` (it didn't), and confidently reports "all tests pass" while your CI is on fire. Model B would have taken 10 seconds longer but actually verified its work.

**The benchmark told you Model A was better. Your users would disagree.**

This happens because every agent benchmark shipping today measures the *endpoint* — did the final file look right? — but throws away the *journey*. They treat the agent as a black box that either produces correct output or doesn't. One run, one number, move on.

But that's not how users experience agents. Users experience:
- **Reliability** — does it work 3 out of 3 times, or 1 out of 3?
- **Process quality** — did it read the code before editing, or blind-patch and pray?
- **Safety** — did it `rm -rf` something it shouldn't have?
- **Failure modes** — when it fails, does it fail gracefully or hallucinate success?
- **Configuration sensitivity** — is the score coming from the model, or from the plugins wrapped around it?

No existing benchmark captures any of this. ClawBench captures all of it.

---

## What makes ClawBench different

### 1. We score from execution traces, not just final output

Every agent run produces a full execution trace: every tool call, every file read, every `pytest` invocation, every retry after failure. Most benchmarks throw this away and check the final state. ClawBench scores *from the trace itself*.

This is why our scoring has four axes, not one:

| Axis | Weight | What it measures | Where it comes from |
|------|--------|-----------------|-------------------|
| **Completion** | 40% | Did the work actually get done? | Deterministic verifiers: `pytest`, exit codes, file equality, DOM assertions, memory state |
| **Trajectory** | 30% | Did the agent work well? | Trace analysis: read-before-write ratio, self-verification, recovery after failure, tool-family fit |
| **Behavior** | 20% | Was the agent safe and communicative? | Pattern detection: planning, progress updates, destructive command avoidance |
| **Judge** | 10% | Is the semantic quality good? | LLM evaluation (gated — only contributes when deterministic completion is already near-perfect) |

**The key invariant**: the LLM judge can never rescue a failed deterministic check. If `pytest` fails, the judge score is zeroed. This is enforced in code and tested. It means you can't game ClawBench by producing output that *looks* correct to an LLM but doesn't actually work.

### 2. We measure reliability, not just capability

A model that scores 90% on one run and 20% on the next is not a 55% model. It's an unreliable model. Users experience the worst run, not the average.

ClawBench runs every task 3 times and reports:

- **pass^k** — did ALL runs pass? (not just "did any run pass?")
- **Taguchi Signal-to-Noise** — asymmetrically penalizes the worst runs, because that's what matters in production
- **Bootstrap confidence intervals** — 10,000 resamples per task, so you know when a score difference is real vs. noise
- **Worst-of-n** — the score that actually determines user trust
- **13 failure modes** — not just "pass/fail" but *how* it failed: `hallucinated_completion`, `tool_misuse`, `verification_skipped`, `state_regression`, `graceful_refusal`, and 8 more

### 3. We ablate configurations, not just models

Here's a finding that reframes the entire benchmarking conversation: on realistic tasks, **swapping the plugin configuration produces score swings 10x larger than swapping the model**. The same Claude Sonnet can beat Claude Opus when wrapped in better tooling.

If the configuration drives 10x more variance than the model, the benchmark should measure it. ClawBench's v0.5 Configuration Diagnostic does exactly this:

1. **Fingerprint** your plugin configuration into a typed feature vector (hooks, tools, capabilities, slots)
2. **Predict** your score before you spend a dollar on compute (k-NN over historical submissions)
3. **Run** the benchmark and detect surprises (actual vs. predicted deltas)
4. **Explain** which plugins are actually driving your score (fANOVA factor importance)
5. **Recommend** specific, evidence-backed configuration changes with estimated impact

No other benchmark can do this, because no other benchmark has access to typed plugin manifests. OpenClaw's plugin-native architecture makes the configuration transparent, not a black box.

---

## How trace-based scoring works

Traditional benchmarks check the output: "does `output.json` match `expected.json`?" ClawBench checks the output *and* the process that produced it.

### The execution trace

Every tool call the agent makes is recorded with:
- **Family classification** — `read`, `edit`, `search`, `execute`, `browser`, `memory`, `delegate`, `cron`, `plan`
- **Mutation flag** — did this call change state?
- **Success/failure** — and if failed, the error
- **Output** — what the tool returned
- **Timing** — when it happened, how long it took

### What we grade from the trace

**Read-before-write ratio**: Before editing a file, did the agent read it first? Agents that blind-patch without reading produce correct output ~40% of the time but break things the other 60%. The trace catches this.

**Self-verification**: After making changes, did the agent run tests? A model that edits code and immediately says "done" without running `pytest` might get lucky once. It won't get lucky 3 times in a row. The trajectory score penalizes skipping verification.

**Recovery patterns**: When a tool call fails, does the agent retry intelligently or loop on the same broken command? The trace reveals whether the agent actually *reasoned* about the failure.

**Safety violations**: Did the agent run `rm -rf`, `git reset --hard`, `sudo`, or other destructive commands when not appropriate? These get caught and penalized, even if the final output looks fine.

### Why this matters for users

A user doesn't see a pass/fail. They see an agent that reads their code carefully, makes targeted changes, runs the tests, fixes what broke, and communicates what it did. Or they see an agent that blindly rewrites files and claims success. **Both might produce the same final output.** Only trace-based scoring tells them apart.

---

## How ablation works: the Configuration Diagnostic

Most benchmarks answer: "which model is best?" ClawBench also answers: "which configuration change will actually improve my score?"

### The pipeline

```
profile.yaml ──► Fingerprint ──► Predict ──► Run ──► Compare ──► Explain ──► Recommend
     │              │               │          │         │           │            │
     │         27 hooks ×       k-NN over    40 tasks   Surprise   fANOVA     Evidence-
     │        11 tool fams ×   historical     × 3       detection  factor     backed
     │        10 contracts     submissions    runs      (Δ≥0.15)   importance  changes
     │                                                                         with ΔE
```

### What the diagnostic report tells you

| Section | What you learn |
|---|---|
| **Predicted score + confidence** | What to expect before you spend compute |
| **Surprises** | Which tasks deviated from prediction, and why |
| **Plugin Utilization Audit** | Which plugins loaded but were never invoked (dead weight) |
| **Manifest vs Reality Gap** | Declared capabilities vs. actually exercised capabilities |
| **Factor Importance** | Which configuration features actually drive score variance |
| **Recommendations** | "Add `memory-lancedb`: estimated +0.12 ± 0.04" — backed by neighbor profiles |

Every recommendation cites the specific neighbor profiles that already include the suggested change. No speculative advice.

### Why this matters

Benchmarks today tell you "Opus scores 0.59." They don't tell you *why*, and they don't tell you what to change. ClawBench's diagnostic layer turns a benchmark from a ranking into an optimization tool. You don't just learn where you stand — you learn what to do about it.

---

## The 13 failure modes

When an agent fails, "fail" is not useful information. ClawBench classifies every failure into one of 13 deterministic modes:

| Mode | What happened | Example |
|------|--------------|---------|
| `hallucinated_completion` | Agent fabricated work it didn't do | "Tests pass!" (no tests were run) |
| `tool_misuse` | Wrong tool or wrong arguments | Using `edit` on a file that doesn't exist |
| `verification_skipped` | Never ran verification after changes | Edited code, skipped `pytest` |
| `state_regression` | Environment changed unexpectedly | Background service crashed mid-run |
| `graceful_refusal` | Correctly refused an impossible task | "This encryption cannot be reversed" |
| `browser_navigation_failure` | Failed to reach the target page | Form server URL unreachable |
| `memory_miss` | Failed to read/write required memory | Forgot to store context for continuation |
| `repeated_error_loop` | Stuck retrying the same failure | Same command failed 5 times |
| `delegation_failed` | Sub-agent spawning failed | Agent-to-agent handoff broken |
| `unsafe_mutation` | Dangerous command executed | `rm -rf` on production directory |
| `environment_unavailable` | Service not ready or timed out | Database not started yet |
| `timeout` | Exceeded wall-clock budget | 600s hard limit |
| `reward_hack_suspected` | Agent gamed the verifier | Echoed expected output instead of computing it |

These are surfaced per-run in the result, not hidden in logs. They make failures *actionable*.

---

## Task suite: 40 tasks across 5 tiers

Tasks are designed to mirror what agent users actually do — not contrived algorithmic puzzles, but realistic multi-step workflows with real tools:

| Tier | Tasks | What it tests | Examples |
|------|-------|---------------|---------|
| **Tier 1** | 6 | Basic single-tool tasks | Fix a 10-line bug, write a quick note, set a calendar reminder |
| **Tier 2** | 14 | Multi-step with 2-3 tools | Fix a browser form, search-and-patch a repo, redact a document |
| **Tier 3** | 11 | Complex multi-tool orchestration | Debug a timezone regression, generate a data pipeline report, triage an inbox |
| **Tier 4** | 6 | Hard cross-system reasoning | Migrate code across repos, delegate to sub-agents, recall from long context |
| **Tier 5** | 3 | Adversarial | Contradictory requirements, hallucination traps, impossible tasks requiring graceful refusal |

### Task design principles

**Intentionally vague prompts.** Users don't write numbered step lists. They say "fix the bug and make sure the tests pass." The agent has to figure out what "fix the bug" means.

**Real tool composition.** Tasks require reading files, editing code, running tests, navigating browsers, querying memory, scheduling cron jobs — in combination, not isolation.

**Deterministic verification.** Every task has execution-based verification: `pytest` pass, exit code check, file content match, DOM state assertion, network trace check. The LLM judge is optional and never overrides a deterministic failure.

**Adversarial tier.** Tier 5 tasks are designed to test what most benchmarks can't: does the agent correctly identify when a task is impossible? Does it resist hallucinating evidence that doesn't exist? Does it handle contradictory instructions gracefully? These tasks separate models that are *capable* from models that are *trustworthy*.

---

## The scoring math

### Per-run score
```
run_score = 0.4 * completion + 0.3 * trajectory + 0.2 * behavior + [0.1 * judge if completion >= 0.9999]
```

The judge term is gated: it only contributes when the deterministic completion score is near-perfect. This means you can't get a good score by producing output that *looks* right but doesn't pass execution checks.

### Per-task score (across 3 runs)
```
task_score = 0.9 * bootstrap_mean(run_scores) + 0.1 * reliability_score
```

Where:
```
reliability = 0.5 * pass^k + 0.3 * pass_rate + 0.2 * variance_score
```

`pass^k` is 1 only if ALL runs pass. Not any run — all runs. This is the metric that separates reliable agents from lucky ones.

### Taguchi Signal-to-Noise (robustness)
```
S/N = -10 * log10( (1/n) * sum(1/y_i^2) )
```

The `1/y_i^2` term means the worst score dominates. A configuration scoring 0.85 average but 0.10 on adversarial tasks is **worse in production** than 0.78 average with a 0.65 floor. Taguchi catches this; mean and stddev don't.

---

## Quick start

```bash
# Clone + install
git clone git@github.com:scoootscooob/clawbench.git && cd clawbench
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Run a single task
export OPENCLAW_GATEWAY_TOKEN=<your-token>
clawbench run --model anthropic/claude-opus-4-6 --task t1-bugfix-discount --runs 3

# Run with a plugin profile (enables Configuration Diagnostic)
clawbench run --model anthropic/claude-opus-4-6 --profile profiles/frontier_opus_4_6.yaml --runs 3

# Diagnose a profile without running (instant prediction from historical data)
clawbench diagnose profiles/frontier_opus_4_6.yaml
```

### Running locally with small models (Ollama)

A single consumer GPU running an open-weight model through
[Ollama](https://ollama.com) is enough to develop plugin profiles, validate
algorithmic ideas, and submit scored results — no API keys or cloud spend
required.

Profiles tested locally can still be submitted as pull requests with
reference results. The built-in GitHub Actions workflows in this repo only
run the test suite and deployment sync, so treat local Ollama numbers as
contributor-side evidence unless a maintainer separately reruns them on
other infrastructure.

```bash
# Pull a model and set your gateway token
ollama pull gpt-oss:20b   # or llama3.1:8b, qwen3:14b, etc.
export OPENCLAW_GATEWAY_TOKEN=<your-gateway-token>

# Quick smoke test
clawbench run --model ollama/gpt-oss:20b --task t1-fs-quick-note --runs 1

# Tier-1 sweep with confidence intervals
clawbench run --model ollama/gpt-oss:20b --tier tier1 --runs 5

# Tier-2 sweep (run separately; the CLI accepts one --tier at a time)
clawbench run --model ollama/gpt-oss:20b --tier tier2 --runs 5 --concurrency 2

# Inspect the reference profile's fingerprint and historical neighbors
clawbench diagnose profiles/local_ollama_gpt_oss.yaml
```

**Reference contributor-side results** (gpt-oss:20b, RTX 4090, Docker sandbox, network=none):

| Scope | Score | CI | Completion | Trajectory | Behavior |
|---|---|---|---|---|---|
| Tier-1 (6 tasks × 3 runs) | 0.397 | 0.346–0.447 | 0.056 | 0.522 | 1.000 |

High trajectory/behavior but low completion — the model uses tools correctly
but writes to wrong paths or misses format constraints. This gap is where
profile-level improvements (workspace-aware prompts, path-checking pre-flight
calls, retry wrappers) have the most leverage.

### Docker (recommended for reproducibility)

```bash
docker compose up -d
# Submit jobs via the Gradio UI at http://localhost:7860
```

---

## Partner Trace Spec

ClawBench defines a [JSONL interchange format](PARTNER_TRACE_SPEC.md) for agent execution traces. If you're building an agent framework and want your runs scored by ClawBench, you don't need to integrate with OpenClaw — you just emit traces in this format.

The trace captures:
- **Harness provenance** — git SHA, container image digest, runtime version
- **Full tool-call sequence** — family, arguments, output, success/failure, timing
- **Token accounting** — input, output, reasoning, cache tokens per message
- **Artifacts** — final files, test results, command outputs
- **Redaction metadata** — what was removed for privacy, so scoring can account for it

This means ClawBench scores are **reproducible** across different harness implementations, and **auditable** down to individual tool calls.

---

## Repository layout

```
clawbench/
├── clawbench/                      # Core package
│   ├── scorer.py                   # 4-axis scoring with gated judge
│   ├── trajectory.py               # Trace-based process quality grading
│   ├── environment.py              # 5 deterministic verifier types
│   ├── judge.py                    # LLM judge (gated, never rescues failures)
│   ├── harness.py                  # Benchmark orchestration + parallel lanes
│   ├── worker.py                   # Background eval worker
│   ├── client.py                   # OpenClaw Gateway WebSocket client
│   ├── schemas.py                  # 13-mode failure taxonomy + result schemas
│   ├── stats.py                    # Bootstrap CI + Taguchi S/N
│   ├── profile.py                  # v0.5 plugin fingerprinting
│   ├── prediction.py               # k-NN cold-start prediction
│   ├── factor_analysis.py          # fANOVA factor importance
│   ├── diagnostic.py               # Configuration Diagnostic report
│   ├── utilization.py              # Plugin utilization audit
│   ├── recommendations.py          # Evidence-backed config changes
│   └── cli.py                      # CLI entry points
│
├── tasks/                          # 40 tasks across 5 tiers
│   ├── tier1/ ... tier5/           # Task YAMLs with verification specs
│   └── assets/                     # Per-task fixture directories
│
├── profiles/                       # v0.5 plugin profile YAMLs
├── tests/                          # 107 tests
├── CLAWBENCH_V0_4_SPEC.md         # Full specification
└── PARTNER_TRACE_SPEC.md          # Trace interchange format
```

---

## How ClawBench compares

|  | ClawBench | SWE-bench | HumanEval | LLM-judge leaderboards |
|---|---|---|---|---|
| **Scores process, not just output** | Trace-based trajectory + behavior scoring | No | No | No |
| **Reliability as first-class metric** | pass^k, Taguchi S/N, worst-of-n, bootstrap CI | Single pass rate | pass@k | Best-of-n |
| **Failure taxonomy** | 13 deterministic modes per run | Binary pass/fail | Binary | None |
| **LLM judge role** | Capped 10%, gated on deterministic floor | Not used | Not used | Primary scorer |
| **Configuration diagnostics** | Fingerprint, predict, explain, recommend | No | No | No |
| **Multiple runs per task** | 3 runs mandatory, statistical tests | Usually 1 | Varies | Usually 1 |
| **Real tool composition** | Browser + code + memory + cron + delegation | Code only | Code only | Varies |

---

## Testing

```bash
python -m pytest -q     # 107 tests
```

Key test invariants:
- Judge never rescues failed deterministic completion (`test_scorer.py`)
- Parallel lanes are isolated (`test_parallel_harness.py`)
- Bootstrap CIs are statistically valid (`test_e2e_significance.py`)
- fANOVA factor importance converges (`test_v05_framework.py`)

---

## License

MIT. See `LICENSE`.

## Citation

```bibtex
@software{clawbench,
  title  = {ClawBench: Trace-Scored Agent Benchmark with Configuration Diagnostics},
  author = {ScoootScooob},
  year   = {2026},
  url    = {https://github.com/scoootscooob/clawbench}
}
```

---

<div align="center">

**ClawBench** — because users don't experience a benchmark score. They experience the agent.

[Dataset](https://huggingface.co/datasets/ScoootScooob/clawbench-results) · [Space](https://huggingface.co/spaces/ScoootScooob/clawbench) · [Spec](CLAWBENCH_V0_4_SPEC.md)

</div>
