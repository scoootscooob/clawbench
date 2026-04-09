from __future__ import annotations

import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "check_service.py", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def main() -> None:
    healthy_url = sys.argv[1]
    healthy = _run(healthy_url)
    assert healthy.returncode == 0, healthy.stdout + healthy.stderr
    assert healthy.stdout.strip() == "healthy"

    failing = _run(healthy_url.replace("/health", "/missing"))
    assert failing.returncode != 0, "health-check script should fail for a bad endpoint"


if __name__ == "__main__":
    main()
