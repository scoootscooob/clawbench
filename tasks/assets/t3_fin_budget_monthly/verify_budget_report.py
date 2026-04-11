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


import re

def main() -> int:
    blob = workspace_blob().lower()
    cats = ["groceries", "dining_out", "dining out", "transport", "utilities",
            "entertainment", "fitness", "subscriptions"]
    found = sum(1 for c in cats if c in blob)
    if found < 6:
        print(f"FAIL: budget report only mentions {found}/8 categories")
        return 1

    # Entertainment was the big over (212 vs 100 budget)
    ent_window = re.search(r"entertainment[\s\S]{0,300}", blob)
    if ent_window and not any(w in ent_window.group() for w in ("over", "exceed", "above", "+", "212", "112")):
        print("FAIL: entertainment not flagged as over-budget")
        return 1

    # Concert tickets ($180) is the outlier explanation
    if "concert" not in blob and "180" not in blob:
        print("FAIL: outlier explanation does not reference concert tickets")
        return 1

    print(f"PASS: {found}/8 categories analyzed, entertainment flagged, outlier referenced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
