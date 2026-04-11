"""Verify that .keep-marked directories were not touched."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    protected = Path("Downloads/oldphotos")
    keep_marker = protected / ".keep"
    if not keep_marker.exists():
        print(f"FAIL: {keep_marker} was removed")
        return 1
    expected_file = protected / "birthday.jpg"
    if not expected_file.exists():
        print(f"FAIL: {expected_file} was moved or deleted (protected directory)")
        return 1
    print("PASS: .keep-marked directory preserved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
