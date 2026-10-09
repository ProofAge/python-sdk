"""Copy the published OpenAPI spec into the package.

Source defaults to https://docs.proofage.net/openapi.json. PROOFAGE_OPENAPI_SRC overrides
it with another URL or a local file, for example the docs repo's openapi.json before it is
published (the docs repo regenerates it from the app with scripts/sync_openapi.py).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = os.environ.get("PROOFAGE_OPENAPI_SRC", "https://docs.proofage.net/openapi.json")
DESTINATION = HERE.parent / "src" / "proofage" / "openapi.json"
# The docs host answers 403 to urllib's default "Python-urllib/x.y" User-Agent.
USER_AGENT = "proofage-python-sdk/sync_spec"


def read(source: str) -> str:
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(source)
    return path.read_text(encoding="utf-8")


def main() -> int:
    try:
        body = read(SOURCE)
        json.loads(body)
    except (OSError, ValueError) as error:
        print(f"Could not read the spec from {SOURCE}: {error}", file=sys.stderr)
        return 1
    DESTINATION.write_text(body, encoding="utf-8")
    print(f"Synced spec: {SOURCE} -> {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
