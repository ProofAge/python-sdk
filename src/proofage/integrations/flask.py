"""Flask: a view decorator that passes the handler a verified `WebhookEvent`.

```python
from proofage.integrations.flask import proofage_webhook

@app.post("/webhooks/proofage")
@proofage_webhook
def webhook(event): ...
```

A failed verification answers 401 (400 for a signed body that is not an event, 500 when the
keys are not configured) with `{"error": {"code": ..., "message": ...}}`.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, overload

from ..errors import WebhookVerificationError
from ..models import WebhookEvent
from ..webhooks import verify_webhook
from ._common import error_body, missing_extra, report_failure

try:
    from flask import Response, jsonify, request
except ImportError as exc:
    raise missing_extra("proofage.integrations.flask", "flask") from exc

__all__ = ["proofage_webhook"]

View = Callable[..., Any]


@overload
def proofage_webhook(view: View, /) -> View: ...


@overload
def proofage_webhook(
    *,
    api_key: str | None = None,
    secret_key: str | None = None,
    tolerance: int | None = None,
) -> Callable[[View], View]: ...


def proofage_webhook(
    view: View | None = None,
    /,
    *,
    api_key: str | None = None,
    secret_key: str | None = None,
    tolerance: int | None = None,
) -> View | Callable[[View], View]:
    """Verify the request, then call the view with the `WebhookEvent` as its first argument.

    Use it bare (`@proofage_webhook`) with the keys in the environment, or with explicit
    keys (`@proofage_webhook(api_key=..., secret_key=...)`).
    """

    def decorate(inner: View) -> View:
        @functools.wraps(inner)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                event: WebhookEvent = verify_webhook(
                    request.get_data(),
                    dict(request.headers.items()),
                    api_key=api_key,
                    secret_key=secret_key,
                    tolerance=tolerance,
                )
            except WebhookVerificationError as error:
                report_failure(error)
                response: Response = jsonify(error_body(error))
                response.status_code = error.http_status
                return response
            return inner(event, *args, **kwargs)

        return wrapper

    return decorate(view) if view is not None else decorate
