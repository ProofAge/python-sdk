"""What the framework integrations share."""

from __future__ import annotations

from typing import Any

from ..errors import WebhookVerificationError


def missing_extra(module: str, extra: str) -> ImportError:
    """The error an integration raises when its framework is not installed."""
    return ImportError(f'{module} needs {extra}: install it with pip install "proofage[{extra}]"')


def error_body(error: WebhookVerificationError) -> dict[str, Any]:
    """The JSON body of a failed verification, in the shape of the ProofAge API's own errors."""
    return {"error": {"code": error.code, "message": error.message}}
