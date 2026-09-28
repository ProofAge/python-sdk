from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import respx

from proofage import AsyncProofAge, ProofAge
from proofage.errors import NotFoundError, RateLimitError, TransportError

from .conftest import API_KEY, SECRET_KEY, VERIFICATION_ID

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
