"""Classify each archived run's dynamical regime from its turn trajectory.

Following "When LLMs Are Dreaming..." §What We Expect to See:

  TRAPPED/ATTRACTOR   — low support (Vol_log), high recurrence, high BOPS.
                        Agent converged to a point; may be good (solved it)
                        or bad (got stuck in a loop on a single idea).

  LIMIT-CYCLE         — high recurrence + bounded drift + quasi-periodic revisits.
                        Agent loops between a few states.

  DIFFUSIVE/WANDERING — growing support, rising drift, low recurrence.
                        Agent explores without converging; often "goal drift".

  SENSITIVE           — (requires paraphrased-pair runs; skip here.)

  TOO-SHORT           — trajectory < 3 assistant turns; can't classify dynamics.

We work in a TF-IDF bag-of-words embedding space (same vocab as C(q)),
with each turn's state vector = its assistant text + tool-call args.

Metrics per run:
  - drift_mean:  mean ||e_t − e_{t−1}|| across turns
  - from_start:  max ||e_t − e_0||  (farthest the run drifted from origin)
  - recurrence:  max_{i<j, j−i≥2} cos(e_i, e_j)  — best return-after-gap match
  - vol_log:     log det(Σ + εI) over turn states — support volume proxy

Classifier rules (tuned empirically on the distribution):
  if n_turns < 3                              → too_short
  elif drift_mean < 0.15 and vol_log < −6     → trapped
  elif recurrence > 0.80 and drift_mean < 0.25 → limit_cycle
  elif drift_mean > 0.35 and vol_log > −3     → diffusive
  else                                         → mixed

Output: reports/regimes.json with per-run classification.

Usage:
    .venv/bin/python3 scripts/classify_regimes.py
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "data" / "run_cache_archive" / "v2026-4-19-full"

MODELS = [
    "anthropic_claude-opus-4-6", "anthropic_claude-opus-4-7",
    "anthropic_claude-sonnet-4-6", "openai_gpt-5.4",
    "google_gemini-3.1-pro-preview", "openrouter_z-ai_glm-5.1",
    "openrouter_minimax_minimax-m2.7", "openrouter_moonshotai_kimi-k2.5",
    "openrouter_qwen_qwen3.6-plus",
]

WORD_RE = re.compile(r"[a-z]{3,}")
STOPWORDS = set("the and that with this have from what your will can but not "
                "was will are been one would there been they will their has "
                "had its were only some than about these which into also each "
                "when where them how who them very much more most other then "
                "here such does like just make many like want need take".split())


def tokenize(text: str) -> list[str]:
    return [w for w in WORD_RE.findall((text or "").lower()) if w not in STOPWORDS]


def build_vocab(all_turn_texts: list[str], top_k: int = 500) -> dict[str, int]:
    c = Counter()
    for t in all_turn_texts:
        c.update(set(tokenize(t)))
    return {w: i for i, (w, _) in enumerate(c.most_common(top_k))}


def vectorize(text: str, vocab: dict[str, int]) -> np.ndarray:
    v = np.zeros(len(vocab), dtype=np.float32)
    for w, c in Counter(tokenize(text)).items():
        if w in vocab:
            v[vocab[w]] = c
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def turn_texts(run_data: dict) -> list[str]:
    """Extract one text string per assistant turn (text + tool-call summary)."""
    out = []
    for m in run_data.get("transcript", {}).get("messages", []):
        if m.get("role") != "assistant":
            continue
        parts = []
        if m.get("text"):
            parts.append(m["text"])
        for tc in (m.get("tool_calls") or []):
            name = tc.get("name", "")
            args_str = json.dumps(tc.get("arguments", {}))[:200]
            parts.append(f"{name} {args_str}")
        if parts:
            out.append(" ".join(parts))
    return out


def trajectory_metrics(vecs: np.ndarray) -> dict:
    """Compute dynamical metrics over a (n_turns, d) trajectory matrix."""
    n = vecs.shape[0]
    if n < 2:
        return {"n_turns": n, "drift_mean": 0.0, "from_start": 0.0,
                "recurrence": 0.0, "vol_log": -12.0}
    # Drift: consecutive distances
    diffs = np.linalg.norm(np.diff(vecs, axis=0), axis=1)
    drift_mean = float(diffs.mean())
    # From start: max distance from turn 0
    dists_from_0 = np.linalg.norm(vecs - vecs[0:1], axis=1)
    from_start = float(dists_from_0.max())
    # Recurrence: best non-adjacent cosine similarity (ignoring immediate neighbors)
    recurrence = 0.0
    for i in range(n):
        for j in range(i + 2, n):
            ni, nj = np.linalg.norm(vecs[i]), np.linalg.norm(vecs[j])
            if ni > 0 and nj > 0:
                c = float(vecs[i] @ vecs[j] / (ni * nj))
                if c > recurrence:
                    recurrence = c
    # Vol_log: log det of turn-state covariance
    if n >= 3:
        Sigma = np.cov(vecs.T)
        # Use log|Σ + εI|; since d is large (500) we take eigenvalues + clip
        eigs = np.linalg.eigvalsh(Sigma + 1e-6 * np.eye(vecs.shape[1], dtype=np.float32))
        vol_log = float(np.log(np.clip(eigs, 1e-12, None)).sum())
    else:
        vol_log = -12.0
    return {
        "n_turns": n,
        "drift_mean": drift_mean,
        "from_start": from_start,
        "recurrence": recurrence,
        "vol_log": vol_log,
    }


def classify(m: dict, thresholds: dict) -> str:
    """Classify based on quartile thresholds of the actual distribution.

    Thresholds (set empirically from observed distribution):
      drift_low  = p25  drift_hi = p75
      vol_low    = p25  vol_hi   = p75
      rec_hi     = p75

    Rules (priority order):
      n_turns < 3             → too_short
      drift < drift_low AND vol < vol_low  → trapped
      rec > rec_hi AND drift < median       → limit_cycle
      drift > drift_hi AND vol > vol_hi     → diffusive
      else                                  → mixed
    """
    n = m["n_turns"]
    if n < 3:
        return "too_short"
    d = m["drift_mean"]
    rec = m["recurrence"]
    vol = m["vol_log"]
    if d < thresholds["drift_low"] and vol < thresholds["vol_low"]:
        return "trapped"
    if rec > thresholds["rec_hi"] and d < thresholds["drift_med"]:
        return "limit_cycle"
    if d > thresholds["drift_hi"] and vol > thresholds["vol_hi"]:
        return "diffusive"
    return "mixed"


def main() -> None:
    # First pass: collect turn texts to build vocab
    all_turn_texts: list[str] = []
    run_turns: dict[tuple, list[str]] = {}
    for model in MODELS:
        for rf in (ARCH / model).rglob("run*.json"):
            try:
                d = json.loads(rf.read_text())
            except Exception:
                continue
            task = rf.parent.name
            run_idx = int(re.match(r"run(\d+)", rf.stem).group(1))
            ts = turn_texts(d)
            run_turns[(model, task, run_idx)] = ts
            all_turn_texts.extend(ts)

    vocab = build_vocab(all_turn_texts, top_k=500)
    print(f"Runs collected: {len(run_turns)}  vocab size: {len(vocab)}")

    # Second pass: vectorize + compute metrics
    per_run: dict[str, dict] = {}
    for key, ts in run_turns.items():
        model, task, run_idx = key
        if not ts:
            continue
        vecs = np.stack([vectorize(t, vocab) for t in ts])
        m = trajectory_metrics(vecs)
        per_run[f"{model}/{task}/run{run_idx}"] = m

    # Derive thresholds from actual distribution of n_turns>=3 runs
    drifts = np.array([v["drift_mean"] for v in per_run.values() if v["n_turns"] >= 3])
    recs = np.array([v["recurrence"] for v in per_run.values() if v["n_turns"] >= 3])
    vols = np.array([v["vol_log"] for v in per_run.values() if v["n_turns"] >= 3])
    thresholds = {
        "drift_low": float(np.percentile(drifts, 25)),
        "drift_med": float(np.percentile(drifts, 50)),
        "drift_hi":  float(np.percentile(drifts, 75)),
        "vol_low":   float(np.percentile(vols, 25)),
        "vol_hi":    float(np.percentile(vols, 75)),
        "rec_hi":    float(np.percentile(recs, 75)),
    }
    print(f"\nThresholds (quartile-based from observed distribution):")
    for k, v in thresholds.items():
        print(f"  {k:<12}  {v:>10.3f}")

    # Apply classifier with thresholds
    for key in per_run:
        per_run[key]["regime"] = classify(per_run[key], thresholds)

    # Summary by regime
    counts = Counter(v["regime"] for v in per_run.values())
    print(f"\nRegime distribution (n={len(per_run)} runs):")
    for regime, n in counts.most_common():
        print(f"  {regime:<14} {n:>4}  ({100*n/len(per_run):>4.1f}%)")

    # Per-model regime breakdown
    print(f"\n{'Model':<10}  " + " ".join(f"{r:>11}" for r in ["too_short", "trapped", "limit_cycle", "diffusive", "mixed"]))
    print("-" * 70)
    pm_counts = defaultdict(Counter)
    for key, v in per_run.items():
        model = key.split("/")[0]
        pm_counts[model][v["regime"]] += 1
    for model in MODELS:
        row = [f"{model.split('_')[-1][:9]:<10}"]
        for r in ["too_short", "trapped", "limit_cycle", "diffusive", "mixed"]:
            row.append(f"{pm_counts[model][r]:>11}")
        print("  ".join(row))

    # Write output
    out = ROOT / "reports" / "regimes.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(per_run, indent=2))
    print(f"\nWrote: {out}")


if __name__ == "__main__":
    main()
