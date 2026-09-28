from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import respx

from proofage import AsyncProofAge, ProofAge

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


@dataclass
class Harness:
    """Runs one scenario against the sync or the async client, recording sleeps."""

    kind: str
    sleeps: list[float] = field(default_factory=list)

    def call(self, fn: Callable[[Any], Any], **client_kwargs: Any) -> Any:
        kwargs: dict[str, Any] = {
            "api_key": API_KEY,
            "secret_key": SECRET_KEY,
            "base_url": BASE_URL,
            **client_kwargs,
        }
        if self.kind == "sync":
            with ProofAge(**kwargs) as client:
                client._sleep = self.sleeps.append
                return fn(client)

        async def main() -> Any:
            async with AsyncProofAge(**kwargs) as client:

                async def record(seconds: float) -> None:
                    self.sleeps.append(seconds)

                client._sleep = record
                return await fn(client)

        return asyncio.run(main())


@pytest.fixture(params=["sync", "async"])
def sdk(request: pytest.FixtureRequest) -> Harness:
    return Harness(request.param)


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=API, assert_all_called=False) as router:
        yield router
