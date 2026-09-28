"""Python client for the ProofAge age and identity verification API."""

from __future__ import annotations

from ._async_client import AsyncProofAge
from ._client import ProofAge
from ._version import __version__
from .errors import (
    AuthenticationError,
    ConfigurationError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    ProofAgeError,
    RateLimitError,
    ServerError,
    TransportError,
    ValidationError,
    WebhookVerificationError,
)
from .models import BlockFaceReasonCode, VerificationStatus

__all__ = [
    "AsyncProofAge",
    "AuthenticationError",
    "BlockFaceReasonCode",
    "ConfigurationError",
    "NotFoundError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "ProofAge",
    "ProofAgeError",
    "RateLimitError",
    "ServerError",
    "TransportError",
    "ValidationError",
    "VerificationStatus",
    "WebhookVerificationError",
    "__version__",
]
