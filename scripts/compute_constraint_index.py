"""Compute Constraint Index C(q) per task from existing v4-19-full archive.

Following "When LLMs Are Dreaming..." paper §Query-design:

  C(q) = z(PR(q)) + z(entropy(q)) + z(BOPS(q))

Where:
  - PR(q): participation ratio = (tr Σ)² / tr(Σ²) of response embeddings
           across all (model, run) responses to query q. Low PR = everyone
           writes similar thing (prompt is constrained). High PR = responses
           spread out (prompt is open-ended).
  - entropy(q): Shannon entropy of (discretized) response-feature distribution.
  - BOPS(q): Bayesian Optimal Prediction Score — how well can we predict
             response given q? Proxied here as inter-run cosine similarity
             for the same model (high similarity = high predictability).

Since we don't have sentence-transformers, we use TF-IDF-style bag-of-words
from the final assistant message per run. This is crude but measures the
same signal — whether models produce similar vs divergent output.

Output: reports/constraint_index.json with per-task C(q) components +
        combined z-score.

Usage:
    .venv/bin/python3 scripts/compute_constraint_index.py
"""

from __future__ import annotations

import json
import re
import glob
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import entropy as shannon_entropy

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


def final_assistant_text(run_path: Path, max_chars: int = 4000) -> str:
    """Extract the last assistant message text + tool-call arg summary."""
    try:
        d = json.loads(run_path.read_text())
    except Exception:
        return ""
    msgs = d.get("transcript", {}).get("messages", [])
    texts = []
    for m in msgs:
        if m.get("role") != "assistant":
            continue
        if m.get("text"):
            texts.append(m["text"])
        for tc in (m.get("tool_calls") or []):
            name = tc.get("name", "")
            args_str = json.dumps(tc.get("arguments", {}))[:200]
            texts.append(f"{name} {args_str}")
    blob = " ".join(texts)[:max_chars]
    return blob


def tokenize(text: str) -> list[str]:
    return [w for w in WORD_RE.findall(text.lower()) if w not in STOPWORDS]


def build_vocab(texts: list[str], top_k: int = 500) -> dict[str, int]:
    """Build a vocab of the top-k most common tokens across all texts."""
    counter = Counter()
    for t in texts:
        counter.update(set(tokenize(t)))
    return {w: i for i, (w, _) in enumerate(counter.most_common(top_k))}


def vectorize(text: str, vocab: dict[str, int]) -> np.ndarray:
    """TF-IDF-ish: token frequency normalized to unit L2 for cosine geometry."""
    v = np.zeros(len(vocab), dtype=np.float32)
    toks = tokenize(text)
    if not toks:
        return v
    counts = Counter(toks)
    for w, c in counts.items():
        if w in vocab:
            v[vocab[w]] = c
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def participation_ratio(X: np.ndarray) -> float:
    """PR(X) = (tr Σ)² / tr(Σ²). Measures effective dimensionality 1–d."""
    if X.shape[0] < 2:
        return 1.0
    Sigma = np.cov(X.T)
    if Sigma.ndim == 0:
        return 1.0
    tr = np.trace(Sigma)
    tr_sq = np.trace(Sigma @ Sigma)
    if tr_sq < 1e-12:
        return 1.0
    return float(tr ** 2 / tr_sq)


def response_entropy(X: np.ndarray, n_clusters: int = 8) -> float:
    """Entropy of a k-means-like discretization of responses.

    Since we have small n per task (~27 responses), we cluster by nearest-
    centroid using the top-few PCA directions. Simpler: use normalized
    eigenvalues of covariance as a proxy for entropy over principal modes.
    """
    if X.shape[0] < 2:
        return 0.0
    Sigma = np.cov(X.T)
    eigs = np.linalg.eigvalsh(Sigma)
    eigs = np.clip(eigs, 1e-12, None)
    eigs = eigs / eigs.sum()
    return float(shannon_entropy(eigs, base=2))


def bops_inter_run_predictability(run_vecs: dict[str, list[np.ndarray]]) -> float:
    """BOPS proxy: inter-run cosine similarity within same model.

    High similarity = predictable (high BOPS). Low similarity = novel each run.
    Returns mean cosine across all pairs within each model, averaged across models.
    """
    per_model_means = []
    for _model, vecs in run_vecs.items():
        if len(vecs) < 2:
            continue
        sims = []
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                v1, v2 = vecs[i], vecs[j]
                n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                if n1 > 0 and n2 > 0:
                    sims.append(float(v1 @ v2 / (n1 * n2)))
        if sims:
            per_model_means.append(float(np.mean(sims)))
    return float(np.mean(per_model_means)) if per_model_means else 0.0


