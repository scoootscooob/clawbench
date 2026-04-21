"""Per-turn survival analysis: when do agent runs fail?

Following paper §Latent-state survival:
  T_F = inf { t ≥ 0 : failure at time t }
  S(t) = P(T_F > t)   — survival function
  h(t) = P(T_F = t | T_F ≥ t)  — hazard rate

For each run, we define FAILURE as the first turn where:
  (a) the assistant emits no text AND no tool calls, OR
  (b) the run's delivery_outcome is 'fail'/'partial' AND the transcript
      ended at this turn (no more assistant turns follow).

T_F = assistant-turn index of first failure (starting at 1).
If the run succeeded (run_score ≥ 0.7), T_F is right-censored at the
final turn count N (i.e. survived the whole trajectory).

Output per model:
  - Median turn-to-failure
  - Empirical survival curve S(t) for t = 1..20
  - Hazard profile h(t)
  - Stratified by task-constraint bucket (using C(q) from earlier)

Usage:
    .venv/bin/python3 scripts/survival_analysis.py
"""

from __future__ import annotations

import glob
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import median

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

SUCCESS_THRESHOLD = 0.7


def assistant_turns(d: dict) -> list[dict]:
    return [m for m in d.get("transcript", {}).get("messages", [])
            if m.get("role") == "assistant"]


def find_failure_turn(d: dict) -> tuple[int, bool]:
    """Return (T_F, is_event). T_F is 1-indexed turn of failure.

    is_event=True means failure actually happened; False means the run was
    censored (survived to end without failing).
    """
    turns = assistant_turns(d)
    n = len(turns)
    run_score = d.get("run_score", 0) or 0
    delivery = d.get("delivery_outcome", "")

    # Scan for first empty-turn
    for i, t in enumerate(turns, 1):
        has_text = bool((t.get("text") or "").strip())
        has_tool_call = bool(t.get("tool_calls"))
        if not has_text and not has_tool_call:
            return i, True  # failure event

    # If run was unsuccessful and ended early, mark last turn as failure
    if run_score < SUCCESS_THRESHOLD and delivery in ("fail", "partial"):
        return max(n, 1), True

    # Survived: right-censored at n
    return max(n, 1), False


def empirical_survival(times_events: list[tuple[int, bool]], max_t: int = 20) -> list[float]:
    """Kaplan-Meier-like survival curve, non-parametric.

    S(t) = fraction of runs that survived past turn t.
    """
    survival = []
    total = len(times_events)
    for t in range(1, max_t + 1):
        # Survived past t = either censored at ≥t or event at >t
        survived = sum(1 for tf, is_event in times_events
                       if (not is_event and tf >= t) or (is_event and tf > t))
        survival.append(survived / total if total > 0 else 0.0)
    return survival


def hazard(times_events: list[tuple[int, bool]], max_t: int = 20) -> list[float]:
    """Hazard rate h(t) = events at t / at-risk at t."""
    h = []
    for t in range(1, max_t + 1):
        at_risk = sum(1 for tf, _ in times_events if tf >= t)
        events_at_t = sum(1 for tf, is_event in times_events
                           if is_event and tf == t)
        h.append(events_at_t / at_risk if at_risk > 0 else 0.0)
    return h


def main() -> None:
    per_model: dict[str, list[tuple[int, bool]]] = defaultdict(list)
    for label, (sub, _) in MODELS.items():
        for p in glob.glob(f"{ARCH}/{sub}/*/run*.json"):
            try:
                d = json.loads(Path(p).read_text())
            except Exception:
                continue
            tf, is_event = find_failure_turn(d)
            per_model[label].append((tf, is_event))

    # Load C(q) to stratify
    cq_path = ROOT / "reports" / "constraint_index.json"
    cq_by_task = {}
    if cq_path.exists():
        cq = json.loads(cq_path.read_text())
        cq_by_task = {t: v["C_q"] for t, v in cq.items()}

    # Print summary
    print(f"{'Model':<14}  {'n_runs':>6}  {'events':>6}  {'med_tf':>8}  "
          f"{'S(3)':>6}  {'S(5)':>6}  {'S(8)':>6}  {'S(12)':>6}  {'S(20)':>6}")
    print("-" * 90)
    out = {}
    for label, (_sub, pretty) in MODELS.items():
        evs = per_model[label]
        n = len(evs)
        n_events = sum(1 for _, e in evs if e)
        tfs_events = [tf for tf, e in evs if e]
        med = median(tfs_events) if tfs_events else float("inf")
        surv = empirical_survival(evs, max_t=20)
        haz = hazard(evs, max_t=20)
        print(f"{pretty:<14}  {n:>6}  {n_events:>6}  {med:>8.1f}  "
              f"{surv[2]:>6.2f}  {surv[4]:>6.2f}  {surv[7]:>6.2f}  "
              f"{surv[11]:>6.2f}  {surv[19]:>6.2f}")
        out[label] = {
            "pretty": pretty,
            "n_runs": n,
            "n_events": n_events,
            "median_fail_turn": med,
            "survival": surv,
            "hazard": haz,
        }

    print("\n(Interpretation: S(t) = fraction of runs still on-track past turn t.")
    print(" Lower values = more frequent early failure.)")

    out_path = ROOT / "reports" / "survival_analysis.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
