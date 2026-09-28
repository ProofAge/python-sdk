"""The `/verifications` endpoints."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

import httpx

from ..errors import TransportError
from ..models import (
    AcceptConsentResult,
    AgeEstimation,
    BlockFaceReasonCode,
    CreatedVerification,
    Verification,
    VerificationDocument,
)
from ._payloads import compact, path_segment, read_upload, upload_fields, verification_path

if TYPE_CHECKING:
    from .._async_client import AsyncProofAge
    from .._client import ProofAge


def _media_path(verification_id: str, media_id: str) -> str:
    return verification_path(verification_id, f"/media/{path_segment(media_id, 'media_id')}")


def _temporary_sibling(target: Path) -> tuple[int, str]:
    return tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".part")


class Verifications:
    """Verification sessions: create one, read its outcome, act on it."""

    def __init__(self, client: ProofAge) -> None:
        self._client = client

    def create(
        self,
        *,
        callback_url: str | None = None,
        external_id: str | None = None,
        external_metadata: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        fingerprint: str | None = None,
        page_url: str | None = None,
    ) -> CreatedVerification:
        """`POST /verifications`. Send the person to the returned `url`."""
        payload = compact(
            {
                "callback_url": callback_url,
                "external_id": external_id,
                "external_metadata": external_metadata,
                "metadata": metadata,
                "fingerprint": fingerprint,
                "page_url": page_url,
            }
        )
        return self._client._post_model("verifications", payload, CreatedVerification)

    def get(self, verification_id: str) -> Verification:
        """`GET /verifications/{id}`."""
        return self._client._get_model(verification_path(verification_id), Verification)

    def accept_consent(
        self,
        verification_id: str,
        *,
        consent_version_id: int,
        text_sha256: str,
        device: dict[str, Any] | None = None,
        in_app_browser: str | None = None,
        camera_permission: str | None = None,
        camera_policy_allowed: bool | None = None,
        in_iframe: bool | None = None,
        referrer: str | None = None,
    ) -> AcceptConsentResult:
        """`POST /verifications/{id}/consent`. Custom capture flows only."""
        payload = compact(
            {
                "consent_version_id": consent_version_id,
                "text_sha256": text_sha256,
                "device": device,
                "in_app_browser": in_app_browser,
                "camera_permission": camera_permission,
                "camera_policy_allowed": camera_policy_allowed,
                "in_iframe": in_iframe,
                "referrer": referrer,
            }
        )
        return self._client._post_model(
            verification_path(verification_id, "/consent"), payload, AcceptConsentResult
        )

    def submit(self, verification_id: str) -> None:
        """`POST /verifications/{id}/submit`. Custom capture flows only."""
        self._client._post_empty(verification_path(verification_id, "/submit"))

    def document(self, verification_id: str) -> VerificationDocument:
        """`GET /verifications/{id}/document`: extracted fields and media ids."""
        return self._client._get_model(
            verification_path(verification_id, "/document"), VerificationDocument
        )

    def estimation(self, verification_id: str) -> AgeEstimation:
        """`GET /verifications/{id}/estimation`."""
        return self._client._get_model(
            verification_path(verification_id, "/estimation"), AgeEstimation
        )

    def block_face(
        self,
        verification_id: str,
        *,
        reason_code: BlockFaceReasonCode | str | None = None,
        reason: str | None = None,
    ) -> None:
        """`POST /verifications/{id}/blocked-face`. Irreversible for the person."""
        payload = compact({"reason_code": reason_code, "reason": reason})
        self._client._post_empty(verification_path(verification_id, "/blocked-face"), payload)

    def upload_media(
        self,
        verification_id: str,
        *,
        file: bytes | bytearray | os.PathLike[str] | BinaryIO,
        type: str,
        side: str | None = None,
        document: str | None = None,
        filename: str | None = None,
        fingerprint: str | None = None,
        head_turn_step: int | None = None,
        capture_resolution: str | dict[str, Any] | None = None,
        device_info: str | dict[str, Any] | None = None,
        liveness_telemetry: str | list[Any] | None = None,
    ) -> None:
        """`POST /verifications/{id}/media` (multipart). Custom capture flows only."""
        fields = upload_fields(
            type=type,
            side=side,
            document=document,
            fingerprint=fingerprint,
            head_turn_step=head_turn_step,
            capture_resolution=capture_resolution,
            device_info=device_info,
            liveness_telemetry=liveness_telemetry,
        )
        content, name = read_upload(file, filename)
        self._client._post_multipart(
            verification_path(verification_id, "/media"), fields, filename=name, content=content
        )

    @contextmanager
    def download_media(self, verification_id: str, media_id: str) -> Iterator[Iterator[bytes]]:
        """`GET /verifications/{id}/media/{media}` as a byte stream.

        Take `media_id` from `document().media`; a media whose `url` is None is gone.
        An HTTP status is never retried (a queue's backoff should own that wait); a
        transport failure is retried `download_retry_attempts` times, before the first byte.
        """
        with self._client._stream_media(_media_path(verification_id, media_id)) as response:

            def chunks() -> Iterator[bytes]:
                try:
                    yield from response.iter_bytes()
                except httpx.TransportError as exc:
                    raise TransportError(f"Download interrupted: {exc}") from exc

            yield chunks()

    def download_media_to(
        self, verification_id: str, media_id: str, path: str | os.PathLike[str]
    ) -> Path:
        """Stream a media file to `path`; a failure never leaves a partial file there."""
        target = Path(path)
        with self.download_media(verification_id, media_id) as chunks:
            descriptor, temporary = _temporary_sibling(target)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    for chunk in chunks:
                        handle.write(chunk)
                os.replace(temporary, target)
            except BaseException:
                with suppress(FileNotFoundError):
                    os.unlink(temporary)
                raise
        return target


class AsyncVerifications:
    """Verification sessions: create one, read its outcome, act on it."""

    def __init__(self, client: AsyncProofAge) -> None:
        self._client = client

    async def create(
        self,
        *,
        callback_url: str | None = None,
        external_id: str | None = None,
        external_metadata: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        fingerprint: str | None = None,
        page_url: str | None = None,
    ) -> CreatedVerification:
        """`POST /verifications`. Send the person to the returned `url`."""
        payload = compact(
            {
                "callback_url": callback_url,
                "external_id": external_id,
                "external_metadata": external_metadata,
                "metadata": metadata,
                "fingerprint": fingerprint,
                "page_url": page_url,
            }
        )
        return await self._client._post_model("verifications", payload, CreatedVerification)

    async def get(self, verification_id: str) -> Verification:
        """`GET /verifications/{id}`."""
        return await self._client._get_model(verification_path(verification_id), Verification)

    async def accept_consent(
        self,
        verification_id: str,
        *,
        consent_version_id: int,
        text_sha256: str,
        device: dict[str, Any] | None = None,
        in_app_browser: str | None = None,
        camera_permission: str | None = None,
        camera_policy_allowed: bool | None = None,
        in_iframe: bool | None = None,
        referrer: str | None = None,
    ) -> AcceptConsentResult:
        """`POST /verifications/{id}/consent`. Custom capture flows only."""
        payload = compact(
            {
                "consent_version_id": consent_version_id,
                "text_sha256": text_sha256,
                "device": device,
                "in_app_browser": in_app_browser,
                "camera_permission": camera_permission,
                "camera_policy_allowed": camera_policy_allowed,
                "in_iframe": in_iframe,
                "referrer": referrer,
            }
        )
        return await self._client._post_model(
            verification_path(verification_id, "/consent"), payload, AcceptConsentResult
        )

    async def submit(self, verification_id: str) -> None:
        """`POST /verifications/{id}/submit`. Custom capture flows only."""
        await self._client._post_empty(verification_path(verification_id, "/submit"))

    async def document(self, verification_id: str) -> VerificationDocument:
        """`GET /verifications/{id}/document`: extracted fields and media ids."""
        return await self._client._get_model(
            verification_path(verification_id, "/document"), VerificationDocument
        )

    async def estimation(self, verification_id: str) -> AgeEstimation:
        """`GET /verifications/{id}/estimation`."""
        return await self._client._get_model(
            verification_path(verification_id, "/estimation"), AgeEstimation
        )

    async def block_face(
        self,
        verification_id: str,
        *,
        reason_code: BlockFaceReasonCode | str | None = None,
        reason: str | None = None,
    ) -> None:
        """`POST /verifications/{id}/blocked-face`. Irreversible for the person."""
        payload = compact({"reason_code": reason_code, "reason": reason})
        await self._client._post_empty(verification_path(verification_id, "/blocked-face"), payload)

    async def upload_media(
        self,
        verification_id: str,
        *,
        file: bytes | bytearray | os.PathLike[str] | BinaryIO,
        type: str,
        side: str | None = None,
        document: str | None = None,
        filename: str | None = None,
        fingerprint: str | None = None,
        head_turn_step: int | None = None,
        capture_resolution: str | dict[str, Any] | None = None,
        device_info: str | dict[str, Any] | None = None,
        liveness_telemetry: str | list[Any] | None = None,
    ) -> None:
        """`POST /verifications/{id}/media` (multipart). Custom capture flows only.

        The file is read before the request, in the calling thread.
        """
        fields = upload_fields(
            type=type,
            side=side,
            document=document,
            fingerprint=fingerprint,
            head_turn_step=head_turn_step,
            capture_resolution=capture_resolution,
            device_info=device_info,
            liveness_telemetry=liveness_telemetry,
        )
        content, name = read_upload(file, filename)
        await self._client._post_multipart(
            verification_path(verification_id, "/media"), fields, filename=name, content=content
        )

    @asynccontextmanager
    async def download_media(
        self, verification_id: str, media_id: str
    ) -> AsyncIterator[AsyncIterator[bytes]]:
        """`GET /verifications/{id}/media/{media}` as an async byte stream (see the sync twin)."""
        async with self._client._stream_media(_media_path(verification_id, media_id)) as response:

            async def chunks() -> AsyncIterator[bytes]:
                try:
                    async for chunk in response.aiter_bytes():
                        yield chunk
                except httpx.TransportError as exc:
                    raise TransportError(f"Download interrupted: {exc}") from exc

            yield chunks()

    async def download_media_to(
        self, verification_id: str, media_id: str, path: str | os.PathLike[str]
    ) -> Path:
        """Stream a media file to `path`; a failure never leaves a partial file there."""
        target = Path(path)
        async with self.download_media(verification_id, media_id) as chunks:
            descriptor, temporary = _temporary_sibling(target)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    async for chunk in chunks:
                        handle.write(chunk)
                os.replace(temporary, target)
            except BaseException:
                with suppress(FileNotFoundError):
                    os.unlink(temporary)
                raise
        return target
