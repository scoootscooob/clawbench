"""Pydantic models for rigorous agent harness evaluation.

Three independent evaluation axes:
1. Environment state — did the world actually change correctly?
2. Trajectory — was the tool call sequence valid and efficient?
3. Behavior — does the agent handle edge cases, failures, ambiguity?
"""

from __future__ import annotations

import enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Category(str, enum.Enum):
    GENERAL = "general"
    OPENCLAW = "openclaw"
    ADVERSARIAL = "adversarial"


class Difficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# ---------------------------------------------------------------------------
# Tool call and transcript (observed agent behavior)
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """A single tool invocation extracted from the transcript."""

    id: str = ""
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: str = ""  # Tool result text
    success: bool = True  # Did the tool execution succeed?
    timestamp_ms: int = 0


class TranscriptMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result_for: str | None = None
    timestamp_ms: int = 0


class Transcript(BaseModel):
    messages: list[TranscriptMessage] = Field(default_factory=list)

    @property
    def tool_call_sequence(self) -> list[ToolCall]:
        """Ordered list of all tool calls made by the agent."""
        calls: list[ToolCall] = []
        for m in self.messages:
            if m.role == "assistant":
                calls.extend(m.tool_calls)
        return calls

    @property
    def tool_name_sequence(self) -> list[str]:
        """Just the tool names in order — for trajectory comparison."""
        return [tc.name for tc in self.tool_call_sequence]


# ---------------------------------------------------------------------------
# Environment goal state (what the world should look like after the task)
# ---------------------------------------------------------------------------


class FileState(BaseModel):
    """Expected state of a workspace file."""

    path: str
    exists: bool = True
    content_contains: list[str] = Field(default_factory=list)
    content_not_contains: list[str] = Field(default_factory=list)
    content_matches: str | None = None  # Regex for full content
    min_size_bytes: int = 0


class MemoryState(BaseModel):
    """Expected state of agent memory after the task."""

    key_pattern: str  # Regex to match memory key
    exists: bool = True
    value_contains: list[str] = Field(default_factory=list)


class SessionState(BaseModel):
    """Expected gateway session state after the task."""

    should_exist: bool = True
    model_should_be: str | None = None  # Verify model was switched


class CronState(BaseModel):
    """Expected cron/scheduled task state."""

    exists: bool = True
    description_contains: str | None = None


class GoalState(BaseModel):
    """The ground truth: what the environment should look like after the task.

    This is what separates real agent evaluation from response-quality checking.
    We verify the WORLD changed, not that the agent SAID it changed.
    """

    files: list[FileState] = Field(default_factory=list)
    memory: list[MemoryState] = Field(default_factory=list)
    session: SessionState | None = None
    cron: list[CronState] = Field(default_factory=list)
    # Gateway state queries (raw protocol queries to verify state)
    gateway_assertions: list[GatewayAssertion] = Field(default_factory=list)


class GatewayAssertion(BaseModel):
    """A raw gateway protocol query + expected result for state verification."""

    method: str  # e.g. "sessions.list", "tools.effective", "skills.status"
    params: dict[str, Any] = Field(default_factory=dict)
    # JSONPath-like assertion on the response payload
    assert_path: str  # e.g. "$.sessions[0].model"
    assert_equals: Any | None = None
    assert_contains: str | None = None
    assert_exists: bool = True


# ---------------------------------------------------------------------------
# Reference trajectory (the expected tool call sequence)
# ---------------------------------------------------------------------------


class ReferenceStep(BaseModel):
    """A single expected step in the reference trajectory."""

    tool_name: str
    # Expected arguments (partial match — only specified keys checked)
    expected_args: dict[str, Any] = Field(default_factory=dict)
    required: bool = True  # Must appear vs nice-to-have
    description: str = ""  # Why this step is expected


class ReferenceTrajectory(BaseModel):
    """The expected sequence of tool calls.

    Used for trajectory precision/recall/F1 scoring.
    Supports both strict ordering and unordered required-set matching.
    """

    steps: list[ReferenceStep] = Field(default_factory=list)
    strict_order: bool = False  # If true, order must match exactly
    max_total_calls: int | None = None  # Efficiency bound — flag if exceeded
    forbidden_tools: list[str] = Field(default_factory=list)  # Tools that must NOT be called


# ---------------------------------------------------------------------------
# Simulated user (adaptive, not static prompts)
# ---------------------------------------------------------------------------


class UserTurn(BaseModel):
    """A single user turn — can be static or LLM-generated."""

    message: str | None = None  # Static message (None = generate dynamically)
    # For adaptive user simulation
    generate_prompt: str | None = None  # Prompt for LLM to generate user response
    # Conditions for when to inject this turn
    inject_after_tool: str | None = None  # Inject after agent calls this tool
    inject_on_error: bool = False  # Inject when agent hits an error


class SimulatedUser(BaseModel):
    """Configuration for the simulated user.

    The user can be:
    1. Static: fixed sequence of messages (simple, deterministic)
    2. Adaptive: LLM-generated responses based on agent behavior (realistic)
    3. Adversarial: deliberately ambiguous, contradictory, or impossible requests
    """

    mode: Literal["static", "adaptive", "adversarial"] = "static"
    # Static turns (used when mode="static")
    turns: list[UserTurn] = Field(default_factory=list)
    # Adaptive user configuration
    persona: str = ""  # System prompt for simulated user LLM
    goal: str = ""  # What the user is trying to accomplish
    max_turns: int = 10  # Conversation limit
    # Adversarial settings
    contradiction_turn: int | None = None  # Turn at which to contradict previous request
    impossible_request: bool = False  # Task is intentionally unsolvable


