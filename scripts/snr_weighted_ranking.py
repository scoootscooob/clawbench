"""SNR × |C(q)|-weighted ranking — the dynamical-systems-informed metric.

Motivation: from variance_decomp.py we know 47% of run_score variance is
seed noise. From compute_constraint_index.py we know some tasks are
high-constraint (everyone converges) and others are open-ended (responses
diverge for style reasons, not capability).

Weighted mean:
    w(task) = SNR(task) × |C(q)(task)|
    score(model) = Σ_task w(task) · mean_run_score(task, model) / Σ_task w(task)

Why:
- High SNR tasks contribute more than low-SNR tasks (noise-weighted)
- |C(q)| amplifies tasks that are either strongly constrained OR strongly
  open-ended (i.e. measures what they're supposed to measure, regardless
  of polarity)
- Moderate C(q) tasks (C near 0) are inherently ambiguous — down-weighted

Outputs:
  - Per-model weighted score
  - Comparison against flat-mean ranking
  - Published to reports/snr_weighted_ranking.json
"""

from __future__ import annotations

import glob
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "data" / "run_cache_archive" / "v2026-4-19-full"
REPORTS = ROOT / "reports"

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
    cq = json.loads((REPORTS / "constraint_index.json").read_text())
    var = json.loads((REPORTS / "variance_decomposition.json").read_text())
    snr_by_task = {r["task"]: r["snr"] for r in var["per_task"]}

    # Per (model, task): mean run_score over the 3 runs
    per_mt: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for label, (sub, _) in MODELS.items():
        for p in glob.glob(f"{ARCH}/{sub}/*/run*.json"):
            try:
                d = json.loads(Path(p).read_text())
            except Exception:
                continue
            task = p.split("/")[-2]
            per_mt[label].setdefault(task, []).append(d.get("run_score", 0))
    per_mt_mean = {
        m: {t: mean(v) for t, v in d.items() if v} for m, d in per_mt.items()
    }

    # Only consider tasks present in both C(q) and SNR
    common_tasks = sorted(set(cq) & set(snr_by_task))
    print(f"Using {len(common_tasks)} tasks with both C(q) and SNR.")

    # Compute weights w(task) = SNR × |C(q)|, clamped to [0, ∞)
    weights = {}
    for t in common_tasks:
        w = max(0.0, snr_by_task[t]) * abs(cq[t]["C_q"])
        weights[t] = w
    # Also: SNR-only weighting (simpler, no C(q))
    snr_weights = {t: max(0.0, snr_by_task[t]) for t in common_tasks}
    # Also: Winsorize — clamp top-1 task's weight to 95th percentile to
    # prevent single task from dominating
    import numpy as _np
    _w95 = float(_np.percentile(list(weights.values()), 95))
    weights_wins = {t: min(w, _w95) for t, w in weights.items()}
    wsum = sum(weights.values())
    if wsum == 0:
        print("All weights zero — bail.")
        return

    # Compute per-model scores under 3 variants
    results = []
    snr_sum = sum(snr_weights.values())
    wins_sum = sum(weights_wins.values())
    for label, (sub, pretty) in MODELS.items():
        task_means = per_mt_mean.get(label, {})
        if not task_means:
            continue
        num_cq = sum(weights[t] * task_means.get(t, 0) for t in common_tasks)
        num_snr = sum(snr_weights[t] * task_means.get(t, 0) for t in common_tasks)
        num_wins = sum(weights_wins[t] * task_means.get(t, 0) for t in common_tasks)
        wscore = num_cq / wsum
        snr_only = num_snr / snr_sum if snr_sum > 0 else 0
        wins_score = num_wins / wins_sum if wins_sum > 0 else 0
        flat = mean(task_means[t] for t in common_tasks if t in task_means)
        results.append((label, pretty, flat, wscore, snr_only, wins_score))

    print()
    print(f"{'Model':<16}  {'Flat':>7}  {'SNR×|C|':>8}  {'Winsorized':>11}  {'SNR-only':>9}")
    print("-" * 66)
    # Rank by winsorized variant (primary)
    for label, pretty, flat, w, snr_only, wins in sorted(results, key=lambda x: -x[5]):
        print(f"{pretty:<16}  {flat:>7.4f}  {w:>8.4f}  {wins:>11.4f}  {snr_only:>9.4f}")

    # Rank comparisons
    print("\n=== Ranking shifts vs flat-mean (winsorized) ===")
    flat_rank_order = sorted(results, key=lambda x: -x[2])
    flat_rank = {r[0]: i + 1 for i, r in enumerate(flat_rank_order)}
    wins_rank_order = sorted(results, key=lambda x: -x[5])
    print(f"{'Rank':<5}{'Model':<16} {'Flat':>8}  {'Winsorized':>11}  {'Δrank':>6}")
    for i, (label, pretty, flat, _w, _snr, wins) in enumerate(wins_rank_order, 1):
        fr = flat_rank[label]
        move = ""
        if fr > i: move = f"↑{fr-i}"
        elif fr < i: move = f"↓{i-fr}"
        print(f"{i:<5}{pretty:<16} {flat:>8.4f}  {wins:>11.4f}  {move:>6}")

    # Save
    out = {
        "flat_score": {r[0]: r[2] for r in results},
        "snr_x_cq_weighted": {r[0]: r[3] for r in results},
        "snr_x_cq_winsorized": {r[0]: r[5] for r in results},
        "snr_only_weighted": {r[0]: r[4] for r in results},
        "weights_per_task": weights,
        "common_tasks": common_tasks,
    }
    (REPORTS / "snr_weighted_ranking.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote reports/snr_weighted_ranking.json")

    # Show top-5 contributing tasks (highest weight) for context
    print()
    print("Top-10 tasks by weight (SNR × |C(q)|):")
    for t, w in sorted(weights.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {t:<38}  SNR={snr_by_task[t]:>5.1f}  |C(q)|={abs(cq[t]['C_q']):>5.2f}  w={w:>6.2f}")


if __name__ == "__main__":
    main()
