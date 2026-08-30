"""Fail closed unless the local API and bundled Workbench are both ready."""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    try:
        health_request = Request(
            "http://127.0.0.1:8000/api/health",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urlopen(health_request, timeout=2) as response:
            health_ok = response.status == 200 and json.load(response) == {
                "status": "ok",
                "database": "ok",
            }
        workbench_request = Request(
            "http://127.0.0.1:8000/",
            headers={"Accept": "text/html"},
            method="GET",
        )
        with urlopen(workbench_request, timeout=2) as response:
            workbench_ok = (
                response.status == 200 and response.headers.get_content_type() == "text/html"
            )
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return 1
    return 0 if health_ok and workbench_ok else 1


if __name__ == "__main__":
    sys.exit(main())
