from __future__ import annotations

import json
from pathlib import Path

REQUIRED_KEYS = {
    "entrypoint",
    "total_module",
    "formatter_module",
    "smoke_test",
}


def _normalize_path(value: str) -> str:
    return value.strip().replace("\\", "/").removeprefix("./").lower()


def _contains_path(value: str, expected: str) -> bool:
    normalized = _normalize_path(value)
    return normalized == expected or normalized.endswith(expected)


def _is_valid_smoke_command(value: str) -> bool:
    normalized = " ".join(value.strip().lower().split())
    if "pytest" not in normalized:
        return False
    return (
        "tests/test_smoke.py" in normalized
        or "test_smoke.py" in normalized
        or normalized in {"pytest -q", "python -m pytest -q", "python3 -m pytest -q"}
    )


def main() -> None:
    payload = json.loads(Path("architecture.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert REQUIRED_KEYS.issubset(payload)
    assert _contains_path(str(payload["entrypoint"]), "app.py")
    assert _contains_path(str(payload["total_module"]), "shop/cart.py")
    assert _contains_path(str(payload["formatter_module"]), "shop/formatting.py")
    assert _is_valid_smoke_command(str(payload["smoke_test"]))


if __name__ == "__main__":
    main()
