"""Simulated user for POMDP-style agent evaluation.

Three modes:
1. Static: fixed message sequence (deterministic, for baseline tasks)
2. Adaptive: LLM-generated responses based on agent behavior (realistic)
3. Adversarial: contradicts, confuses, or requests impossible things
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from clawbench.schemas import SimulatedUser, Transcript, TranscriptMessage, UserTurn

logger = logging.getLogger(__name__)


class UserSimulator:
    """Drives the user side of the conversation."""

    def __init__(
        self,
        config: SimulatedUser,
        llm_model: str = "claude-sonnet-4-6-20250514",
        llm_api_key: str = "",
        llm_base_url: str = "https://api.anthropic.com",
    ) -> None:
        self.config = config
        self.llm_model = llm_model
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self._turn_index = 0
        self._done = False

    @property
    def is_done(self) -> bool:
        """Whether the simulated user has no more turns."""
        if self._done:
            return True
        if self.config.mode == "static":
            return self._turn_index >= len(self.config.turns)
        return self._turn_index >= self.config.max_turns

    async def next_message(self, transcript: Transcript) -> str | None:
        """Generate the next user message based on conversation state.

        Returns None if the user has no more turns.
        """
        if self.is_done:
            return None

        if self.config.mode == "static":
            return self._static_next()
        elif self.config.mode == "adaptive":
            return await self._adaptive_next(transcript)
        elif self.config.mode == "adversarial":
            return await self._adversarial_next(transcript)
        return None

    def _static_next(self) -> str | None:
        """Return the next static message."""
        if self._turn_index >= len(self.config.turns):
            return None
        turn = self.config.turns[self._turn_index]
        self._turn_index += 1
        return turn.message

    async def _adaptive_next(self, transcript: Transcript) -> str | None:
        """Generate an adaptive user response via LLM."""
        if not self.llm_api_key:
            logger.warning("No API key for adaptive user simulation, falling back to static")
            return self._static_next()

        system = self._build_adaptive_system_prompt()
        messages = self._transcript_to_messages(transcript)

        # Add instruction for what the user should do next
        messages.append({
            "role": "user",
            "content": (
                "Based on the conversation above, generate the NEXT user message. "
                "Stay in character as the simulated user. "
                "If the task is complete, respond with exactly: [DONE]"
            ),
        })

        response = await self._call_llm(system, messages)
        self._turn_index += 1

        if "[DONE]" in response:
            self._done = True
            return None

        return response

    async def _adversarial_next(self, transcript: Transcript) -> str | None:
        """Generate an adversarial user message.

        Adversarial modes:
        - Contradiction: change requirements mid-conversation
        - Impossible: ask for something that cannot be done
        - Ambiguous: give unclear instructions
        """
        # Check if we should inject a contradiction
        if (
            self.config.contradiction_turn is not None
            and self._turn_index == self.config.contradiction_turn
        ):
            self._turn_index += 1
            return await self._generate_contradiction(transcript)

        # For impossible tasks, the first turn contains the impossible request
        if self.config.impossible_request and self._turn_index == 0:
            self._turn_index += 1
            # Use static turn if available, or generate
            if self.config.turns:
                return self.config.turns[0].message
            return await self._generate_impossible(transcript)

        # Fall back to adaptive for other turns
        return await self._adaptive_next(transcript)

    async def _generate_contradiction(self, transcript: Transcript) -> str:
        """Generate a message that contradicts a previous request."""
        system = (
            "You are simulating a user who is changing their mind. "
            "Look at what the agent has been working on and generate a message "
            "that contradicts the original request. Be natural — users change "
            "their minds. Don't be absurd."
        )
        messages = self._transcript_to_messages(transcript)
        messages.append({
            "role": "user",
            "content": "Generate a contradictory follow-up message from the user.",
        })
        return await self._call_llm(system, messages)

    async def _generate_impossible(self, transcript: Transcript) -> str:
        """Generate an impossible request."""
        system = (
            "You are simulating a user who is asking for something that cannot be done "
            "with the available tools. The request should sound reasonable but be "
            "fundamentally impossible for the agent to fulfill. The correct agent "
            "behavior is to explain why it can't be done."
        )
        return await self._call_llm(system, [{
            "role": "user",
            "content": "Generate an impossible but reasonable-sounding request.",
        }])

    def _build_adaptive_system_prompt(self) -> str:
        parts = [
            "You are simulating a user interacting with an AI agent.",
            f"Your persona: {self.config.persona}" if self.config.persona else "",
            f"Your goal: {self.config.goal}" if self.config.goal else "",
            "",
            "Rules:",
            "- Stay in character at all times",
            "- Respond naturally as a real user would",
            "- If the agent asks a clarifying question, answer it",
            "- If the agent completes your task, you may ask a follow-up or say [DONE]",
            "- If the agent is going off track, redirect it",
            "- Generate ONLY the user's message, nothing else",
        ]
        return "\n".join(p for p in parts if p)

    def _transcript_to_messages(self, transcript: Transcript) -> list[dict[str, str]]:
        """Convert transcript to LLM message format."""
        messages: list[dict[str, str]] = []
        for msg in transcript.messages:
            if msg.role in ("user", "assistant"):
                text = msg.text
                if msg.tool_calls:
                    tool_names = ", ".join(tc.name for tc in msg.tool_calls)
                    text += f"\n[Agent used tools: {tool_names}]"
                messages.append({"role": msg.role, "content": text or "(empty)"})
        return messages

    async def _call_llm(self, system: str, messages: list[dict[str, str]]) -> str:
        """Call the LLM for user simulation."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    f"{self.llm_base_url}/v1/messages",
                    headers={
                        "x-api-key": self.llm_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.llm_model,
                        "max_tokens": 256,
                        "system": system,
                        "messages": messages,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("content", [{}])[0].get("text", "")
        except Exception as e:
            logger.error("User simulation LLM call failed: %s", e)
            return "(User simulation failed — ending conversation)"