def main() -> None:
    # Gather: per-task list of texts + per-model list of per-run vectors
    per_task_texts: dict[str, list[str]] = defaultdict(list)
    per_task_model_runs: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for model in MODELS:
        model_dir = ARCH / model
        if not model_dir.exists():
            continue
        for task_dir in model_dir.iterdir():
            if not task_dir.is_dir():
                continue
            task = task_dir.name
            for rf in sorted(task_dir.glob("run*.json")):
                text = final_assistant_text(rf)
                if text:
                    per_task_texts[task].append(text)
                    per_task_model_runs[task][model].append(text)

    print(f"Tasks with responses: {len(per_task_texts)}")

    # Build a GLOBAL vocab across all tasks for comparable vector spaces
    all_texts = [t for ts in per_task_texts.values() for t in ts]
    vocab = build_vocab(all_texts, top_k=500)
    print(f"Global vocab size: {len(vocab)}")

    # Compute per-task metrics
    per_task: dict[str, dict] = {}
    for task, texts in sorted(per_task_texts.items()):
        if len(texts) < 5:
            continue
        X = np.stack([vectorize(t, vocab) for t in texts])  # (n_responses, vocab_dim)
        pr = participation_ratio(X)
        ent = response_entropy(X)
        # BOPS: within-model run predictability
        model_vecs: dict[str, list[np.ndarray]] = {}
        for m, ts in per_task_model_runs[task].items():
            model_vecs[m] = [vectorize(t, vocab) for t in ts]
        bops = bops_inter_run_predictability(model_vecs)
        per_task[task] = {
            "n_responses": len(texts),
            "PR": pr,
            "entropy": ent,
            "BOPS": bops,
        }

    # Z-score each component across tasks → combine into C(q)
    prs = np.array([v["PR"] for v in per_task.values()])
    ents = np.array([v["entropy"] for v in per_task.values()])
    bopss = np.array([v["BOPS"] for v in per_task.values()])

    def z(x, arr):
        return float((x - arr.mean()) / (arr.std() or 1.0))

    for task, v in per_task.items():
        zpr = z(v["PR"], prs)
        zent = z(v["entropy"], ents)
        zbops = z(v["BOPS"], bopss)
        # Paper: higher PR/entropy = MORE open-ended. Higher BOPS = MORE predictable.
        # "Constraint" = opposite of openness. C(q) high ⇒ constrained task.
        # So: C(q) = −z(PR) − z(entropy) + z(BOPS)
        v["z_PR"] = zpr
        v["z_entropy"] = zent
        v["z_BOPS"] = zbops
        v["C_q"] = -zpr - zent + zbops

    # Sort + print
    ranked = sorted(per_task.items(), key=lambda kv: -kv[1]["C_q"])
    print(f"\n{'Task':<38} {'n':>3}  {'PR':>5}  {'H':>5}  {'BOPS':>5}  {'C(q)':>6}  (constraint level)")
    print("-" * 78)
    for task, v in ranked:
        print(f"{task:<38} {v['n_responses']:>3}  {v['PR']:>5.2f}  {v['entropy']:>5.2f}  "
              f"{v['BOPS']:>5.2f}  {v['C_q']:>+6.2f}")

    out_path = ROOT / "reports" / "constraint_index.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(per_task, indent=2))
    print(f"\nWrote: {out_path}")

    # Bucket summary
    highs = [t for t, v in per_task.items() if v["C_q"] > 0.5]
    lows = [t for t, v in per_task.items() if v["C_q"] < -0.5]
    mids = [t for t, v in per_task.items() if -0.5 <= v["C_q"] <= 0.5]
    print(f"\nHigh-constraint (C>+0.5): {len(highs)} tasks  (responses converge)")
    print(f"Mid:                       {len(mids)} tasks")
    print(f"Low-constraint (C<-0.5):   {len(lows)} tasks  (responses diverge — open-ended)")


if __name__ == "__main__":
    main()
