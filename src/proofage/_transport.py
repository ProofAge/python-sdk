"""Everything about a request that is not I/O: preparation, retry rules, decoding, errors.

Both clients call these functions, so the sync and async clients can only
differ in how they send and how they sleep.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import (
    AuthenticationError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    ProofAgeError,
    RateLimitError,
    ServerError,
    ValidationError,
)

_STATUS_ERRORS: dict[int, type[ProofAgeError]] = {
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: PermissionDeniedError,
    404: NotFoundError,
}


def parse_error_body(
    text: str,
) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, list[str]]]:
    """Read `message`, `code`, the error object and field errors from any of the API's
    four error shapes: `{error: {code, message}}`, flat `{code, message, ...}`,
    Laravel's `{message, errors}` and `{message}`."""
    try:
        body = json.loads(text) if text.strip() else None
    except ValueError:
        return None, None, None, {}
    if not isinstance(body, dict):
        return None, None, None, {}

    raw_errors = body.get("errors")
    field_errors: dict[str, list[str]] = {}
    if isinstance(raw_errors, dict):
        for field, messages in raw_errors.items():
            items = messages if isinstance(messages, list) else [messages]
            field_errors[str(field)] = [str(m) for m in items]

    inner = body.get("error")
    source: dict[str, Any] = inner if isinstance(inner, dict) else body
    message = source.get("message")
    code = source.get("code")
    if isinstance(inner, dict):
        error_data: dict[str, Any] | None = inner
    else:
        rest = {k: v for k, v in body.items() if k != "errors"}
        error_data = rest or None
    return (
        message if isinstance(message, str) else None,
        code if isinstance(code, str) else None,
        error_data,
        field_errors,
    )


def error_for_response(status: int, text: str, retry_after: float | None = None) -> ProofAgeError:
    """The exception for a non-2xx response."""
    message, code, error_data, field_errors = parse_error_body(text)
    if message is None:
        snippet = text if len(text) <= 200 else f"{text[:200]}…"
        message = f"HTTP {status}: {snippet}" if snippet else f"HTTP {status}"

    if status == 422:
        return ValidationError(
            message,
            errors=field_errors,
            status_code=status,
            code=code,
            error_data=error_data,
            response_body=text,
        )
    if status == 429:
        return RateLimitError(
            message,
            retry_after=retry_after,
            status_code=status,
            code=code,
            error_data=error_data,
            response_body=text,
        )
    error_class = _STATUS_ERRORS.get(status, ServerError if status >= 500 else ProofAgeError)
    return error_class(
        message, status_code=status, code=code, error_data=error_data, response_body=text
    )


def decode_success(
    status: int, text: str, url: str, content_type: str | None, *, expect_body: bool
) -> Any:
    """The decoded JSON of a 2xx, or None for the calls that promise nothing."""
    if not expect_body:
        return None
    if text.strip() == "":
        raise ProofAgeError(
            f"Expected a JSON body from {url} but HTTP {status} carried none",
            status_code=status,
            response_body=text,
        )
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ProofAgeError(
            f"Expected a JSON response from {url} but got HTTP {status} with a non-JSON body "
            f"(Content-Type: {content_type or 'unknown'}). Check that base_url is the API "
            "origin, e.g. https://api.proofage.xyz",
            status_code=status,
            response_body=text,
        ) from exc
