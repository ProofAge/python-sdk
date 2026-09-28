from __future__ import annotations

import respx

from proofage.models import ConsentInfo, WorkspaceInfo

from .conftest import Harness

WORKSPACE = {
    "id": "ws-1",
    "name": "Shop",
    "flow_type": "age",
    "mode": "live",
    "age_mode": "estimation",
    "age_threshold": 18,
    "verification_type": "age",
    "redirect_url": None,
    "webhook_url": "https://shop.example/hook",
    "allow_expired_documents": False,
    "allow_duplicate_accounts": True,
}


def test_get_workspace(sdk: Harness, api: respx.MockRouter) -> None:
    api.get("/workspace").respond(200, json=WORKSPACE)
    workspace = sdk.call(lambda c: c.workspace.get())
    assert isinstance(workspace, WorkspaceInfo)
    assert workspace.age_threshold == 18


def test_get_consent(sdk: Harness, api: respx.MockRouter) -> None:
    api.get("/consent").respond(
        200, json={"id": 3, "version": "2026-01", "text_sha256": "ab" * 32, "url": "https://x"}
    )
    consent = sdk.call(lambda c: c.workspace.consent())
    assert isinstance(consent, ConsentInfo)
    assert consent.id == 3


def test_an_unexpected_response_shape_is_a_proofage_error(
    sdk: Harness, api: respx.MockRouter
) -> None:
    import pytest

    from proofage.errors import ProofAgeError

    api.get("/workspace").respond(200, json={"id": "ws-1", "name": "a.person@example.com"})
    with pytest.raises(
        ProofAgeError, match="Unexpected response shape from GET /v1/workspace"
    ) as e:
        sdk.call(lambda c: c.workspace.get())
    assert "a.person@example.com" not in e.value.message
    assert "flow_type" in e.value.message
