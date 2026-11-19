"""X-Timestamp on every attempt, and the Idempotency-Key on creates."""

from __future__ import annotations

import re

import httpx
import pytest
import respx

from proofage._signing import sign
from proofage.errors import ConfigurationError, ProofAgeError, ServerError

from .conftest import NOW, SECRET_KEY, Harness
from .test_models import VERIFICATION

CREATED = VERIFICATION
SUBSCRIPTION = {
    "id": "s1",
    "url": "https://example.com/hook",
    "statuses": None,
    "include_document_data": False,
    "created_at": "2026-11-19T10:00:00+00:00",
}
UUID_V4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
IN_PROGRESS = {"error": {"code": "IDEMPOTENCY_KEY_IN_PROGRESS", "message": "Still running."}}


class Ticking:
    """A clock that moves one second per read, so each attempt gets its own timestamp."""

    def __init__(self) -> None:
        self.value = float(NOW)

    def __call__(self) -> float:
        self.value += 1
        return self.value


def test_every_request_carries_the_timestamp_it_signed(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").respond(200, json={"id": "ws", "name": "Shop"})
    sdk.call(lambda c: c._get("workspace"))
    headers = route.calls.last.request.headers
    assert headers["X-Timestamp"] == str(NOW)
    assert headers["X-HMAC-Signature"] == sign(SECRET_KEY, f"{NOW}.GET/v1/workspace")


def test_a_retry_is_signed_again_with_a_new_timestamp(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"id": "ws", "name": "Shop"})]
    )
    sdk.clock = Ticking()
    sdk.call(lambda c: c._get("workspace"), retry_delay=0)
    first, second = (call.request for call in route.calls)
    assert first.headers["X-Timestamp"] == str(NOW + 1)
    assert second.headers["X-Timestamp"] != first.headers["X-Timestamp"]
    for request in (first, second):
        stamp = request.headers["X-Timestamp"]
        assert request.headers["X-HMAC-Signature"] == sign(SECRET_KEY, f"{stamp}.GET/v1/workspace")
    assert first.headers["X-HMAC-Signature"] != second.headers["X-HMAC-Signature"]


def test_a_multipart_retry_is_signed_again(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications/v1/media").mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200)]
    )
    sdk.clock = Ticking()
    sdk.call(
        lambda c: c._post_multipart(
            "verifications/v1/media", {"type": "document"}, filename="a.jpg", content=b"x"
        ),
        retry_delay=0,
    )
    first, second = (call.request for call in route.calls)
    assert first.headers["X-Timestamp"] != second.headers["X-Timestamp"]
    assert first.headers["X-HMAC-Signature"] != second.headers["X-HMAC-Signature"]


def test_a_create_sends_a_uuid_v4_key(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(201, json=CREATED)
    sdk.call(lambda c: c.verifications.create(external_id="a"))
    assert UUID_V4.fullmatch(route.calls.last.request.headers["Idempotency-Key"])


def test_each_create_call_gets_its_own_key(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(201, json=CREATED)
    sdk.call(lambda c: c.verifications.create())
    sdk.call(lambda c: c.verifications.create())
    keys = {call.request.headers["Idempotency-Key"] for call in route.calls}
    assert len(keys) == 2


def test_the_callers_key_is_sent(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(201, json=CREATED)
    sdk.call(lambda c: c.verifications.create(idempotency_key="order-42"))
    assert route.calls.last.request.headers["Idempotency-Key"] == "order-42"


def test_the_callers_key_is_sent_on_a_subscription(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/webhook-subscriptions").respond(201, json=SUBSCRIPTION)
    sdk.call(
        lambda c: c.webhook_subscriptions.create(
            url="https://example.com/hook", idempotency_key="hook-1"
        )
    )
    assert route.calls.last.request.headers["Idempotency-Key"] == "hook-1"


@pytest.mark.parametrize("key", ["", "has space", "ünï", "x" * 256])
def test_a_malformed_key_is_refused_before_anything_is_sent(
    sdk: Harness, api: respx.MockRouter, key: str
) -> None:
    with pytest.raises(ConfigurationError):
        sdk.call(lambda c: c.verifications.create(idempotency_key=key))
    assert not api.calls


def test_other_requests_carry_no_key(sdk: Harness, api: respx.MockRouter) -> None:
    get = api.get("/workspace").respond(200, json={"id": "ws", "name": "Shop"})
    post = api.post("/verifications/v1/consent").respond(204)
    sdk.call(lambda c: c._get("workspace"))
    sdk.call(lambda c: c._post_empty("verifications/v1/consent", {}))
    assert "Idempotency-Key" not in get.calls.last.request.headers
    assert "Idempotency-Key" not in post.calls.last.request.headers


def test_a_keyed_create_is_retried_on_5xx_with_the_same_key_and_a_fresh_signature(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[httpx.Response(503), httpx.Response(201, json=CREATED)]
    )
    sdk.clock = Ticking()
    created = sdk.call(lambda c: c.verifications.create(external_id="a"), retry_delay=0)
    assert created.id == CREATED["id"]
    first, second = (call.request for call in route.calls)
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert first.content == second.content
    assert first.headers["X-Timestamp"] != second.headers["X-Timestamp"]
    assert first.headers["X-HMAC-Signature"] != second.headers["X-HMAC-Signature"]


def test_a_keyed_create_is_retried_after_a_failure_mid_request(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(201, json=CREATED)]
    )
    sdk.call(lambda c: c.verifications.create(), retry_delay=0)
    assert route.call_count == 2


def test_an_unkeyed_post_is_still_not_retried_on_5xx(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(503)
    with pytest.raises(ServerError):
        sdk.call(lambda c: c._post("verifications", {}), retry_delay=0)
    assert route.call_count == 1


def test_a_keyed_create_waits_out_an_in_progress_conflict(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[
            httpx.Response(409, headers={"Retry-After": "1"}, json=IN_PROGRESS),
            httpx.Response(201, json=CREATED),
        ]
    )
    sdk.call(lambda c: c.verifications.create(idempotency_key="k"), retry_delay=0)
    assert route.call_count == 2
    assert sdk.sleeps == [1.0]


def test_a_reused_key_is_not_retried(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(
        409, json={"error": {"code": "IDEMPOTENCY_KEY_REUSED", "message": "Other request."}}
    )
    with pytest.raises(ProofAgeError) as raised:
        sdk.call(lambda c: c.verifications.create(idempotency_key="k"), retry_delay=0)
    assert raised.value.code == "IDEMPOTENCY_KEY_REUSED"
    assert route.call_count == 1


def test_a_409_in_progress_on_an_unkeyed_post_is_not_retried(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").respond(409, json=IN_PROGRESS)
    with pytest.raises(ProofAgeError):
        sdk.call(lambda c: c._post("verifications", {}), retry_delay=0)
    assert route.call_count == 1
