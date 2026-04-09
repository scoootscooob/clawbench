from pathlib import Path

import pytest

from clawbench.environment import verify_completion
from clawbench.schemas import CompletionSpec, MemoryState, ToolCall, Transcript, TranscriptMessage


class MemoryFallbackClient:
    async def _rpc(self, method: str, params=None):  # noqa: ANN001
        if method == "memory.search":
            raise RuntimeError("unknown method: memory.search")
        raise AssertionError(f"Unexpected RPC: {method} {params}")

    async def get_agent_file(self, agent_id: str, name: str):  # noqa: ARG002
        if name == "MEMORY.md":
            return {
                "file": {
                    "content": "beta rollout regions: us, eu; retry budget: 3\n",
                }
            }
        return {"file": {"content": ""}}


@pytest.mark.asyncio
async def test_memory_completion_falls_back_to_agent_memory_files(tmp_path: Path):
    completion = CompletionSpec(
        memory=[
            MemoryState(
                key_pattern="beta rollout regions",
                value_contains=["us", "eu", "3"],
            )
        ]
    )

    result = await verify_completion(
        completion,
        workspace=tmp_path,
        client=MemoryFallbackClient(),  # type: ignore[arg-type]
        session_key="session-test",
        agent_id="agent-test",
        runtime_values={},
    )

    assert result.score == 1.0


@pytest.mark.asyncio
async def test_memory_completion_falls_back_to_transcript_when_memory_rpc_is_unavailable(tmp_path: Path):
    completion = CompletionSpec(
        memory=[
            MemoryState(
                key_pattern="beta rollout regions",
                value_contains=["us", "eu", "3"],
            )
        ]
    )
    transcript = Transcript(
        messages=[
            TranscriptMessage(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        name="write",
                        family="edit",
                        input={
                            "path": "memory/notes.md",
                            "content": "beta rollout regions: us, eu; retry budget: 3\n",
                        },
                        success=True,
                    )
                ],
            )
        ]
    )

    result = await verify_completion(
        completion,
        workspace=tmp_path,
        client=MemoryFallbackClient(),  # type: ignore[arg-type]
        session_key="session-test",
        agent_id="agent-test",
        runtime_values={},
        transcript=transcript,
    )

    assert result.score == 1.0
