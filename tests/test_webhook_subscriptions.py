from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
import respx

from proofage import ProofAge
from proofage.errors import NotFoundError, ServerError, ValidationError
from proofage.models import VerificationStatus, WebhookSubscription, WebhookSubscriptionList

from .conftest import API_KEY, SECRET_KEY, Harness

SUBSCRIPTION: dict[str, Any] = {
    "id": "0199c4b2-7d1e-7a3f-9c0e-5b6a7c8d9e0f",
    "url": "https://hooks.zapier.com/hooks/standard/12345678/abcdef/",
    "statuses": ["approved", "declined"],
    "include_document_data": False,
    "created_at": "2026-10-08T12:00:00+00:00",
}
SID = SUBSCRIPTION["id"]


def body(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


def test_create_sends_only_what_was_given(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/webhook-subscriptions").respond(201, json=SUBSCRIPTION)
    subscription = sdk.call(
        lambda c: c.webhook_subscriptions.create(
            url=SUBSCRIPTION["url"], statuses=[VerificationStatus.APPROVED, "declined"]
        )
    )
    assert isinstance(subscription, WebhookSubscription)
    assert subscription.statuses == [VerificationStatus.APPROVED, VerificationStatus.DECLINED]
    assert subscription.include_document_data is False
    assert subscription.created_at == datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    assert body(route) == {"url": SUBSCRIPTION["url"], "statuses": ["approved", "declined"]}


def test_create_with_every_field(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/webhook-subscriptions").respond(
        201, json={**SUBSCRIPTION, "statuses": None, "include_document_data": True}
    )
    subscription = sdk.call(
        lambda c: c.webhook_subscriptions.create(
            url="https://example.com/hook", include_document_data=True
        )
    )
    assert subscription.statuses is None
    assert body(route) == {"url": "https://example.com/hook", "include_document_data": True}


def test_create_refuses_a_single_string_for_statuses(api: respx.MockRouter) -> None:
    with (
        ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url="https://api.test") as client,
        pytest.raises(TypeError, match="list of statuses"),
    ):
        client.webhook_subscriptions.create(url="https://example.com/hook", statuses="approved")
    assert not api.calls


def test_create_is_not_retried_on_5xx(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/webhook-subscriptions").respond(502)
    with pytest.raises(ServerError):
        sdk.call(
            lambda c: c.webhook_subscriptions.create(url="https://example.com/hook"),
            retry_delay=0,
        )
    assert route.call_count == 1


def test_create_past_the_limit(sdk: Harness, api: respx.MockRouter) -> None:
    api.post("/webhook-subscriptions").respond(
        422,
        json={
            "error": {
                "code": "WEBHOOK_SUBSCRIPTION_LIMIT",
                "message": "A workspace can have at most 50 webhook subscriptions.",
            }
        },
    )
    with pytest.raises(ValidationError) as caught:
        sdk.call(lambda c: c.webhook_subscriptions.create(url="https://example.com/hook"))
    assert caught.value.code == "WEBHOOK_SUBSCRIPTION_LIMIT"


def test_list(sdk: Harness, api: respx.MockRouter) -> None:
    unknown = {**SUBSCRIPTION, "id": "s2", "statuses": ["approved", "quarantined"]}
    api.get("/webhook-subscriptions").respond(200, json={"data": [SUBSCRIPTION, unknown]})
    subscriptions = sdk.call(lambda c: c.webhook_subscriptions.list())
    assert isinstance(subscriptions, WebhookSubscriptionList)
    assert [s.id for s in subscriptions.data] == [SID, "s2"]
    assert subscriptions.data[1].statuses == [VerificationStatus.APPROVED, "quarantined"]


def test_delete_reads_no_body(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.delete(f"/webhook-subscriptions/{SID}").respond(204)
    assert sdk.call(lambda c: c.webhook_subscriptions.delete(SID)) is None
    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.content == b""


def test_delete_an_unknown_subscription(sdk: Harness, api: respx.MockRouter) -> None:
    api.delete(f"/webhook-subscriptions/{SID}").respond(404, json={"message": "Resource not found"})
    with pytest.raises(NotFoundError, match="Resource not found"):
        sdk.call(lambda c: c.webhook_subscriptions.delete(SID))


def test_delete_is_not_retried_on_5xx(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.delete(f"/webhook-subscriptions/{SID}").respond(503)
    with pytest.raises(ServerError):
        sdk.call(lambda c: c.webhook_subscriptions.delete(SID), retry_delay=0)
    assert route.call_count == 1


@pytest.mark.parametrize("bad_id", ["../verifications", "a/b", "", "a?b"])
def test_a_malformed_id_never_reaches_the_network(api: respx.MockRouter, bad_id: str) -> None:
    with (
        ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url="https://api.test") as client,
        pytest.raises(ValueError, match="subscription_id"),
    ):
        client.webhook_subscriptions.delete(bad_id)
    assert not api.calls
