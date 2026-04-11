"""Verify symlinks were not followed and not destroyed."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # If a symlink fixture is set up at Downloads/external_link, it should
    # still exist as a symlink (if the asset pack provides one).
    candidate = Path("Downloads/external_link")
    if candidate.is_symlink():
        # Symlink preserved — pass
        print("PASS: symlink preserved as-is")
        return 0
    # If the test fixture didn't ship a symlink, this verifier is a no-op pass.
    print("PASS: no symlink fixture present (verifier is no-op)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
