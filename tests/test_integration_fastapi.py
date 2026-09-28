from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from proofage.integrations.fastapi import ProofAgeWebhook, webhook_dependency
from proofage.models import WebhookEvent

from .conftest import API_KEY, SECRET_KEY
from .integration_support import BODY, assert_needs_extra, configure_keys, signed_headers


def make_client() -> TestClient:
    app = FastAPI()

    @app.post("/webhooks/proofage")
    async def proofage_webhook(event: ProofAgeWebhook) -> dict[str, str | None]:
        return {
            "id": event.verification_id,
            "status": str(event.status),
            "delivery": event.delivery_id,
        }

    return TestClient(app)


def test_a_valid_webhook_reaches_the_handler_as_a_typed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_keys(monkeypatch)
    response = make_client().post("/webhooks/proofage", content=BODY, headers=signed_headers())
    assert response.status_code == 200
    assert response.json() == {"id": "v-1", "status": "approved", "delivery": "d-1"}


def test_a_tampered_body_is_a_401_with_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_keys(monkeypatch)
    response = make_client().post(
        "/webhooks/proofage",
        content=BODY.replace(b"approved", b"declined"),
        headers=signed_headers(),
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_SIGNATURE"


def test_missing_headers_are_a_401(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_keys(monkeypatch)
    response = make_client().post("/webhooks/proofage", content=BODY)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "MISSING_SIGNATURE"


def test_an_unconfigured_server_is_a_500(monkeypatch: pytest.MonkeyPatch) -> None:
    response = make_client().post("/webhooks/proofage", content=BODY, headers=signed_headers())
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "CONFIGURATION_ERROR"


def test_a_signed_body_that_is_not_an_event_is_a_400(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_keys(monkeypatch)
    body = b'{"hello":"world"}'
    response = make_client().post("/webhooks/proofage", content=body, headers=signed_headers(body))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_PAYLOAD"


KeyedWebhook = Annotated[
    WebhookEvent, Depends(webhook_dependency(api_key=API_KEY, secret_key=SECRET_KEY))
]


def test_keys_can_be_passed_instead_of_read_from_the_environment() -> None:
    app = FastAPI()

    @app.post("/hook")
    async def hook(event: KeyedWebhook) -> dict[str, str]:
        return {"id": event.verification_id}

    response = TestClient(app).post("/hook", content=BODY, headers=signed_headers())
    assert response.status_code == 200
    assert response.json() == {"id": "v-1"}


def test_importing_without_fastapi_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    assert_needs_extra(monkeypatch, "proofage.integrations.fastapi", "fastapi")
