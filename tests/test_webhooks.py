from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from proofage import WebhookVerificationError, verify_webhook, verify_webhook_signature
from proofage._signing import webhook_signature
from proofage.models import DocumentResultType, VerificationStatus, WebhookEventType

from .conftest import API_KEY, SECRET_KEY

VECTORS: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "hmac-vectors.json").read_text(encoding="utf-8")
)
NOW = 1_756_800_000
BODY = (
    b'{"verification_id":"v-1","status":"approved","external_id":"u-1",'
    b'"external_metadata":null,"reason":null,"timestamp":"2026-09-02T09:00:00+00:00"}'
)


def headers(body: bytes = BODY, timestamp: int = NOW, **overrides: str) -> dict[str, str]:
    values = {
        "X-HMAC-Signature": webhook_signature(SECRET_KEY, timestamp, body),
        "X-Timestamp": str(timestamp),
        "X-Auth-Client": API_KEY,
        "X-ProofAge-Webhook-Delivery-Id": "d-1",
    }
    values.update(overrides)
    return values


def verify(body: bytes = BODY, hdrs: dict[str, str] | None = None, **kwargs: Any) -> Any:
    return verify_webhook(
        body,
        hdrs if hdrs is not None else headers(body),
        api_key=API_KEY,
        secret_key=SECRET_KEY,
        now=NOW,
        **kwargs,
    )


def test_a_valid_webhook_becomes_an_event() -> None:
    event = verify()
    assert event.verification_id == "v-1"
    assert event.status is VerificationStatus.APPROVED
    assert event.delivery_id == "d-1"


