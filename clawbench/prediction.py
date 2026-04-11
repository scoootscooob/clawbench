"""ClawBench v0.5 — Cold-start prediction via k-NN over fingerprints.

When a new Plugin Profile is submitted, this module produces a pre-run
estimate of how it will score by finding the nearest neighbors in the
historical fingerprint database and weighting their actual scores by
similarity.

This is the cold-start path. It works after as few as 3 historical
submissions, and gets sharper as more accumulate. No deep model. No
training pipeline. Pure k-NN with a well-engineered similarity metric.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

from clawbench.profile import ProfileFingerprint, fingerprint_similarity


@dataclass
class HistoricalRun:
    """One observed (profile, results) datapoint in the database."""

    profile_name: str
    fingerprint: ProfileFingerprint
    overall_score: float
    per_task_score: dict[str, float] = field(default_factory=dict)
    # Optional calibration data captured at run time so we can track how
    # prediction accuracy improves as the database grows.
    predicted_score_at_submission: float | None = None
    prediction_confidence_at_submission: float | None = None
    n_runs_contributing: int = 1  # v0.4 run multiplicity (≥3 for official)


@dataclass
class Neighbor:
    historical: HistoricalRun
    similarity: float
    distance: float


@dataclass
class PredictionReport:
    predicted_overall_score: float
    confidence: float  # 0..1, function of neighbor density and consistency
    n_neighbors_used: int
    neighbor_names: list[str]
    predicted_per_task: dict[str, float]
    capability_attributions: dict[str, float]
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class HistoricalDatabase:
    """In-memory historical database, persisted to JSON."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.runs: list[HistoricalRun] = []
        if path is not None and path.exists():
            self._load()

    def add(self, run: HistoricalRun) -> None:
        self.runs.append(run)
        if self.path is not None:
            self._save()

    def _load(self) -> None:
        assert self.path is not None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for raw in data:
            fp_raw = raw["fingerprint"]
            fp = ProfileFingerprint(**fp_raw)
            self.runs.append(HistoricalRun(
                profile_name=raw["profile_name"],
                fingerprint=fp,
                overall_score=float(raw["overall_score"]),
                per_task_score={k: float(v) for k, v in raw.get("per_task_score", {}).items()},
                predicted_score_at_submission=raw.get("predicted_score_at_submission"),
                prediction_confidence_at_submission=raw.get("prediction_confidence_at_submission"),
                n_runs_contributing=int(raw.get("n_runs_contributing", 1)),
            ))

    def _save(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([
            {
                "profile_name": r.profile_name,
                "fingerprint": asdict(r.fingerprint),
                "overall_score": r.overall_score,
                "per_task_score": r.per_task_score,
                "predicted_score_at_submission": r.predicted_score_at_submission,
                "prediction_confidence_at_submission": r.prediction_confidence_at_submission,
                "n_runs_contributing": r.n_runs_contributing,
            }
            for r in self.runs
        ], indent=2), encoding="utf-8")

    def __len__(self) -> int:
        return len(self.runs)

    def calibration_metrics(self) -> dict[str, float]:
        """Compute running prediction calibration error.

        Uses only runs that stored a `predicted_score_at_submission`,
        since earlier submissions may not have had prediction data
        available. Returns mean absolute error (MAE), root mean square
        error (RMSE), signed bias, and the sample size.

        Success criterion in CLAWBENCH_V0_4_SPEC.md §v0.5 Success: MAE
        below 0.08 after 100+ submissions.
        """
        predicted = []
        actual = []
        for run in self.runs:
            if run.predicted_score_at_submission is None:
                continue
            predicted.append(float(run.predicted_score_at_submission))
            actual.append(float(run.overall_score))
        if not predicted:
            return {
                "n": 0,
                "mae": 0.0,
                "rmse": 0.0,
                "bias": 0.0,
                "mae_target_met": False,
            }
        n = len(predicted)
        errors = [a - p for p, a in zip(predicted, actual)]
        abs_errors = [abs(e) for e in errors]
        mae = sum(abs_errors) / n
        rmse = (sum(e * e for e in errors) / n) ** 0.5
        bias = sum(errors) / n
        return {
            "n": n,
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "bias": round(bias, 4),
            # The v0.5 spec says MAE < 0.08 after 100+ submissions; we
            # only claim the target is met when both conditions hold.
            "mae_target_met": bool(n >= 100 and mae < 0.08),
        }


