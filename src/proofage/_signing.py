"""The canonical strings ProofAge signs, and the HMAC over them.

The server recomputes the same string from the request it receives
(`VerifyHmacSignature` in the app), so every rule here is pinned by the golden
vectors in `tests/fixtures/hmac-vectors.json`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, quote


def rawurlencode(value: str) -> str:
    """PHP's `rawurlencode()`: RFC 3986, leaving only `A-Z a-z 0-9 - _ . ~` bare."""
    return quote(value, safe="~")


def serialize_json_body(payload: Mapping[str, Any]) -> str:
    """Serialise a JSON body once; an empty payload is the empty string, never `{}`."""
    if not payload:
        return ""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def normalize_query(query: str) -> str:
    """Symfony's normalised query string: keys sorted, values RFC 3986-encoded."""
    if not query:
        return ""
    pairs = sorted(parse_qsl(query, keep_blank_values=True))
    return "?" + "&".join(f"{rawurlencode(k)}={rawurlencode(v)}" for k, v in pairs)


def canonical_request(method: str, path: str, body: str, query: str = "") -> str:
    """`METHOD + /{version}/{path} + ?query + body` for JSON and body-less requests."""
    return f"{method.upper()}{path}{normalize_query(query)}{body}"


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def http_build_query(fields: Mapping[str, Any]) -> str:
    """PHP's `http_build_query(ksort($fields), '', '&', PHP_QUERY_RFC3986)`, recursively."""
    pairs: list[str] = []

    def walk(key: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, Mapping):
            for child in sorted(value, key=str):
                walk(f"{key}[{child}]", value[child])
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(f"{key}[{index}]", item)
        else:
            pairs.append(f"{rawurlencode(key)}={rawurlencode(_scalar(value))}")

    for name in sorted(fields, key=str):
        walk(str(name), fields[name])
    return "&".join(pairs)


def canonical_multipart_request(
    method: str, path: str, fields: Mapping[str, Any], files: Sequence[bytes]
) -> str:
    """`METHOD/{version}/{path}\\n{sorted fields}\\n{sorted sha256 of each file, comma-joined}`."""
    hashes = sorted(hashlib.sha256(content).hexdigest() for content in files)
    return f"{method.upper()}{path}\n{http_build_query(fields)}\n{','.join(hashes)}"


def to_multipart_fields(data: Mapping[str, Any]) -> dict[str, str]:
    """The exact strings a multipart request sends, and therefore signs.

    httpx would otherwise encode `True` as `"true"` and `None` as `""`, sending
    different bytes from the ones signed.
    """
    fields: dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, str):
            fields[key] = value
        elif isinstance(value, bool):
            fields[key] = "1" if value else "0"
        elif isinstance(value, (int, float)):
            fields[key] = str(value)
        else:
            fields[key] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return fields


def sign(secret: str, canonical: str | bytes) -> str:
    """Hex HMAC-SHA256 of the canonical string with the workspace secret key."""
    message = canonical.encode("utf-8") if isinstance(canonical, str) else canonical
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def webhook_signature(secret: str, timestamp: int, payload: bytes) -> str:
    """Hex HMAC-SHA256 of `{timestamp}.{raw body}`, as ProofAge signs outbound webhooks."""
    return sign(secret, f"{timestamp}.".encode() + payload)
