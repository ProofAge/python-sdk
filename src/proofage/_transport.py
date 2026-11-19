"""Everything about a request that is not I/O: preparation, retry rules, decoding, errors.

Both clients call these functions, so the sync and async clients can only
differ in how they send and how they sleep.
"""

from __future__ import annotations

import email.utils
import json
import math
import mimetypes
import re
import uuid
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
    timestamped_canonical,
    to_multipart_fields,
)
from .errors import (
    AuthenticationError,
    ConfigurationError,
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


IDEMPOTENCY_HEADER = "Idempotency-Key"
TIMESTAMP_HEADER = "X-Timestamp"
IN_PROGRESS_CODE = "IDEMPOTENCY_KEY_IN_PROGRESS"

_IDEMPOTENCY_KEY = re.compile(r"[\x21-\x7E]{1,255}")


def new_idempotency_key() -> str:
    """A fresh UUID v4, one per logical create call."""
    return str(uuid.uuid4())


def resolve_idempotency_key(supplied: str | None) -> str:
    """The caller's key, checked against the server's rule (1-255 printable ASCII), or a new one."""
    if supplied is None:
        return new_idempotency_key()
    if not isinstance(supplied, str) or not _IDEMPOTENCY_KEY.fullmatch(supplied):
        raise ConfigurationError(
            "Invalid idempotency_key: expected 1 to 255 printable ASCII characters "
            "(no spaces), e.g. a UUID"
        )
    return supplied


@dataclass(frozen=True)
class PreparedRequest:
    """A request ready for either client to send, apart from its timestamp and signature.

    `canonical` is the legacy canonical string; `signed_headers()` adds `X-Timestamp` and the
    signature over `{timestamp}.{canonical}`. Call it once per attempt: the server accepts a
    signed request other than GET once, so a retry must carry a new timestamp and signature.
    """

    method: str
    url: str
    headers: dict[str, str]
    canonical: str
    content: bytes | None = None
    data: dict[str, str] | None = None
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None
    idempotency_key: str | None = None

    def signed_headers(self, secret_key: str, now: float) -> dict[str, str]:
        """The headers of one attempt, stamped with `now` (Unix seconds)."""
        timestamp = str(int(now))
        headers = dict(self.headers)
        headers[TIMESTAMP_HEADER] = timestamp
        headers["X-HMAC-Signature"] = sign(
            secret_key, timestamped_canonical(timestamp, self.canonical)
        )
        return headers


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
    idempotency_key: str | None = None,
) -> PreparedRequest:
    """Serialise once, sign those bytes, send those bytes.

    The query string is built here, already in the server's normalised form (keys sorted,
    RFC 3986), and sent as that exact string: httpx's `params=` would encode it differently.
    """
    path = api_path(config, endpoint)
    query_string = build_query(query or {})
    body = serialize_json_body(payload or {})
    headers = _base_headers(config, accept)
    if idempotency_key is not None:
        headers[IDEMPOTENCY_HEADER] = idempotency_key
    content: bytes | None = None
    if body:
        headers["Content-Type"] = "application/json"
        content = body.encode("utf-8")
    url = config.base_url + path + (f"?{query_string}" if query_string else "")
    return PreparedRequest(
        method.upper(),
        url,
        headers,
        canonical_request(method, path, body, query_string),
        content=content,
        idempotency_key=idempotency_key,
    )


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
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return PreparedRequest(
        method.upper(),
        config.base_url + path,
        headers,
        canonical_multipart_request(method, path, wire, [content]),
        data=wire,
        files=[("file", (filename, content, mime))],
    )


def is_retryable_status(method: str, status: int, *, keyed: bool = False, text: str = "") -> bool:
    """GET, or a POST carrying an `Idempotency-Key` (`keyed`): 408, 429, 5xx, and for the keyed
    POST also 409 `IDEMPOTENCY_KEY_IN_PROGRESS`. Other POSTs and DELETEs: only 429, which the
    rate limiter answers before anything runs."""
    if method.upper() in _IDEMPOTENT or keyed:
        if status == 409:
            return keyed and parse_error_body(text)[1] == IN_PROGRESS_CODE
        return status in (408, 429) or 500 <= status < 600
    return status == 429


REPLAYED_CODE = "REPLAYED_REQUEST"


def is_replayed_request(method: str, status: int, text: str) -> bool:
    """A non-GET 401 `REPLAYED_REQUEST`: a byte-identical request was signed in the same second.
    The server refused it in middleware, so nothing ran and one re-signed resend is safe."""
    return (
        method.upper() not in _IDEMPOTENT
        and status == 401
        and parse_error_body(text)[1] == REPLAYED_CODE
    )


def replay_wait(signed_at: float, now: float) -> float:
    """Seconds until the whole second after the one the request was signed in."""
    return max(0.0, int(signed_at) + 1 - now)


def is_retryable_exception(method: str, exc: httpx.TransportError, *, keyed: bool = False) -> bool:
    """GET and keyed POST: any transport failure. Other POSTs and DELETEs: only failures before
    a byte was sent."""
    if method.upper() in _IDEMPOTENT or keyed:
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
    """A 429's or 409's `Retry-After` when sent, otherwise `retry_delay * attempt number`."""
    if status in (409, 429) and retry_after is not None:
        return retry_after
    return config.retry_delay * (attempt + 1)


MAX_RETRY_AFTER = 60.0
"""A 429 asking for a longer wait is raised at once rather than slept on in-process."""

M = TypeVar("M", bound=BaseModel)


NOT_WORTH_RETRYING_429 = frozenset({"REAUTH_RATE_LIMITED"})
"""429 codes that clear over hours, not seconds: waiting in-process cannot help."""


def within_retry_after_cap(status: int, retry_after: float | None, text: str = "") -> bool:
    """False when a 429 (or a 409 in progress) should be raised at once: its `Retry-After` is
    longer than the SDK will block a caller for, or its code (`REAUTH_RATE_LIMITED`) says a
    retry cannot help."""
    if status not in (409, 429):
        return True
    if retry_after is not None and retry_after > MAX_RETRY_AFTER:
        return False
    return status != 429 or parse_error_body(text)[1] not in NOT_WORTH_RETRYING_429


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
