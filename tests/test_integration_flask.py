from __future__ import annotations

import pytest
from flask import Flask, jsonify
from flask.testing import FlaskClient

from proofage.integrations.flask import proofage_webhook
from proofage.models import WebhookEvent

from .conftest import API_KEY, SECRET_KEY
from .integration_support import BODY, assert_needs_extra, configure_keys, signed_headers


def make_client() -> FlaskClient:
    app = Flask(__name__)

    @app.post("/webhooks/proofage")
    @proofage_webhook
    def hook(event: WebhookEvent) -> object:
        return jsonify(
            id=event.verification_id, status=str(event.status), delivery=event.delivery_id
        )

    @app.post("/keyed")
    @proofage_webhook(api_key=API_KEY, secret_key=SECRET_KEY)
    def keyed(event: WebhookEvent) -> object:
        return jsonify(id=event.verification_id)

    return app.test_client()


def test_a_valid_webhook_reaches_the_view_as_a_typed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_keys(monkeypatch)
    response = make_client().post("/webhooks/proofage", data=BODY, headers=signed_headers())
    assert response.status_code == 200
    assert response.get_json() == {"id": "v-1", "status": "approved", "delivery": "d-1"}


def test_a_tampered_body_is_a_401_with_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_keys(monkeypatch)
    response = make_client().post(
        "/webhooks/proofage", data=BODY.replace(b"approved", b"declined"), headers=signed_headers()
    )
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_SIGNATURE"


def test_an_unconfigured_server_is_a_500(monkeypatch: pytest.MonkeyPatch) -> None:
    response = make_client().post("/webhooks/proofage", data=BODY, headers=signed_headers())
    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "CONFIGURATION_ERROR"


def test_a_signed_body_that_is_not_an_event_is_a_400(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_keys(monkeypatch)
    body = b'{"hello":"world"}'
    response = make_client().post("/webhooks/proofage", data=body, headers=signed_headers(body))
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_PAYLOAD"


def test_keys_can_be_passed_to_the_decorator() -> None:
    response = make_client().post("/keyed", data=BODY, headers=signed_headers())
    assert response.status_code == 200
    assert response.get_json() == {"id": "v-1"}


def test_importing_without_flask_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    assert_needs_extra(monkeypatch, "proofage.integrations.flask", "flask")


def test_a_misconfigured_server_says_so_in_its_own_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING", logger="proofage"):
        make_client().post("/webhooks/proofage", data=BODY, headers=signed_headers())
    assert "PROOFAGE_SECRET_KEY" in caplog.text
