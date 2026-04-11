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
    for path, text in iter_workspace_text_files():
        if not any("\u4e00" <= ch <= "\u9fff" for ch in text):
            continue
        if "Dear Mr. Chen" in text or "The Procurement Team" in text:
            continue  # the original english source
        if len(text.strip()) < 20:
            continue
        print(f"PASS: Chinese translation present at {path}")
        return 0
    print("FAIL: no non-trivial Chinese translation found anywhere in workspace")
    return 1


if __name__ == "__main__":
    sys.exit(main())
