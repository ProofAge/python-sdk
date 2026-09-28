from __future__ import annotations

import re

import proofage


def test_the_package_reports_its_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", proofage.__version__)
