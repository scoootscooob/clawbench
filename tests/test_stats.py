import pytest

from clawbench.stats import compute_reliability, summarize_task_runs


def test_compute_reliability_uses_pass_hat_rate_and_variance():
    summary = compute_reliability([0.9, 0.8, 0.85], pass_threshold=0.7)
    assert summary.pass_at_1 is True
    assert summary.pass_rate == 1.0
    assert summary.pass_hat_k is True
    assert summary.worst_of_n == 0.8
    assert 0.0 <= summary.variance_score <= 1.0
    assert summary.reliability_score > 0.9


def test_summarize_task_runs_combines_mean_and_reliability():
    summary = summarize_task_runs([0.9, 0.4, 0.8], pass_threshold=0.7)
    assert summary.mean > 0.6
    assert summary.pass_rate == 2 / 3
    assert summary.pass_hat_k is False
    assert summary.worst_of_n == 0.4
    assert summary.task_score == pytest.approx(0.65)


def test_summarize_task_runs_can_reach_full_scale():
    summary = summarize_task_runs([1.0, 1.0, 1.0], pass_threshold=0.7)
    assert summary.mean == 1.0
    assert summary.reliability_score == 1.0
    assert summary.task_score == 1.0


def test_summarize_task_runs_respects_explicit_pass_flags():
    summary = summarize_task_runs([0.72], pass_threshold=0.7, pass_flags=[False])
    assert summary.pass_at_1 is False
    assert summary.pass_rate == 0.0
    assert summary.pass_hat_k is False
    assert summary.reliability_score == 0.2
    assert summary.task_score == pytest.approx(0.668)
