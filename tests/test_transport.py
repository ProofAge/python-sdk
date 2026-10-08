from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
import respx

from proofage import AsyncProofAge, ProofAge
from proofage._signing import canonical_multipart_request, canonical_request, sign
from proofage._transport import parse_retry_after
from proofage._version import __version__
from proofage.errors import (
    AuthenticationError,
    RateLimitError,
    ServerError,
    TransportError,
)

from .conftest import API_KEY, BASE_URL, SECRET_KEY, VERIFICATION_ID, Harness

WORKSPACE = {"id": "ws", "name": "Shop"}


def test_the_signature_covers_exactly_the_bytes_sent(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(201, json={"id": "v"})
    sdk.call(lambda c: c._post("verifications", {"external_id": "Jürgen/1", "n": 1}))
    request = route.calls.last.request
    assert request.content == '{"external_id":"Jürgen/1","n":1}'.encode()
    expected = sign(
        SECRET_KEY, canonical_request("POST", "/v1/verifications", request.content.decode())
    )
    assert request.headers["X-HMAC-Signature"] == expected
    assert request.headers["X-API-Key"] == API_KEY
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Accept"] == "application/json"


def test_a_bodyless_request_sends_no_content_type(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").respond(200, json=WORKSPACE)
    sdk.call(lambda c: c._get("workspace"))
    request = route.calls.last.request
    assert request.content == b""
    assert "Content-Type" not in request.headers
    assert request.headers["X-HMAC-Signature"] == sign(SECRET_KEY, "GET/v1/workspace")


def test_a_query_is_sent_as_the_exact_string_signed(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/verifications").respond(200, json={"data": [], "next_cursor": None})
    query = {"status": "approved,declined", "limit": 5, "external_id": "user 1/ä", "cursor": None}
    sdk.call(lambda c: c._get("verifications", query))
    request = route.calls.last.request
    wire = "external_id=user%201%2F%C3%A4&limit=5&status=approved%2Cdeclined"
    assert request.url.query == wire.encode()
    canonical = f"GET/v1/verifications?{wire}"
    assert canonical_request("GET", "/v1/verifications", "", wire) == canonical
    expected = hmac.new(SECRET_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    assert request.headers["X-HMAC-Signature"] == expected


def test_a_delete_is_not_retried_on_5xx(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.delete("/webhook-subscriptions/s1").respond(503)
    with pytest.raises(ServerError):
        sdk.call(lambda c: c._delete("webhook-subscriptions/s1"), retry_delay=0)
    assert route.call_count == 1


def test_a_delete_is_retried_on_429(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.delete("/webhook-subscriptions/s1").mock(
        side_effect=[httpx.Response(429), httpx.Response(204)]
    )
    assert sdk.call(lambda c: c._delete("webhook-subscriptions/s1"), retry_delay=0) is None
    assert route.call_count == 2
    assert route.calls.last.request.headers["X-HMAC-Signature"] == sign(
        SECRET_KEY, "DELETE/v1/webhook-subscriptions/s1"
    )


def test_multipart_sends_the_strings_it_signed(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post(f"/verifications/{VERIFICATION_ID}/media").respond(200)
    fields = {
        "type": "document",
        "side": "front",
        "document": "passport",
        "device_info": {"os": "iOS"},
        "head_turn_step": 2,
        "fingerprint": None,
    }
    sdk.call(
        lambda c: c._post_multipart(
            f"verifications/{VERIFICATION_ID}/media",
            fields,
            filename="front.jpg",
            content=b"jpeg-bytes",
        )
    )
    request = route.calls.last.request
    body = request.content
    assert b'name="device_info"\r\n\r\n{"os":"iOS"}' in body
    assert b'name="head_turn_step"\r\n\r\n2' in body
    assert b'name="fingerprint"' not in body
    wire = {
        "type": "document",
        "side": "front",
        "document": "passport",
        "device_info": '{"os":"iOS"}',
        "head_turn_step": "2",
    }
    canonical = canonical_multipart_request(
        "POST", f"/v1/verifications/{VERIFICATION_ID}/media", wire, [b"jpeg-bytes"]
    )
    assert request.headers["X-HMAC-Signature"] == sign(SECRET_KEY, canonical)


def test_every_request_identifies_the_sdk(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").respond(200, json=WORKSPACE)
    sdk.call(lambda c: c._get("workspace"), sdk_tokens=["telegram-bot/1.2.0"])
    request = route.calls.last.request
    assert request.headers["X-ProofAge-Sdk"] == f"telegram-bot/1.2.0 python/{__version__}"
    assert request.headers["User-Agent"].startswith(f"ProofAge-Python/{__version__} (Python ")


def test_identification_is_sent_on_every_retry(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=WORKSPACE)]
    )
    sdk.call(lambda c: c._get("workspace"), retry_delay=0)
    assert route.call_count == 2
    for call in route.calls:
        assert call.request.headers["X-ProofAge-Sdk"] == f"python/{__version__}"


def test_get_retries_5xx_408_and_429(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").mock(
        side_effect=[httpx.Response(500), httpx.Response(408), httpx.Response(200, json=WORKSPACE)]
    )
    assert sdk.call(lambda c: c._get("workspace"), retry_delay=0.5) == WORKSPACE
    assert route.call_count == 3
    assert sdk.sleeps == [0.5, 1.0]


def test_get_gives_up_after_the_last_attempt(sdk: Harness, api: respx.MockRouter) -> None:
    api.get("/workspace").respond(503, json={"message": "down"})
    with pytest.raises(ServerError, match="down"):
        sdk.call(lambda c: c._get("workspace"), retry_delay=0)


def test_post_is_not_retried_on_5xx(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(502)
    with pytest.raises(ServerError):
        sdk.call(lambda c: c._post("verifications", {"external_id": "a"}), retry_delay=0)
    assert route.call_count == 1


def test_post_is_retried_when_the_connection_never_opened(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(201, json={"id": "v"})]
    )
    assert sdk.call(lambda c: c._post("verifications", {}), retry_delay=0) == {"id": "v"}
    assert route.call_count == 2


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("cut"), httpx.WriteError("broken")],
)
def test_post_is_not_retried_once_sending_began(
    sdk: Harness, api: respx.MockRouter, error: Exception
) -> None:
    route = api.post("/verifications").mock(side_effect=error)
    with pytest.raises(TransportError) as raised:
        sdk.call(lambda c: c._post("verifications", {}), retry_delay=0)
    assert route.call_count == 1
    assert raised.value.__cause__ is error


def test_post_is_retried_on_429_and_honours_retry_after(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(201, json={"id": "v"}),
        ]
    )
    sdk.call(lambda c: c._post("verifications", {}), retry_delay=0.1)
    assert route.call_count == 2
    assert sdk.sleeps == [2.0]


def test_rate_limit_after_the_last_attempt(sdk: Harness, api: respx.MockRouter) -> None:
    api.get("/workspace").respond(
        429, headers={"Retry-After": "7"}, json={"error": {"code": "RATE_LIMIT", "message": "Slow"}}
    )
    with pytest.raises(RateLimitError) as raised:
        sdk.call(lambda c: c._get("workspace"), retry_delay=0)
    assert raised.value.retry_after == 7.0
    assert raised.value.code == "RATE_LIMIT"


def test_a_401_is_not_retried(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/workspace").respond(401, json={"error": {"code": "INVALID_API_KEY"}})
    with pytest.raises(AuthenticationError):
        sdk.call(lambda c: c._get("workspace"), retry_delay=0)
    assert route.call_count == 1


def test_retry_after_parses_seconds_and_http_dates() -> None:
    assert parse_retry_after("3", now=0) == 3.0
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:10 GMT", now=1445412480) == 10.0
    assert parse_retry_after("soon", now=0) is None
    assert parse_retry_after(None, now=0) is None


def test_a_caller_owned_client_is_used_and_left_open(api: respx.MockRouter) -> None:
    api.get("/workspace").respond(200, json=WORKSPACE)
    owned = httpx.Client(headers={"User-Agent": "Corp-Proxy/3"})
    with ProofAge(
        api_key=API_KEY, secret_key=SECRET_KEY, base_url=BASE_URL, http_client=owned
    ) as client:
        client._get("workspace")
    assert not owned.is_closed
    assert api.calls.last.request.headers["User-Agent"] == "Corp-Proxy/3"
    owned.close()


def test_an_async_caller_owned_client_is_left_open(api: respx.MockRouter) -> None:
    import asyncio

    api.get("/workspace").respond(200, json=WORKSPACE)

    async def main() -> bool:
        owned = httpx.AsyncClient()
        async with AsyncProofAge(
            api_key=API_KEY, secret_key=SECRET_KEY, base_url=BASE_URL, http_client=owned
        ) as client:
            await client._get("workspace")
        closed = owned.is_closed
        await owned.aclose()
        return closed

    assert asyncio.run(main()) is False


def test_repr_hides_the_secret() -> None:
    client = ProofAge(api_key=API_KEY, secret_key=SECRET_KEY)
    assert SECRET_KEY not in repr(client)
    client.close()


def test_the_error_body_is_decoded(sdk: Harness, api: respx.MockRouter) -> None:
    api.get("/workspace").respond(
        200, text="<html>landing page</html>", headers={"Content-Type": "text/html"}
    )
    from proofage.errors import ProofAgeError

    with pytest.raises(ProofAgeError, match="base_url"):
        sdk.call(lambda c: c._get("workspace"))


def test_json_payload_order_is_preserved_in_the_signature(api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(201, json={})
    with ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url=BASE_URL) as client:
        client._post("verifications", {"b": 1, "a": 2})
    assert json.loads(route.calls.last.request.content) == {"b": 1, "a": 2}
    assert route.calls.last.request.content == b'{"b":1,"a":2}'


def test_a_retry_after_beyond_the_cap_is_not_waited_for(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.get("/workspace").respond(429, headers={"Retry-After": "3600"})
    with pytest.raises(RateLimitError) as raised:
        sdk.call(lambda c: c._get("workspace"))
    assert route.call_count == 1
    assert sdk.sleeps == []
    assert raised.value.retry_after == 3600.0


def test_the_secret_never_leaves_the_client(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(201, json={"id": "v"})
    sdk.call(lambda c: c._post("verifications", {"external_id": "a"}))
    request = route.calls.last.request
    assert SECRET_KEY.encode() not in request.content
    assert all(SECRET_KEY not in value for value in request.headers.values())
