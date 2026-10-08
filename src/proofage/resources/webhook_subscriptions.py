"""The `/webhook-subscriptions` endpoints (REST hooks)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..models import VerificationStatus, WebhookSubscription, WebhookSubscriptionList
from ._payloads import compact, path_segment, status_list

if TYPE_CHECKING:
    from .._async_client import AsyncProofAge
    from .._client import ProofAge


def _subscription_path(subscription_id: str) -> str:
    return f"webhook-subscriptions/{path_segment(subscription_id, 'subscription_id')}"


def _create_payload(
    url: str,
    statuses: Sequence[VerificationStatus | str] | None,
    include_document_data: bool | None,
) -> dict[str, object]:
    return compact(
        {
            "url": url,
            "statuses": status_list(statuses),
            "include_document_data": include_document_data,
        }
    )


class WebhookSubscriptions:
    """Extra URLs that receive the decision webhooks, for REST hooks such as Zapier."""

    def __init__(self, client: ProofAge) -> None:
        self._client = client

    def create(
        self,
        *,
        url: str,
        statuses: Sequence[VerificationStatus | str] | None = None,
        include_document_data: bool | None = None,
    ) -> WebhookSubscription:
        """`POST /webhook-subscriptions`. Up to 50 per workspace.

        `statuses` limits the deliveries to these decision statuses (`approved`, `declined`,
        `resubmission_requested`, `review`, `abandoned`, `expired`); None sends all of them.
        `include_document_data=True` adds the document, the fingerprint signals and the
        moderator's name and email to the body; the API's default leaves them out.
        """
        payload = _create_payload(url, statuses, include_document_data)
        return self._client._post_model("webhook-subscriptions", payload, WebhookSubscription)

    def list(self) -> WebhookSubscriptionList:
        """`GET /webhook-subscriptions`: every subscription of the workspace, newest first."""
        return self._client._get_model("webhook-subscriptions", WebhookSubscriptionList)

    def delete(self, subscription_id: str) -> None:
        """`DELETE /webhook-subscriptions/{id}`. Deliveries already queued are not sent."""
        self._client._delete(_subscription_path(subscription_id))


class AsyncWebhookSubscriptions:
    """Extra URLs that receive the decision webhooks, for REST hooks such as Zapier."""

    def __init__(self, client: AsyncProofAge) -> None:
        self._client = client

    async def create(
        self,
        *,
        url: str,
        statuses: Sequence[VerificationStatus | str] | None = None,
        include_document_data: bool | None = None,
    ) -> WebhookSubscription:
        """`POST /webhook-subscriptions`. Up to 50 per workspace (see the sync twin)."""
        payload = _create_payload(url, statuses, include_document_data)
        return await self._client._post_model("webhook-subscriptions", payload, WebhookSubscription)

    async def list(self) -> WebhookSubscriptionList:
        """`GET /webhook-subscriptions`: every subscription of the workspace, newest first."""
        return await self._client._get_model("webhook-subscriptions", WebhookSubscriptionList)

    async def delete(self, subscription_id: str) -> None:
        """`DELETE /webhook-subscriptions/{id}`. Deliveries already queued are not sent."""
        await self._client._delete(_subscription_path(subscription_id))
