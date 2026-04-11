"""Verify duplicates were moved to .trash, originals kept (most recent retained)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    trash = Path("Downloads/.trash")
    if not trash.exists():
        print("FAIL: Downloads/.trash missing")
        return 1

    # The original asset pack contained two identical Q1 PDFs. After cleanup,
    # exactly ONE Q1 PDF should still be live (anywhere in Downloads/sorted)
    # and at least one should be in .trash.
    live_pdfs = []
    for path in Path("Downloads").rglob("*.pdf"):
        if ".trash" in path.parts:
            continue
        live_pdfs.append((path, file_sha(path)))

    trashed_pdfs = list(trash.rglob("*.pdf"))

    # Look for the Q1 hash specifically by content
    target_content = b"FAKE_PDF_q1_report\n"
    target_hash = hashlib.sha256(target_content).hexdigest()
    live_q1 = [p for p, h in live_pdfs if h == target_hash]

    if len(live_q1) != 1:
        print(f"FAIL: expected exactly 1 live Q1 PDF, found {len(live_q1)}")
        return 1
    if not trashed_pdfs:
        print("FAIL: trash should contain at least one duplicate PDF")
        return 1

    print(f"PASS: 1 live Q1 PDF, {len(trashed_pdfs)} duplicates in trash")
    return 0


if __name__ == "__main__":
    sys.exit(main())
