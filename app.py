"""ClawBench HF Space — leaderboard + submission + background eval worker.

This single file is the entry point for the HF Docker Space.
It runs:
1. Gradio frontend (leaderboard + submission form + queue status)
2. Background eval worker (polls queue, runs benchmark, stores results)

All state persists via:
- /data/ directory (HF persistent storage)
- HF Dataset (`<space-owner>/clawbench-results`) for cross-restart persistence
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path

import gradio as gr
import pandas as pd
from clawbench.hub import dataset_has_submission_results, resolve_dataset_repo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("clawbench.app")

RESULTS_DIR = Path("/data/results") if Path("/data").exists() else Path("data/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
HF_DATASET_TOKEN = os.environ.get("HF_TOKEN", "")
HF_DATASET_REPO = resolve_dataset_repo(HF_DATASET_TOKEN)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r, using default %s", name, raw, default)
        return default
    return max(minimum, min(maximum, value))


DEFAULT_RUNS_PER_TASK = _env_int("CLAWBENCH_DEFAULT_RUNS_PER_TASK", 3, minimum=1, maximum=10)
DEFAULT_PARALLEL_LANES = _env_int("CLAWBENCH_DEFAULT_PARALLEL_LANES", 1, minimum=1, maximum=4)

# ---------------------------------------------------------------------------
# Preset models for quick submission
# ---------------------------------------------------------------------------

PRESET_MODELS = {
    # All models verified working on HF Inference API (free with HF_TOKEN)
    # Tested 2026-04-07 via router.huggingface.co/v1/chat/completions
    #
    # --- Chinese open-source ---
    "GLM 5.1 (754B MoE)": "huggingface/zai-org/GLM-5.1",
    "GLM 5 (400B MoE)": "huggingface/zai-org/GLM-5",
    "Qwen3 32B": "huggingface/Qwen/Qwen3-32B",
    "DeepSeek R1": "huggingface/deepseek-ai/DeepSeek-R1",
    "Kimi K2 Instruct": "huggingface/moonshotai/Kimi-K2-Instruct",
    "MiniMax M2.5": "huggingface/MiniMaxAI/MiniMax-M2.5",
    # --- Google open-source ---
    "Gemma 4 26B MoE": "huggingface/google/gemma-4-26B-A4B-it",
    # --- Meta open-source ---
    "Llama 3.3 70B": "huggingface/meta-llama/Llama-3.3-70B-Instruct",
    "Llama 3.1 70B": "huggingface/meta-llama/Llama-3.1-70B-Instruct",
    # --- Proprietary models (require runtime auth configured for the model provider) ---
    "Claude Sonnet 4.6": "anthropic/claude-sonnet-4-6",
    "Claude Opus 4.6": "anthropic/claude-opus-4-6",
}

# ---------------------------------------------------------------------------
# Background worker (starts in a thread)
# ---------------------------------------------------------------------------

from clawbench.queue import JobQueue, SubmissionRequest

queue = JobQueue()


def _start_worker() -> None:
    """Start the eval worker in a background thread with its own event loop."""
    from clawbench.worker import EvalWorker

    async def _run():
        worker = EvalWorker(queue)
        await worker.start()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_run())


worker_thread = threading.Thread(target=_start_worker, daemon=True)
worker_thread.start()
logger.info("Background eval worker started")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_leaderboard() -> pd.DataFrame:
    rows = []

    # Load from HF Dataset
    try:
        from datasets import load_dataset
        from huggingface_hub import HfApi

        api = HfApi(token=HF_DATASET_TOKEN or None)
        if dataset_has_submission_results(api, HF_DATASET_REPO):
            ds = load_dataset(
                HF_DATASET_REPO,
                split="submissions",
                token=HF_DATASET_TOKEN or None,
            )
            for row in ds:
                rows.append(_flatten_result(row))
    except Exception as exc:
        logger.info("Remote leaderboard unavailable: %s", exc)

    # Load from local results
    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                rows.append(_flatten_result(data))
            except Exception:
                pass

    if not rows:
        return pd.DataFrame(columns=[
            "Model", "Judge Model", "Prompt", "Scenario", "Score", "Weighted", "Completion", "Trajectory",
            "Behavior", "Judge", "Reliability", "Hard", "Consensus", "Median ms", "Cost/Pass", "pass^k",
            "CI", "Tasks", "Timestamp",
        ])

    # Deduplicate by model + prompt variant + scenario + judge model (keep latest)
    seen = {}
    for r in rows:
        key = f"{r['Model']}|{r['Prompt']}|{r['Scenario']}|{r['Judge Model']}"
        if key not in seen or r["Timestamp"] > seen[key]["Timestamp"]:
            seen[key] = r

    df = pd.DataFrame(list(seen.values()))
    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "#"
    return df


def _flatten_result(data: dict) -> dict:
    tasks = data.get("task_results", [])
    n_tasks = len(tasks) if isinstance(tasks, list) else 0
    environment = data.get("environment", {}) or {}
    return {
        "Model": data.get("model", ""),
        "Judge Model": data.get("judge_model", environment.get("judge_model", "")) or "-",
        "Prompt": environment.get("prompt_variant", "clear"),
        "Scenario": environment.get("scenario", "all"),
        "Score": round(data.get("overall_score", data.get("overall_composite", 0)), 3),
        "Weighted": round(data.get("overall_weighted_query_score", 0), 3),
        "Completion": round(data.get("overall_completion", data.get("overall_state", 0)), 3),
        "Trajectory": round(data.get("overall_trajectory", 0), 3),
        "Behavior": round(data.get("overall_behavior", 0), 3),
        "Judge": round(data.get("overall_judge_score", 0), 3),
        "Reliability": round(data.get("overall_reliability", data.get("overall_pass_hat_k", 0)), 3),
        "Hard": round(data.get("hard_subset_score", 0), 3),
        "Consensus": round(data.get("consensus_subset_score", 0), 3),
        "Median ms": round(data.get("overall_median_latency_ms", 0)),
        "Cost/Pass": round(data.get("overall_cost_per_pass", 0), 4),
        "pass^k": f"{data.get('overall_pass_hat_k', 0):.0%}",
        "CI": f"{data.get('overall_ci_lower', 0):.2f}-{data.get('overall_ci_upper', 0):.2f}",
        "Tasks": n_tasks,
        "Timestamp": data.get("timestamp", "")[:16],
    }


def load_queue() -> pd.DataFrame:
    jobs = asyncio.run(queue.list_jobs(limit=20))
    if not jobs:
        return pd.DataFrame(
            columns=[
                "ID",
                "Model",
                "Judge",
                "Prompt",
                "Scenario",
                "Status",
                "Submitted",
                "Started",
                "Heartbeat",
                "Task",
                "Run",
                "Runs",
                "Lanes",
                "Attempts",
                "Requeues",
                "Progress",
            ]
        )
    rows = []
    for j in jobs:
        run_label = ""
        if j.current_run_index is not None and j.current_run_total is not None:
            run_label = f"{j.current_run_index}/{j.current_run_total}"
        rows.append({
            "ID": j.job_id,
            "Model": j.request.model,
            "Judge": j.request.judge_model or "-",
            "Prompt": j.request.prompt_variant,
            "Scenario": j.request.scenario or "all",
            "Status": j.status.value,
            "Submitted": j.submitted_at[:16] if j.submitted_at else "",
            "Started": j.started_at[:16] if j.started_at else "",
            "Heartbeat": j.last_progress_at[:16] if j.last_progress_at else "",
            "Task": j.current_task_id or "-",
            "Run": run_label or "-",
            "Runs": j.request.runs_per_task,
            "Lanes": j.request.max_parallel_lanes,
            "Attempts": j.attempt_count,
            "Requeues": j.stale_requeues,
            "Progress": j.progress_message or "-",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Submission handler
# ---------------------------------------------------------------------------


def submit_model(
    model: str,
    preset: str,
    provider: str,
    judge_model: str,
    runs: int,
    max_parallel_lanes: int,
    tier: str | None,
    scenario: str | None,
    prompt_variant: str,
    submitter: str,
) -> str:
    # Use preset if selected, otherwise use custom model ID
    model_id = PRESET_MODELS.get(preset, "") or model.strip()
    if not model_id:
        return "Please enter a model ID or select a preset."

    selected_tier = tier if tier != "all" else None
    request = SubmissionRequest(
        model=model_id,
        provider=provider.strip(),
        judge_model=judge_model.strip(),
        runs_per_task=int(runs),
        max_parallel_lanes=int(max_parallel_lanes),
        tier=selected_tier,
        scenario=scenario if scenario != "all" else None,
        prompt_variant=prompt_variant,
        submitter=submitter.strip(),
    )
    job = asyncio.run(queue.submit(request))
    return f"Submitted [{model_id}]! Job ID: {job.job_id}. Check the Queue tab."


def submit_all_presets(runs: int, max_parallel_lanes: int, submitter: str) -> str:
    """Submit all preset models at once."""
    submitted = []
    for name, model_id in PRESET_MODELS.items():
        request = SubmissionRequest(
            model=model_id,
            provider="",
            runs_per_task=int(runs),
            max_parallel_lanes=int(max_parallel_lanes),
            submitter=submitter.strip(),
        )
        job = asyncio.run(queue.submit(request))
        submitted.append(f"{name} ({job.job_id})")
    return f"Submitted {len(submitted)} models:\n" + "\n".join(f"  - {s}" for s in submitted)


# ---------------------------------------------------------------------------
# Gradio app
# ---------------------------------------------------------------------------

DESCRIPTION = """
# ClawBench

