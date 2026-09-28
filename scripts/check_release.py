"""Refuse a release number PyPI already serves or one below the published latest.

The registry, not `git tag`, is the truth: a sibling SDK once lost tags for
versions it had published. Usage: `uv run python scripts/check_release.py 0.1.1`.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from packaging.version import Version

PACKAGE = "proofage"
VERSION_FILE = Path(__file__).resolve().parent.parent / "src" / "proofage" / "_version.py"


def published() -> list[Version]:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{PACKAGE}/json", timeout=15) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    return sorted(Version(v) for v in data["releases"])


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_release.py X.Y.Z", file=sys.stderr)
        return 2
    candidate = Version(argv[1])
    match = re.search(r'__version__ = "([^"]+)"', VERSION_FILE.read_text(encoding="utf-8"))
    if match is None or Version(match.group(1)) != candidate:
        print(
            f"_version.py says {match.group(1) if match else '?'}, not {candidate}", file=sys.stderr
        )
        return 1
    versions = published()
    print(f"PyPI serves: {', '.join(map(str, versions)) or 'nothing yet'}")
    if candidate in versions:
        print(f"{candidate} is already published", file=sys.stderr)
        return 1
    if versions and candidate < versions[-1]:
        print(f"{candidate} is below the latest published {versions[-1]}", file=sys.stderr)
        return 1
    print(f"{candidate} is free")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
