from __future__ import annotations

import json

import pytest
from django.conf import settings

if not settings.configured:
    settings.configure(DEBUG=True, ALLOWED_HOSTS=["*"], SECRET_KEY="test", USE_TZ=True)

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.test import RequestFactory

from proofage.integrations.django import proofage_webhook

from .conftest import API_KEY, SECRET_KEY
from .integration_support import (
    BODY,
    assert_needs_extra,
    configure_keys,
    signed_headers,
)


@proofage_webhook
def hook(request: HttpRequest) -> HttpResponse:
    event = request.proofage_event  # type: ignore[attr-defined]
    return JsonResponse(
        {"id": event.verification_id, "status": str(event.status), "delivery": event.delivery_id}
    )


@proofage_webhook(api_key=API_KEY, secret_key=SECRET_KEY)
def keyed(request: HttpRequest) -> HttpResponse:
    return JsonResponse({"id": request.proofage_event.verification_id})  # type: ignore[attr-defined]


def post(view: object, body: bytes = BODY, headers: dict[str, str] | None = None) -> HttpResponse:
    request = RequestFactory().post(
        "/webhooks/proofage",
        data=body,
        content_type="application/json",
        headers=signed_headers(body) if headers is None else headers,
    )
    return view(request)  # type: ignore[operator, no-any-return]


def test_a_valid_webhook_sets_the_typed_event_on_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_keys(monkeypatch)
    response = post(hook)
    assert response.status_code == 200
    assert json.loads(response.content) == {"id": "v-1", "status": "approved", "delivery": "d-1"}


def test_a_tampered_body_is_a_401_with_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_keys(monkeypatch)
    response = post(hook, BODY.replace(b"approved", b"declined"), signed_headers())
    assert response.status_code == 401
    assert json.loads(response.content)["error"]["code"] == "INVALID_SIGNATURE"


def test_only_post_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_keys(monkeypatch)
    response = hook(RequestFactory().get("/webhooks/proofage"))
    assert response.status_code == 405


def test_csrf_does_not_apply() -> None:
    assert getattr(hook, "csrf_exempt", False) is True


def test_an_unconfigured_server_is_a_500() -> None:
    response = post(hook)
    assert response.status_code == 500
    assert json.loads(response.content)["error"]["code"] == "CONFIGURATION_ERROR"


def test_a_signed_body_that_is_not_an_event_is_a_400(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_keys(monkeypatch)
    body = b'{"hello":"world"}'
    response = post(hook, body, signed_headers(body))
    assert response.status_code == 400
    assert json.loads(response.content)["error"]["code"] == "INVALID_PAYLOAD"


def test_keys_can_be_passed_to_the_decorator() -> None:
    assert post(keyed).status_code == 200


def test_importing_without_django_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    assert_needs_extra(monkeypatch, "proofage.integrations.django", "django")
