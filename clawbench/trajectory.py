"""Trajectory evaluation — was the tool call sequence valid and efficient?

Computes precision, recall, F1, ordering, and efficiency metrics
by comparing the agent's actual tool call sequence against a reference trajectory.
"""

from __future__ import annotations

import re
from typing import Any

from clawbench.schemas import (
    ReferenceStep,
    ReferenceTrajectory,
    ToolCall,
    TrajectoryScore,
    Transcript,
)


def evaluate_trajectory(
    transcript: Transcript,
    reference: ReferenceTrajectory,
) -> TrajectoryScore:
    """Compare actual tool call sequence against reference trajectory.

    Three dimensions:
    1. Precision: fraction of agent's calls that were relevant
    2. Recall: fraction of required reference steps that were satisfied
    3. Efficiency: was the agent within the call budget?

    Plus: ordering score and forbidden tool violations.
    """
    actual_calls = transcript.tool_call_sequence
    ref_steps = reference.steps

    if not ref_steps and not actual_calls:
        # No tools expected and none used — perfect
        return TrajectoryScore(
            precision=1.0, recall=1.0, f1=1.0,
            order_score=1.0, efficiency_score=1.0, score=1.0,
        )

    if not ref_steps:
        # No tools expected but agent used some — precision is 0
        return TrajectoryScore(
            precision=0.0, recall=1.0, f1=0.0,
            order_score=1.0,
            efficiency_score=0.0 if actual_calls else 1.0,
            forbidden_violations=_check_forbidden(actual_calls, reference.forbidden_tools),
            score=0.0,
        )

    # --- Recall: which required reference steps were satisfied? ---
    matched_ref_indices: list[int] = []
    matched_actual_indices: list[int] = []
    required_steps = [s for s in ref_steps if s.required]

    for ref_idx, step in enumerate(ref_steps):
        for act_idx, call in enumerate(actual_calls):
            if act_idx in matched_actual_indices:
                continue
            if _step_matches_call(step, call):
                matched_ref_indices.append(ref_idx)
                matched_actual_indices.append(act_idx)
                break

    required_matched = sum(
        1 for i, s in enumerate(ref_steps)
        if s.required and i in matched_ref_indices
    )
    recall = required_matched / len(required_steps) if required_steps else 1.0

    # --- Precision: fraction of agent's calls that match any reference step ---
    relevant_calls = len(matched_actual_indices)
    precision = relevant_calls / len(actual_calls) if actual_calls else 0.0

    # --- F1 ---
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    # --- Order score ---
    order_score = _compute_order_score(
        matched_ref_indices, matched_actual_indices, ref_steps, reference.strict_order,
    )

    # --- Efficiency ---
    efficiency_score = _compute_efficiency(actual_calls, reference.max_total_calls)

    # --- Forbidden tool violations ---
    forbidden_violations = _check_forbidden(actual_calls, reference.forbidden_tools)
    forbidden_penalty = 0.0 if not forbidden_violations else 0.3 * len(forbidden_violations)

    # Composite trajectory score
    raw_score = (
        0.35 * recall
        + 0.25 * precision
        + 0.20 * order_score
        + 0.20 * efficiency_score
    )
    score = max(0.0, raw_score - forbidden_penalty)

    return TrajectoryScore(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        order_score=round(order_score, 4),
        efficiency_score=round(efficiency_score, 4),
        forbidden_violations=forbidden_violations,
        score=round(score, 4),
    )


def _step_matches_call(step: ReferenceStep, call: ToolCall) -> bool:
    """Check if an actual tool call satisfies a reference step."""
    # Tool name match (supports regex)
    if not re.search(step.tool_name, call.name, re.IGNORECASE):
        return False

    # Argument match (partial — only check specified keys)
    for key, expected in step.expected_args.items():
        actual = call.input.get(key)
        if actual is None:
            return False
        if isinstance(expected, str):
            if expected.lower() not in str(actual).lower():
                return False
        elif actual != expected:
            return False

    return True


def _compute_order_score(
    matched_ref_indices: list[int],
    matched_actual_indices: list[int],
    ref_steps: list[ReferenceStep],
    strict: bool,
) -> float:
    """Score how well the actual ordering matches the reference ordering.

    Uses longest increasing subsequence of matched reference indices
    relative to their actual call order.
    """
    if len(matched_ref_indices) <= 1:
        return 1.0

    if strict:
        # Strict mode: must be exactly the same order
        pairs = sorted(zip(matched_actual_indices, matched_ref_indices))
        ref_order = [r for _, r in pairs]
        # Check if ref_order is strictly increasing
        is_ordered = all(ref_order[i] < ref_order[i + 1] for i in range(len(ref_order) - 1))
        return 1.0 if is_ordered else 0.0

    # Relaxed mode: compute LIS ratio
    pairs = sorted(zip(matched_actual_indices, matched_ref_indices))
    ref_order = [r for _, r in pairs]
    lis_len = _longest_increasing_subsequence_length(ref_order)
    return lis_len / len(ref_order)


def _longest_increasing_subsequence_length(seq: list[int]) -> int:
    """Compute length of LIS using patience sorting."""
    if not seq:
        return 0
    from bisect import bisect_left

    tails: list[int] = []
    for val in seq:
        pos = bisect_left(tails, val)
        if pos == len(tails):
            tails.append(val)
        else:
            tails[pos] = val
    return len(tails)


def _compute_efficiency(actual_calls: list[ToolCall], max_calls: int | None) -> float:
    """Score efficiency: 1.0 if within budget, degrades linearly past it."""
    if max_calls is None:
        return 1.0
    if not actual_calls:
        return 1.0
    n = len(actual_calls)
    if n <= max_calls:
        return 1.0
    # Linear degradation: at 2x budget = 0.0
    overshoot = (n - max_calls) / max_calls
    return max(0.0, 1.0 - overshoot)


def _check_forbidden(calls: list[ToolCall], forbidden: list[str]) -> list[str]:
    """Check if any forbidden tools were called."""
    violations: list[str] = []
    for call in calls:
        for pattern in forbidden:
            if re.search(pattern, call.name, re.IGNORECASE):
                violations.append(f"Forbidden tool called: {call.name}")
                break
    return violations
