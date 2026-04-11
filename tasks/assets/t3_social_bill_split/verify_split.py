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

EXPECTED_TOTAL = 273.21


def main() -> int:
    blob = workspace_blob().lower()
    for name in ("sasha", "jin", "rio", "priya"):
        if name not in blob:
            print(f"FAIL: bill split does not mention {name}")
            return 1

    # Sum dollar amounts in the workspace
    raw = workspace_blob()
    amounts = [float(x.replace(",", "")) for x in re.findall(r"\$\s?(\d+(?:\.\d{1,2})?)", raw)]
    if amounts:
        total = sum(amounts)
        # Should be roughly 1x or 2x EXPECTED_TOTAL
        ok = (abs(total - EXPECTED_TOTAL) < EXPECTED_TOTAL * 0.10
              or abs(total - 2 * EXPECTED_TOTAL) < 2 * EXPECTED_TOTAL * 0.10
              or abs(total - 3 * EXPECTED_TOTAL) < 3 * EXPECTED_TOTAL * 0.10)
        if not ok:
            print(f"FAIL: dollar amounts sum to {total:.2f}, not near expected {EXPECTED_TOTAL}")
            return 1

    print("PASS: bill split mentions all 4 non-payers and totals are reasonable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
