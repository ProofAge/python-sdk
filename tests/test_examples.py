"""The examples import, and their logic works, so they cannot rot silently."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx
from aiohttp.test_utils import TestClient as AioTestClient
from aiohttp.test_utils import TestServer
from django.conf import settings
from fastapi.testclient import TestClient

from proofage import AsyncProofAge

from .conftest import API, API_KEY, BASE_URL, SECRET_KEY
from .integration_support import BODY, configure_keys, signed_headers
from .test_models import VERIFICATION

EXAMPLES = Path(__file__).parent.parent / "examples"


def load(relative: str) -> ModuleType:
    path = EXAMPLES / relative
    spec = importlib.util.spec_from_file_location(f"example_{path.parent.name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingBot:
    """Stands in for aiogram's Bot: records what the example sends."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def webhook_headers(body: bytes = BODY) -> dict[str, str]:
    return signed_headers(body)


def test_the_aiogram_bot_sends_a_verification_link(api: respx.MockRouter) -> None:
    bot_module = load("aiogram_bot/bot.py")
    route = api.post("/verifications").respond(201, json=VERIFICATION)

    async def main() -> str:
        async with AsyncProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url=BASE_URL) as c:
            return await bot_module.start_verification(c, chat_id=4242)

    text = asyncio.run(main())
    assert VERIFICATION["url"] in text
    assert json.loads(route.calls.last.request.content) == {"external_id": "4242"}


def test_the_aiogram_bot_reports_the_outcome_once_per_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_keys(monkeypatch)
    bot_module = load("aiogram_bot/bot.py")
    bot = RecordingBot()
    body = BODY.replace(b'"external_id":"u-1"', b'"external_id":"4242"')

    async def main() -> list[int]:
        server = TestServer(bot_module.build_webhook_app(bot))
        async with AioTestClient(server) as client:
            first = await client.post(
                "/webhooks/proofage", data=body, headers=webhook_headers(body)
            )
            again = await client.post(
                "/webhooks/proofage", data=body, headers=webhook_headers(body)
            )
            forged = await client.post(
                "/webhooks/proofage",
                data=body.replace(b"approved", b"declined"),
                headers=webhook_headers(body),
            )
            return [first.status, again.status, forged.status]

    assert asyncio.run(main()) == [200, 200, 401]
    assert len(bot.sent) == 1
    assert bot.sent[0][0] == 4242


def test_the_fastapi_example_creates_and_receives(
    monkeypatch: pytest.MonkeyPatch, api: respx.MockRouter
) -> None:
    configure_keys(monkeypatch)
    monkeypatch.setenv("PROOFAGE_BASE_URL", BASE_URL)
    module = load("fastapi_app/main.py")
    api.post("/verifications").respond(201, json=VERIFICATION)

    with TestClient(module.app) as client:
        created = client.post("/verifications", json={"user_id": "u-1"})
        assert created.status_code == 200
        assert created.json()["url"] == VERIFICATION["url"]

        received = client.post("/webhooks/proofage", content=BODY, headers=webhook_headers())
        assert received.status_code == 200
        assert client.get("/status/u-1").json() == {"status": "approved"}


def test_the_django_example_imports_and_redirects(
    monkeypatch: pytest.MonkeyPatch, api: respx.MockRouter
) -> None:
    from django.test import RequestFactory

    if not settings.configured:
        settings.configure(DEBUG=True, ALLOWED_HOSTS=["*"], SECRET_KEY="test", USE_TZ=True)
    configure_keys(monkeypatch)
    monkeypatch.setenv("PROOFAGE_BASE_URL", BASE_URL)
    views: Any = load("django_view/views.py")
    api.post("/verifications").mock(return_value=httpx.Response(201, json=VERIFICATION))

    request = RequestFactory().post("/verify/")
    request.user = type("User", (), {"pk": 7, "is_authenticated": True})()
    response = views.start(request)
    assert response.status_code == 302
    assert response["Location"] == VERIFICATION["url"]
    assert API.startswith(BASE_URL)
