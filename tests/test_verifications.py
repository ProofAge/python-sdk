from __future__ import annotations

import json
import re
import warnings
from datetime import date
from typing import Any

import pytest
import respx

from proofage import ProofAge
from proofage.models import (
    AcceptConsentResult,
    AgeEstimation,
    BlockFaceReasonCode,
    CreatedVerification,
    DocumentGender,
    DocumentResultType,
    Verification,
    VerificationDocument,
)

from .conftest import API_KEY, SECRET_KEY, VERIFICATION_ID, Harness
from .test_models import VERIFICATION

VID = VERIFICATION_ID


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
                "type": "id",
                "issuing_country": "FR",
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
