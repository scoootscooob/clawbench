"""Seed the v0.5 historical database with a synthetic 40-profile ecosystem.

This is a bootstrap script for demos and tests. In production, the database
fills in organically as real submissions accumulate.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_e2e_significance import build_ecosystem  # type: ignore
from clawbench.prediction import HistoricalDatabase


def main():
    db_path = Path(__file__).resolve().parents[1] / ".clawbench/historical/profile_runs.json"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    in_mem_db, _, _, _ = build_ecosystem(n_profiles=40)
    persistent_db = HistoricalDatabase(path=db_path)
    for run in in_mem_db.runs:
        persistent_db.add(run)
    print(f"Seeded {len(persistent_db)} runs into {db_path}")


if __name__ == "__main__":
    main()
