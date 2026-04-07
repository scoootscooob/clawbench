"""ClawBench HF Space — leaderboard + submission + background eval worker.

This single file is the entry point for the HF Docker Space.
It runs:
1. Gradio frontend (leaderboard + submission form + queue status)
2. Background eval worker (polls queue, runs benchmark, stores results)

All state persists via:
- /data/ directory (HF persistent storage)
- HF Dataset (openclaw/clawbench-results) for cross-restart persistence
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("clawbench.app")

RESULTS_DIR = Path("/data/results") if Path("/data").exists() else Path("data/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Preset models for quick submission
# ---------------------------------------------------------------------------

PRESET_MODELS = {
    # Top 15 by OpenRouter usage + key Chinese/open-source models
    # --- Proprietary leaders ---
    "Claude Sonnet 4.6": "anthropic/claude-sonnet-4-6",
    "Claude Opus 4.6": "anthropic/claude-opus-4-6",
    "GPT-5.4": "openai/gpt-5.4",
    "GPT-5.4 Mini": "openai/gpt-5.4-mini",
    "Gemini 3.1 Pro": "google/gemini-3.1-pro-preview",
    "Gemini 3 Flash": "google/gemini-3-flash-preview",
    "Grok 4.20": "x-ai/grok-4.20",
    # --- Chinese models ---
    "Qwen 3.6 Plus": "qwen/qwen3.6-plus",
    "DeepSeek V3.1": "deepseek/deepseek-chat-v3.1",
    "Kimi K2.5": "moonshotai/kimi-k2.5",
    "MiniMax M2.7": "minimax/minimax-m2.7",
    "GLM 5.1": "z-ai/glm-5.1",
    "GLM 5 Turbo": "z-ai/glm-5-turbo",
    # --- Open-source (via HF Inference or OpenRouter free) ---
    "Gemma 4 31B": "google/gemma-4-31b-it",
    "Llama 3.3 70B": "meta-llama/llama-3.3-70b-instruct",
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
        ds = load_dataset(
            os.environ.get("CLAWBENCH_QUEUE_DATASET", "openclaw/clawbench-results"),
            split="submissions",
        )
        for row in ds:
            rows.append(_flatten_result(row))
    except Exception:
        pass

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
            "Model", "Composite", "State", "Trajectory", "Behavior",
            "pass^k", "CI", "Tasks", "Timestamp",
        ])

    # Deduplicate by model (keep latest)
    seen = {}
    for r in rows:
        key = r["Model"]
        if key not in seen or r["Timestamp"] > seen[key]["Timestamp"]:
            seen[key] = r

    df = pd.DataFrame(list(seen.values()))
    df = df.sort_values("Composite", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    df.index.name = "#"
    return df


def _flatten_result(data: dict) -> dict:
    tasks = data.get("task_results", [])
    n_tasks = len(tasks) if isinstance(tasks, list) else 0
    return {
        "Model": data.get("model", ""),
        "Composite": round(data.get("overall_composite", 0), 3),
        "State": round(data.get("overall_state", 0), 3),
        "Trajectory": round(data.get("overall_trajectory", 0), 3),
        "Behavior": round(data.get("overall_behavior", 0), 3),
        "pass^k": f"{data.get('overall_pass_hat_k', 0):.0%}",
        "CI": f"{data.get('overall_ci_lower', 0):.2f}-{data.get('overall_ci_upper', 0):.2f}",
        "Tasks": n_tasks,
        "Timestamp": data.get("timestamp", "")[:16],
    }


def load_queue() -> pd.DataFrame:
    jobs = asyncio.run(queue.list_jobs(limit=20))
    if not jobs:
        return pd.DataFrame(columns=["ID", "Model", "Status", "Submitted", "Runs"])
    rows = []
    for j in jobs:
        rows.append({
            "ID": j.job_id,
            "Model": j.request.model,
            "Status": j.status.value,
            "Submitted": j.submitted_at[:16] if j.submitted_at else "",
            "Runs": j.request.runs_per_task,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Submission handler
# ---------------------------------------------------------------------------


def submit_model(model: str, preset: str, provider: str, runs: int, category: str | None, submitter: str) -> str:
    # Use preset if selected, otherwise use custom model ID
    model_id = PRESET_MODELS.get(preset, "") or model.strip()
    if not model_id:
        return "Please enter a model ID or select a preset."

    cat = category if category != "all" else None
    request = SubmissionRequest(
        model=model_id,
        provider=provider.strip(),
        runs_per_task=int(runs),
        category=cat,
        submitter=submitter.strip(),
    )
    job = asyncio.run(queue.submit(request))
    return f"Submitted [{model_id}]! Job ID: {job.job_id}. Check the Queue tab."


def submit_all_presets(runs: int, submitter: str) -> str:
    """Submit all preset models at once."""
    submitted = []
    for name, model_id in PRESET_MODELS.items():
        request = SubmissionRequest(
            model=model_id,
            provider="",
            runs_per_task=int(runs),
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

**Three axes**: Environment State | Tool Trajectory | Agent Behavior
**Primary metric**: pass^k (ALL runs must succeed)
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
            "run via HuggingFace Inference API. Proprietary models need API keys set as Space secrets."
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
        with gr.Row():
            runs_input = gr.Slider(
                minimum=1, maximum=10, value=3, step=1,
                label="Runs per task (higher = more reliable pass^k)",
            )
            category_input = gr.Dropdown(
                choices=["all", "general", "openclaw", "adversarial"],
                value="all",
                label="Category",
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
            inputs=[model_input, preset_input, provider_input, runs_input, category_input, submitter_input],
            outputs=submit_output,
        )
        submit_all_btn.click(
            fn=submit_all_presets,
            inputs=[runs_input, submitter_input],
            outputs=submit_output,
        )

        gr.Markdown("""
