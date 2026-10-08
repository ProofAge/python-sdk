from __future__ import annotations

import hashlib
import hmac
import json
import re
import warnings
from datetime import date
from typing import Any

import httpx
import pytest
import respx

from proofage import ProofAge
from proofage.errors import PermissionDeniedError, ServerError, ValidationError
from proofage.models import (
    AcceptConsentResult,
    AgeEstimation,
    BlockFaceReasonCode,
    CreatedVerification,
    DocumentGender,
    DocumentResultType,
    Verification,
    VerificationDocument,
    VerificationList,
    VerificationOutcome,
    VerificationStatus,
)

from .conftest import API_KEY, SECRET_KEY, VERIFICATION_ID, Harness
from .test_models import VERIFICATION

VID = VERIFICATION_ID


def sign_raw(canonical: str) -> str:
    """The signature computed here, independently of the SDK's signing module."""
    return hmac.new(SECRET_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def body(route: respx.Route) -> Any:
    return json.loads(route.calls.last.request.content)


def test_create_sends_only_what_was_given(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(201, json=VERIFICATION)
    created = sdk.call(
        lambda c: c.verifications.create(
            external_id="candidate-42", external_metadata={"email": "a@example.com"}
        )
    )
    assert isinstance(created, CreatedVerification)
    assert created.url.endswith("/v/token")
    assert body(route) == {
        "external_id": "candidate-42",
        "external_metadata": {"email": "a@example.com"},
    }


def test_create_with_nothing_sends_no_body(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post("/verifications").respond(201, json=VERIFICATION)
    sdk.call(lambda c: c.verifications.create())
    assert route.calls.last.request.content == b""


def test_get(sdk: Harness, api: respx.MockRouter) -> None:
    payload = {k: v for k, v in VERIFICATION.items() if k != "url"}
    api.get(f"/verifications/{VID}").respond(200, json=payload)
    verification = sdk.call(lambda c: c.verifications.get(VID))
    assert type(verification) is Verification
    assert verification.external_id == "candidate-42"


def test_accept_consent(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post(f"/verifications/{VID}/consent").respond(
        200, json={"consent_version_id": 3, "consent_accepted_at": "2026-09-28T12:00:00Z"}
    )
    with pytest.warns(DeprecationWarning, match="camera_permission, in_iframe"):
        result = sdk.call(
            lambda c: c.verifications.accept_consent(
                VID,
                consent_version_id=3,
                text_sha256="ab" * 32,
                camera_permission="granted",
                in_iframe=False,
            )
        )
    assert isinstance(result, AcceptConsentResult)
    assert body(route) == {
        "consent_version_id": 3,
        "text_sha256": "ab" * 32,
        "camera_permission": "granted",
        "in_iframe": False,
    }


def test_submit_returns_none(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post(f"/verifications/{VID}/submit").respond(200)
    assert sdk.call(lambda c: c.verifications.submit(VID)) is None
    assert route.calls.last.request.content == b""


def test_document(sdk: Harness, api: respx.MockRouter) -> None:
    api.get(f"/verifications/{VID}/document").respond(
        200,
        json={
            "document": {
                "fields": {
                    "first_name": None,
                    "last_name": None,
                    "date_of_birth": None,
                    "document_number": None,
                }
            },
            "media": [],
            "meta": {"attempt_id": "a1"},
        },
    )
    document = sdk.call(lambda c: c.verifications.document(VID))
    assert isinstance(document, VerificationDocument)
    assert document.meta.attempt_id == "a1"


def test_document_kyc_body_parses_all_eleven_fields(sdk: Harness, api: respx.MockRouter) -> None:
    api.get(f"/verifications/{VID}/document").respond(
        200,
        json={
            "document": {
                "type": "passport",
                "issuing_country": "DE",
                "issuing_subdivision": None,
                "fields": {
                    "first_name": "JANE",
                    "middle_name": None,
                    "last_name": "DOE",
                    "date_of_birth": "1990-04-12",
                    "gender": "F",
                    "nationality": "DE",
                    "place_of_birth": "BERLIN",
                    "address": "Rua das Flores 12\n1000-001 LISBOA",
                    "document_number": "X1234567",
                    "issue_date": "2020-04-14",
                    "expiry_date": "2030-04-30",
                },
            },
            "media": [],
            "meta": {"attempt_id": "a1"},
        },
    )
    document = sdk.call(lambda c: c.verifications.document(VID))
    assert document.document.type is DocumentResultType.PASSPORT
    assert document.document.issuing_country == "DE"
    assert document.document.issuing_subdivision is None
    assert document.document.fields.gender is DocumentGender.F
    assert document.document.fields.expiry_date == date(2030, 4, 30)
    assert document.document.fields.middle_name is None
    assert document.document.fields.address == "Rua das Flores 12\n1000-001 LISBOA"


def test_document_age_body_leaves_the_kyc_only_keys_unset(
    sdk: Harness, api: respx.MockRouter
) -> None:
    api.get(f"/verifications/{VID}/document").respond(
        200,
        json={
            "document": {
                "type": "driver_license",
                "issuing_country": "US",
                "issuing_subdivision": "CA",
                "fields": {
                    "first_name": "JEAN",
                    "last_name": "MARTIN",
                    "date_of_birth": None,
                    "document_number": "X4RTBPFW4",
                },
            },
            "media": [],
            "meta": {"attempt_id": None},
        },
    )
    document = sdk.call(lambda c: c.verifications.document(VID))
    assert document.document.issuing_subdivision == "CA"
    fields = document.document.fields
    assert fields.date_of_birth is None
    assert fields.gender is None and fields.expiry_date is None and fields.nationality is None
    assert fields.address is None


def test_document_unknown_type_and_gender_arrive_as_strings(
    sdk: Harness, api: respx.MockRouter
) -> None:
    api.get(f"/verifications/{VID}/document").respond(
        200,
        json={
            "document": {
                "type": "health_card",
                "issuing_country": None,
                "fields": {
                    "first_name": None,
                    "last_name": None,
                    "date_of_birth": None,
                    "document_number": None,
                    "gender": "Z",
                },
            },
            "media": [],
            "meta": {"attempt_id": None},
        },
    )
    document = sdk.call(lambda c: c.verifications.document(VID))
    assert document.document.type == "health_card"
    assert not isinstance(document.document.type, DocumentResultType)
    assert document.document.fields.gender == "Z"


def test_estimation(sdk: Harness, api: respx.MockRouter) -> None:
    api.get(f"/verifications/{VID}/estimation").respond(
        200,
        json={
            "verification_id": VID,
            "attempt_id": None,
            "age_threshold": {"minimum": 18, "passed": False, "confidence": 0.8},
            "gender": {"value": 0, "confidence": 0.9},
        },
    )
    estimation = sdk.call(lambda c: c.verifications.estimation(VID))
    assert isinstance(estimation, AgeEstimation)
    assert estimation.gender is not None and estimation.gender.value == 0


def test_block_face_accepts_the_enum_or_a_string(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post(f"/verifications/{VID}/blocked-face").respond(204)
    sdk.call(
        lambda c: c.verifications.block_face(
            VID, reason_code=BlockFaceReasonCode.UNDERAGE, reason="Admitted being 15"
        )
    )
    assert body(route) == {"reason_code": "underage", "reason": "Admitted being 15"}
    sdk.call(lambda c: c.verifications.block_face(VID, reason_code="other", reason="x"))
    assert body(route) == {"reason_code": "other", "reason": "x"}


GET_PAYLOAD = {k: v for k, v in VERIFICATION.items() if k != "url"}


def test_list_sends_no_query_without_filters(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/verifications").respond(
        200, json={"data": [GET_PAYLOAD], "next_cursor": "eyJpZCI6MX0"}
    )
    page = sdk.call(lambda c: c.verifications.list())
    assert isinstance(page, VerificationList)
    assert type(page.data[0]) is Verification
    assert page.data[0].status is VerificationStatus.APPROVED
    assert page.next_cursor == "eyJpZCI6MX0"
    request = route.calls.last.request
    assert request.url.query == b""
    assert request.headers["X-HMAC-Signature"] == sign_raw("GET/v1/verifications")


def test_list_signs_the_query_it_sends(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/verifications").respond(200, json={"data": [], "next_cursor": None})
    page = sdk.call(
        lambda c: c.verifications.list(
            status=[VerificationStatus.APPROVED, "declined"],
            external_id="user 42",
            limit=50,
            cursor="eyJpZCI6MX0",
        )
    )
    assert page.data == [] and page.next_cursor is None
    request = route.calls.last.request
    query = "cursor=eyJpZCI6MX0&external_id=user%2042&limit=50&status=approved%2Cdeclined"
    assert request.url.query == query.encode()
    assert request.headers["X-HMAC-Signature"] == sign_raw(f"GET/v1/verifications?{query}")


@pytest.mark.parametrize(
    ("status", "sent"),
    [
        ("review", "review"),
        (VerificationStatus.EXPIRED, "expired"),
        ("approved,declined", "approved%2Cdeclined"),
        (("created",), "created"),
    ],
)
def test_list_takes_one_status_a_list_or_a_comma_string(
    sdk: Harness, api: respx.MockRouter, status: Any, sent: str
) -> None:
    route = api.get("/verifications").respond(200, json={"data": [], "next_cursor": None})
    sdk.call(lambda c: c.verifications.list(status=status))
    assert route.calls.last.request.url.query == f"status={sent}".encode()


def test_list_refuses_an_empty_status_list(api: respx.MockRouter) -> None:
    with (
        ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url="https://api.test") as client,
        pytest.raises(ValueError, match="at least one status"),
    ):
        client.verifications.list(status=[])
    assert not api.calls


def test_list_is_retried_on_5xx(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.get("/verifications").mock(
        side_effect=[
            httpx.Response(502),
            httpx.Response(200, json={"data": [], "next_cursor": None}),
        ]
    )
    sdk.call(lambda c: c.verifications.list(limit=1), retry_delay=0)
    assert route.call_count == 2
    assert route.calls.last.request.url.query == b"limit=1"


def test_set_test_outcome(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post(f"/verifications/{VID}/test-outcome").respond(
        200, json={**GET_PAYLOAD, "status": "resubmission_requested"}
    )
    verification = sdk.call(
        lambda c: c.verifications.set_test_outcome(
            VID, status=VerificationOutcome.RESUBMISSION_REQUESTED, reason="Blurry photo"
        )
    )
    assert type(verification) is Verification
    assert verification.status is VerificationStatus.RESUBMISSION_REQUESTED
    assert body(route) == {"status": "resubmission_requested", "reason": "Blurry photo"}
    sdk.call(lambda c: c.verifications.set_test_outcome(VID, status="approved"))
    assert body(route) == {"status": "approved"}


def test_set_test_outcome_is_not_retried_on_5xx(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post(f"/verifications/{VID}/test-outcome").respond(500)
    with pytest.raises(ServerError):
        sdk.call(lambda c: c.verifications.set_test_outcome(VID, status="approved"), retry_delay=0)
    assert route.call_count == 1


def test_set_test_outcome_in_a_live_workspace(sdk: Harness, api: respx.MockRouter) -> None:
    api.post(f"/verifications/{VID}/test-outcome").respond(
        403,
        json={
            "error": {
                "code": "TEST_WORKSPACE_ONLY",
                "message": "The outcome can only be set in a test workspace.",
            }
        },
    )
    with pytest.raises(PermissionDeniedError) as caught:
        sdk.call(lambda c: c.verifications.set_test_outcome(VID, status="approved"))
    assert caught.value.code == "TEST_WORKSPACE_ONLY"


def test_set_test_outcome_on_a_final_verification(sdk: Harness, api: respx.MockRouter) -> None:
    api.post(f"/verifications/{VID}/test-outcome").respond(
        422,
        json={
            "error": {
                "code": "INVALID_STATUS",
                "message": "The verification is already approved, a final status.",
            }
        },
    )
    with pytest.raises(ValidationError) as caught:
        sdk.call(lambda c: c.verifications.set_test_outcome(VID, status="declined"))
    assert caught.value.code == "INVALID_STATUS"


@pytest.mark.parametrize("bad_id", ["../workspace", "abc?x=1", "", "a/b", "a#b", "a%2F"])
def test_a_malformed_id_never_reaches_the_network(api: respx.MockRouter, bad_id: str) -> None:
    with (
        ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url="https://api.test") as client,
        pytest.raises(ValueError, match="verification_id"),
    ):
        client.verifications.get(bad_id)
    assert not api.calls


def test_create_warns_about_the_widget_fields_and_still_sends_them(
    sdk: Harness, api: respx.MockRouter
) -> None:
    route = api.post("/verifications").respond(201, json=VERIFICATION)
    with pytest.warns(
        DeprecationWarning, match=r"create\(\): page_url is sent by the ProofAge widget"
    ):
        sdk.call(lambda c: c.verifications.create(page_url="https://shop.example/checkout"))
    assert body(route) == {"page_url": "https://shop.example/checkout"}


def test_public_fields_raise_no_warning(sdk: Harness, api: respx.MockRouter) -> None:
    api.post("/verifications").respond(201, json=VERIFICATION)
    api.post(f"/verifications/{VID}/consent").respond(
        200, json={"consent_version_id": 3, "consent_accepted_at": "2026-09-28T12:00:00Z"}
    )
    api.post(f"/verifications/{VID}/media").respond(200)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        sdk.call(lambda c: c.verifications.create(external_id="candidate-42"))
        sdk.call(
            lambda c: c.verifications.accept_consent(
                VID, consent_version_id=3, text_sha256="ab" * 32
            )
        )
        sdk.call(lambda c: c.verifications.upload_media(VID, file=b"x", type="selfie"))


@pytest.mark.parametrize(
    ("kwargs", "named"),
    [
        ({"type": "selfie", "head_turn_step": 2}, "head_turn_step"),
        ({"type": "liveness_selfie"}, "type='liveness_selfie'"),
    ],
)
def test_upload_warns_about_the_widget_fields(
    sdk: Harness, api: respx.MockRouter, kwargs: dict[str, Any], named: str
) -> None:
    api.post(f"/verifications/{VID}/media").respond(200)
    with pytest.warns(DeprecationWarning, match=re.escape(named)):
        sdk.call(lambda c: c.verifications.upload_media(VID, file=b"x", **kwargs))
