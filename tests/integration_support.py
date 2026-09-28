"""Shared pieces of the framework-integration tests."""

from __future__ import annotations

import sys
import time

import pytest

from proofage._signing import webhook_signature

from .conftest import API_KEY, SECRET_KEY

BODY = (
    b'{"verification_id":"v-1","status":"approved","external_id":"u-1",'
    b'"external_metadata":null,"reason":null,"timestamp":"2026-09-02T09:00:00+00:00"}'
)


def signed_headers(body: bytes = BODY, *, secret: str = SECRET_KEY) -> dict[str, str]:
    """The headers ProofAge sends with a webhook, signed now."""
    timestamp = int(time.time())
    return {
        "X-HMAC-Signature": webhook_signature(secret, timestamp, body),
        "X-Timestamp": str(timestamp),
        "X-Auth-Client": API_KEY,
        "X-ProofAge-Webhook-Delivery-Id": "d-1",
        "Content-Type": "application/json",
    }


def configure_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFAGE_API_KEY", API_KEY)
    monkeypatch.setenv("PROOFAGE_SECRET_KEY", SECRET_KEY)


def assert_needs_extra(monkeypatch: pytest.MonkeyPatch, module: str, framework: str) -> None:
    """Importing an integration without its framework names the exact pip command."""
    monkeypatch.delitem(sys.modules, module, raising=False)
    for name in [n for n in sys.modules if n == framework or n.startswith(f"{framework}.")]:
        monkeypatch.setitem(sys.modules, name, None)
    with pytest.raises(ImportError, match=rf'pip install "proofage\[{framework}\]"'):
        __import__(module)
