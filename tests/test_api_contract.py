from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from proofage.models import (
    AcceptConsentResult,
    AgeEstimation,
    BlockFaceReasonCode,
    ConsentInfo,
    CreatedVerification,
    Verification,
    VerificationDocument,
    WorkspaceInfo,
)
from proofage.resources.verifications import AsyncVerifications, Verifications
from proofage.resources.workspace import AsyncWorkspace, Workspace

SPEC: dict[str, Any] = json.loads(
    resources.files("proofage").joinpath("openapi.json").read_text(encoding="utf-8")
)
AGENTS = (Path(__file__).parent.parent / "AGENTS.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    request: tuple[str, ...]
    model: type[BaseModel] | None
    response_status: str | None = None


OPERATIONS: dict[str, Operation] = {
    "workspace.get": Operation("GET", "/workspace", (), WorkspaceInfo),
    "workspace.consent": Operation("GET", "/consent", (), ConsentInfo),
    "verifications.create": Operation(
        "POST",
        "/verifications",
        ("callback_url", "external_id", "external_metadata", "metadata"),
        CreatedVerification,
        "201",
    ),
    "verifications.get": Operation("GET", "/verifications/{verification}", (), Verification),
    "verifications.accept_consent": Operation(
        "POST",
        "/verifications/{verification}/consent",
        ("consent_version_id", "text_sha256"),
        AcceptConsentResult,
    ),
    "verifications.upload_media": Operation(
        "POST",
        "/verifications/{verification}/media",
        ("file", "type", "side", "document"),
        None,
    ),
    "verifications.submit": Operation("POST", "/verifications/{verification}/submit", (), None),
    "verifications.document": Operation(
        "GET", "/verifications/{verification}/document", (), VerificationDocument
    ),
    "verifications.download_media": Operation(
        "GET", "/verifications/{verification}/media/{media}", (), None
    ),
    "verifications.download_media_to": Operation(
        "GET", "/verifications/{verification}/media/{media}", (), None
    ),
    "verifications.estimation": Operation(
        "GET", "/verifications/{verification}/estimation", (), AgeEstimation
    ),
    "verifications.block_face": Operation(
        "POST", "/verifications/{verification}/blocked-face", ("reason", "reason_code"), None
    ),
}

SYNC = {"workspace": Workspace, "verifications": Verifications}
ASYNC = {"workspace": AsyncWorkspace, "verifications": AsyncVerifications}


def schema_properties(schema: Any) -> list[str]:
    """Top-level property names, resolving $ref and merging allOf/anyOf/oneOf."""
    if not isinstance(schema, dict):
        return []
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return schema_properties(SPEC["components"]["schemas"][name])
    names: list[str] = []
    for combinator in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(combinator, []):
            names += schema_properties(sub)
    names += list(schema.get("properties", {}))
    return sorted(set(names))


def request_properties(op: Operation) -> list[str]:
    content = SPEC["paths"][op.path][op.method.lower()].get("requestBody", {}).get("content", {})
    schema = (content.get("application/json") or content.get("multipart/form-data") or {}).get(
        "schema", {}
    )
    return schema_properties(schema)


def response_properties(op: Operation) -> list[str]:
    responses = SPEC["paths"][op.path][op.method.lower()].get("responses", {})
    for code, response in responses.items():
        if not code.startswith("2") or (op.response_status and code != op.response_status):
            continue
        schema = response.get("content", {}).get("application/json", {}).get("schema")
        if schema:
            return schema_properties(schema)
    return []


def method(name: str, surface: dict[str, type]) -> Any:
    resource, attribute = name.split(".")
    return getattr(surface[resource], attribute)


def test_every_sdk_operation_exists_in_the_spec() -> None:
    for name, op in OPERATIONS.items():
        assert op.method.lower() in SPEC["paths"].get(op.path, {}), f"{name}: {op.method} {op.path}"


def test_every_spec_operation_is_covered() -> None:
    mapped = {(op.method, op.path) for op in OPERATIONS.values()}
    for path, methods in SPEC["paths"].items():
        for verb in methods:
            assert (verb.upper(), path) in mapped, f"no SDK method covers {verb.upper()} {path}"


@pytest.mark.parametrize("name", [n for n, op in OPERATIONS.items() if op.request])
def test_request_fields_match_the_spec(name: str) -> None:
    op = OPERATIONS[name]
    assert request_properties(op) == sorted(op.request)
    parameters = inspect.signature(method(name, SYNC)).parameters
    assert set(op.request) <= set(parameters), f"{name} is missing a request field"


@pytest.mark.parametrize("name", list(OPERATIONS))
def test_sync_and_async_surfaces_match(name: str) -> None:
    sync_params = list(inspect.signature(method(name, SYNC)).parameters)
    async_params = list(inspect.signature(method(name, ASYNC)).parameters)
    assert sync_params == async_params


def test_response_models_match_the_spec_where_it_describes_them() -> None:
    checked = []
    for name, op in OPERATIONS.items():
        properties = response_properties(op)
        if not properties or op.model is None:
            continue
        assert sorted(op.model.model_fields) == properties, f"response fields for {name}"
        checked.append(name)
    assert sorted(checked) == [
        "verifications.accept_consent",
        "verifications.create",
        "verifications.document",
        "verifications.estimation",
        "verifications.get",
        "workspace.consent",
        "workspace.get",
    ]


def test_calls_resolving_to_none_have_no_json_body() -> None:
    for name in ("verifications.upload_media", "verifications.submit", "verifications.block_face"):
        op = OPERATIONS[name]
        responses = SPEC["paths"][op.path][op.method.lower()]["responses"]
        for code, response in responses.items():
            if code.startswith("2"):
                assert "application/json" not in response.get("content", {}), f"{name} {code}"


def test_agents_md_documents_every_endpoint() -> None:
    for op in OPERATIONS.values():
        assert f"{op.method} {op.path}" in AGENTS, f"AGENTS.md is missing {op.method} {op.path}"


def test_reason_codes_match_the_api() -> None:
    op = OPERATIONS["verifications.block_face"]
    schema = SPEC["paths"][op.path]["post"]["requestBody"]["content"]["application/json"]["schema"]

    def find_enum(node: Any) -> list[str] | None:
        if isinstance(node, dict):
            if "$ref" in node:
                return find_enum(SPEC["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]])
            if "enum" in node:
                return list(node["enum"])
            for key in ("allOf", "anyOf", "oneOf"):
                for sub in node.get(key, []):
                    found = find_enum(sub)
                    if found:
                        return found
            reason = node.get("properties", {}).get("reason_code")
            if reason is not None:
                return find_enum(reason)
        return None

    assert sorted(find_enum(schema) or []) == sorted(code.value for code in BlockFaceReasonCode)
