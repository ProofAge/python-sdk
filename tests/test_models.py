from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from proofage.models import (
    AgeEstimation,
    ConsentInfo,
    CreatedVerification,
    VerificationDocument,
    VerificationStatus,
    WebhookEvent,
)

VERIFICATION: dict[str, Any] = {
    "id": "0192a3b4-c5d6-7e8f-9a0b-1c2d3e4f5a6b",
    "external_id": "candidate-42",
    "external_metadata": {"email": "a@example.com"},
    "redirect_url": None,
    "status": "approved",
    "reason": None,
    "duplicate_check": {
        "checked": True,
        "duplicate_count": 1,
        "duplicates": [
            {
                "verification_id": "x",
                "external_id": None,
                "similarity_score": 0.91,
                "verified_at": "2026-09-01T10:00:00+00:00",
            }
        ],
    },
    "erasure": None,
    "consent_accepted_at": "2026-09-28T12:00:00.000000Z",
    "created_at": "2026-09-28T11:59:00.000000Z",
    "updated_at": "2026-09-28T12:05:00.000000Z",
    "url": "https://idv.proofage.xyz/v/token",
}


def test_a_known_status_is_the_enum_member() -> None:
    model = CreatedVerification.model_validate(VERIFICATION)
    assert model.status is VerificationStatus.APPROVED
    assert model.status == "approved"


def test_an_unknown_status_arrives_as_a_string() -> None:
    model = CreatedVerification.model_validate({**VERIFICATION, "status": "quarantined"})
    assert model.status == "quarantined"
    assert not isinstance(model.status, VerificationStatus)


def test_unknown_fields_are_kept() -> None:
    model = CreatedVerification.model_validate({**VERIFICATION, "risk_score": 0.2})
    assert model.model_extra == {"risk_score": 0.2}


def test_timestamps_are_aware_datetimes() -> None:
    model = CreatedVerification.model_validate(VERIFICATION)
    assert model.created_at == datetime(2026, 9, 28, 11, 59, tzinfo=timezone.utc)
    assert model.duplicate_check.duplicates[0].similarity_score == 0.91


def test_model_dump_json_round_trips() -> None:
    model = CreatedVerification.model_validate(VERIFICATION)
    dumped = model.model_dump(mode="json")
    assert dumped["status"] == "approved"
    assert CreatedVerification.model_validate(dumped) == model


def test_date_of_birth_is_a_date() -> None:
    document = VerificationDocument.model_validate(
        {
            "document": {
                "fields": {
                    "first_name": "Ann",
                    "last_name": "Lee",
                    "date_of_birth": "1990-04-02",
                    "document_number": "X1",
                }
            },
            "media": [{"id": "m1", "type": "selfie", "url": None}],
            "meta": {"attempt_id": None},
        }
    )
    assert document.document.fields.date_of_birth == date(1990, 4, 2)


def test_estimation_without_gender() -> None:
    estimation = AgeEstimation.model_validate(
        {
            "verification_id": "v",
            "attempt_id": None,
            "age_threshold": {"minimum": 18, "passed": True, "confidence": 0.97},
            "gender": None,
        }
    )
    assert estimation.age_threshold.passed is True
    assert estimation.gender is None


def test_webhook_event_optional_blocks() -> None:
    event = WebhookEvent.model_validate(
        {
            "verification_id": "v",
            "status": "declined",
            "external_id": None,
            "external_metadata": None,
            "reason": "document.face.mismatch",
            "timestamp": "2026-09-02T09:00:00+00:00",
            "duplicate_detected": True,
            "duplicate_count": 1,
            "duplicate_of": {"verification_id": "w", "external_id": "u-1"},
        }
    )
    assert event.status is VerificationStatus.DECLINED
    assert event.duplicate_of is not None
    assert event.manual_moderation is None
    assert event.delivery_id is None


def test_a_number_where_a_string_is_documented_does_not_break_parsing() -> None:
    # The live API sends the consent version as an integer although the spec says string.
    consent = ConsentInfo.model_validate(
        {"id": 3, "version": 2, "text_sha256": "ab" * 32, "url": "https://x"}
    )
    assert consent.version == "2"


def test_enum_members_print_as_their_api_values() -> None:
    from proofage.models import BlockFaceReasonCode

    assert str(VerificationStatus.APPROVED) == "approved"
    assert f"{VerificationStatus.DECLINED}" == "declined"
    assert str(BlockFaceReasonCode.UNDERAGE) == "underage"
