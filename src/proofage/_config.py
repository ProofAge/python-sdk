"""Client configuration: arguments, environment, defaults, and how the SDK names itself."""

from __future__ import annotations

import os
import platform
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from ._version import __version__
from .errors import ConfigurationError

DEFAULT_BASE_URL = "https://api.proofage.net"
DEFAULT_VERSION = "v1"
SDK_HEADER = "X-ProofAge-Sdk"
OWN_TOKEN_NAME = "python"

_TOKEN = re.compile(r"[\x21-\x2E\x30-\x7E]+/[\x21-\x2E\x30-\x7E]+")
_PRINTABLE = re.compile(r"[\x20-\x7E]+")
_HTTPX_DEFAULT_USER_AGENT = "python-httpx/"


@dataclass(frozen=True, repr=False)
class ClientConfig:
    """Resolved settings of one client. `user_agent` None keeps the caller client's own."""

    api_key: str
    secret_key: str
    base_url: str
    version: str
    timeout: float
    retry_attempts: int
    retry_delay: float
    download_retry_attempts: int
    sdk_header: str
    user_agent: str | None

    def __repr__(self) -> str:
        return (
            f"ClientConfig(base_url={self.base_url!r}, version={self.version!r}, "
            f"api_key={mask_key(self.api_key)!r}, secret_key='***')"
        )


def mask_key(key: str) -> str:
    """The first eight characters (the `pk_live_` / `pk_test_` prefix) and nothing more."""
    return f"{key[:8]}***" if len(key) > 12 else "***"


def normalize_base_url(raw: str, version: str) -> str:
    """The API origin without the version; a trailing `/{version}` is stripped."""
    parts = urlsplit(raw.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ConfigurationError(
            f"Invalid base_url {raw!r}: expected the API origin, e.g. {DEFAULT_BASE_URL} "
            f"(without /{version})"
        )
    if parts.query or parts.fragment:
        raise ConfigurationError(
            f"Invalid base_url {raw!r}: it must not carry a query string or fragment"
        )
    path = parts.path.rstrip("/")
    suffix = "/" + version.strip("/")
    if path.endswith(suffix):
        path = path[: -len(suffix)]
    return f"{parts.scheme}://{parts.netloc}{path}"


def build_sdk_header(wrapper_tokens: Sequence[str] = ()) -> str:
    """`X-ProofAge-Sdk`: wrapper tokens, outermost first, then `python/{version}`, always last."""
    tokens: list[str] = []
    for token in wrapper_tokens:
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise ConfigurationError(
                f"Invalid sdk_tokens entry {token!r}: expected '<name>/<version>' in printable "
                "ASCII with no spaces, e.g. 'telegram-bot/1.2.0'"
            )
        if token.split("/", 1)[0].lower() != OWN_TOKEN_NAME:
            tokens.append(token)
    tokens.append(f"{OWN_TOKEN_NAME}/{__version__}")
    return " ".join(tokens)


def default_user_agent() -> str:
    """`ProofAge-Python/{version} (Python {x.y.z})`."""
    return f"ProofAge-Python/{__version__} (Python {platform.python_version()})"


def _choose_user_agent(
    explicit: str | None, client_headers: Mapping[str, str] | None
) -> str | None:
    if explicit is not None and explicit.strip() != "":
        if not _PRINTABLE.fullmatch(explicit):
            raise ConfigurationError(
                f"Invalid user_agent {explicit!r}: use printable ASCII only, with no line breaks"
            )
        return explicit
    existing = client_headers.get("user-agent") if client_headers is not None else None
    if existing and not existing.startswith(_HTTPX_DEFAULT_USER_AGENT):
        return None
    return default_user_agent()


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _env_number(name: str, kind: type[int] | type[float]) -> int | float | None:
    value = _env(name)
    if value is None:
        return None
    try:
        return kind(value)
    except ValueError:
        raise ConfigurationError(f"{name} must be a number, got {value!r}") from None


def _first(*values: float | int | None, default: float) -> float:
    for value in values:
        if value is not None:
            return float(value)
    return default


def resolve_config(
    *,
    api_key: str | None,
    secret_key: str | None,
    base_url: str | None,
    version: str | None,
    timeout: float | None,
    retry_attempts: int | None,
    retry_delay: float | None,
    download_retry_attempts: int | None,
    sdk_tokens: Sequence[str],
    user_agent: str | None,
    client_headers: Mapping[str, str] | None,
) -> ClientConfig:
    """Argument, then environment variable (in the Laravel SDK's units), then default."""
    key = api_key or _env("PROOFAGE_API_KEY")
    if not key:
        raise ConfigurationError("API key is required: pass api_key or set PROOFAGE_API_KEY")
    secret = secret_key or _env("PROOFAGE_SECRET_KEY")
    if not secret:
        raise ConfigurationError(
            "Secret key is required: pass secret_key or set PROOFAGE_SECRET_KEY"
        )

    resolved_version = version or _env("PROOFAGE_VERSION") or DEFAULT_VERSION
    env_delay_ms = _env_number("PROOFAGE_RETRY_DELAY", int)

    resolved_timeout = _first(timeout, _env_number("PROOFAGE_TIMEOUT", float), default=30.0)
    attempts = int(_first(retry_attempts, _env_number("PROOFAGE_RETRY_ATTEMPTS", int), default=3))
    delay = _first(retry_delay, None if env_delay_ms is None else env_delay_ms / 1000, default=1.0)
    download_attempts = int(
        _first(
            download_retry_attempts,
            _env_number("PROOFAGE_DOWNLOAD_RETRY_ATTEMPTS", int),
            default=1,
        )
    )

    if resolved_timeout <= 0:
        raise ConfigurationError("timeout must be greater than 0 seconds")
    if attempts < 1:
        raise ConfigurationError("retry_attempts must be at least 1")
    if delay < 0:
        raise ConfigurationError("retry_delay must not be negative")
    if download_attempts < 1:
        raise ConfigurationError("download_retry_attempts must be at least 1")

    return ClientConfig(
        api_key=key,
        secret_key=secret,
        base_url=normalize_base_url(
            base_url or _env("PROOFAGE_BASE_URL") or DEFAULT_BASE_URL, resolved_version
        ),
        version=resolved_version,
        timeout=resolved_timeout,
        retry_attempts=attempts,
        retry_delay=delay,
        download_retry_attempts=download_attempts,
        sdk_header=build_sdk_header(sdk_tokens),
        user_agent=_choose_user_agent(user_agent, client_headers),
    )
