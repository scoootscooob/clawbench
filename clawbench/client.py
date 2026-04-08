"""Gateway client using WebSocket protocol v3.

Connects as control-ui client to preserve operator scopes with token auth.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from clawbench.schemas import Transcript, TranscriptMessage, ToolCall

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 3


@dataclass
class GatewayConfig:
    url: str = "ws://127.0.0.1:18789"
    token: str = ""
    connect_timeout: float = 15.0
    request_timeout: float = 300.0


class GatewayClient:
    """WebSocket client for OpenClaw gateway protocol v3.

    Connects as control-ui client (preserves scopes with token auth on localhost).
    Maintains a persistent connection for the session lifecycle.
    """

    def __init__(self, config: GatewayConfig | None = None) -> None:
        self.config = config or GatewayConfig()
        self._ws: ClientConnection | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._event_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._listen_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> GatewayClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def connect(self) -> None:
        # Set Origin header to localhost so control-ui auth accepts it
        host = self.config.url.replace("ws://", "http://").replace("wss://", "https://")
        self._ws = await websockets.connect(
            self.config.url,
            max_size=10 * 1024 * 1024,
            open_timeout=self.config.connect_timeout,
            additional_headers={"Origin": host},
        )
        self._listen_task = asyncio.create_task(self._listener())

        # Wait for connect.challenge
        challenge = await self._wait_event("connect.challenge", timeout=self.config.connect_timeout)
        logger.debug("Got connect.challenge")

        # Connect as control-ui — with dangerouslyDisableDeviceAuth + allowInsecureAuth,
        # this preserves operator.write scopes with token auth on localhost
        resp = await self._rpc("connect", {
            "minProtocol": PROTOCOL_VERSION,
            "maxProtocol": PROTOCOL_VERSION,
            "client": {
                "id": "openclaw-control-ui",
                "version": "0.1.0",
                "platform": "linux",
                "mode": "ui",
            },
            "role": "operator",
            "scopes": [
                "operator.admin", "operator.read", "operator.write",
                "operator.approvals", "operator.pairing",
            ],
            "caps": [],
            "commands": [],
            "permissions": {},
            "auth": {"token": self.config.token} if self.config.token else {},
        })

        payload = resp.get("payload", {})
        if payload.get("type") != "hello-ok":
            raise ConnectionError(f"Expected hello-ok, got: {payload}")
        logger.info("Connected to gateway (protocol v%d)", payload.get("protocol", 0))

    async def close(self) -> None:
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    async def create_session(
        self,
        model: str | None = None,
        agent_id: str | None = None,
        label: str | None = None,
    ) -> str:
        params: dict[str, Any] = {}
        if model:
            params["model"] = model
        if agent_id:
            params["agentId"] = agent_id
        if label:
            params["label"] = label
        resp = await self._rpc("sessions.create", params)
        payload = resp.get("payload", {})
        key = payload.get("sessionKey") or payload.get("key", "")
        if not key:
            raise RuntimeError(f"sessions.create returned no key: {payload}")
        logger.info("Created session: %s", key)
        return key

    async def subscribe(self, session_key: str) -> None:
        await self._rpc("sessions.messages.subscribe", {"key": session_key})

    async def send_and_wait(
        self,
        session_key: str,
        message: str,
        timeout: float | None = None,
    ) -> Transcript:
        """Send a message and wait for the agent to finish (state=final).

        Collects the transcript from streaming chat events (not chat.history,
        which is connection-scoped and returns empty from a fresh connection).
        Returns a Transcript with all messages from this turn.
        """
        timeout = timeout or self.config.request_timeout
        idempotency_key = str(uuid.uuid4())

        # Listen on both `chat` (for state=final) and `session.message` (for tool calls)
        chat_queue_key = f"chat:{session_key}"
        msg_queue_key = f"session.message:{session_key}"
        chat_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        msg_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._event_queues[chat_queue_key] = chat_queue
        self._event_queues[msg_queue_key] = msg_queue

        await self._rpc("sessions.send", {
            "key": session_key,
            "message": message,
            "idempotencyKey": idempotency_key,
        })

        # Collect transcript from session.message events (has tool calls + full messages)
        # Use chat event with state=final to know when agent is done
        collected_messages: list[TranscriptMessage] = []
        done = False
        deadline = asyncio.get_event_loop().time() + timeout
        try:
            while not done:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.warning("Timeout waiting for agent on %s", session_key)
                    break

                # Check chat queue for completion (non-blocking)
                try:
                    event = await asyncio.wait_for(chat_queue.get(), timeout=min(0.5, remaining))
                    payload = event.get("payload", {})
                    state = payload.get("state", "")
                    if state in ("final", "aborted", "error"):
                        if state == "error":
                            logger.warning("Agent error: %s", payload.get("errorMessage"))
                        done = True
                except asyncio.TimeoutError:
                    pass

            # Wait a moment for remaining session.message events to arrive
            await asyncio.sleep(0.5)

            # Drain ALL session.message events — this is our transcript source
            while not msg_queue.empty():
                event = msg_queue.get_nowait()
                payload = event.get("payload", {})
                msg_data = payload.get("message", {})
                if isinstance(msg_data, dict) and msg_data:
                    parsed = _parse_single_message(msg_data)
                    if parsed:
                        collected_messages.append(parsed)
        finally:
            self._event_queues.pop(chat_queue_key, None)
            self._event_queues.pop(msg_queue_key, None)

        tool_names = [tc.name for m in collected_messages for tc in m.tool_calls]
        logger.info("Collected %d messages, tools: %s", len(collected_messages), tool_names or "(none)")
        return Transcript(messages=collected_messages)

    async def get_history(self, session_key: str, max_chars: int = 500_000) -> Transcript:
        """Try chat.history first, fall back to collected events."""
        try:
            resp = await self._rpc("chat.history", {
                "sessionKey": session_key,
                "maxChars": max_chars,
            })
            transcript = _parse_transcript(resp.get("payload", {}))
            if transcript.messages:
                return transcript
        except Exception as e:
            logger.debug("chat.history failed: %s", e)
        # Return empty — caller should use transcript from send_and_wait
        return Transcript()

    async def delete_session(self, session_key: str) -> None:
        try:
            await self._rpc("sessions.delete", {"key": session_key})
        except Exception as e:
            logger.warning("Failed to delete session: %s", e)

    # ------------------------------------------------------------------
    # Low-level protocol
    # ------------------------------------------------------------------

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._ws:
            raise RuntimeError("Not connected")

        req_id = str(uuid.uuid4())
        frame = {"type": "req", "id": req_id, "method": method}
        if params is not None:
            frame["params"] = params

        future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        await self._ws.send(json.dumps(frame))
        logger.debug("Sent %s", method)

        try:
            resp = await asyncio.wait_for(future, timeout=self.config.request_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"RPC {method} timed out")

        if not resp.get("ok", False):
            error = resp.get("error", {})
            raise RuntimeError(f"RPC {method} failed: {error.get('code', '?')} - {error.get('message', '')}")
        return resp

    async def _listener(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                frame_type = frame.get("type")

                if frame_type == "res":
                    req_id = frame.get("id", "")
                    future = self._pending.pop(req_id, None)
                    if future and not future.done():
                        future.set_result(frame)

                elif frame_type == "event":
                    event_name = frame.get("event", "")
                    payload = frame.get("payload", {})
                    session_key = payload.get("sessionKey", "")
                    state = payload.get("state", "")

                    msg_preview = str(payload.get("message", ""))[:120]
                    logger.debug("EVENT %s session=%s state=%s msg=%s", event_name, session_key[:30] if session_key else "", state, msg_preview)

                    # Route to session-specific queue
                    queue_key = f"{event_name}:{session_key}"
                    if queue_key in self._event_queues:
                        await self._event_queues[queue_key].put(frame)
                    # Also route to generic event queue (for connect.challenge etc)
                    if event_name not in self._event_queues:
                        self._event_queues[event_name] = asyncio.Queue()
                    await self._event_queues[event_name].put(frame)

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket closed")
        except asyncio.CancelledError:
            pass

    async def _wait_event(self, event_name: str, timeout: float = 15.0) -> dict[str, Any]:
        if event_name not in self._event_queues:
            self._event_queues[event_name] = asyncio.Queue()
        return await asyncio.wait_for(self._event_queues[event_name].get(), timeout=timeout)


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def _parse_single_message(msg_data: dict[str, Any]) -> TranscriptMessage | None:
    """Parse a single message from a chat streaming event."""
    role = msg_data.get("role", "")
    if not role:
        return None

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    content = msg_data.get("content", "")
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type in ("tool_use", "toolCall"):
                # Handle both Anthropic format (tool_use) and OpenClaw format (toolCall)
                args = block.get("input", block.get("arguments", {}))
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    input=args if isinstance(args, dict) else {},
                ))
            elif block_type == "tool_result":
                rc = block.get("content", "")
                if isinstance(rc, str):
                    text_parts.append(rc)

    text = "\n".join(text_parts)
    if not text and not tool_calls:
        return None

    return TranscriptMessage(
        role=role,
        text=text,
        tool_calls=tool_calls,
    )


def _parse_transcript(payload: Any) -> Transcript:
    if not isinstance(payload, dict):
        return Transcript()

    raw_messages = payload.get("messages", [])
    if not isinstance(raw_messages, list):
        return Transcript()

    messages: list[TranscriptMessage] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue

        role = raw.get("role", "unknown")
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        tool_result_for: str | None = None

        content = raw.get("content", "")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type", "")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        input=block.get("input", {}),
                    ))
                elif block_type == "tool_result":
                    tool_result_for = block.get("tool_use_id", "")
                    rc = block.get("content", "")
                    if isinstance(rc, str):
                        text_parts.append(rc)

        messages.append(TranscriptMessage(
            role=role,
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            tool_result_for=tool_result_for,
        ))

    return Transcript(messages=messages)
