"""Deterministic scripted user simulation for ClawBench v0.3."""

from __future__ import annotations

import re
from typing import Any

from clawbench.render import render_template
from clawbench.schemas import PromptVariant, SimulatedUser, Transcript, UserTurn


class UserSimulator:
    """Drives the user side of a deterministic benchmark conversation."""

    def __init__(
        self,
        config: SimulatedUser,
        runtime_values: dict[str, Any] | None = None,
        *,
        prompt_variant: str = PromptVariant.CLEAR.value,
    ) -> None:
        self.config = config
        self.runtime_values = runtime_values or {}
        self.prompt_variant = prompt_variant
        self._turn_index = 0
        self._done = False

    @property
    def is_done(self) -> bool:
        if self._done:
            return True
        return self._turn_index >= len(self.config.turns) or self._turn_index >= self.config.max_turns

    async def next_message(self, transcript: Transcript) -> str | None:
        if self.is_done:
            return None

        turn = self.config.turns[self._turn_index]
        if not self._turn_is_ready(turn, transcript):
            self._done = True
            return None

        self._turn_index += 1
        message = turn.variant_messages.get(self.prompt_variant, turn.message)
        return render_template(message, self.runtime_values)

    def _turn_is_ready(self, turn: UserTurn, transcript: Transcript) -> bool:
        assistant_messages = transcript.assistant_messages
        if turn.after_assistant_turns is not None and len(assistant_messages) < turn.after_assistant_turns:
            return False

        last_call = transcript.tool_call_sequence[-1] if transcript.tool_call_sequence else None
        if turn.when_tool_family:
            if not last_call or last_call.family != turn.when_tool_family:
                return False

        if turn.when_tool_name:
            if not last_call or not re.search(turn.when_tool_name, last_call.name, re.IGNORECASE):
                return False

        if turn.when_assistant_contains:
            latest_text = assistant_messages[-1].text if assistant_messages else ""
            if not re.search(turn.when_assistant_contains, latest_text, re.IGNORECASE):
                return False

        if turn.when_last_tool_failed:
            if not last_call or last_call.success is not False:
                return False

        return True