Rigorous benchmark for AI models as [OpenClaw](https://github.com/openclaw/openclaw) agents.
Submit a model below and it will be evaluated on HF infrastructure.

**Official benchmark axes**: Completion | Trajectory | Behavior | Reliability
**Primary metric**: pass^k
**Side surfaces**: Hard subset | Consensus subset | Prompt robustness | Scenario coverage | Advisory LLM judge | Median latency | Cost per pass

```text
task yaml + assets
  -> isolated workspace
  -> optional local services
  -> OpenClaw session(s)
  -> transcript + tool results
  -> completion / trajectory / behavior
  -> repeated runs
  -> reliability
  -> leaderboard
```

| Suite shape | Count |
| --- | ---: |
| Tasks | 20 |
| Tiers | 5 |
| Browser tasks | 2 |
| Multi-phase tasks | 1 |
| Judge-enabled tasks | 6 |
"""

with gr.Blocks(title="ClawBench", theme=gr.themes.Base()) as demo:
    gr.Markdown(DESCRIPTION)

    with gr.Tab("Leaderboard"):
        refresh_btn = gr.Button("Refresh", scale=0)
        leaderboard = gr.Dataframe(
            value=load_leaderboard,
            interactive=False,
            wrap=True,
        )
        refresh_btn.click(fn=load_leaderboard, outputs=leaderboard)

    with gr.Tab("Submit"):
        gr.Markdown("### Submit a model for evaluation")
        gr.Markdown(
            "Select a preset or enter a custom model ID. Open-source models "
            "run via HuggingFace Inference API. Proprietary models need model auth configured in the Space runtime."
        )

        preset_input = gr.Dropdown(
            choices=["(custom)"] + list(PRESET_MODELS.keys()),
            value="(custom)",
            label="Preset models",
        )
        with gr.Row():
            model_input = gr.Textbox(
                label="Custom Model ID (if not using preset)",
                placeholder="e.g. huggingface/org/model-name",
                scale=3,
            )
            provider_input = gr.Textbox(
                label="Provider",
                placeholder="auto-detected from model ID",
                scale=1,
            )
        judge_model_input = gr.Textbox(
            label="Judge Model (optional, advisory only)",
            placeholder="e.g. anthropic/claude-opus-4-6",
        )
        with gr.Row():
            runs_input = gr.Slider(
                minimum=1, maximum=10, value=DEFAULT_RUNS_PER_TASK, step=1,
                label="Runs per task (higher = more reliable pass^k)",
            )
            max_parallel_lanes_input = gr.Slider(
                minimum=1,
                maximum=4,
                value=DEFAULT_PARALLEL_LANES,
                step=1,
                label="Parallel lanes (browser tasks stay serialized on one lane)",
            )
            tier_input = gr.Dropdown(
                choices=["all", "tier1", "tier2", "tier3", "tier4", "tier5"],
                value="all",
                label="Tier",
            )
        gr.Markdown(
            "Use more than 1 lane only on CPU-upgraded Spaces. Non-browser tasks can run in parallel, "
            "while browser tasks stay on a dedicated serial lane to avoid port and Chromium contention."
        )
        with gr.Row():
            scenario_input = gr.Dropdown(
                choices=[
                    "all",
                    "coding_dev_assist",
                    "data_processing_analysis",
                    "web_info_ops",
                    "multi_step_compound",
                    "context_continuation",
                    "error_boundary_cases",
                    "system_capabilities",
                ],
                value="all",
                label="Scenario",
            )
            prompt_variant_input = gr.Dropdown(
                choices=["clear", "ambiguous"],
                value="clear",
                label="Prompt Variant",
            )
        submitter_input = gr.Textbox(
            label="Your name (optional)",
            placeholder="HF username",
        )
        with gr.Row():
            submit_btn = gr.Button("Submit Model", variant="primary")
            submit_all_btn = gr.Button("Submit All Presets", variant="secondary")
        submit_output = gr.Textbox(label="Status", interactive=False, lines=5)
        submit_btn.click(
            fn=submit_model,
            inputs=[
                model_input,
                preset_input,
                provider_input,
                judge_model_input,
                runs_input,
                max_parallel_lanes_input,
                tier_input,
                scenario_input,
                prompt_variant_input,
                submitter_input,
            ],
            outputs=submit_output,
        )
        submit_all_btn.click(
            fn=submit_all_presets,
            inputs=[runs_input, max_parallel_lanes_input, submitter_input],
            outputs=submit_output,
        )

        gr.Markdown("""
**All presets verified working on HF Inference API (free):**

| Model | Provider | Size | Runtime |
|-------|----------|------|---------|
| GLM 5.1 | Z.ai | 754B MoE | HF free |
| GLM 5 | Z.ai | 400B MoE | HF free |
| Qwen3 32B | Alibaba | 32B | HF free |
| DeepSeek R1 | DeepSeek | 671B MoE | HF free |
| Kimi K2 Instruct | Moonshot AI | MoE | HF free |
| MiniMax M2.5 | MiniMax | MoE | HF free |
| Gemma 4 26B MoE | Google | 26B MoE | HF free |
| Llama 3.3 70B | Meta | 70B | HF free |
| Llama 3.1 70B | Meta | 70B | HF free |
| Claude Sonnet 4.6 | Anthropic | - | configured auth |
| Claude Opus 4.6 | Anthropic | - | configured auth |
""")

    with gr.Tab("Queue"):
        gr.Markdown("### Evaluation Queue")
        gr.Markdown(
            "Heartbeat and progress fields update during long evaluations. "
            "If a job loses its lease after a restart, the worker will auto-requeue it."
        )
        queue_refresh = gr.Button("Refresh", scale=0)
        queue_table = gr.Dataframe(value=load_queue, interactive=False, wrap=True)
        queue_refresh.click(fn=load_queue, outputs=queue_table)

    with gr.Tab("Methodology"):
        gr.Markdown("""
## How ClawBench evaluates agents

### Design principles
- verify the actual work instead of trusting the transcript
- score trajectory properties instead of one reference trace
- keep the official score deterministic
- reward reliability across repeated runs
- expose coverage through tier, scenario, prompt, and subset slices

### Runtime flow
```text
task yaml + assets
  -> isolated workspace
  -> optional local background services
  -> OpenClaw agent session(s)
  -> transcript + tool-result correlation
  -> completion / trajectory / behavior scoring
  -> repeated runs
  -> reliability aggregation
```

### Completion
After the agent runs, we execute tests, scripts, and deterministic checks against the actual workspace and gateway state.
We **never** trust what the agent said. We verify the work by running it.

### Trajectory
We score trajectory properties instead of matching a reference trace:
- exploration before mutation
- recovery quality after failures
- tool-family fit for the task
- safety and forbidden operations

### Behavior
Behavior is deterministic and transcript-based:
- planning when the task calls for it
- progress communication on longer tasks
- graceful blocker or refusal language
- no destructive commands

### Reliability
Per-run score uses completion, trajectory, and behavior.
Per-task leaderboard score then adds a reliability term across all runs using `pass^k`, pass rate, and variance.

Current formula:
- normalized weighted average of `0.4 completion + 0.3 trajectory + 0.2 behavior`
- `0.9 * mean_run_score + 0.1 * reliability_score`

### Query Benchmark Layer
- scenario coverage mapped from a 12-domain user-query dataset
- `clear` and `ambiguous` prompt variants for robustness slices
- pass / partial / fail delivery buckets as a user-facing outcome view
- weighted query-score reporting for a second aggregate view

### Advisory LLM Judge
- optional task-level rubric checks for nuanced quality on selected high-ambiguity tasks
- artifact-aware judging prompts using the produced files plus transcript excerpts
- reported as a sidecar signal and does not change the official deterministic leaderboard score

### Task Design
- 20 tasks across 5 tiers
- deterministic local services for browser tasks
- multi-file assets with real bugs, missing tests, and migration work
- scripted user turns and optional multi-phase fresh-session tasks

### Coverage snapshot
```text
Tier mix
tier1 | ###   3
tier2 | ##### 5
tier3 | ##### 5
tier4 | ####  4
tier5 | ###   3

Family mix
repo        | ###### 6
coding      | ####   4
multi_tool  | ###    3
adversarial | ###    3
browser     | ##     2
tools       | ##     2
```

### pass^k: Production Reliability
| pass@1 | pass^5 | pass^8 |
|--------|--------|--------|
| 90% | 59% | 43% |
| 95% | 77% | 66% |
| 99% | 95% | 92% |

### Based on
- [TAU-bench](https://github.com/sierra-research/tau-bench) — POMDP, pass^k, state verification
- [SWE-bench](https://www.swebench.com/) — deterministic test-based verification
- [WebArena](https://webarena.dev/) — programmatic state assertions
- [Anthropic eval guide](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
""")


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
