from __future__ import annotations

import sys
import urllib.request


def main(url: str) -> None:
    with urllib.request.urlopen(f"{url}/status", timeout=3) as response:
        body = response.read().decode("utf-8")
    print(body)


if __name__ == "__main__":
    main(sys.argv[1])
