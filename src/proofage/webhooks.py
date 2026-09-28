"""Verifying the webhooks ProofAge sends to your `callback_url` / workspace webhook URL."""

from __future__ import annotations

import hmac
import json
import os
import time
from collections.abc import Mapping

from pydantic import ValidationError as PydanticValidationError

from ._signing import webhook_signature
from .errors import WebhookVerificationError
from .models import WebhookEvent

DEFAULT_TOLERANCE = 300


def _fail(code: str, message: str, status: int = 401) -> WebhookVerificationError:
    return WebhookVerificationError(code, message, status)


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_webhook_signature(
    raw_body: bytes | str,
    headers: Mapping[str, str],
    *,
    api_key: str | None = None,
    secret_key: str | None = None,
    tolerance: int | None = None,
    now: float | None = None,
) -> None:
    """Check the three headers, the workspace, the timestamp and the HMAC; raise on any failure.

    Pass the body exactly as received. Keys and tolerance fall back to
    `PROOFAGE_API_KEY`, `PROOFAGE_SECRET_KEY` and `PROOFAGE_WEBHOOK_TOLERANCE`.
    """
    lowered = {key.lower(): value for key, value in headers.items()}
    signature = lowered.get("x-hmac-signature")
    timestamp_raw = lowered.get("x-timestamp")
    auth_client = lowered.get("x-auth-client")

    if not signature:
        raise _fail("MISSING_SIGNATURE", "X-HMAC-Signature header is required")
    if not timestamp_raw:
        raise _fail("MISSING_TIMESTAMP", "X-Timestamp header is required")
    if not auth_client:
        raise _fail("MISSING_AUTH_CLIENT", "X-Auth-Client header is required")

    key = api_key or os.environ.get("PROOFAGE_API_KEY")
    secret = secret_key or os.environ.get("PROOFAGE_SECRET_KEY")
    if not key or not secret:
        raise _fail(
            "CONFIGURATION_ERROR",
            "Webhook verification needs the api key and secret key "
            "(pass them or set PROOFAGE_API_KEY / PROOFAGE_SECRET_KEY)",
            500,
        )
    if not _same(auth_client, key):
        raise _fail("INVALID_AUTH_CLIENT", "X-Auth-Client header is invalid")

    try:
        timestamp = int(timestamp_raw.strip())
    except ValueError:
        raise _fail("MISSING_TIMESTAMP", "X-Timestamp header is invalid") from None

    if tolerance is None:
        env_tolerance = os.environ.get("PROOFAGE_WEBHOOK_TOLERANCE")
        tolerance = int(env_tolerance) if env_tolerance else DEFAULT_TOLERANCE
    current = time.time() if now is None else now
    if abs(int(current) - timestamp) > tolerance:
        raise _fail("TIMESTAMP_TOO_OLD", "Timestamp is outside allowed tolerance")

    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    if _same(signature, webhook_signature(secret, timestamp, body)):
        return

    canonical: bytes | None
    try:
        canonical = json.dumps(json.loads(body), ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except ValueError:
        canonical = None
    if (
        canonical is not None
        and canonical != body
        and _same(signature, webhook_signature(secret, timestamp, canonical))
    ):
        return

    raise _fail(
        "INVALID_SIGNATURE",
        "HMAC signature is invalid. Pass the raw request body exactly as received, "
        "not a re-serialised copy of its JSON",
    )


def verify_webhook(
    raw_body: bytes | str,
    headers: Mapping[str, str],
    *,
    api_key: str | None = None,
    secret_key: str | None = None,
    tolerance: int | None = None,
    now: float | None = None,
) -> WebhookEvent:
    """Verify a webhook and return it as a `WebhookEvent` (see `verify_webhook_signature`)."""
    verify_webhook_signature(
        raw_body, headers, api_key=api_key, secret_key=secret_key, tolerance=tolerance, now=now
    )
    try:
        event = WebhookEvent.model_validate_json(raw_body)
    except PydanticValidationError as exc:
        raise _fail(
            "INVALID_PAYLOAD", f"Signed body is not a ProofAge webhook: {exc}", 400
        ) from exc
    lowered = {key.lower(): value for key, value in headers.items()}
    delivery_id = lowered.get("x-proofage-webhook-delivery-id")
    return event.model_copy(update={"delivery_id": delivery_id}) if delivery_id else event
