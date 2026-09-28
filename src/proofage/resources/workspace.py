"""`GET /workspace` and `GET /consent`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._async_client import AsyncProofAge
    from .._client import ProofAge


class Workspace:
    """The workspace the API key belongs to."""

    def __init__(self, client: ProofAge) -> None:
        self._client = client

    def get(self) -> Any:
        return self._client._get("workspace")

    def consent(self) -> Any:
        return self._client._get("consent")


class AsyncWorkspace:
    """The workspace the API key belongs to."""

    def __init__(self, client: AsyncProofAge) -> None:
        self._client = client

    async def get(self) -> Any:
        return await self._client._get("workspace")

    async def consent(self) -> Any:
        return await self._client._get("consent")