# ---------------------------------------------------------------------------
# Task definition (the complete specification)
# ---------------------------------------------------------------------------


class TaskSetup(BaseModel):
    """Environment setup before the task runs."""

    workspace_files: list[str] = Field(default_factory=list)
    memory_seed: list[dict[str, str]] = Field(default_factory=list)  # Pre-seeded memories
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    # Environment verification before task starts
    pre_check_gateway: list[GatewayAssertion] = Field(default_factory=list)


class TaskDefinition(BaseModel):
    """A complete benchmark task specification.

    A task defines:
    - Setup: initial environment state
    - User: who talks to the agent (static, adaptive, or adversarial)
    - Goal state: what the environment should look like after
    - Reference trajectory: expected tool call sequence
    - Scoring weights across the three axes
    """

    id: str
    name: str
    category: Category
    surface: str
    difficulty: Difficulty = Difficulty.MEDIUM
    timeout_seconds: int = 120

    setup: TaskSetup = Field(default_factory=TaskSetup)
    user: SimulatedUser
    goal_state: GoalState = Field(default_factory=GoalState)
    reference_trajectory: ReferenceTrajectory = Field(default_factory=ReferenceTrajectory)

    # Scoring axis weights (must sum to 1.0)
    weight_state: float = 0.5  # Environment state verification
    weight_trajectory: float = 0.3  # Trajectory quality
    weight_behavior: float = 0.2  # Behavioral properties (LLM judge)
    # LLM judge rubric for the behavior axis only
    behavior_rubric: str | None = None

    # Consistency requirements
    pass_threshold: float = 0.7
    required_pass_rate: float = 0.8  # For pass^k


# ---------------------------------------------------------------------------
# Scoring results
# ---------------------------------------------------------------------------


class StateVerificationResult(BaseModel):
    """Result of verifying the environment goal state."""

    total_assertions: int
    passed_assertions: int
    failed_assertions: list[str] = Field(default_factory=list)  # Human-readable failures
    score: float  # passed / total


class TrajectoryScore(BaseModel):
    """Result of comparing agent trajectory to reference."""

    precision: float  # Fraction of agent's calls that were relevant
    recall: float  # Fraction of required calls that were made
    f1: float
    order_score: float  # 1.0 if order matches, 0.0-1.0 for partial
    efficiency_score: float  # 1.0 if within budget, degrades with excess
    forbidden_violations: list[str] = Field(default_factory=list)
    score: float  # Composite trajectory score


class BehaviorScore(BaseModel):
    """Result of LLM judge evaluation of behavioral quality."""

    score: float
    reason: str = ""


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    total_cost_usd: float = 0.0


class TaskRunResult(BaseModel):
    """Result of a single task run."""

    task_id: str
    run_index: int

    # Three-axis scores
    state_score: StateVerificationResult
    trajectory_score: TrajectoryScore
    behavior_score: BehaviorScore

    # Composite
    composite_score: float  # Weighted combination of three axes

    transcript: Transcript
    duration_ms: int
    token_usage: TokenUsage = Field(default_factory=lambda: TokenUsage())
    error: str | None = None


class TaskStats(BaseModel):
    """Aggregated statistics across multiple runs of a task."""

    task_id: str
    runs: int

    # Per-axis means
    mean_state_score: float
    mean_trajectory_score: float
    mean_behavior_score: float

    # Composite
    mean_composite: float
    stddev: float
    min_score: float
    max_score: float

    # Reliability (the real metric for production agents)
    pass_at_1: bool  # Did first run pass?
    pass_at_k: float  # Fraction of runs that passed
    pass_hat_k: bool  # Did ALL runs pass? (pass^k)

    scores: list[float]
    mean_duration_ms: float
    mean_tokens: TokenUsage = Field(default_factory=lambda: TokenUsage())

    # Flags
    high_variance: bool = False
    trajectory_precision: float = 0.0
    trajectory_recall: float = 0.0


class CategoryResult(BaseModel):
    category: str
    mean_composite: float
    mean_state: float
    mean_trajectory: float
    mean_behavior: float
    ci_lower: float
    ci_upper: float
    pass_hat_k_rate: float  # What fraction of tasks passed all runs?
    task_stats: list[TaskStats]


class BenchmarkResult(BaseModel):
    """The complete benchmark output."""

    submission_id: str
    model: str
    provider: str
    timestamp: str
    openclaw_version: str = ""
    benchmark_version: str = "0.2.0"
    environment: dict[str, Any] = Field(default_factory=dict)

    # Overall scores
    overall_composite: float
    overall_state: float
    overall_trajectory: float
    overall_behavior: float
    overall_ci_lower: float
    overall_ci_upper: float

    # Reliability
    overall_pass_hat_k: float  # Fraction of tasks where ALL runs passed

    category_results: list[CategoryResult]
    task_results: list[TaskStats]

    # Baselines (sanity checks)
    noop_baseline: float = 0.0  # Score of an agent that does nothing
    random_baseline: float = 0.0  # Score of an agent that calls random tools

    # Environment integrity
    environment_checksum: str = ""  # Hash of initial env state
    certified: bool = False
