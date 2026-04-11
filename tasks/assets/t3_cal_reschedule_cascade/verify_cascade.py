"""Recursive workspace search verifier."""

from __future__ import annotations

import sys
from pathlib import Path

EXCLUDE_FRAGMENTS = (
    "verify_", "/.git/", "/.openclaw/",
    "BOOTSTRAP.md", "IDENTITY.md", "AGENTS.md",
    "USER.md", "SOUL.md", "HEARTBEAT.md",
)
TEXT_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".log",
                  ".jsonl", ".html", ".sh", ".py")


def iter_workspace_text_files(root: Path = Path(".")):
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


def workspace_blob() -> str:
    return "\n".join(text for _, text in iter_workspace_text_files())


def main() -> int:
    blob = workspace_blob().lower()
    if "prd" not in blob:
        print("FAIL: notification does not mention PRD review")
        return 1

    downstream = [
        ("design_review", ["design review", "design_review"]),
        ("eng_kickoff", ["engineering kickoff", "eng kickoff", "eng_kickoff"]),
        ("sprint_plan", ["sprint planning", "sprint plan", "sprint_plan"]),
    ]
    missing = []
    for label, patterns in downstream:
        if not any(p in blob for p in patterns):
            missing.append(label)
    if missing:
        print(f"FAIL: missing downstream events: {missing}")
        return 1

    print("PASS: cascade includes 3 downstream events")
    return 0


if __name__ == "__main__":
    sys.exit(main())
