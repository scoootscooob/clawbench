from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def summarize_log(path: str) -> dict[str, object]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    summary = {
        "total": 0,
        "levels": {},
        "services": {},
    }
    for line in lines:
        if not line.strip():
            continue
        summary["total"] += 1
        parts = dict(item.split("=", 1) for item in line.split()[1:])
        # TODO: this should count all levels and services, not only ERROR rows.
        if parts["level"] == "ERROR":
            summary["levels"][parts["level"]] = summary["levels"].get(parts["level"], 0) + 1
            summary["services"][parts["service"]] = summary["services"].get(parts["service"], 0) + 1
    return summary


def main() -> None:
    args = parse_args()
    summary = summarize_log(args.path)
    if args.as_json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(summary)


if __name__ == "__main__":
    main()

