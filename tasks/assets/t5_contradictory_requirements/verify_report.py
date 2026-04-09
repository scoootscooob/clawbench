from __future__ import annotations

import sys

import yaml


def main(path: str) -> None:
    with open(path, encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    assert payload == {"open": 3, "closed": 2}


if __name__ == "__main__":
    main(sys.argv[1])

