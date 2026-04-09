import pytest

from clawbench.schemas import SimulatedUser, ToolCall, Transcript, TranscriptMessage, UserTurn
from clawbench.simulated_user import UserSimulator


@pytest.mark.asyncio
async def test_simulated_user_obeys_turn_conditions():
    simulator = UserSimulator(
        SimulatedUser(
            turns=[
                UserTurn(message="Open http://127.0.0.1:{port}/"),
                UserTurn(
                    message="Now continue with the fix.",
                    after_assistant_turns=1,
                    when_assistant_contains="continue",
                ),
            ]
        ),
        {"port": 8123},
    )

    transcript = Transcript()
    assert await simulator.next_message(transcript) == "Open http://127.0.0.1:8123/"

    transcript.messages.append(
        TranscriptMessage(
            role="assistant",
            text="I found the bug and can continue.",
            tool_calls=[ToolCall(name="browser", input={"action": "snapshot"}, family="browser")],
        )
    )
    assert await simulator.next_message(transcript) == "Now continue with the fix."
    assert await simulator.next_message(transcript) is None


@pytest.mark.asyncio
async def test_simulated_user_prefers_variant_message_when_available():
    simulator = UserSimulator(
        SimulatedUser(
            turns=[
                UserTurn(
                    message="Write the exact checklist.",
                    variant_messages={"ambiguous": "Can you jot that checklist down for me?"},
                )
            ]
        ),
        prompt_variant="ambiguous",
    )

    assert await simulator.next_message(Transcript()) == "Can you jot that checklist down for me?"
