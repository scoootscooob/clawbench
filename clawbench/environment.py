"""Environment state verification — the ground truth axis.

Verifies the WORLD changed correctly, not that the agent SAID it changed.
Queries workspace filesystem, gateway protocol state, and agent memory
to compare actual state against the task's goal state.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from clawbench.client import GatewayClient
from clawbench.schemas import (
    CronState,
    FileState,
    GatewayAssertion,
    GoalState,
    MemoryState,
    SessionState,
    StateVerificationResult,
)

logger = logging.getLogger(__name__)


async def verify_goal_state(
    goal: GoalState,
    workspace: Path,
    client: GatewayClient,
    session_key: str,
) -> StateVerificationResult:
    """Verify the environment matches the expected goal state.

    This is the core of what makes this a real agent benchmark:
    we don't read the agent's response — we inspect the actual world.
    """
    total = 0
    passed = 0
    failures: list[str] = []

    # 1. Filesystem state
    for fs in goal.files:
        result, reason = _verify_file(fs, workspace)
        total += 1
        if result:
            passed += 1
        else:
            failures.append(f"FILE {fs.path}: {reason}")

    # 2. Memory state (query gateway for memory entries)
    for ms in goal.memory:
        result, reason = await _verify_memory(ms, client, session_key)
        total += 1
        if result:
            passed += 1
        else:
            failures.append(f"MEMORY {ms.key_pattern}: {reason}")

    # 3. Session state
    if goal.session:
        result, reason = await _verify_session(goal.session, client, session_key)
        total += 1
        if result:
            passed += 1
        else:
            failures.append(f"SESSION: {reason}")

    # 4. Cron/scheduled task state
    for cs in goal.cron:
        result, reason = await _verify_cron(cs, client)
        total += 1
        if result:
            passed += 1
        else:
            failures.append(f"CRON: {reason}")

    # 5. Raw gateway assertions (most flexible — query any protocol method)
    for ga in goal.gateway_assertions:
        result, reason = await _verify_gateway_assertion(ga, client)
        total += 1
        if result:
            passed += 1
        else:
            failures.append(f"GATEWAY {ga.method}:{ga.assert_path}: {reason}")

    score = passed / total if total > 0 else 1.0

    return StateVerificationResult(
        total_assertions=total,
        passed_assertions=passed,
        failed_assertions=failures,
        score=score,
    )


# ---------------------------------------------------------------------------
# Filesystem verification
# ---------------------------------------------------------------------------


def _verify_file(spec: FileState, workspace: Path) -> tuple[bool, str]:
    """Check a workspace file against its expected state."""
    path = workspace / spec.path
    exists = path.exists() and path.is_file()

    if not spec.exists:
        if exists:
            return False, "File should not exist but does"
        return True, "Correctly absent"

    if not exists:
        return False, "File does not exist"

    try:
        content = path.read_text(errors="replace")
    except Exception as e:
        return False, f"Cannot read file: {e}"

    if spec.min_size_bytes > 0 and path.stat().st_size < spec.min_size_bytes:
        return False, f"File too small: {path.stat().st_size} < {spec.min_size_bytes}"

    for pattern in spec.content_contains:
        if not re.search(re.escape(pattern), content, re.IGNORECASE):
            return False, f"Missing expected content: '{pattern}'"

    for pattern in spec.content_not_contains:
        if re.search(re.escape(pattern), content, re.IGNORECASE):
            return False, f"Contains forbidden content: '{pattern}'"

    if spec.content_matches:
        if not re.search(spec.content_matches, content, re.MULTILINE | re.DOTALL):
            return False, f"Content does not match pattern: {spec.content_matches[:60]}"

    return True, "OK"


# ---------------------------------------------------------------------------
# Memory verification (query gateway)
# ---------------------------------------------------------------------------


async def _verify_memory(
    spec: MemoryState,
    client: GatewayClient,
    session_key: str,
) -> tuple[bool, str]:
    """Query agent memory via gateway and verify state."""
    try:
        # Use the gateway to search memory
        resp = await client._rpc("memory.search", {
            "query": spec.key_pattern,
            "sessionKey": session_key,
            "limit": 10,
        })
        payload = resp.get("payload", {})
        entries = payload.get("entries", [])

        if not spec.exists:
            if entries:
                return False, "Memory entry exists but should not"
            return True, "Correctly absent"

        if not entries:
            return False, "No matching memory entries found"

        # Check value contains
        all_values = " ".join(str(e.get("value", "")) for e in entries)
        for pattern in spec.value_contains:
            if pattern.lower() not in all_values.lower():
                return False, f"Memory value missing: '{pattern}'"

        return True, "OK"
    except Exception as e:
        # Memory might not be available — degrade gracefully
        logger.warning("Memory verification failed: %s", e)
        return False, f"Memory query failed: {e}"


# ---------------------------------------------------------------------------
# Session state verification
# ---------------------------------------------------------------------------


async def _verify_session(
    spec: SessionState,
    client: GatewayClient,
    session_key: str,
) -> tuple[bool, str]:
    """Verify session state via gateway protocol."""
    try:
        resp = await client._rpc("sessions.resolve", {"key": session_key})
        payload = resp.get("payload", {})

        if not spec.should_exist:
            return False, "Session exists but should not"

        if spec.model_should_be:
            actual_model = payload.get("model", "")
            if spec.model_should_be.lower() not in actual_model.lower():
                return False, f"Model mismatch: expected '{spec.model_should_be}', got '{actual_model}'"

        return True, "OK"
    except Exception as e:
        if not spec.should_exist:
            return True, "Correctly absent"
        return False, f"Session query failed: {e}"


# ---------------------------------------------------------------------------
# Cron state verification
# ---------------------------------------------------------------------------


async def _verify_cron(
    spec: CronState,
    client: GatewayClient,
) -> tuple[bool, str]:
    """Verify scheduled task state via gateway protocol."""
    try:
        resp = await client._rpc("cron.list", {})
        payload = resp.get("payload", {})
        jobs = payload.get("jobs", [])

        if not spec.exists:
            if jobs:
                return False, "Cron jobs exist but should not"
            return True, "Correctly absent"

        if not jobs:
            return False, "No cron jobs found"

        if spec.description_contains:
            any_match = any(
                spec.description_contains.lower() in str(j).lower()
                for j in jobs
            )
            if not any_match:
                return False, f"No cron job matching '{spec.description_contains}'"

        return True, "OK"
    except Exception as e:
        logger.warning("Cron verification failed: %s", e)
        return False, f"Cron query failed: {e}"


# ---------------------------------------------------------------------------
# Raw gateway assertion
# ---------------------------------------------------------------------------


async def _verify_gateway_assertion(
    spec: GatewayAssertion,
    client: GatewayClient,
) -> tuple[bool, str]:
    """Execute a raw gateway protocol query and verify the result."""
    try:
        resp = await client._rpc(spec.method, spec.params)
        payload = resp.get("payload", {})

        # Navigate the JSONPath-like assertion path
        value = _resolve_path(payload, spec.assert_path)

        if not spec.assert_exists:
            if value is not None:
                return False, f"Path {spec.assert_path} exists but should not"
            return True, "Correctly absent"

        if value is None:
            return False, f"Path {spec.assert_path} not found in response"

        if spec.assert_equals is not None:
            if value != spec.assert_equals:
                return False, f"Expected {spec.assert_equals}, got {value}"

        if spec.assert_contains is not None:
            if spec.assert_contains.lower() not in str(value).lower():
                return False, f"Value does not contain '{spec.assert_contains}'"

        return True, "OK"
    except Exception as e:
        return False, f"Gateway query {spec.method} failed: {e}"


def _resolve_path(data: Any, path: str) -> Any:
    """Resolve a simple JSONPath-like expression.

    Supports: $.key, $.array[0], $.nested.path
    """
    if not path or path == "$":
        return data

    parts = path.lstrip("$.").split(".")
    current = data

    for part in parts:
        if current is None:
            return None

        # Handle array index: key[0]
        bracket_match = re.match(r"(\w+)\[(\d+)\]", part)
        if bracket_match:
            key, idx = bracket_match.group(1), int(bracket_match.group(2))
            if isinstance(current, dict):
                current = current.get(key)
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None

    return current
