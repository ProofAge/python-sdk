"""Response models. Lenient on purpose: unknown fields are kept and unknown enum
values arrive as plain strings, so an additive API change never breaks parsing."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class ProofAgeModel(BaseModel):
    """Base of every response model; extra fields land in `model_extra`."""

    model_config = ConfigDict(extra="allow")


class VerificationStatus(str, Enum):
    """The documented statuses. `documents_required` comes from the latest attempt."""

    CREATED = "created"
    STARTED = "started"
    SUBMITTED = "submitted"
    RESUBMISSION_REQUESTED = "resubmission_requested"
    APPROVED = "approved"
    DECLINED = "declined"
    ABANDONED = "abandoned"
    EXPIRED = "expired"
    REVIEW = "review"
    DOCUMENTS_REQUIRED = "documents_required"


class BlockFaceReasonCode(str, Enum):
    """Why a face is blocked; send one whenever a person made the decision."""

    PRESENTATION_ATTACK = "presentation_attack"
    FRAUDULENT_DOCUMENT = "fraudulent_document"
    SCAM_OR_ABUSE = "scam_or_abuse"
    UNDERAGE = "underage"
    OTHER = "other"


Status = Annotated[VerificationStatus | str, Field(union_mode="left_to_right")]
"""A known status as the enum member, an unknown one as the raw string."""


class WorkspaceInfo(ProofAgeModel):
    id: str
    name: str
    flow_type: str
    mode: str
    age_mode: str | None
    age_threshold: int | None
    verification_type: str
    redirect_url: str | None
    webhook_url: str | None
    allow_expired_documents: bool
    allow_duplicate_accounts: bool


class ConsentInfo(ProofAgeModel):
    id: int
    version: str
    text_sha256: str
    url: str


class DuplicateMatch(ProofAgeModel):
    verification_id: str
    external_id: str | None
    similarity_score: float
    verified_at: datetime | None


class DuplicateCheck(ProofAgeModel):
    checked: bool
    duplicate_count: int
    duplicates: list[DuplicateMatch]


class Erasure(ProofAgeModel):
    erased_at: datetime
    scope: str
    reason: str | None
    requested_via: str | None


class Verification(ProofAgeModel):
    id: str
    external_id: str | None
    external_metadata: dict[str, Any] | None
    redirect_url: str | None
    status: Status
    reason: str | None
    duplicate_check: DuplicateCheck
    erasure: Erasure | None
    consent_accepted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreatedVerification(Verification):
    url: str
    """The hosted session the person opens."""


class AcceptConsentResult(ProofAgeModel):
    consent_version_id: int
    consent_accepted_at: datetime


class DocumentFields(ProofAgeModel):
    first_name: str | None
    last_name: str | None
    date_of_birth: date | None
    document_number: str | None


class Document(ProofAgeModel):
    fields: DocumentFields


class MediaItem(ProofAgeModel):
    id: str
    type: str
    url: str | None
    """Null once the media is purged or past retention."""


class DocumentMeta(ProofAgeModel):
    attempt_id: str | None


class VerificationDocument(ProofAgeModel):
    document: Document
    media: list[MediaItem]
    meta: DocumentMeta


class AgeThreshold(ProofAgeModel):
    minimum: int | None
    passed: bool | None
    confidence: float | None


class Gender(ProofAgeModel):
    value: int | None
    """0 female, 1 male."""
    confidence: float | None


class AgeEstimation(ProofAgeModel):
    verification_id: str
    attempt_id: str | None
    age_threshold: AgeThreshold
    gender: Gender | None


class PerformedBy(ProofAgeModel):
    id: int
    name: str | None
    email: str | None
    role: str | None


class ManualModeration(ProofAgeModel):
    action: str
    reason: str
    source: str
    performed_by: PerformedBy
    source_status: str | None = None
    source_reason: str | None = None


class DuplicateOf(ProofAgeModel):
    verification_id: str
    external_id: str | None


class WebhookEvent(ProofAgeModel):
    """A verified webhook. `delivery_id` comes from `X-ProofAge-Webhook-Delivery-Id`:
    the same on every automatic retry of one delivery, so de-duplicate on it."""

    verification_id: str
    status: Status
    external_id: str | None
    external_metadata: dict[str, Any] | None
    reason: str | None
    timestamp: datetime
    duplicate_detected: bool = False
    duplicate_count: int | None = None
    duplicate_of: DuplicateOf | None = None
    fingerprint_signals: dict[str, Any] | None = None
    manual_moderation: ManualModeration | None = None
    delivery_id: str | None = None
