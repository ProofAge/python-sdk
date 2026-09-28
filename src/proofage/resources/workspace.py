"""`GET /workspace` and `GET /consent`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import ConsentInfo, WorkspaceInfo

if TYPE_CHECKING:
    from .._async_client import AsyncProofAge
    from .._client import ProofAge


class Workspace:
    """The workspace the API key belongs to."""

    def __init__(self, client: ProofAge) -> None:
        self._client = client

    def get(self) -> WorkspaceInfo:
        """`GET /workspace`."""
        return self._client._get_model("workspace", WorkspaceInfo)

    def consent(self) -> ConsentInfo:
        """`GET /consent`: the consent text version a person must accept."""
        return self._client._get_model("consent", ConsentInfo)


class AsyncWorkspace:
    """The workspace the API key belongs to."""

    def __init__(self, client: AsyncProofAge) -> None:
        self._client = client

    async def get(self) -> WorkspaceInfo:
        """`GET /workspace`."""
        return await self._client._get_model("workspace", WorkspaceInfo)

    async def consent(self) -> ConsentInfo:
        """`GET /consent`: the consent text version a person must accept."""
        return await self._client._get_model("consent", ConsentInfo)
