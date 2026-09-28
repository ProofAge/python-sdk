from __future__ import annotations

from collections.abc import Iterator

import pytest

API_KEY = "pk_test_0123456789abcdef"
SECRET_KEY = "sk_test_do_not_leak_0123456789"
BASE_URL = "https://api.test"
API = f"{BASE_URL}/v1"
VERIFICATION_ID = "0192a3b4-c5d6-7e8f-9a0b-1c2d3e4f5a6b"


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test may read a developer's real PROOFAGE_* variables."""
    import os

    for name in list(os.environ):
        if name.startswith("PROOFAGE_"):
            monkeypatch.delenv(name)
    yield
