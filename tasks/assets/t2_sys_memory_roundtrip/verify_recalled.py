"""Phase 2 verifier: agent must recall from memory, not ask the user."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    recall_path = Path("recall.md")
    if not recall_path.exists():
        print("FAIL: recall.md missing")
        return 1
    text = recall_path.read_text(encoding="utf-8").lower()

    expected = ["react", "node", "postgres"]
    missing = [t for t in expected if t not in text]
    if missing:
        print(f"FAIL: recall.md missing {missing}")
        return 1

    # Negative checks: the agent should not have asked the user to repeat
    # the tech stack. Catch common phrasing.
    refusal_patterns = [
        r"what is your.*tech stack",
        r"could you tell me.*stack",
        r"i don.?t know.*stack",
        r"please remind me",
        r"can you provide.*stack",
    ]
    for pat in refusal_patterns:
        if re.search(pat, text):
            print(f"FAIL: recall.md contains evidence the agent asked the user instead of recalling: pattern '{pat}'")
            return 1

    print("PASS: tech stack recalled without re-asking")
    return 0


if __name__ == "__main__":
    sys.exit(main())