def _signed(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


_BASE = {
    "verification_id": "v-1",
    "status": "approved",
    "external_id": "u-1",
    "external_metadata": None,
    "reason": None,
    "timestamp": "2026-09-02T09:00:00+00:00",
}


def test_a_kyc_webhook_carries_a_typed_document() -> None:
    body = _signed(
        {
            **_BASE,
            "document": {
                "type": "passport",
                "issuing_country": "US",
                "issuing_subdivision": "FL",
                "fields": {
                    "first_name": "ÉLODIE",
                    "middle_name": None,
                    "last_name": "DOE",
                    "date_of_birth": "1990-04-12",
                    "gender": "F",
                    "nationality": None,
                    "place_of_birth": "BERLIN",
                    "address": "1 Main St\n10115 BERLIN",
                    "document_number": "X1234567",
                    "issue_date": None,
                    "expiry_date": "2030-04-30",
                },
            },
        }
    )
    document = verify(body).document
    assert document is not None
    assert document.type is DocumentResultType.PASSPORT
    assert document.issuing_subdivision == "FL"
    assert document.fields.first_name == "ÉLODIE"
    assert document.fields.address == "1 Main St\n10115 BERLIN"
    assert document.fields.expiry_date == date(2030, 4, 30)


def test_an_age_webhook_and_an_unknown_type_parse() -> None:
    body = _signed(
        {
            **_BASE,
            "document": {
                "type": "health_card",
                "issuing_country": None,
                "fields": {
                    "first_name": None,
                    "last_name": None,
                    "date_of_birth": None,
                    "document_number": None,
                },
            },
        }
    )
    document = verify(body).document
    assert document is not None
    assert document.type == "health_card"
    assert document.fields.gender is None and document.fields.address is None


def test_a_webhook_without_a_document_has_none() -> None:
    assert verify().document is None


def test_headers_are_case_insensitive() -> None:
    lowered = {k.lower(): v for k, v in headers().items()}
    assert verify(hdrs=lowered).external_id == "u-1"


def test_a_str_body_is_accepted() -> None:
    event = verify_webhook(
        BODY.decode(), headers(), api_key=API_KEY, secret_key=SECRET_KEY, now=NOW
    )
    assert event.verification_id == "v-1"


@pytest.mark.parametrize(
    ("missing", "code"),
    [
        ("X-HMAC-Signature", "MISSING_SIGNATURE"),
        ("X-Timestamp", "MISSING_TIMESTAMP"),
        ("X-Auth-Client", "MISSING_AUTH_CLIENT"),
    ],
)
def test_missing_headers(missing: str, code: str) -> None:
    hdrs = headers()
    del hdrs[missing]
    with pytest.raises(WebhookVerificationError) as raised:
        verify(hdrs=hdrs)
    assert raised.value.code == code


def test_configuration_is_checked_after_the_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    hdrs = headers()
    del hdrs["X-HMAC-Signature"]
    with pytest.raises(WebhookVerificationError) as raised:
        verify_webhook(BODY, hdrs, now=NOW)
    assert raised.value.code == "MISSING_SIGNATURE"
    with pytest.raises(WebhookVerificationError) as raised:
        verify_webhook(BODY, headers(), now=NOW)
    assert raised.value.code == "CONFIGURATION_ERROR"
    assert raised.value.http_status == 500


def test_keys_fall_back_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFAGE_API_KEY", API_KEY)
    monkeypatch.setenv("PROOFAGE_SECRET_KEY", SECRET_KEY)
    assert verify_webhook(BODY, headers(), now=NOW).verification_id == "v-1"


def test_the_auth_client_must_be_this_workspace() -> None:
    with pytest.raises(WebhookVerificationError) as raised:
        verify(hdrs=headers(**{"X-Auth-Client": "pk_other"}))
    assert raised.value.code == "INVALID_AUTH_CLIENT"


def test_a_non_integer_timestamp() -> None:
    with pytest.raises(WebhookVerificationError) as raised:
        verify(hdrs=headers(**{"X-Timestamp": "yesterday"}))
    assert raised.value.code == "MISSING_TIMESTAMP"


@pytest.mark.parametrize(("skew", "ok"), [(300, True), (-300, True), (301, False), (-301, False)])
def test_tolerance_in_both_directions(skew: int, ok: bool) -> None:
    timestamp = NOW + skew
    hdrs = headers(timestamp=timestamp)
    if ok:
        assert verify(hdrs=hdrs).verification_id == "v-1"
    else:
        with pytest.raises(WebhookVerificationError) as raised:
            verify(hdrs=hdrs)
        assert raised.value.code == "TIMESTAMP_TOO_OLD"


def test_tolerance_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFAGE_WEBHOOK_TOLERANCE", "10")
    with pytest.raises(WebhookVerificationError):
        verify(hdrs=headers(timestamp=NOW - 11))


def test_a_tampered_body() -> None:
    with pytest.raises(WebhookVerificationError) as raised:
        verify(BODY.replace(b"approved", b"declined"), headers())
    assert raised.value.code == "INVALID_SIGNATURE"


def test_a_re_serialised_body_is_explained() -> None:
    # PHP escapes slashes; a framework's json.loads/json.dumps round trip loses that, and
    # neither the raw nor the canonical comparison can recover the bytes that were signed.
    raw = (
        b'{"verification_id":"v-1","status":"approved","external_id":null,'
        b'"external_metadata":{"site":"https:\\/\\/shop.example"},"reason":null,'
        b'"timestamp":"2026-09-02T09:00:00+00:00"}'
    )
    reencoded = json.dumps(json.loads(raw)).encode()
    with pytest.raises(WebhookVerificationError, match="raw request body") as raised:
        verify(reencoded, headers(raw))
    assert raised.value.code == "INVALID_SIGNATURE"


def test_the_canonical_re_encoding_vector_is_accepted() -> None:
    vector = VECTORS["webhook"][2]
    secret = VECTORS["secret"]
    payload = json.loads(vector["payload"])
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    hdrs = {
        "X-HMAC-Signature": vector["expected_canonical"],
        "X-Timestamp": str(vector["timestamp"]),
        "X-Auth-Client": API_KEY,
    }
    verify_webhook_signature(
        vector["payload"].encode(),
        hdrs,
        api_key=API_KEY,
        secret_key=secret,
        now=vector["timestamp"],
    )
    assert webhook_signature(secret, vector["timestamp"], canonical) == vector["expected_canonical"]


def test_a_signed_body_that_is_not_an_event() -> None:
    body = b'{"hello":"world"}'
    with pytest.raises(WebhookVerificationError) as raised:
        verify(body, headers(body))
    assert raised.value.code == "INVALID_PAYLOAD"
    assert raised.value.http_status == 400


def test_an_invalid_payload_error_does_not_echo_the_body() -> None:
    body = b'{"hello":"a.person@example.com"}'
    with pytest.raises(WebhookVerificationError) as raised:
        verify(body, headers(body))
    assert raised.value.code == "INVALID_PAYLOAD"
    assert "a.person@example.com" not in raised.value.message
    assert "verification_id" in raised.value.message


def test_a_data_updated_webhook_keeps_the_status_and_names_the_changed_fields() -> None:
    body = _signed(
        {
            **_BASE,
            "event": "data.updated",
            "document": {
                "type": "id",
                "issuing_country": "FR",
                "issuing_subdivision": None,
                "fields": {
                    "first_name": "JEAN",
                    "last_name": "MARTIN",
                    "date_of_birth": "1988-02-11",
                    "document_number": "X1",
                },
            },
            "changed_fields": ["date_of_birth"],
        }
    )
    event = verify(body)
    assert event.event is WebhookEventType.DATA_UPDATED
    assert event.status is VerificationStatus.APPROVED
    assert event.changed_fields == ["date_of_birth"]
    assert event.document is not None
    assert event.document.fields.date_of_birth == date(1988, 2, 11)


def test_a_body_without_event_is_a_status_update_and_an_unknown_event_stays_a_string() -> None:
    event = verify()
    assert event.event is None
    assert event.changed_fields is None
    assert verify(_signed({**_BASE, "event": "something.new"})).event == "something.new"
    assert (
        verify(_signed({**_BASE, "event": "status.updated"})).event
        is WebhookEventType.STATUS_UPDATED
    )
