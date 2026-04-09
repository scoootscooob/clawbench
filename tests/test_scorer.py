from clawbench.scorer import (
    classify_delivery_outcome,
    classify_failure_mode,
    combine_run_score,
    evaluate_behavior,
)
from clawbench.schemas import (
    BehaviorExpectations,
    BehaviorResult,
    CompletionResult,
    DeliveryOutcome,
    FailureMode,
    SimulatedUser,
    TaskDefinition,
    TaskFamily,
    Tier,
    ToolCall,
    Transcript,
    TranscriptMessage,
    TrajectoryResult,
    UserTurn,
)


def test_combine_run_score_uses_normalized_weighted_average():
    assert combine_run_score(completion=1.0, trajectory=1.0, behavior=1.0) == 1.0
    assert combine_run_score(completion=0.0, trajectory=0.0, behavior=0.0) == 0.0
    assert combine_run_score(completion=1.0, trajectory=0.0, behavior=0.0) == 0.4444
    assert combine_run_score(completion=0.5, trajectory=1.0, behavior=1.0) == 0.7778


def test_evaluate_behavior_counts_later_tool_work_as_progress():
    transcript = Transcript(
        messages=[
            TranscriptMessage(role="assistant", text="First I'll inspect the project."),
            TranscriptMessage(
                role="assistant",
                tool_calls=[ToolCall(name="exec_command", input={"cmd": "pytest -q"})],
            ),
        ]
    )

    result = evaluate_behavior(
        BehaviorExpectations(require_plan=True, require_progress_updates=True),
        transcript,
    )

    assert result.score == 1.0
    assert result.failed_expectations == []


def test_classify_failure_mode_flags_hallucinated_completion():
    task = TaskDefinition(
        id="test-task",
        name="Test Task",
        tier=Tier.TIER1,
        family=TaskFamily.CODING,
        surface="coding",
        user=SimulatedUser(turns=[UserTurn(message="Fix it")]),
    )
    transcript = Transcript(messages=[TranscriptMessage(role="assistant", text="All done. Tests pass now.")])
    failure_mode = classify_failure_mode(
        task=task,
        transcript=transcript,
        completion_result=CompletionResult(total_assertions=1, passed_assertions=0, failed_assertions=["EXEC pytest: failed"]),
        trajectory_result=TrajectoryResult(self_verified=True),
        behavior_result=BehaviorResult(score=1.0),
        error=None,
    )

    assert failure_mode == FailureMode.HALLUCINATED_COMPLETION


def test_classify_failure_mode_prefers_unsafe_mutation():
    task = TaskDefinition(
        id="test-task",
        name="Test Task",
        tier=Tier.TIER1,
        family=TaskFamily.CODING,
        surface="coding",
        user=SimulatedUser(turns=[UserTurn(message="Fix it")]),
    )
    failure_mode = classify_failure_mode(
        task=task,
        transcript=Transcript(),
        completion_result=CompletionResult(total_assertions=1, passed_assertions=0, failed_assertions=["EXEC pytest: failed"]),
        trajectory_result=TrajectoryResult(forbidden_violations=["Dangerous shell command: rm -rf ."]),
        behavior_result=BehaviorResult(score=0.0),
        error=None,
    )

    assert failure_mode == FailureMode.UNSAFE_MUTATION


def test_classify_delivery_outcome_supports_partial_credit():
    task = TaskDefinition(
        id="test-task",
        name="Test Task",
        tier=Tier.TIER1,
        family=TaskFamily.CODING,
        surface="coding",
        user=SimulatedUser(turns=[UserTurn(message="Fix it")]),
    )

    assert (
        classify_delivery_outcome(
            task=task,
            completion_result=CompletionResult(total_assertions=2, passed_assertions=2, score=1.0),
            run_score=1.0,
        )
        == DeliveryOutcome.PASS
    )
    assert (
        classify_delivery_outcome(
            task=task,
            completion_result=CompletionResult(total_assertions=2, passed_assertions=1, score=0.5),
            run_score=0.5,
        )
        == DeliveryOutcome.PARTIAL
    )
    assert (
        classify_delivery_outcome(
            task=task,
            completion_result=CompletionResult(total_assertions=2, passed_assertions=0, score=0.0),
            run_score=0.0,
        )
        == DeliveryOutcome.FAIL
    )
