from __future__ import annotations

import json

import pytest

from proofage._transport import decode_success, error_for_response
from proofage.errors import (
    AuthenticationError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    ProofAgeError,
    RateLimitError,
    ServerError,
    ValidationError,
)


def test_nested_error_shape() -> None:
    body = json.dumps({"error": {"code": "INVALID_SIGNATURE", "message": "Bad signature"}})
    error = error_for_response(401, body)
    assert isinstance(error, AuthenticationError)
    assert error.message == "Bad signature"
    assert error.code == "INVALID_SIGNATURE"
    assert error.error_data == {"code": "INVALID_SIGNATURE", "message": "Bad signature"}
    assert error.status_code == 401
    assert error.response_body == body


def test_flat_error_shape_keeps_the_extra_fields() -> None:
    body = json.dumps(
        {
            "code": "PAYMENT_METHOD_REQUIRED",
            "message": "Add a payment method",
            "free_verifications_remaining": 0,
            "trial_ends_at": None,
            "trial_active": False,
        }
    )
    error = error_for_response(402, body)
    assert isinstance(error, PaymentRequiredError)
    assert error.code == "PAYMENT_METHOD_REQUIRED"
    assert error.error_data is not None
    assert error.error_data["trial_active"] is False


def test_laravel_validation_shape() -> None:
    body = json.dumps({"message": "Invalid.", "errors": {"external_id": ["Too long."]}})
    error = error_for_response(422, body)
    assert isinstance(error, ValidationError)
    assert error.code is None
    assert error.errors == {"external_id": ["Too long."]}


def test_media_rejection_is_a_validation_error_with_a_code() -> None:
    error = error_for_response(422, json.dumps({"code": "FACE_NOT_FOUND", "message": "No face"}))
    assert isinstance(error, ValidationError)
    assert error.code == "FACE_NOT_FOUND"


@pytest.mark.parametrize(
    ("status", "error_class"),
    [(403, PermissionDeniedError), (404, NotFoundError), (500, ServerError), (503, ServerError)],
)
def test_message_only_shape_and_status_mapping(status: int, error_class: type) -> None:
    error = error_for_response(status, json.dumps({"message": "Resource not found"}))
    assert isinstance(error, error_class)
    assert error.message == "Resource not found"


def test_rate_limit_carries_retry_after() -> None:
    error = error_for_response(429, json.dumps({"error": {"code": "RATE_LIMIT"}}), 12.0)
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 12.0


def test_non_json_error_body_becomes_a_snippet() -> None:
    error = error_for_response(502, "<html>" + "x" * 300)
    assert error.message.startswith("HTTP 502: <html>")
    assert error.message.endswith("…")


def test_empty_error_body() -> None:
    assert error_for_response(500, "").message == "HTTP 500"


def test_other_statuses_are_plain_proofage_errors() -> None:
    error = error_for_response(409, json.dumps({"message": "Conflict"}))
    assert type(error) is ProofAgeError


def test_success_json_is_decoded() -> None:
    assert decode_success(200, '{"a":1}', "u", "application/json", expect_body=True) == {"a": 1}


def test_success_without_a_body_is_none_for_none_methods() -> None:
    assert decode_success(200, "", "u", None, expect_body=False) is None


def test_success_without_a_body_raises_where_a_model_is_promised() -> None:
    with pytest.raises(ProofAgeError, match="carried none"):
        decode_success(200, "  ", "https://api.test/v1/workspace", None, expect_body=True)


def test_html_success_points_at_the_base_url() -> None:
    with pytest.raises(ProofAgeError, match="base_url is the API origin"):
        decode_success(
            200, "<html></html>", "https://proofage.xyz/v1/workspace", "text/html", expect_body=True
        )
