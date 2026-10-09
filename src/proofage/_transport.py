"""Everything about a request that is not I/O: preparation, retry rules, decoding, errors.

Both clients call these functions, so the sync and async clients can only
differ in how they send and how they sleep.
"""

from __future__ import annotations

import email.utils
import json
import math
import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timezone
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from ._config import SDK_HEADER, ClientConfig
from ._signing import (
    build_query,
    canonical_multipart_request,
    canonical_request,
    serialize_json_body,
    sign,
    to_multipart_fields,
)
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
            "origin, e.g. https://api.proofage.net",
            status_code=status,
            response_body=text,
        ) from exc


DOWNLOAD_ACCEPT = "application/json, */*;q=0.8"
"""The API renders errors as JSON only when JSON is the first acceptable type."""

_IDEMPOTENT = frozenset({"GET", "HEAD"})
_NEVER_SENT = (httpx.ConnectError, httpx.ConnectTimeout)


@dataclass(frozen=True)
class PreparedRequest:
    """A signed request, ready for either client to send."""

    method: str
    url: str
    headers: dict[str, str]
    content: bytes | None = None
    data: dict[str, str] | None = None
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None


def api_path(config: ClientConfig, endpoint: str) -> str:
    """`/{version}/{endpoint}`, the path the server signs."""
    return f"/{config.version}/{endpoint.lstrip('/')}"


def _base_headers(config: ClientConfig, accept: str) -> dict[str, str]:
    headers = {SDK_HEADER: config.sdk_header, "Accept": accept, "X-API-Key": config.api_key}
    if config.user_agent is not None:
        headers["User-Agent"] = config.user_agent
    return headers


def prepare_json(
    config: ClientConfig,
    method: str,
    endpoint: str,
    payload: Mapping[str, Any] | None = None,
    *,
    query: Mapping[str, Any] | None = None,
    accept: str = "application/json",
) -> PreparedRequest:
    """Serialise once, sign those bytes, send those bytes.

    The query string is built here, already in the server's normalised form (keys sorted,
    RFC 3986), and sent as that exact string: httpx's `params=` would encode it differently.
    """
    path = api_path(config, endpoint)
    query_string = build_query(query or {})
    body = serialize_json_body(payload or {})
    headers = _base_headers(config, accept)
    headers["X-HMAC-Signature"] = sign(
        config.secret_key, canonical_request(method, path, body, query_string)
    )
    content: bytes | None = None
    if body:
        headers["Content-Type"] = "application/json"
        content = body.encode("utf-8")
    url = config.base_url + path + (f"?{query_string}" if query_string else "")
    return PreparedRequest(method.upper(), url, headers, content=content)


def prepare_multipart(
    config: ClientConfig,
    method: str,
    endpoint: str,
    fields: Mapping[str, Any],
    *,
    filename: str,
    content: bytes,
) -> PreparedRequest:
    """A one-file multipart upload whose text fields are exactly the strings signed."""
    path = api_path(config, endpoint)
    wire = to_multipart_fields(fields)
    headers = _base_headers(config, "application/json")
    headers["X-HMAC-Signature"] = sign(
        config.secret_key, canonical_multipart_request(method, path, wire, [content])
    )
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return PreparedRequest(
        method.upper(),
        config.base_url + path,
        headers,
        data=wire,
        files=[("file", (filename, content, mime))],
    )


def is_retryable_status(method: str, status: int) -> bool:
    """GET: 408, 429, 5xx. POST and DELETE: only 429, which the rate limiter answers before
    anything runs."""
    if method.upper() in _IDEMPOTENT:
        return status in (408, 429) or 500 <= status < 600
    return status == 429


def is_retryable_exception(method: str, exc: httpx.TransportError) -> bool:
    """GET: any transport failure. POST and DELETE: only failures before a byte was sent."""
    if method.upper() in _IDEMPOTENT:
        return True
    return isinstance(exc, _NEVER_SENT)


def parse_retry_after(value: str | None, now: float) -> float | None:
    """`Retry-After` in seconds, from delta-seconds or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, when.timestamp() - now)
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def retry_delay(
    config: ClientConfig, attempt: int, status: int | None, retry_after: float | None
) -> float:
    """A 429's `Retry-After` when sent, otherwise `retry_delay * attempt number`."""
    if status == 429 and retry_after is not None:
        return retry_after
    return config.retry_delay * (attempt + 1)


MAX_RETRY_AFTER = 60.0
"""A 429 asking for a longer wait is raised at once rather than slept on in-process."""

M = TypeVar("M", bound=BaseModel)


def within_retry_after_cap(status: int, retry_after: float | None) -> bool:
    """False when a 429's `Retry-After` is longer than the SDK will block a caller for."""
    return not (status == 429 and retry_after is not None and retry_after > MAX_RETRY_AFTER)


def describe_validation_error(exc: PydanticValidationError) -> str:
    """Which fields did not match, never the values: a response or webhook body carries PII."""
    problems = [
        f"{'.'.join(str(part) for part in error['loc']) or '<body>'}: {error['msg']}"
        for error in exc.errors(include_url=False, include_input=False)
    ]
    shown = "; ".join(problems[:5])
    return shown if len(problems) <= 5 else f"{shown}; and {len(problems) - 5} more"


def parse_model(model: type[M], data: Any, where: str) -> M:
    """Validate a decoded response, turning a shape mismatch into a `ProofAgeError`."""
    try:
        return model.model_validate(data)
    except PydanticValidationError as exc:
        raise ProofAgeError(
            f"Unexpected response shape from {where}: {describe_validation_error(exc)}. "
            "The API may be newer than this SDK; upgrade proofage or report it",
        ) from exc
