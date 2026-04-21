"""Decompose run_score variance into seed-noise vs capability-signal.

Each task has 3 runs per model (same prompt, different random seed).
  σ²_seed(task, model)  = variance across the 3 runs of (task, model)
  σ²_capability(task)   = variance across model means for the task

Signal-to-noise ratio per task:
  SNR(task) = σ²_capability / σ²_seed

High SNR → differences between models on this task are REAL (not noise).
Low SNR  → the 3-run variance per model is so large that cross-model gaps
           are indistinguishable from seed noise. These tasks don't
           discriminate models reliably.

Aggregated over all 40 tasks, we also decompose TOTAL variance:
  total_var = mean_capability_var + mean_seed_var
  capability_fraction = mean_capability_var / total_var

This answers "what fraction of the benchmark signal is real model
capability vs. run-to-run luck?"

Usage:
    .venv/bin/python3 scripts/variance_decomp.py
"""

from __future__ import annotations

import glob
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, variance

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "data" / "run_cache_archive" / "v2026-4-19-full"

MODELS = {
    "opus46": ("anthropic_claude-opus-4-6", "Opus 4.6"),
    "opus47": ("anthropic_claude-opus-4-7", "Opus 4.7"),
    "sonnet46": ("anthropic_claude-sonnet-4-6", "Sonnet 4.6"),
    "gpt54": ("openai_gpt-5.4", "GPT 5.4"),
    "gemini": ("google_gemini-3.1-pro-preview", "Gemini 3.1"),
    "glm": ("openrouter_z-ai_glm-5.1", "GLM 5.1"),
    "minimax": ("openrouter_minimax_minimax-m2.7", "MiniMax M2.7"),
    "kimi25": ("openrouter_moonshotai_kimi-k2.5", "Kimi K2.5"),
    "qwen": ("openrouter_qwen_qwen3.6-plus", "Qwen 3.6"),
}


def main() -> None:
    # {task: {model: [run_scores]}}
    scores: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for label, (sub, _) in MODELS.items():
        for p in glob.glob(f"{ARCH}/{sub}/*/run*.json"):
            task = p.split("/")[-2]
            try:
                d = json.loads(Path(p).read_text())
            except Exception:
                continue
            scores[task].setdefault(label, []).append(d.get("run_score", 0))

    # Per-task: seed var per model, cross-model var of means, SNR
    task_stats = []
    for task, per_model in scores.items():
        # Only use models with all 3 runs for clean seed-variance estimate
        model_vars = []
        model_means = []
        for m, runs in per_model.items():
            if len(runs) >= 2:
                model_vars.append(variance(runs))
                model_means.append(mean(runs))
        if len(model_means) < 2 or not model_vars:
            continue
        mean_seed_var = mean(model_vars)        # noise
        cap_var = variance(model_means)          # signal
        snr = cap_var / (mean_seed_var + 1e-9)
        task_stats.append({
            "task": task,
            "seed_var": mean_seed_var,
            "cap_var": cap_var,
            "snr": snr,
            "n_models": len(model_means),
        })

    # Sort by SNR
    task_stats.sort(key=lambda x: -x["snr"])

    print(f"{'Task':<38}  {'seed_var':>9}  {'cap_var':>9}  {'SNR':>8}")
    print("-" * 70)
    for r in task_stats:
        print(f"{r['task']:<38}  {r['seed_var']:>9.4f}  {r['cap_var']:>9.4f}  "
              f"{r['snr']:>8.2f}")

    # Aggregate decomposition
    total_seed = mean(r["seed_var"] for r in task_stats)
    total_cap = mean(r["cap_var"] for r in task_stats)
    total = total_seed + total_cap
    cap_frac = total_cap / (total + 1e-9)

    print("\n=== AGGREGATE VARIANCE DECOMPOSITION ===")
    print(f"  Mean seed variance (noise):        {total_seed:.5f}")
    print(f"  Mean capability variance (signal): {total_cap:.5f}")
    print(f"  Capability fraction:               {cap_frac:.1%}")
    print(f"  (= what % of run_score variance comes from real model differences)")

    # Classify tasks by SNR tiers
    high_snr = [r for r in task_stats if r["snr"] >= 5]
    mid_snr = [r for r in task_stats if 1 <= r["snr"] < 5]
    low_snr = [r for r in task_stats if r["snr"] < 1]
    print(f"\n=== SNR TIERS ===")
    print(f"  High SNR (≥5):       {len(high_snr)} tasks — differentiate models reliably")
    print(f"  Mid SNR (1–5):       {len(mid_snr)} tasks — moderate signal")
    print(f"  Low SNR (<1):        {len(low_snr)} tasks — seed noise ≥ capability signal")
    print(f"     (these tasks give random-ish results; weight down)")

    # Write output
    out_path = ROOT / "reports" / "variance_decomposition.json"
    out_path.write_text(json.dumps({
        "per_task": task_stats,
        "aggregate": {
            "mean_seed_var": total_seed,
            "mean_cap_var": total_cap,
            "capability_fraction": cap_frac,
        },
    }, indent=2))
    print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
