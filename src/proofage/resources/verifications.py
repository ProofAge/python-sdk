"""The `/verifications` endpoints."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, BinaryIO

from ..models import (
    AcceptConsentResult,
    AgeEstimation,
    BlockFaceReasonCode,
    CreatedVerification,
    Verification,
    VerificationDocument,
)
from ._payloads import compact, read_upload, upload_fields, verification_path

if TYPE_CHECKING:
    from .._async_client import AsyncProofAge
    from .._client import ProofAge


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
        return CreatedVerification.model_validate(self._client._post("verifications", payload))

    def get(self, verification_id: str) -> Verification:
        """`GET /verifications/{id}`."""
        return Verification.model_validate(self._client._get(verification_path(verification_id)))

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
        data = self._client._post(verification_path(verification_id, "/consent"), payload)
        return AcceptConsentResult.model_validate(data)

    def submit(self, verification_id: str) -> None:
        """`POST /verifications/{id}/submit`. Custom capture flows only."""
        self._client._post_empty(verification_path(verification_id, "/submit"))

    def document(self, verification_id: str) -> VerificationDocument:
        """`GET /verifications/{id}/document`: extracted fields and media ids."""
        data = self._client._get(verification_path(verification_id, "/document"))
        return VerificationDocument.model_validate(data)

    def estimation(self, verification_id: str) -> AgeEstimation:
        """`GET /verifications/{id}/estimation`."""
        data = self._client._get(verification_path(verification_id, "/estimation"))
        return AgeEstimation.model_validate(data)

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
        data = await self._client._post("verifications", payload)
        return CreatedVerification.model_validate(data)

    async def get(self, verification_id: str) -> Verification:
        """`GET /verifications/{id}`."""
        data = await self._client._get(verification_path(verification_id))
        return Verification.model_validate(data)

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
        data = await self._client._post(verification_path(verification_id, "/consent"), payload)
        return AcceptConsentResult.model_validate(data)

    async def submit(self, verification_id: str) -> None:
        """`POST /verifications/{id}/submit`. Custom capture flows only."""
        await self._client._post_empty(verification_path(verification_id, "/submit"))

    async def document(self, verification_id: str) -> VerificationDocument:
        """`GET /verifications/{id}/document`: extracted fields and media ids."""
        data = await self._client._get(verification_path(verification_id, "/document"))
        return VerificationDocument.model_validate(data)

    async def estimation(self, verification_id: str) -> AgeEstimation:
        """`GET /verifications/{id}/estimation`."""
        data = await self._client._get(verification_path(verification_id, "/estimation"))
        return AgeEstimation.model_validate(data)

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