def predict_profile(
    fingerprint: ProfileFingerprint,
    db: HistoricalDatabase,
    k: int = 10,
    min_similarity: float = 0.05,
) -> PredictionReport:
    """Predict scores for a new profile via similarity-weighted k-NN."""

    if len(db) == 0:
        return PredictionReport(
            predicted_overall_score=0.5,
            confidence=0.0,
            n_neighbors_used=0,
            neighbor_names=[],
            predicted_per_task={},
            capability_attributions={},
            note="cold start: no historical data — returning neutral midpoint",
        )

    neighbors = _rank_neighbors(fingerprint, db, k=k, min_similarity=min_similarity)

    if not neighbors:
        return PredictionReport(
            predicted_overall_score=_global_mean(db),
            confidence=0.0,
            n_neighbors_used=0,
            neighbor_names=[],
            predicted_per_task={},
            capability_attributions={},
            note="no neighbors above similarity floor — using global mean",
        )

    # Similarity-weighted prediction with epsilon smoothing
    eps = 1e-6
    weights = [n.similarity + eps for n in neighbors]
    total_weight = sum(weights)
    predicted_overall = sum(
        w * n.historical.overall_score
        for w, n in zip(weights, neighbors)
    ) / total_weight

    # Per-task prediction (only tasks where at least one neighbor has data)
    all_tasks: set[str] = set()
    for n in neighbors:
        all_tasks.update(n.historical.per_task_score.keys())
    predicted_per_task: dict[str, float] = {}
    for task_id in sorted(all_tasks):
        task_weights, task_scores = [], []
        for w, n in zip(weights, neighbors):
            if task_id in n.historical.per_task_score:
                task_weights.append(w)
                task_scores.append(n.historical.per_task_score[task_id])
        if task_weights:
            predicted_per_task[task_id] = sum(
                w * s for w, s in zip(task_weights, task_scores)
            ) / sum(task_weights)

    # Confidence: combines neighbor density (closer = better) and consistency
    # (low variance among neighbors = better)
    avg_sim = sum(n.similarity for n in neighbors) / len(neighbors)
    score_variance = _variance([n.historical.overall_score for n in neighbors])
    consistency = max(0.0, 1.0 - math.sqrt(score_variance) / 0.3)
    confidence = round(0.6 * avg_sim + 0.4 * consistency, 4)

    # Capability attributions: rough marginal-effect estimate
    attributions = _estimate_capability_attributions(fingerprint, db)

    return PredictionReport(
        predicted_overall_score=round(predicted_overall, 4),
        confidence=round(min(1.0, max(0.0, confidence)), 4),
        n_neighbors_used=len(neighbors),
        neighbor_names=[n.historical.profile_name for n in neighbors],
        predicted_per_task=predicted_per_task,
        capability_attributions=attributions,
    )


def _rank_neighbors(
    fingerprint: ProfileFingerprint,
    db: HistoricalDatabase,
    k: int,
    min_similarity: float,
) -> list[Neighbor]:
    scored: list[Neighbor] = []
    for run in db.runs:
        sim = fingerprint_similarity(fingerprint, run.fingerprint)
        if sim < min_similarity:
            continue
        scored.append(Neighbor(historical=run, similarity=sim, distance=1.0 - sim))
    scored.sort(key=lambda n: n.similarity, reverse=True)
    return scored[:k]


def _global_mean(db: HistoricalDatabase) -> float:
    if not db.runs:
        return 0.5
    return sum(r.overall_score for r in db.runs) / len(db.runs)


def _variance(values: Iterable[float]) -> float:
    vals = list(values)
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)


def attribute_surprise(
    fingerprint: ProfileFingerprint,
    task_id: str,
    delta: float,
    db: HistoricalDatabase,
) -> str:
    """Generate a hypothesis for why a task score deviated from prediction.

    Strategy:
      1. Find the fingerprint capabilities that appear in THIS profile but
         are absent in most neighbors who got low scores on `task_id`.
         If `delta > 0` (positive surprise), those capabilities are
         candidate causes for the lift.
      2. Conversely, if `delta < 0`, look for capabilities the profile is
         MISSING that most successful neighbors had.
      3. Fall back to a generic note if the database is too small.

    Returns a short English hypothesis string. Never raises.
    """
    if len(db) < 3:
        return "insufficient historical data to attribute"

    same_task_runs = [
        r for r in db.runs if task_id in r.per_task_score
    ]
    if len(same_task_runs) < 2:
        return f"no comparable runs for {task_id}"

    if delta > 0:
        # Positive surprise: find capabilities this profile has that
        # low-scoring neighbors lack.
        low = [r for r in same_task_runs if r.per_task_score[task_id] < 0.5]
        if not low:
            return "positive surprise; no low-scoring comparators"
        low_caps = set.intersection(
            *(set(r.fingerprint.capability_coverage) for r in low)
        ) if low else set()
        our_caps = set(fingerprint.capability_coverage)
        lifting = sorted(our_caps - low_caps)
        if lifting:
            return f"likely lift from capabilities absent in low scorers: {', '.join(lifting[:3])}"
        # Hook-level fallback
        low_hooks = set.intersection(
            *(set(r.fingerprint.hook_footprint) for r in low)
        ) if low else set()
        our_hooks = set(fingerprint.hook_footprint)
        hook_lift = sorted(our_hooks - low_hooks)
        if hook_lift:
            return f"likely lift from hooks absent in low scorers: {', '.join(hook_lift[:3])}"
        return "positive surprise; no clear structural cause"

    # Negative surprise: find capabilities successful neighbors had that we lack
    high = [r for r in same_task_runs if r.per_task_score[task_id] >= 0.7]
    if not high:
        return "negative surprise; no high-scoring comparators"
    high_caps_union = set().union(
        *(set(r.fingerprint.capability_coverage) for r in high)
    ) if high else set()
    our_caps = set(fingerprint.capability_coverage)
    missing = sorted(high_caps_union - our_caps)
    if missing:
        return f"likely drag from capabilities missing vs high scorers: {', '.join(missing[:3])}"
    return "negative surprise; no clear structural cause"


def _estimate_capability_attributions(
    fingerprint: ProfileFingerprint,
    db: HistoricalDatabase,
) -> dict[str, float]:
    """For each capability in the new profile, estimate the marginal effect.

    This is the simplest possible attribution: for each capability the new
    profile has, look at runs that DID and DID NOT include that capability,
    and report the score delta. Confounded by other factors but interpretable
    enough to be useful, and exact under random configuration sampling.
    """
    if len(db) < 4:
        return {}
    attributions: dict[str, float] = {}
    for cap in fingerprint.capability_coverage:
        with_cap = [r.overall_score for r in db.runs if cap in r.fingerprint.capability_coverage]
        without_cap = [r.overall_score for r in db.runs if cap not in r.fingerprint.capability_coverage]
        if not with_cap or not without_cap:
            continue
        delta = (sum(with_cap) / len(with_cap)) - (sum(without_cap) / len(without_cap))
        attributions[cap] = round(delta, 4)
    return attributions
