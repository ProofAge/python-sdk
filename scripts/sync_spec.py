"""Copy the app's generated OpenAPI spec into the package.

Source defaults to the sibling app checkout; override with PROOFAGE_OPENAPI_SRC.
Regenerate it first in the app: `cd developer-docs && npm run generate:openapi`.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = Path(
    os.environ.get(
        "PROOFAGE_OPENAPI_SRC",
        HERE.parent.parent / "proofageapp" / "developer-docs" / "public" / "openapi.json",
    )
)
DESTINATION = HERE.parent / "src" / "proofage" / "openapi.json"


def main() -> int:
    if not SOURCE.exists():
        print(f"Source spec not found: {SOURCE}", file=sys.stderr)
        print(
            "Run `npm run generate:openapi` in the app, or set PROOFAGE_OPENAPI_SRC.",
            file=sys.stderr,
        )
        return 1
    shutil.copyfile(SOURCE, DESTINATION)
    print(f"Synced spec: {SOURCE} -> {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
