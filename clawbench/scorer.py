"""Three-axis scoring engine.

Axis 1: Environment state — did the world actually change? (environment.py)
Axis 2: Trajectory — was the tool call sequence correct? (trajectory.py)
Axis 3: Behavior — LLM judge for subjective quality (this file)

The composite score is a weighted sum of the three axes.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from clawbench.client import GatewayClient
from clawbench.environment import verify_goal_state
from clawbench.schemas import (
    BehaviorScore,
    StateVerificationResult,
    TaskDefinition,
    TaskRunResult,
    TokenUsage,
    TrajectoryScore,
    Transcript,
)
from clawbench.trajectory import evaluate_trajectory

logger = logging.getLogger(__name__)


class JudgeConfig:
    def __init__(
        self,
        model: str = "claude-sonnet-4-6-20250514",
        api_key: str = "",
        base_url: str = "https://api.anthropic.com",
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url


async def score_task_run(
    task: TaskDefinition,
    transcript: Transcript,
    workspace: Path,
    client: GatewayClient,
    session_key: str,
    duration_ms: int,
    judge_config: JudgeConfig | None = None,
) -> TaskRunResult:
    """Score a single task run across all three axes."""

    # Axis 1: Environment state verification
    state_result = await verify_goal_state(
        task.goal_state, workspace, client, session_key,
    )

    # Axis 2: Trajectory evaluation
    trajectory_result = evaluate_trajectory(
        transcript, task.reference_trajectory,
    )

    # Axis 3: Behavioral quality (LLM judge)
    behavior_result = await _evaluate_behavior(
        task, transcript, workspace, judge_config,
    )

    # Composite score
    composite = (
        task.weight_state * state_result.score
        + task.weight_trajectory * trajectory_result.score
        + task.weight_behavior * behavior_result.score
    )

    return TaskRunResult(
        task_id=task.id,
        run_index=0,  # Set by caller
        state_score=state_result,
        trajectory_score=trajectory_result,
        behavior_score=behavior_result,
        composite_score=round(composite, 4),
        transcript=transcript,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Axis 3: Behavioral quality (LLM judge)
# ---------------------------------------------------------------------------


async def _evaluate_behavior(
    task: TaskDefinition,
    transcript: Transcript,
    workspace: Path,
    judge_config: JudgeConfig | None,
) -> BehaviorScore:
    """Use LLM judge for subjective behavioral quality."""

    if not task.behavior_rubric:
        # No rubric = behavior axis not applicable, full score
        return BehaviorScore(score=1.0, reason="No behavior rubric defined")

    if not judge_config or not judge_config.api_key:
        return BehaviorScore(score=0.0, reason="No API key for LLM judge")

    transcript_text = _format_transcript_for_judge(transcript)

    prompt = f"""You are evaluating an AI agent's behavioral quality. You are NOT evaluating whether the task was completed (that's verified separately). You are evaluating HOW the agent behaved.

## Task
{task.name}

## Rubric
{task.behavior_rubric}

## Agent Transcript
{transcript_text}

## Instructions
Score ONLY the behavioral aspects described in the rubric.
Do NOT score task completion — that is measured by environment state verification.
Do NOT score tool usage efficiency — that is measured by trajectory evaluation.

Respond with ONLY a JSON object:
{{"score": <float 0.0-1.0>, "reason": "<brief explanation>"}}"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.post(
                f"{judge_config.base_url}/v1/messages",
                headers={
                    "x-api-key": judge_config.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": judge_config.model,
                    "max_tokens": 256,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("content", [{}])[0].get("text", "")
            result = _parse_judge_json(text)
            return BehaviorScore(
                score=result.get("score", 0.0),
                reason=result.get("reason", ""),
            )
    except Exception as e:
        logger.error("LLM judge failed: %s", e)
        return BehaviorScore(score=0.0, reason=f"Judge error: {e}")


def _format_transcript_for_judge(transcript: Transcript, max_chars: int = 50_000) -> str:
    lines: list[str] = []
    for msg in transcript.messages:
        prefix = msg.role.upper()
        if msg.tool_calls:
            for tc in msg.tool_calls:
                args_str = json.dumps(tc.input, default=str)[:200]
                lines.append(f"[{prefix}] TOOL_CALL: {tc.name}({args_str})")
                if tc.output:
                    lines.append(f"  -> {tc.output[:300]}")
        if msg.text:
            lines.append(f"[{prefix}] {msg.text}")

    text = "\n".join(lines)
    return text[:max_chars] if len(text) > max_chars else text


def _parse_judge_json(text: str) -> dict[str, Any]:
    text = text.strip()
    for attempt in [
        lambda: json.loads(text),
        lambda: json.loads(re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL).group(1)),  # type: ignore
        lambda: json.loads(re.search(r'\{[^{}]*"score"[^{}]*\}', text).group(0)),  # type: ignore
    ]:
        try:
            return attempt()
        except Exception:
            continue
    return {"score": 0.0, "reason": f"Unparseable judge response: {text[:200]}"}
