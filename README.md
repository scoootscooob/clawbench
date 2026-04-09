# ClawBench

Rigorous benchmark for AI models acting as [OpenClaw](https://github.com/openclaw/openclaw) agents.

ClawBench v0.4 extends the deterministic 20-task suite with a user-query benchmark layer built around scenario coverage, clear-vs-ambiguous prompt variants, delivery outcomes, and dataset-backed task metadata. The benchmark runs on Hugging Face Spaces or locally against an OpenClaw gateway.

## What v0.4 measures

Each run gets a deterministic score from three per-run axes:

- **Completion**: run tests, scripts, and deterministic assertions against the actual workspace and gateway state.
- **Trajectory**: score exploration before mutation, recovery quality, tool-family fit, and safety.
- **Behavior**: score planning, progress communication, blocker handling, and destructive-command avoidance from the transcript.

Then each task gets a cross-run **Reliability** score based on:

- `pass^k`
- pass rate
- score variance

Per-run score:

```text
normalize(0.4 * completion + 0.3 * trajectory + 0.2 * behavior)
```

Per-task score:

```text
0.9 * mean_run_score + 0.1 * reliability_score
```

The query layer adds secondary benchmark surfaces without replacing the execution-first core:

- **Scenario coverage**: task-level mapping into a 12-domain user-query taxonomy distilled from `baselines/basic_usage_query_summary.json`
- **Prompt robustness**: the same task can run in `clear` or `ambiguous` wording modes
- **Delivery buckets**: every run is also labeled `pass`, `partial`, or `fail`
- **Weighted query score**: tasks can carry scenario weights from the query dataset for an additional user-facing aggregate

## Task suite

The benchmark ships 20 tasks across 5 tiers:

- **Tier 1**: architecture summary, simple Python bugfix, refactor-with-tests
- **Tier 2**: test authoring, exact-output CLI work, config bugfix, Node patching, browser form repair
- **Tier 3**: feature implementation, multifile refactor, timezone debugging, data pipeline build, monitoring + cron
- **Tier 4**: delegation workflow, cross-repo migration, fresh-session memory continuation, browser research + code
- **Tier 5**: impossible request handling, contradictory requirements, hallucination-resistant evidence gathering

Task metadata is tier-first. Each task also carries a secondary family such as `coding`, `repo`, `browser`, `tools`, `multi_tool`, or `adversarial`.
Tasks can also carry query metadata such as scenario domain, subscenario, atomic capabilities, artifact type, prompt variants, and source-dataset mapping.

## Query dataset layer

This repo now includes a distilled summary of the spreadsheet-backed query corpus in `baselines/basic_usage_query_summary.json`.

That dataset contributes:

- a 12-domain user scenario taxonomy
- clear and ambiguous query variants
- artifact and prerequisite metadata
- pass/partial/fail delivery framing
- scenario weights for additional aggregate views

The current 20-task suite is mapped into that taxonomy so we can see both what it measures well and which scenario domains are still under-covered.

## Deterministic runtime

ClawBench intentionally avoids making the official score depend on a separate judge model:

- user turns are scripted and condition-based, not LLM-generated
- behavior checks are deterministic transcript rules
- browser tasks use local task-owned services, not live public websites
- the benchmark does not require a separate scorer API key

Optional subjective judging can still sit beside the benchmark later, but the official path stays verifier-first.

ClawBench now supports an optional advisory LLM judge for selected tasks. Those rubrics read the produced artifacts and transcript excerpts, report a separate judge score, and never overwrite the official deterministic benchmark score.
Judge coverage is intentionally partial and concentrated on the more ambiguous artifact-quality tasks.

Model auth comes from the OpenClaw runtime you use for the evaluated model.

## Browser support

Browser tasks are real browser tasks:

- the Docker image installs full Node Playwright plus Chromium
- the worker keeps the OpenClaw browser control service enabled
- browser verification runs against local deterministic apps and docs

## Hermes provenance

This repo keeps only a compact aggregate trace summary in `baselines/hermes_trace_summary.json`.
Raw Hermes traces are intentionally not checked in.

## Local development

```bash
./.venv/bin/python -m pip install -e '.[dev]'

# Run a tier locally
clawbench run -m anthropic/claude-sonnet-4-6 --runs 3 --tier tier2

# Add an advisory judge with an independent model for the ambiguity-heavy tasks
# If you are using OpenAI Codex OAuth instead of OPENAI_API_KEY, prefer openai-codex/gpt-5.4
clawbench run -m anthropic/claude-sonnet-4-6 --judge-model openai-codex/gpt-5.4 --runs 3 --tier tier5

# Run the ambiguous prompt variant for a scenario slice
clawbench run -m anthropic/claude-sonnet-4-6 --runs 3 --scenario coding_dev_assist --prompt-variant ambiguous

# List tasks
clawbench list-tasks

# Run tests
./.venv/bin/pytest -q
```

You still need an OpenClaw gateway running locally for actual benchmark runs.

## HF Space deployment

1. Create a Docker Space.
2. Copy `SPACE_README.md` into the Space `README.md`.
3. Push this repo.
4. Configure any model-provider auth the Space needs for the models you want to benchmark.

## File layout

```text
app.py
clawbench/
  client.py
  cli.py
  environment.py
  harness.py
  queue.py
  render.py
  schemas.py
  scorer.py
  services.py
  simulated_user.py
  stats.py
  tasks.py
  trajectory.py
  upload.py
  worker.py
tasks/
  tier1/ ... tier5/
  assets/
baselines/
  hermes_trace_summary.json
tests/
Dockerfile
SPACE_README.md
```

## References

- [TAU-bench](https://github.com/sierra-research/tau-bench)
- [SWE-bench](https://www.swebench.com/)
- [WebArena](https://webarena.dev/)
- [Anthropic: Demystifying evals for agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
