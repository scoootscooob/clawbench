"""Helpers for unique gateway session labels."""

from __future__ import annotations

import re
import uuid

_NON_ALNUM_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def unique_session_label(prefix: str, *, max_prefix_len: int = 80) -> str:
    """Return a gateway-friendly label with a unique suffix.

    Some gateway deployments keep session labels reserved longer than the
    benchmark lifetime, so deterministic labels can collide across runs.
    """

    normalized = _NON_ALNUM_RE.sub("-", prefix).strip("-") or "clawbench-session"
    trimmed = normalized[:max_prefix_len].rstrip("-") or "clawbench-session"
    return f"{trimmed}-{uuid.uuid4().hex[:10]}"
