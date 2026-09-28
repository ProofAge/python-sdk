from __future__ import annotations

import proofage


def test_the_package_reports_its_version() -> None:
    assert proofage.__version__ == "0.1.0"
