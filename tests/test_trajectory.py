from clawbench.schemas import ToolCall, TrajectoryExpectations, Transcript, TranscriptMessage
from clawbench.trajectory import evaluate_trajectory


def test_trajectory_rewards_read_before_write_and_self_verification():
    transcript = Transcript(
        messages=[
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="exec", input={"command": "rg TODO ."}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="write_file", input={"path": "foo.py"}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="exec", input={"command": "pytest -q"}, success=True)]),
        ]
    )
    expectations = TrajectoryExpectations(
        required_families=["search", "edit", "execute"],
        required_pre_edit_families=["search"],
        required_post_edit_families=["execute"],
        min_distinct_families=3,
        min_pre_edit_exploration_calls=1,
        min_post_edit_verification_calls=1,
        require_read_before_mutation=True,
        require_self_verification=True,
    )

    result = evaluate_trajectory(transcript, expectations)

    assert result.score > 0.8
    assert result.read_before_write_ratio == 1.0
    assert result.self_verified is True
    assert result.required_families_missing == []


def test_trajectory_penalizes_missing_successful_delegation():
    transcript = Transcript(
        messages=[
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="read_file", input={"path": "billing.py"}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="write_file", input={"path": "billing.py"}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="exec", input={"command": "pytest -q"}, success=True)]),
        ]
    )
    expectations = TrajectoryExpectations(
        required_families=["read", "edit", "execute", "delegate"],
        required_pre_edit_families=["read"],
        required_post_edit_families=["execute", "delegate"],
        min_distinct_families=4,
        min_successful_delegations=1,
        require_read_before_mutation=True,
        require_self_verification=True,
    )

    result = evaluate_trajectory(transcript, expectations)

    assert "delegate" in result.required_families_missing
    assert result.tool_fit_score == 0.0
    assert result.score < 0.6


def test_trajectory_tracks_recovery_and_dangerous_commands():
    transcript = Transcript(
        messages=[
            TranscriptMessage(
                role="assistant",
                tool_calls=[ToolCall(name="exec", input={"command": "pytest -q"}, success=False, output="ERROR failed test")],
            ),
            TranscriptMessage(
                role="assistant",
                tool_calls=[ToolCall(name="exec", input={"command": "pytest -q"}, success=False, output="ERROR failed test")],
            ),
            TranscriptMessage(
                role="assistant",
                tool_calls=[ToolCall(name="exec", input={"command": "pytest -q"}, success=True, output="2 passed")],
            ),
            TranscriptMessage(
                role="assistant",
                tool_calls=[ToolCall(name="exec", input={"command": "rm -rf build"}, success=True)],
            ),
        ]
    )
    expectations = TrajectoryExpectations(
        required_families=["execute"],
        expect_recovery=True,
        max_recovery_turns=3,
    )

    result = evaluate_trajectory(transcript, expectations)

    assert result.recovered_failures == 2
    assert result.repeated_failures >= 1
    assert any("Dangerous shell command" in violation for violation in result.forbidden_violations)


def test_trajectory_counts_distinct_read_and_mutation_targets():
    transcript = Transcript(
        messages=[
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="read_file", input={"path": "src/app.py"}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="read_file", input={"path": "tests/test_app.py"}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="write_file", input={"path": "src/app.py"}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="write_file", input={"path": "src/helpers.py"}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="exec", input={"command": "pytest -q"}, success=True)]),
        ]
    )
    expectations = TrajectoryExpectations(
        required_families=["read", "edit", "execute"],
        min_distinct_families=3,
        min_distinct_read_targets_pre_edit=2,
        min_distinct_mutation_targets=2,
        require_read_before_mutation=True,
        require_self_verification=True,
    )

    result = evaluate_trajectory(transcript, expectations)

    assert result.distinct_read_targets_pre_edit == ["src/app.py", "tests/test_app.py"]
    assert result.distinct_mutation_targets == ["src/app.py", "src/helpers.py"]
    assert result.score > 0.8


def test_memory_search_is_not_treated_as_a_mutation():
    transcript = Transcript(
        messages=[
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="memory_search", input={"query": "release notes"}, success=True)]),
            TranscriptMessage(role="assistant", tool_calls=[ToolCall(name="write_file", input={"path": "handoff.md"}, success=True)]),
        ]
    )
    expectations = TrajectoryExpectations(
        required_families=["memory", "edit"],
        require_read_before_mutation=True,
    )

    result = evaluate_trajectory(transcript, expectations)

    assert result.read_before_write_ratio == 1.0
