"""Statistical aggregation with pass^k reliability as the primary metric.

pass@k: probability of success in at least one of k trials (lenient)
pass^k: probability ALL k trials succeed (strict — production reliability)

A model with 90% pass@1 has only 57% pass^8. This is the metric that matters
for production agents where every interaction must succeed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ConfidenceInterval:
    mean: float
    lower: float
    upper: float
    stddev: float


def bootstrap_ci(
    scores: list[float],
    confidence: float = 0.95,
    n_resamples: int = 10_000,
    seed: int = 42,
) -> ConfidenceInterval:
    if not scores:
        return ConfidenceInterval(mean=0.0, lower=0.0, upper=0.0, stddev=0.0)

    arr = np.array(scores)
    observed_mean = float(arr.mean())
    observed_std = float(arr.std(ddof=1)) if len(scores) > 1 else 0.0

    if len(scores) == 1:
        return ConfidenceInterval(
            mean=observed_mean, lower=observed_mean,
            upper=observed_mean, stddev=0.0,
        )

    rng = np.random.default_rng(seed)
    boot_means = np.array([
        rng.choice(arr, size=len(arr), replace=True).mean()
        for _ in range(n_resamples)
    ])

    alpha = 1 - confidence
    lower = float(np.percentile(boot_means, 100 * alpha / 2))
    upper = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))

    return ConfidenceInterval(
        mean=observed_mean, lower=lower, upper=upper, stddev=observed_std,
    )


def pass_at_k(scores: list[float], k: int = 1, threshold: float = 0.7) -> bool:
    """At least one of first k runs passes."""
    return any(s >= threshold for s in scores[:k])


def pass_hat_k(scores: list[float], threshold: float = 0.7) -> bool:
    """ALL runs pass — the production reliability metric.

    pass^k = p^k where p is the per-trial success rate.
    90% pass@1 → 57% pass^8
    95% pass@1 → 66% pass^8
    99% pass@1 → 92% pass^8
    """
    return all(s >= threshold for s in scores) if scores else False


def consistency_rate(scores: list[float], threshold: float = 0.7) -> float:
    """Fraction of runs that pass the threshold."""
    if not scores:
        return 0.0
    return sum(1 for s in scores if s >= threshold) / len(scores)


@dataclass
class TaskStatsSummary:
    mean: float
    stddev: float
    min_score: float
    max_score: float
    consistency: float  # = pass_at_k rate (fraction that pass)
    pass_at_1: bool
    pass_hat_k: bool  # ALL passed
    ci: ConfidenceInterval
    high_variance: bool


def summarize_task_runs(
    scores: list[float],
    pass_threshold: float = 0.7,
    variance_threshold: float = 0.15,
) -> TaskStatsSummary:
    if not scores:
        ci = ConfidenceInterval(mean=0.0, lower=0.0, upper=0.0, stddev=0.0)
        return TaskStatsSummary(
            mean=0.0, stddev=0.0, min_score=0.0, max_score=0.0,
            consistency=0.0, pass_at_1=False, pass_hat_k=False,
            ci=ci, high_variance=False,
        )

    ci = bootstrap_ci(scores)
    return TaskStatsSummary(
        mean=ci.mean,
        stddev=ci.stddev,
        min_score=min(scores),
        max_score=max(scores),
        consistency=consistency_rate(scores, pass_threshold),
        pass_at_1=pass_at_k(scores, k=1, threshold=pass_threshold),
        pass_hat_k=pass_hat_k(scores, pass_threshold),
        ci=ci,
        high_variance=ci.stddev > variance_threshold,
    )
