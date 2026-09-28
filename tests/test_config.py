from __future__ import annotations

import platform
from typing import Any

import pytest

from proofage._config import (
    build_sdk_header,
    default_user_agent,
    normalize_base_url,
    resolve_config,
)
from proofage.errors import ConfigurationError

from .conftest import API_KEY, SECRET_KEY


def config(**overrides: Any) -> Any:
    arguments: dict[str, Any] = {
        "api_key": API_KEY,
        "secret_key": SECRET_KEY,
        "base_url": None,
        "version": None,
        "timeout": None,
        "retry_attempts": None,
        "retry_delay": None,
        "download_retry_attempts": None,
        "sdk_tokens": (),
        "user_agent": None,
        "client_headers": None,
    }
    arguments.update(overrides)
    return resolve_config(**arguments)


def test_defaults() -> None:
    c = config()
    assert c.base_url == "https://api.proofage.xyz"
    assert c.version == "v1"
    assert c.timeout == 30.0
    assert c.retry_attempts == 3
    assert c.retry_delay == 1.0
    assert c.download_retry_attempts == 1


def test_keys_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFAGE_API_KEY", "pk_env_key_abcdefgh")
    monkeypatch.setenv("PROOFAGE_SECRET_KEY", "sk_env")
    c = config(api_key=None, secret_key=None)
    assert c.api_key == "pk_env_key_abcdefgh"
    assert c.secret_key == "sk_env"


@pytest.mark.parametrize(
    ("missing", "variable"),
    [("api_key", "PROOFAGE_API_KEY"), ("secret_key", "PROOFAGE_SECRET_KEY")],
)
def test_a_missing_key_names_the_variable(missing: str, variable: str) -> None:
    with pytest.raises(ConfigurationError, match=variable):
        config(**{missing: None})


def test_environment_units_match_the_laravel_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFAGE_RETRY_DELAY", "1000")
    monkeypatch.setenv("PROOFAGE_TIMEOUT", "12")
    monkeypatch.setenv("PROOFAGE_RETRY_ATTEMPTS", "5")
    monkeypatch.setenv("PROOFAGE_DOWNLOAD_RETRY_ATTEMPTS", "2")
    c = config()
    assert c.retry_delay == 1.0
    assert c.timeout == 12.0
    assert c.retry_attempts == 5
    assert c.download_retry_attempts == 2


def test_arguments_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFAGE_RETRY_DELAY", "5000")
    assert config(retry_delay=0.25).retry_delay == 0.25


def test_a_non_numeric_environment_value_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROOFAGE_RETRY_ATTEMPTS", "three")
    with pytest.raises(ConfigurationError, match="PROOFAGE_RETRY_ATTEMPTS"):
        config()


@pytest.mark.parametrize(
    "overrides",
    [{"timeout": 0}, {"retry_attempts": 0}, {"retry_delay": -1}, {"download_retry_attempts": 0}],
)
def test_out_of_range_numbers_are_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ConfigurationError):
        config(**overrides)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://api.proofage.xyz", "https://api.proofage.xyz"),
        ("https://api.proofage.xyz/", "https://api.proofage.xyz"),
        ("https://api.proofage.xyz/v1", "https://api.proofage.xyz"),
        ("https://api.proofage.xyz/v1/", "https://api.proofage.xyz"),
        ("http://localhost:8000/proxy", "http://localhost:8000/proxy"),
    ],
)
def test_base_url_normalisation(raw: str, expected: str) -> None:
    assert normalize_base_url(raw, "v1") == expected


@pytest.mark.parametrize(
    "raw",
    [
        "api.proofage.xyz",
        "ftp://api.proofage.xyz",
        "https://api.proofage.xyz?x=1",
        "https://api.proofage.xyz#frag",
    ],
)
def test_unusable_base_urls_are_refused(raw: str) -> None:
    with pytest.raises(ConfigurationError, match="base_url"):
        normalize_base_url(raw, "v1")


def test_sdk_header_puts_wrappers_first_and_the_sdk_last() -> None:
    assert build_sdk_header() == "python/0.1.0"
    assert build_sdk_header(["telegram-bot/1.2.0", "shop/2"]) == (
        "telegram-bot/1.2.0 shop/2 python/0.1.0"
    )


def test_a_wrapper_cannot_impersonate_the_sdk() -> None:
    assert build_sdk_header(["Python/9.9.9"]) == "python/0.1.0"


@pytest.mark.parametrize("token", ["no-slash", "a/b/c", "has space/1", "ünï/1", "", "/1", "a/"])
def test_invalid_tokens_fail_at_construction(token: str) -> None:
    with pytest.raises(ConfigurationError, match="sdk_tokens"):
        config(sdk_tokens=[token])


def test_default_user_agent() -> None:
    assert default_user_agent() == f"ProofAge-Python/0.1.0 (Python {platform.python_version()})"
    assert config().user_agent == default_user_agent()


def test_an_explicit_user_agent_is_kept_and_validated() -> None:
    assert config(user_agent="MyShop/1.0").user_agent == "MyShop/1.0"
    with pytest.raises(ConfigurationError, match="user_agent"):
        config(user_agent="Bad\r\nInjected: yes")
    with pytest.raises(ConfigurationError, match="user_agent"):
        config(user_agent="Café/1")


def test_a_caller_clients_own_user_agent_is_kept() -> None:
    assert config(client_headers={"user-agent": "Corp-Proxy/3"}).user_agent is None
    assert config(client_headers={"user-agent": "python-httpx/0.28.1"}).user_agent == (
        default_user_agent()
    )


def test_repr_never_shows_the_secret() -> None:
    text = repr(config())
    assert SECRET_KEY not in text
    assert API_KEY not in text
    assert "secret_key='***'" in text