**15 preset models (by OpenRouter usage ranking):**

| Model | Provider | Notes |
|-------|----------|-------|
| Claude Sonnet 4.6 | Anthropic | #1 on OpenRouter |
| Claude Opus 4.6 | Anthropic | Flagship |
| GPT-5.4 | OpenAI | Latest |
| GPT-5.4 Mini | OpenAI | Cost-efficient |
| Gemini 3.1 Pro | Google | Latest |
| Gemini 3 Flash | Google | Fast |
| Grok 4.20 | xAI | Latest |
| Qwen 3.6 Plus | Alibaba | Latest Chinese |
| DeepSeek V3.1 | DeepSeek | Latest |
| Kimi K2.5 | Moonshot AI | Latest |
| MiniMax M2.7 | MiniMax | Latest |
| GLM 5.1 | Zhipu AI | Latest |
| GLM 5 Turbo | Zhipu AI | Fast |
| Gemma 4 31B | Google | Open-source |
| Llama 3.3 70B | Meta | Open-source |
""")

    with gr.Tab("Queue"):
        gr.Markdown("### Evaluation Queue")
        queue_refresh = gr.Button("Refresh", scale=0)
        queue_table = gr.Dataframe(value=load_queue, interactive=False, wrap=True)
        queue_refresh.click(fn=load_queue, outputs=queue_table)

    with gr.Tab("Methodology"):
        gr.Markdown("""
## How ClawBench evaluates agents

### Axis 1: Environment State (ground truth)
After the agent runs, we query the actual environment — filesystem, memory, cron jobs, gateway state.
We **never** trust what the agent said. We verify the world changed.

### Axis 2: Trajectory (tool call graph)
Precision/recall/F1 on tool call sequences vs reference.
Plus ordering (LIS-based), efficiency scoring, and forbidden tool detection.

### Axis 3: Behavior (LLM judge)
Only for subjective quality. Judge is scoped: does NOT score completion or efficiency.

### Simulated Users
- **Static**: deterministic baseline
- **Adaptive**: LLM-generated, reacts to agent
- **Adversarial**: contradictions, impossible requests, hallucination traps

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
