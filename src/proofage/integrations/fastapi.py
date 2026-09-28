"""FastAPI / Starlette: a dependency that hands the handler a verified `WebhookEvent`.

```python
from proofage.integrations.fastapi import ProofAgeWebhook

@app.post("/webhooks/proofage")
async def proofage_webhook(event: ProofAgeWebhook): ...
```

A failed verification answers 401 (400 for a signed body that is not an event, 500 when the
keys are not configured) with `{"detail": {"code": ..., "message": ...}}`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from ..errors import WebhookVerificationError
from ..models import WebhookEvent
from ..webhooks import verify_webhook
from ._common import error_body, missing_extra

try:
    from fastapi import Depends, HTTPException, Request
except ImportError as exc:
    raise missing_extra("proofage.integrations.fastapi", "fastapi") from exc

__all__ = ["ProofAgeWebhook", "webhook_dependency"]


def webhook_dependency(
    *,
    api_key: str | None = None,
    secret_key: str | None = None,
    tolerance: int | None = None,
) -> Callable[[Request], Awaitable[WebhookEvent]]:
    """A dependency verifying the request with explicit keys (default: the environment)."""

    async def verified_event(request: Request) -> WebhookEvent:
        try:
            return verify_webhook(
                await request.body(),
                request.headers,
                api_key=api_key,
                secret_key=secret_key,
                tolerance=tolerance,
            )
        except WebhookVerificationError as error:
            raise HTTPException(
                status_code=error.http_status, detail=error_body(error)["error"]
            ) from error

    return verified_event


ProofAgeWebhook = Annotated[WebhookEvent, Depends(webhook_dependency())]
"""A handler parameter annotated with this receives the verified event; keys come from
`PROOFAGE_API_KEY` and `PROOFAGE_SECRET_KEY`. For explicit keys use `webhook_dependency(...)`."""
