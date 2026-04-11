"""Statistical helpers for ClawBench v0.3+ (extended for v0.5)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ConfidenceInterval:
    mean: float
    lower: float
    upper: float
    stddev: float


@dataclass
class ReliabilitySummary:
    pass_at_1: bool
    pass_rate: float
    pass_hat_k: bool
    worst_of_n: float
    variance_score: float
    reliability_score: float


@dataclass
class TaskStatsSummary:
    mean: float
    stddev: float
    min_score: float
    max_score: float
    pass_at_1: bool
    pass_rate: float
    pass_hat_k: bool
    worst_of_n: float
    variance_score: float
    reliability_score: float
    task_score: float
    ci: ConfidenceInterval
    high_variance: bool


def bootstrap_ci(
    scores: list[float],
    confidence: float = 0.95,
    n_resamples: int = 10_000,
    seed: int = 42,
) -> ConfidenceInterval:
    if not scores:
        return ConfidenceInterval(mean=0.0, lower=0.0, upper=0.0, stddev=0.0)

    array = np.array(scores)
    observed_mean = float(array.mean())
    observed_std = float(array.std(ddof=1)) if len(scores) > 1 else 0.0
    if len(scores) == 1:
        return ConfidenceInterval(
            mean=observed_mean,
            lower=observed_mean,
            upper=observed_mean,
            stddev=0.0,
        )

    rng = np.random.default_rng(seed)
    bootstrap_means = np.array(
        [
            rng.choice(array, size=len(array), replace=True).mean()
            for _ in range(n_resamples)
        ]
    )
    alpha = 1 - confidence
    lower = float(np.percentile(bootstrap_means, 100 * alpha / 2))
    upper = float(np.percentile(bootstrap_means, 100 * (1 - alpha / 2)))
    return ConfidenceInterval(
        mean=observed_mean,
        lower=lower,
        upper=upper,
        stddev=observed_std,
    )


def compute_reliability(scores: list[float], pass_threshold: float = 0.7) -> ReliabilitySummary:
    return compute_reliability_with_flags(scores, pass_threshold=pass_threshold)


def compute_reliability_with_flags(
    scores: list[float],
    *,
    pass_threshold: float = 0.7,
    pass_flags: list[bool] | None = None,
) -> ReliabilitySummary:
    if not scores:
        return ReliabilitySummary(
            pass_at_1=False,
            pass_rate=0.0,
            pass_hat_k=False,
            worst_of_n=0.0,
            variance_score=0.0,
            reliability_score=0.0,
        )

    if pass_flags is not None:
        if len(pass_flags) != len(scores):
            raise ValueError("pass_flags must align with scores")
        normalized_flags = [bool(flag) for flag in pass_flags]
    else:
        normalized_flags = [score >= pass_threshold for score in scores]

    pass_at_1 = normalized_flags[0]
    pass_rate = sum(1 for flag in normalized_flags if flag) / len(normalized_flags)
    pass_hat_k = all(normalized_flags)
    worst_of_n = min(scores)
    stddev = float(np.std(np.array(scores), ddof=1)) if len(scores) > 1 else 0.0
    variance_score = max(0.0, 1.0 - stddev / 0.2)
    reliability_score = (
        0.5 * (1.0 if pass_hat_k else 0.0)
        + 0.3 * pass_rate
        + 0.2 * variance_score
    )
    return ReliabilitySummary(
        pass_at_1=pass_at_1,
        pass_rate=pass_rate,
        pass_hat_k=pass_hat_k,
        worst_of_n=worst_of_n,
        variance_score=variance_score,
        reliability_score=reliability_score,
    )


@dataclass
class RobustnessProfile:
    """Taguchi-style robustness summary for a profile or model across tasks.

    The larger-is-better signal-to-noise ratio is dominated by the
    worst-performing tasks (because of the 1/yᵢ² term), which is the
    behavior we want for agent benchmarking: a configuration that scores
    0.85 on average but 0.10 on adversarial tasks is worse in production
    than one that averages 0.78 and never drops below 0.65.

    Reference: CLAWBENCH_V0_4_SPEC.md v0.5 §"Taguchi Signal-to-Noise".
    """

    mean: float
    worst_of_n: float
    best_of_n: float
    stddev: float
    sn_ratio_db: float  # larger-is-better S/N ratio in decibels
    tier_means: dict[str, float] = field(default_factory=dict)
    n_tasks: int = 0

    def to_dict(self) -> dict:
        return {
            "mean": round(self.mean, 4),
            "worst_of_n": round(self.worst_of_n, 4),
            "best_of_n": round(self.best_of_n, 4),
            "stddev": round(self.stddev, 4),
            "sn_ratio_db": round(self.sn_ratio_db, 4),
            "tier_means": {k: round(v, 4) for k, v in self.tier_means.items()},
            "n_tasks": self.n_tasks,
        }


def taguchi_sn_larger_is_better(scores: list[float], *, floor: float = 1e-3) -> float:
    """Compute the larger-is-better signal-to-noise ratio in decibels.

    S/N = -10 * log10( (1/n) * Σ (1/yᵢ²) )

    `floor` clamps any zero scores to avoid 1/0. A tiny positive floor
    still heavily penalizes zero-scored tasks in the final S/N, which is
    the desired behavior — a benchmark run that crashes on a task should
    drag the S/N down sharply.
    """
    if not scores:
        return 0.0
    clamped = [max(floor, float(s)) for s in scores]
    mean_inverse_square = sum(1.0 / (y * y) for y in clamped) / len(clamped)
    return -10.0 * math.log10(mean_inverse_square)


def compute_robustness_profile(
    per_task_scores: dict[str, float],
    *,
    tier_of: dict[str, str] | None = None,
) -> RobustnessProfile:
    """Build a RobustnessProfile from a {task_id: score} mapping.

    If `tier_of` is supplied, also compute per-tier mean scores so the
    diagnostic report can show where the configuration is strong or weak.
    """
    if not per_task_scores:
        return RobustnessProfile(
            mean=0.0,
            worst_of_n=0.0,
            best_of_n=0.0,
            stddev=0.0,
            sn_ratio_db=0.0,
            tier_means={},
            n_tasks=0,
        )

    values = list(per_task_scores.values())
    arr = np.array(values, dtype=float)
    mean = float(arr.mean())
    worst = float(arr.min())
    best = float(arr.max())
    stddev = float(arr.std(ddof=1)) if len(values) > 1 else 0.0
    sn = taguchi_sn_larger_is_better(values)

    tier_means: dict[str, float] = {}
    if tier_of:
        bucket: dict[str, list[float]] = {}
        for task_id, score in per_task_scores.items():
            tier = tier_of.get(task_id, "unknown")
            bucket.setdefault(tier, []).append(float(score))
        for tier, scores in bucket.items():
            tier_means[tier] = sum(scores) / len(scores)

    return RobustnessProfile(
        mean=mean,
        worst_of_n=worst,
        best_of_n=best,
        stddev=stddev,
        sn_ratio_db=sn,
        tier_means=tier_means,
        n_tasks=len(values),
    )


def summarize_task_runs(
    scores: list[float],
    pass_threshold: float = 0.7,
    variance_threshold: float = 0.15,
    pass_flags: list[bool] | None = None,
) -> TaskStatsSummary:
    if not scores:
        ci = ConfidenceInterval(mean=0.0, lower=0.0, upper=0.0, stddev=0.0)
        return TaskStatsSummary(
            mean=0.0,
            stddev=0.0,
            min_score=0.0,
            max_score=0.0,
            pass_at_1=False,
            pass_rate=0.0,
            pass_hat_k=False,
            worst_of_n=0.0,
            variance_score=0.0,
            reliability_score=0.0,
            task_score=0.0,
            ci=ci,
            high_variance=False,
        )

    ci = bootstrap_ci(scores)
    reliability = compute_reliability_with_flags(
        scores,
        pass_threshold=pass_threshold,
        pass_flags=pass_flags,
    )
    task_score = 0.9 * ci.mean + 0.1 * reliability.reliability_score
    return TaskStatsSummary(
        mean=ci.mean,
        stddev=ci.stddev,
        min_score=min(scores),
        max_score=max(scores),
        pass_at_1=reliability.pass_at_1,
        pass_rate=reliability.pass_rate,
        pass_hat_k=reliability.pass_hat_k,
        worst_of_n=reliability.worst_of_n,
        variance_score=reliability.variance_score,
        reliability_score=reliability.reliability_score,
        task_score=task_score,
        ci=ci,
        high_variance=ci.stddev > variance_threshold,
    )
