"""Every exception the SDK raises."""

from __future__ import annotations

from typing import Any


class ProofAgeError(Exception):
    """A request to the ProofAge API failed.

    `code` is the API's machine-readable code when it sent one, `error_data`
    the error object as sent, `response_body` the raw text.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        error_data: dict[str, Any] | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.error_data = error_data
        self.response_body = response_body


class AuthenticationError(ProofAgeError):
    """401: the API key or the request signature was not accepted."""


class PaymentRequiredError(ProofAgeError):
    """402: a live workspace has no way to pay (`PAYMENT_METHOD_REQUIRED`)."""


class PermissionDeniedError(ProofAgeError):
    """403: the verification is not in this workspace."""


class NotFoundError(ProofAgeError):
    """404: no such resource."""


class ValidationError(ProofAgeError):
    """422: invalid fields (`errors`), or a media rejection carrying a `code`."""

    def __init__(
        self,
        message: str,
        *,
        errors: dict[str, list[str]] | None = None,
        status_code: int | None = None,
        code: str | None = None,
        error_data: dict[str, Any] | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            code=code,
            error_data=error_data,
            response_body=response_body,
        )
        self.errors = errors or {}


class RateLimitError(ProofAgeError):
    """429 after the retries ran out; `retry_after` is the server's advice in seconds."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        status_code: int | None = None,
        code: str | None = None,
        error_data: dict[str, Any] | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            code=code,
            error_data=error_data,
            response_body=response_body,
        )
        self.retry_after = retry_after


class ServerError(ProofAgeError):
    """5xx."""


class TransportError(ProofAgeError):
    """No response: DNS, connection, TLS or timeout. The httpx exception is `__cause__`."""


class ConfigurationError(Exception):
    """Missing or invalid configuration, raised when a client is built."""


class WebhookVerificationError(Exception):
    """An inbound webhook failed verification; `code` says which check."""

    def __init__(self, code: str, message: str, http_status: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
