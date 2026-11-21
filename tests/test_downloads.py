from __future__ import annotations

import asyncio
import email.utils
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import respx

from proofage import AsyncProofAge, ProofAge
from proofage._signing import sign
from proofage.errors import AuthenticationError, NotFoundError, RateLimitError, TransportError

from .conftest import API_KEY, NOW, SECRET_KEY, VERIFICATION_ID

VID = VERIFICATION_ID
KW = {"api_key": API_KEY, "secret_key": SECRET_KEY, "base_url": "https://api.test"}
MEDIA = f"/verifications/{VID}/media/m-1"


def test_sync_download_streams_the_bytes(api: respx.MockRouter) -> None:
    route = api.get(MEDIA).respond(
        200, content=b"\xff\xd8image", headers={"Content-Type": "image/jpeg"}
    )
    with ProofAge(**KW) as client, client.verifications.download_media(VID, "m-1") as chunks:
        data = b"".join(chunks)
    assert data == b"\xff\xd8image"
    assert route.calls.last.request.headers["Accept"] == "application/json, */*;q=0.8"


def test_async_download_streams_the_bytes(api: respx.MockRouter) -> None:
    api.get(MEDIA).respond(200, content=b"img")

    async def main() -> bytes:
        async with (
            AsyncProofAge(**KW) as client,
            client.verifications.download_media(VID, "m-1") as chunks,
        ):
            return b"".join([chunk async for chunk in chunks])

    assert asyncio.run(main()) == b"img"


def test_download_to_writes_only_after_success(tmp_path: Path, api: respx.MockRouter) -> None:
    api.get(MEDIA).respond(200, content=b"img")
    target = tmp_path / "selfie.jpg"
    with ProofAge(**KW) as client:
        assert client.verifications.download_media_to(VID, "m-1", target) == target
    assert target.read_bytes() == b"img"
    assert [p.name for p in tmp_path.iterdir()] == ["selfie.jpg"]


def test_a_404_leaves_no_file(tmp_path: Path, api: respx.MockRouter) -> None:
    api.get(MEDIA).respond(404, json={"error": {"code": "MEDIA_NOT_FOUND", "message": "Gone"}})
    target = tmp_path / "selfie.jpg"
    with ProofAge(**KW) as client, pytest.raises(NotFoundError) as raised:
        client.verifications.download_media_to(VID, "m-1", target)
    assert raised.value.code == "MEDIA_NOT_FOUND"
    assert list(tmp_path.iterdir()) == []


def test_async_download_to(tmp_path: Path, api: respx.MockRouter) -> None:
    api.get(MEDIA).respond(200, content=b"img")
    target = tmp_path / "doc.jpg"

    async def main() -> Path:
        async with AsyncProofAge(**KW) as client:
            return await client.verifications.download_media_to(VID, "m-1", target)

    assert asyncio.run(main()).read_bytes() == b"img"


def test_a_429_is_never_retried(api: respx.MockRouter) -> None:
    route = api.get(MEDIA).respond(429, headers={"Retry-After": "1"})
    with (
        ProofAge(**KW, download_retry_attempts=3) as client,
        pytest.raises(RateLimitError),
        client.verifications.download_media(VID, "m-1") as chunks,
    ):
        b"".join(chunks)
    assert route.call_count == 1


def test_a_transport_failure_is_retried_when_asked(api: respx.MockRouter) -> None:
    route = api.get(MEDIA).mock(
        side_effect=[httpx.ConnectError("x"), httpx.Response(200, content=b"ok")]
    )
    with (
        ProofAge(**KW, download_retry_attempts=2, retry_delay=0) as client,
        client.verifications.download_media(VID, "m-1") as chunks,
    ):
        assert b"".join(chunks) == b"ok"
    assert route.call_count == 2


def test_by_default_a_transport_failure_is_raised(api: respx.MockRouter) -> None:
    api.get(MEDIA).mock(side_effect=httpx.ConnectError("x"))
    with (
        ProofAge(**KW) as client,
        pytest.raises(TransportError),
        client.verifications.download_media(VID, "m-1"),
    ):
        pass


def test_a_malformed_media_id_is_refused(api: respx.MockRouter) -> None:
    with (
        ProofAge(**KW) as client,
        pytest.raises(ValueError, match="media_id"),
        client.verifications.download_media(VID, "../../workspace"),
    ):
        pass
    assert not api.calls


def _http_date(unix: float) -> str:
    return email.utils.format_datetime(datetime.fromtimestamp(unix, timezone.utc), usegmt=True)


OUT_OF_RANGE = {"error": {"code": "TIMESTAMP_OUT_OF_RANGE", "message": "Clock is off."}}


def _skewed_client_calls(api: respx.MockRouter, kind: str, responses: list[httpx.Response]):  # type: ignore[no-untyped-def]
    route = api.get(MEDIA).mock(side_effect=responses)

    def read_twice_sync() -> None:
        with ProofAge(**KW) as client:
            client._clock = lambda: float(NOW)
            for _ in range(2):
                with client.verifications.download_media(VID, "m-1") as chunks:
                    b"".join(chunks)

    async def read_twice_async() -> None:
        async with AsyncProofAge(**KW) as client:
            client._clock = lambda: float(NOW)
            for _ in range(2):
                async with client.verifications.download_media(VID, "m-1") as chunks:
                    b"".join([chunk async for chunk in chunks])

    if kind == "sync":
        read_twice_sync()
    else:
        asyncio.run(read_twice_async())
    return route


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_download_learns_clock_skew_resends_once_and_reuses_the_offset(
    api: respx.MockRouter, kind: str
) -> None:
    skewed = httpx.Response(401, headers={"Date": _http_date(NOW + 400)}, json=OUT_OF_RANGE)
    route = _skewed_client_calls(
        api, kind, [skewed, httpx.Response(200, content=b"a"), httpx.Response(200, content=b"b")]
    )
    first, second, third = (call.request for call in route.calls)
    assert first.headers["X-Timestamp"] == str(NOW)
    assert second.headers["X-Timestamp"] == str(NOW + 400)
    assert third.headers["X-Timestamp"] == str(NOW + 400)
    assert second.headers["X-HMAC-Signature"] == sign(SECRET_KEY, f"{NOW + 400}.GET/v1{MEDIA}")


@pytest.mark.parametrize("kind", ["sync", "async"])
def test_download_raises_when_the_skew_resend_fails_too(api: respx.MockRouter, kind: str) -> None:
    skewed = httpx.Response(401, headers={"Date": _http_date(NOW + 400)}, json=OUT_OF_RANGE)
    with pytest.raises(AuthenticationError) as raised:
        _skewed_client_calls(api, kind, [skewed, skewed])
    assert raised.value.code == "TIMESTAMP_OUT_OF_RANGE"
    assert len(api.calls) == 2
