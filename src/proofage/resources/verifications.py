"""The `/verifications` endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import (
    AcceptConsentResult,
    AgeEstimation,
    BlockFaceReasonCode,
    CreatedVerification,
    Verification,
    VerificationDocument,
)
from ._payloads import compact, verification_path

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
