"""Scale every task's timeout_seconds by a factor.

Opus is ~3x slower per-call than Sonnet. When we run Opus on timeouts
that were sized for Sonnet, every task gets cut off mid-run and scored
as if it failed. Scaling timeouts up lets us measure Opus's actual
capability instead of its unluckiness with our 240s defaults.

Usage:
    python scripts/scale_timeouts.py 3.0   # triple all timeouts
    python scripts/scale_timeouts.py 1.0   # reset to current values
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parents[1] / "tasks"


def main():
    if len(sys.argv) != 2:
        print("usage: python scripts/scale_timeouts.py <scale>")
        sys.exit(1)
    scale = float(sys.argv[1])

    touched = 0
    for yml in TASKS_DIR.rglob("t*.yaml"):
        raw = yml.read_text(encoding="utf-8")
        def repl(m: re.Match) -> str:
            key = m.group(1)
            orig = int(m.group(2))
            scaled = max(1, int(round(orig * scale)))
            return f"{key}: {scaled}"
        new = re.sub(r"^(timeout_seconds):\s*(\d+)\s*$", repl, raw, flags=re.MULTILINE)
        # Phase-level timeouts too
        new = re.sub(r"^(    timeout_seconds):\s*(\d+)\s*$", repl, new, flags=re.MULTILINE)
        new = re.sub(r"^(  timeout_seconds):\s*(\d+)\s*$", repl, new, flags=re.MULTILINE)
        if new != raw:
            yml.write_text(new, encoding="utf-8")
            touched += 1
    print(f"scaled timeouts in {touched} task files by {scale}x")


if __name__ == "__main__":
    main()
