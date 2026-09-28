"""Django: a view decorator that verifies the webhook and sets `request.proofage_event`.

```python
from proofage.integrations.django import proofage_webhook

@proofage_webhook
def webhook(request):
    event = request.proofage_event
```

The decorator makes the view CSRF-exempt and POST-only (405 otherwise). A failed verification
answers 401 (400 for a signed body that is not an event, 500 when the keys are not configured)
with `{"error": {"code": ..., "message": ...}}`. Synchronous views only.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, overload

from ..errors import WebhookVerificationError
from ..webhooks import verify_webhook
from ._common import error_body, missing_extra, report_failure

try:
    from django.http import HttpRequest, HttpResponse, JsonResponse
    from django.views.decorators.csrf import csrf_exempt
    from django.views.decorators.http import require_POST
except ImportError as exc:
    raise missing_extra("proofage.integrations.django", "django") from exc

__all__ = ["proofage_webhook"]

View = Callable[..., HttpResponse]


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
    """Verify the request, set `request.proofage_event`, then call the view.

    Use it bare (`@proofage_webhook`) with the keys in the environment, or with explicit
    keys (`@proofage_webhook(api_key=..., secret_key=...)`).
    """

    def decorate(inner: View) -> View:
        @csrf_exempt
        @require_POST
        @functools.wraps(inner)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            try:
                event = verify_webhook(
                    request.body,
                    request.headers,
                    api_key=api_key,
                    secret_key=secret_key,
                    tolerance=tolerance,
                )
            except WebhookVerificationError as error:
                report_failure(error)
                return JsonResponse(error_body(error), status=error.http_status)
            request.proofage_event = event
            return inner(request, *args, **kwargs)

        return wrapper

    return decorate(view) if view is not None else decorate
