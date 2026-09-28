"""What the framework integrations share."""

from __future__ import annotations

import logging
from typing import Any

from ..errors import WebhookVerificationError

logger = logging.getLogger("proofage")


def missing_extra(module: str, extra: str) -> ImportError:
    """The error an integration raises when its framework is not installed."""
    return ImportError(f'{module} needs {extra}: install it with pip install "proofage[{extra}]"')


def error_body(error: WebhookVerificationError) -> dict[str, Any]:
    """The JSON body of a failed verification, in the shape of the ProofAge API's own errors."""
    return {"error": {"code": error.code, "message": error.message}}


def report_failure(error: WebhookVerificationError) -> None:
    """Say in the application's own log when the server, not the sender, is at fault.

    A missing key answers 500 to ProofAge, and without this line the app itself would show
    nothing until someone opened the delivery log in the ProofAge console.
    """
    if error.http_status >= 500:
        logger.warning(
            "ProofAge webhook rejected with %s: %s. Set PROOFAGE_API_KEY and PROOFAGE_SECRET_KEY "
            "or pass api_key= and secret_key=.",
            error.code,
            error.message,
        )
