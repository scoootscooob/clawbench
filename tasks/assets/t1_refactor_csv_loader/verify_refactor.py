from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    parsing = Path("parsing.py").read_text(encoding="utf-8")
    csv_loader = Path("csv_loader.py").read_text(encoding="utf-8")
    report_builder = Path("report_builder.py").read_text(encoding="utf-8")

    assert "def parse_inventory_row" in parsing
    assert "from parsing import parse_inventory_row" in csv_loader
    assert "from parsing import parse_inventory_row" in report_builder

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


if __name__ == "__main__":
    main()
