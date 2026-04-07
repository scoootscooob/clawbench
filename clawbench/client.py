"""WebSocket client for OpenClaw gateway protocol v3."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from clawbench.schemas import TokenUsage, Transcript, TranscriptMessage, ToolCall

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 3


@dataclass
class GatewayConfig:
    url: str = "ws://127.0.0.1:18789"
    token: str = ""
    client_id: str = "clawbench"
    client_version: str = "0.1.0"
    platform: str = "linux"
    connect_timeout: float = 15.0
    request_timeout: float = 300.0


@dataclass
class SessionMessage:
    """A streaming event from sessions.messages.subscribe."""

    run_id: str
    session_key: str
    seq: int
    state: str  # "delta" | "final" | "aborted" | "error"
    text: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    stop_reason: str | None = None


class GatewayClient:
    """Async WebSocket client that speaks OpenClaw gateway protocol v3.

    Usage:
        async with GatewayClient(config) as client:
            session_key = await client.create_session(model="anthropic/claude-sonnet-4-6")
            await client.subscribe(session_key)
            messages = await client.send_and_collect(session_key, "Hello")
            transcript = await client.get_history(session_key)
            await client.delete_session(session_key)
    """

    def __init__(self, config: GatewayConfig | None = None) -> None:
        self.config = config or GatewayConfig()
        self._ws: ClientConnection | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._event_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._connected = False

    async def __aenter__(self) -> GatewayClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            self.config.url,
            max_size=10 * 1024 * 1024,  # 10 MB
            open_timeout=self.config.connect_timeout,
        )
        self._listen_task = asyncio.create_task(self._listener())

        # Wait for connect.challenge
        challenge = await self._wait_event("connect.challenge", timeout=self.config.connect_timeout)
        logger.debug("Received connect.challenge nonce=%s", challenge.get("payload", {}).get("nonce"))

        # Send connect request
        resp = await self._rpc("connect", {
            "minProtocol": PROTOCOL_VERSION,
            "maxProtocol": PROTOCOL_VERSION,
            "client": {
                "id": self.config.client_id,
                "version": self.config.client_version,
                "platform": self.config.platform,
                "mode": "operator",
            },
            "role": "operator",
            "scopes": ["operator.read", "operator.write"],
            "caps": [],
            "commands": [],
            "permissions": {},
            "auth": {"token": self.config.token} if self.config.token else {},
        })

        payload = resp.get("payload", {})
        if payload.get("type") != "hello-ok":
            raise ConnectionError(f"Expected hello-ok, got: {payload}")

        negotiated = payload.get("protocol", 0)
        if negotiated != PROTOCOL_VERSION:
            raise ConnectionError(f"Protocol mismatch: wanted {PROTOCOL_VERSION}, got {negotiated}")

        self._connected = True
        logger.info("Connected to gateway (protocol v%d)", negotiated)

    async def close(self) -> None:
        self._connected = False
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
        logger.debug("Subscribed to messages for %s", session_key)

    async def send_and_collect(
        self,
        session_key: str,
        message: str,
        timeout: float | None = None,
    ) -> list[SessionMessage]:
        """Send a message and collect all response events until state is final/aborted/error."""
        timeout = timeout or self.config.request_timeout
        idempotency_key = str(uuid.uuid4())

        # Set up event collection before sending
        queue_key = f"session.message:{session_key}"
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._event_queues[queue_key] = queue

        await self._rpc("sessions.send", {
            "key": session_key,
            "message": message,
            "idempotencyKey": idempotency_key,
        })

        messages: list[SessionMessage] = []
        deadline = asyncio.get_event_loop().time() + timeout

        try:
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.warning("Timeout waiting for final message on %s", session_key)
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for final message on %s", session_key)
                    break

                payload = event.get("payload", {})
                msg = SessionMessage(
                    run_id=payload.get("runId", ""),
                    session_key=payload.get("sessionKey", session_key),
                    seq=payload.get("seq", 0),
                    state=payload.get("state", ""),
                    text=str(payload.get("message", "")),
                    usage=payload.get("usage", {}),
                    error_message=payload.get("errorMessage"),
                    stop_reason=payload.get("stopReason"),
                )
                messages.append(msg)

                if msg.state in ("final", "aborted", "error"):
                    break
        finally:
            self._event_queues.pop(queue_key, None)

        return messages

    async def get_history(self, session_key: str, max_chars: int = 500_000) -> Transcript:
        """Fetch full chat transcript via chat.history."""
        resp = await self._rpc("chat.history", {
            "sessionKey": session_key,
            "maxChars": max_chars,
        })
        return _parse_transcript(resp.get("payload", {}))

    async def delete_session(self, session_key: str) -> None:
        await self._rpc("sessions.delete", {"key": session_key})
        logger.debug("Deleted session %s", session_key)

    async def abort_session(self, session_key: str) -> None:
        await self._rpc("sessions.abort", {"key": session_key})
        logger.debug("Aborted session %s", session_key)

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
        logger.debug("Sent req %s method=%s", req_id[:8], method)

        try:
            resp = await asyncio.wait_for(future, timeout=self.config.request_timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"RPC {method} timed out after {self.config.request_timeout}s")

        if not resp.get("ok", False):
            error = resp.get("error", {})
            raise RuntimeError(
                f"RPC {method} failed: {error.get('code', 'unknown')} - {error.get('message', '')}"
            )
        return resp

    async def _listener(self) -> None:
        """Background task that routes incoming frames to pending RPCs or event queues."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON frame: %s", raw[:100])
                    continue

                frame_type = frame.get("type")

                if frame_type == "res":
                    req_id = frame.get("id", "")
                    future = self._pending.pop(req_id, None)
                    if future and not future.done():
                        future.set_result(frame)
                    else:
                        logger.debug("Unmatched response id=%s", req_id[:8])

                elif frame_type == "event":
                    event_name = frame.get("event", "")
                    # Route to specific queue if subscribed
                    payload = frame.get("payload", {})
                    session_key = payload.get("sessionKey", "")
                    queue_key = f"{event_name}:{session_key}"

                    if queue_key in self._event_queues:
                        await self._event_queues[queue_key].put(frame)
                    elif event_name in self._event_queues:
                        await self._event_queues[event_name].put(frame)
                    else:
                        # Pre-connect events (connect.challenge)
                        if event_name in self._event_queues:
                            await self._event_queues[event_name].put(frame)
                        else:
                            # Store for _wait_event
                            generic_key = event_name
                            if generic_key not in self._event_queues:
                                self._event_queues[generic_key] = asyncio.Queue()
                            await self._event_queues[generic_key].put(frame)
                else:
                    logger.debug("Unknown frame type: %s", frame_type)

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except asyncio.CancelledError:
            pass

    async def _wait_event(self, event_name: str, timeout: float = 15.0) -> dict[str, Any]:
        if event_name not in self._event_queues:
            self._event_queues[event_name] = asyncio.Queue()
        queue = self._event_queues[event_name]
        return await asyncio.wait_for(queue.get(), timeout=timeout)


# ---------------------------------------------------------------------------
# Transcript parsing helpers
# ---------------------------------------------------------------------------


def _parse_transcript(payload: Any) -> Transcript:
    """Parse chat.history payload into a Transcript."""
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
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        text_parts.append(result_content)

        messages.append(TranscriptMessage(
            role=role,
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            tool_result_for=tool_result_for,
        ))

    return Transcript(messages=messages)
