"""Statistical helpers for ClawBench v0.3."""

from __future__ import annotations

from dataclasses import dataclass

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
