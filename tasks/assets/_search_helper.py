"""Shared search helper for v0.5 verifiers.

Verifiers must accept artifacts wherever the agent wrote them. The OpenClaw
agent's AGENTS.md instructs it to capture notes in memory/YYYY-MM-DD.md, so
many tasks end up with content in memory/ rather than the workspace path the
verifier originally expected.

This module is copied into each asset pack rather than imported, because
verifiers run from the per-run workspace where the package isn't installed.
"""

from __future__ import annotations

from pathlib import Path

EXCLUDE_FRAGMENTS = (
    "verify_",
    "/.git/",
    "/.openclaw/",
    "BOOTSTRAP.md",
    "IDENTITY.md",
    "AGENTS.md",
    "USER.md",
    "SOUL.md",
    "HEARTBEAT.md",
    "MEMORY.md",
)

TEXT_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".log",
                  ".jsonl", ".html", ".sh", ".py")


def iter_workspace_text_files(root: Path | str = "."):
    root = Path(root)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        sp = str(path)
        if any(frag in sp for frag in EXCLUDE_FRAGMENTS):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            yield path, path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue


def find_with_all(needed_lower: list[str], root: str = ".") -> tuple[Path | None, str]:
    """Return the first text file containing every substring in needed_lower."""
    needed = [s.lower() for s in needed_lower]
    for path, text in iter_workspace_text_files(root):
        text_lower = text.lower()
        if all(s in text_lower for s in needed):
            return path, text
    return None, ""


def find_with_any(any_lower: list[str], root: str = ".") -> tuple[Path | None, str]:
    """Return the first text file containing any substring in any_lower."""
    any_set = [s.lower() for s in any_lower]
    for path, text in iter_workspace_text_files(root):
        text_lower = text.lower()
        if any(s in text_lower for s in any_set):
            return path, text
    return None, ""


def collect_all_text(root: str = ".") -> str:
    """Concatenate every text file in the workspace into one searchable blob."""
    parts = []
    for _, text in iter_workspace_text_files(root):
        parts.append(text)
    return "\n".join(parts)
