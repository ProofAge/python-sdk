from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import pytest

from proofage._signing import (
    build_query,
    canonical_multipart_request,
    canonical_request,
    rawurlencode,
    serialize_json_body,
    sign,
    to_multipart_fields,
    webhook_signature,
)

VECTORS: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "hmac-vectors.json").read_text(encoding="utf-8")
)
SECRET: str = VECTORS["secret"]


@pytest.mark.parametrize("vector", VECTORS["json"], ids=lambda v: v["name"])
def test_json_vectors(vector: dict[str, Any]) -> None:
    canonical = canonical_request(
        vector["method"], vector["path"], vector["body"], vector.get("query", "")
    )
    assert canonical == vector["canonical"]
    assert sign(SECRET, canonical) == vector["expected"]


@pytest.mark.parametrize("vector", VECTORS["multipart"], ids=lambda v: v["name"])
def test_multipart_vectors(vector: dict[str, Any]) -> None:
    files = [base64.b64decode(f["content_base64"]) for f in vector["files"]]
    canonical = canonical_multipart_request(
        vector["method"], vector["path"], vector["fields"], files
    )
    assert canonical == vector["canonical"]
    assert sign(SECRET, canonical) == vector["expected"]


@pytest.mark.parametrize("vector", VECTORS["webhook"], ids=lambda v: v["name"])
def test_webhook_vectors(vector: dict[str, Any]) -> None:
    payload = vector["payload"].encode("utf-8")
    assert webhook_signature(SECRET, vector["timestamp"], payload) == vector["expected"]


def test_built_query_is_already_normalised() -> None:
    for vector in VECTORS["json"]:
        if not vector.get("query"):
            continue
        built = build_query(dict(parse_qsl(vector["query"], keep_blank_values=True)))
        canonical = canonical_request(vector["method"], vector["path"], vector["body"], built)
        assert canonical == vector["canonical"]
        assert canonical == f"{vector['method']}{vector['path']}?{built}{vector['body']}"


def test_build_query_drops_none_and_sorts() -> None:
    query = build_query({"status": "approved,declined", "cursor": None, "limit": 20, "flag": True})
    assert query == "flag=1&limit=20&status=approved%2Cdeclined"
    assert build_query({}) == ""


def test_rawurlencode_matches_php() -> None:
    assert rawurlencode("a b!'()*~-_.") == "a%20b%21%27%28%29%2A~-_."


def test_empty_payload_is_the_empty_string() -> None:
    assert serialize_json_body({}) == ""


def test_json_body_is_compact_and_keeps_unicode() -> None:
    body = serialize_json_body({"name": "Jürgen", "n": 1})
    assert body == '{"name":"Jürgen","n":1}'


def test_json_body_refuses_nan() -> None:
    with pytest.raises(ValueError):
        serialize_json_body({"x": float("nan")})


def test_multipart_fields_are_the_strings_that_go_on_the_wire() -> None:
    fields = to_multipart_fields(
        {
            "type": "selfie",
            "skip": None,
            "flag": True,
            "off": False,
            "step": 3,
            "device_info": {"os": "iOS", "ua": "Mozilla/5.0 (é)"},
            "telemetry": [1, 2],
        }
    )
    assert fields == {
        "type": "selfie",
        "flag": "1",
        "off": "0",
        "step": "3",
        "device_info": '{"os":"iOS","ua":"Mozilla/5.0 (é)"}',
        "telemetry": "[1,2]",
    }
