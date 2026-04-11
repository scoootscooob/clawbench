"""Verify that files were sorted according to retention_policy.yaml."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main() -> int:
    policy_path = Path("retention_policy.yaml")
    if not policy_path.exists():
        print(f"FAIL: retention_policy.yaml missing")
        return 1
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))

    sorted_root = Path("Downloads/sorted")
    if not sorted_root.exists():
        print(f"FAIL: Downloads/sorted directory missing")
        return 1

    cats = policy.get("categories", {})
    failed = []
    cats_with_files = 0
    for cat_name, spec in cats.items():
        target = Path(spec["target"])
        exts = set(spec.get("extensions", []))
        # A category target dir is REQUIRED only if any file with a matching
        # extension still lives anywhere in Downloads (sorted or not).
        any_matching_in_downloads = any(
            p.suffix.lower() in exts and ".trash" not in p.parts
            for p in Path("Downloads").rglob("*")
            if p.is_file()
        )
        if not any_matching_in_downloads:
            continue  # nothing to sort for this category — directory optional
        if not target.exists():
            failed.append(f"missing target {target} (files of this type exist in Downloads)")
            continue
        files_in_target = [f for f in target.iterdir() if f.is_file()]
        if not files_in_target:
            failed.append(f"{target} exists but is empty")
            continue
        bad_ext = [f for f in files_in_target if f.suffix.lower() not in exts]
        if bad_ext:
            failed.append(f"{target} contains wrong-ext files: {[f.name for f in bad_ext]}")
            continue
        cats_with_files += 1

    if failed:
        print("FAIL:", "; ".join(failed))
        return 1

    print(f"PASS: retention policy honored across {cats_with_files} active categories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
