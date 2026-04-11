"""Phase 1 verifier: check that memory contains the tech-stack assertion.

Memory state for ClawBench tasks is exposed by the gateway via a JSON file
written into the workspace at the path indicated by the env var
CLAWBENCH_MEMORY_DUMP, or `memory_dump.json` if absent.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def main() -> int:
    dump_path = Path(os.environ.get("CLAWBENCH_MEMORY_DUMP", "memory_dump.json"))
    if not dump_path.exists():
        # Fall back to scanning the workspace for any memory file
        for candidate in Path(".").rglob("memory*.json"):
            dump_path = candidate
            break
    if not dump_path.exists():
        print("FAIL: no memory dump found")
        return 1

    try:
        memory = json.loads(dump_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: memory dump is not valid JSON: {exc}")
        return 1

    # Memory may be either a flat dict or a list of {key, value} entries
    blob = json.dumps(memory).lower()
    expected = ["react", "node", "postgres"]
    missing = [token for token in expected if token not in blob]
    if missing:
        print(f"FAIL: memory missing tech stack tokens: {missing}")
        print(f"memory dump: {blob[:500]}")
        return 1
    print("PASS: tech stack stored in memory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
