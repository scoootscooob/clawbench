from typing import Iterable


def load_rows(lines: Iterable[str]) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw_name, raw_count = line.split(",", 1)
        rows.append(
            {
                "name": raw_name.strip().lower(),
                "count": int(raw_count.strip()),
            }
        )
    return rows

