"""X-Timestamp on every attempt, and the Idempotency-Key on creates."""

from __future__ import annotations

import email.utils
import re
from datetime import datetime, timezone

import httpx
import pytest
import respx

from proofage._signing import sign
from proofage.errors import AuthenticationError, ConfigurationError, ProofAgeError, ServerError

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


REPLAYED = {"error": {"code": "REPLAYED_REQUEST", "message": "Already used."}}


def test_a_replayed_request_is_resent_once_with_a_new_timestamp(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[httpx.Response(401, json=REPLAYED), httpx.Response(201, json=CREATED)]
    )
    sdk.clock = Ticking()
    sdk.call(lambda c: c.verifications.create(idempotency_key="k"), retry_delay=0)
    first, second = (call.request for call in route.calls)
    assert first.headers["X-Timestamp"] != second.headers["X-Timestamp"]
    assert first.headers["X-HMAC-Signature"] != second.headers["X-HMAC-Signature"]
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"] == "k"
    assert first.content == second.content


def test_a_second_replayed_request_raises(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(401, json=REPLAYED)
    sdk.clock = Ticking()
    with pytest.raises(AuthenticationError) as raised:
        sdk.call(lambda c: c._post("verifications", {}), retry_delay=0)
    assert raised.value.code == "REPLAYED_REQUEST"
    assert route.call_count == 2


def test_the_replay_resend_works_with_a_single_attempt_and_for_unkeyed_posts(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[httpx.Response(401, json=REPLAYED), httpx.Response(201, json=CREATED)]
    )
    sdk.clock = Ticking()
    sdk.call(lambda c: c._post("verifications", {}), retry_attempts=1)
    assert route.call_count == 2


def test_the_replay_resend_does_not_use_up_a_retry_attempt(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[
            httpx.Response(401, json=REPLAYED),
            httpx.Response(503),
            httpx.Response(201, json=CREATED),
        ]
    )
    sdk.clock = Ticking()
    sdk.call(lambda c: c.verifications.create(), retry_attempts=2, retry_delay=0)
    assert route.call_count == 3


def test_a_get_is_not_resent_on_replayed_request(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").respond(401, json=REPLAYED)
    with pytest.raises(AuthenticationError):
        sdk.call(lambda c: c._get("workspace"))
    assert route.call_count == 1


def test_a_delete_is_resent_on_replayed_request(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.delete("/webhook-subscriptions/s1").mock(
        side_effect=[httpx.Response(401, json=REPLAYED), httpx.Response(204)]
    )
    sdk.clock = Ticking()
    sdk.call(lambda c: c._delete("webhook-subscriptions/s1"))
    assert route.call_count == 2


def http_date(unix: float) -> str:
    return email.utils.format_datetime(datetime.fromtimestamp(unix, timezone.utc), usegmt=True)


OUT_OF_RANGE = {"error": {"code": "TIMESTAMP_OUT_OF_RANGE", "message": "Clock is off."}}


def test_clock_skew_is_learned_from_date_and_the_request_resent_once(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[
            httpx.Response(401, headers={"Date": http_date(NOW + 400)}, json=OUT_OF_RANGE),
            httpx.Response(201, json=CREATED),
            httpx.Response(201, json=CREATED),
        ]
    )

    def two_creates(client):  # type: ignore[no-untyped-def]
        return (
            client.verifications.create(idempotency_key="k"),
            client.verifications.create(idempotency_key="k2"),
        )

    if sdk.kind == "sync":
        sdk.call(two_creates, retry_attempts=1)
    else:

        async def run(client):  # type: ignore[no-untyped-def]
            await client.verifications.create(idempotency_key="k")
            await client.verifications.create(idempotency_key="k2")

        sdk.call(run, retry_attempts=1)
    first, second, third = (call.request for call in route.calls)
    assert first.headers["X-Timestamp"] == str(NOW)
    assert second.headers["X-Timestamp"] == str(NOW + 400)
    assert second.headers["Idempotency-Key"] == "k"
    assert second.headers["X-HMAC-Signature"] == sign(
        SECRET_KEY, f"{NOW + 400}.{second.method}/v1/verifications"
    )
    assert int(third.headers["X-Timestamp"]) >= NOW + 400


def test_a_second_out_of_range_raises(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").respond(
        401, headers={"Date": http_date(NOW + 400)}, json=OUT_OF_RANGE
    )
    with pytest.raises(AuthenticationError) as raised:
        sdk.call(lambda c: c._get("workspace"))
    assert raised.value.code == "TIMESTAMP_OUT_OF_RANGE"
    assert route.call_count == 2


def test_out_of_range_without_a_date_header_raises_at_once(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.get("/workspace").respond(401, json=OUT_OF_RANGE)
    with pytest.raises(AuthenticationError):
        sdk.call(lambda c: c._get("workspace"))
    assert route.call_count == 1


def test_a_keyed_retry_within_the_same_second_waits_for_a_new_one(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[httpx.Response(500), httpx.Response(201, json=CREATED)]
    )
    sdk.call(lambda c: c.verifications.create(), retry_delay=0.1)
    first, second = (call.request for call in route.calls)
    assert int(second.headers["X-Timestamp"]) > int(first.headers["X-Timestamp"])
    assert sum(sdk.sleeps) >= 1


def test_an_early_wakeup_does_not_reuse_the_second(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").mock(
        side_effect=[httpx.Response(503), httpx.Response(201, json=CREATED)]
    )
    real_sleep = sdk.sleep

    def early(seconds: float) -> None:
        real_sleep(seconds / 2)

    sdk.sleep = early  # type: ignore[method-assign]
    sdk.call(lambda c: c.verifications.create(), retry_delay=0.1)
    first, second = (call.request for call in route.calls)
    assert int(second.headers["X-Timestamp"]) > int(first.headers["X-Timestamp"])


def test_a_get_retry_does_not_wait_for_a_new_second(sdk: Harness, api: respx.MockRouter) -> None:
    api.get("/workspace").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"id": "ws", "name": "Shop"})]
    )
    sdk.call(lambda c: c._get("workspace"), retry_delay=0.1)
    assert sdk.sleeps == [0.1]
