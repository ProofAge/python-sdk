"""The synchronous client."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from types import TracebackType
from typing import Any

import httpx

from ._config import resolve_config
from ._transport import (
    DOWNLOAD_ACCEPT,
    NEW_SECOND_MARGIN,
    NEW_SECOND_MAX_WAITS,
    M,
    PreparedRequest,
    api_path,
    decode_success,
    error_for_response,
    is_replayed_request,
    is_retryable_exception,
    is_retryable_status,
    is_signed_once,
    is_timestamp_out_of_range,
    parse_http_date,
    parse_model,
    parse_retry_after,
    prepare_json,
    prepare_multipart,
    retry_delay,
    within_retry_after_cap,
)
from .errors import TransportError
from .resources.verifications import Verifications
from .resources.webhook_subscriptions import WebhookSubscriptions
from .resources.workspace import Workspace


class ProofAge:
    """Synchronous ProofAge client. Use it as a context manager or call `close()`."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        version: str | None = None,
        timeout: float | None = None,
        retry_attempts: int | None = None,
        retry_delay: float | None = None,
        download_retry_attempts: int | None = None,
        sdk_tokens: Sequence[str] = (),
        user_agent: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = resolve_config(
            api_key=api_key,
            secret_key=secret_key,
            base_url=base_url,
            version=version,
            timeout=timeout,
            retry_attempts=retry_attempts,
            retry_delay=retry_delay,
            download_retry_attempts=download_retry_attempts,
            sdk_tokens=sdk_tokens,
            user_agent=user_agent,
            client_headers=http_client.headers if http_client is not None else None,
        )
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client(timeout=self._config.timeout)
        self._clock: Callable[[], float] = time.time
        self._clock_offset = 0.0
        self._sleep: Callable[[float], None] = time.sleep
        self.workspace = Workspace(self)
        self.verifications = Verifications(self)
        self.webhook_subscriptions = WebhookSubscriptions(self)

    def __repr__(self) -> str:
        return f"ProofAge({self._config!r})"

    def close(self) -> None:
        """Close the HTTP client, unless it was passed in by the caller."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> ProofAge:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _get(self, endpoint: str, query: Mapping[str, Any] | None = None) -> Any:
        prepared = prepare_json(self._config, "GET", endpoint, query=query)
        return self._send(prepared, expect_body=True)

    def _post(
        self, endpoint: str, payload: Mapping[str, Any], *, idempotency_key: str | None = None
    ) -> Any:
        prepared = prepare_json(
            self._config, "POST", endpoint, payload, idempotency_key=idempotency_key
        )
        return self._send(prepared, expect_body=True)

    def _get_model(
        self, endpoint: str, model: type[M], query: Mapping[str, Any] | None = None
    ) -> M:
        data = self._get(endpoint, query)
        return parse_model(model, data, f"GET {api_path(self._config, endpoint)}")

    def _post_model(
        self,
        endpoint: str,
        payload: Mapping[str, Any],
        model: type[M],
        *,
        idempotency_key: str | None = None,
    ) -> M:
        data = self._post(endpoint, payload, idempotency_key=idempotency_key)
        return parse_model(model, data, f"POST {api_path(self._config, endpoint)}")

    def _post_empty(self, endpoint: str, payload: Mapping[str, Any] | None = None) -> None:
        self._send(prepare_json(self._config, "POST", endpoint, payload), expect_body=False)

    def _delete(self, endpoint: str) -> None:
        self._send(prepare_json(self._config, "DELETE", endpoint), expect_body=False)

    def _delete_model(self, endpoint: str, payload: Mapping[str, Any], model: type[M]) -> M:
        prepared = prepare_json(self._config, "DELETE", endpoint, payload)
        data = self._send(prepared, expect_body=True)
        return parse_model(model, data, f"DELETE {api_path(self._config, endpoint)}")

    def _post_multipart(
        self, endpoint: str, fields: Mapping[str, Any], *, filename: str, content: bytes
    ) -> None:
        prepared = prepare_multipart(
            self._config, "POST", endpoint, fields, filename=filename, content=content
        )
        self._send(prepared, expect_body=False)

    def _now(self) -> float:
        """Unix time as the server sees it: the local clock plus the skew learned from `Date`."""
        return self._clock() + self._clock_offset

    def _await_new_second(self, previous: int) -> None:
        """Wait until the clock is in another whole second than `previous`, the second the last
        attempt was signed in: a retry of a non-GET in the same second would repeat its
        signature. Loops because a sleep can wake early."""
        for _ in range(NEW_SECOND_MAX_WAITS):
            now = self._now()
            if int(now) != previous:
                return
            self._sleep(previous + 1 - now + NEW_SECOND_MARGIN)

    def _send(self, prepared: PreparedRequest, *, expect_body: bool) -> Any:
        attempts = self._config.retry_attempts
        attempt = 0
        replay_resent = False
        skew_resent = False
        previous: int | None = None
        while attempt < attempts:
            last = attempt == attempts - 1
            if previous is not None and is_signed_once(prepared.method):
                self._await_new_second(previous)
            signed_at = self._now()
            previous = int(signed_at)
            try:
                response = self._http.request(
                    prepared.method,
                    prepared.url,
                    headers=prepared.signed_headers(self._config.secret_key, signed_at),
                    content=prepared.content,
                    data=prepared.data,
                    files=prepared.files,
                    timeout=self._config.timeout,
                )
            except httpx.TransportError as exc:
                if not last and is_retryable_exception(
                    prepared.method, exc, keyed=prepared.idempotency_key is not None
                ):
                    self._sleep(retry_delay(self._config, attempt, None, None))
                    attempt += 1
                    continue
                raise TransportError(f"{prepared.method} {prepared.url} failed: {exc}") from exc

            if response.is_success:
                return decode_success(
                    response.status_code,
                    response.text,
                    prepared.url,
                    response.headers.get("content-type"),
                    expect_body=expect_body,
                )
            if not replay_resent and is_replayed_request(
                prepared.method, response.status_code, response.text
            ):
                # Not counted against retry_attempts, and sent even when the retry policy would
                # not retry: the middleware refused it before anything ran. The next attempt
                # waits for a new second like any other.
                replay_resent = True
                continue
            if not skew_resent and is_timestamp_out_of_range(response.status_code, response.text):
                server_time = parse_http_date(response.headers.get("date"))
                if server_time is not None:
                    # This host's clock is off: learn the skew once, keep it for the client's
                    # later requests, and resend this one, outside retry_attempts.
                    skew_resent = True
                    self._clock_offset = server_time - self._clock()
                    continue
            retry_after = parse_retry_after(response.headers.get("retry-after"), self._now())
            if (
                not last
                and is_retryable_status(
                    prepared.method,
                    response.status_code,
                    keyed=prepared.idempotency_key is not None,
                    text=response.text,
                )
                and within_retry_after_cap(response.status_code, retry_after, response.text)
            ):
                self._sleep(retry_delay(self._config, attempt, response.status_code, retry_after))
                attempt += 1
                continue
            raise error_for_response(response.status_code, response.text, retry_after)
        raise AssertionError("unreachable: the loop returns or raises")

    @contextmanager
    def _stream_media(self, endpoint: str) -> Iterator[httpx.Response]:
        prepared = prepare_json(self._config, "GET", endpoint, accept=DOWNLOAD_ACCEPT)
        attempts = self._config.download_retry_attempts
        attempt = 0
        skew_resent = False
        while attempt < attempts:
            request = self._http.build_request(
                "GET",
                prepared.url,
                headers=prepared.signed_headers(self._config.secret_key, self._now()),
                timeout=self._config.timeout,
            )
            try:
                response = self._http.send(request, stream=True)
            except httpx.TransportError as exc:
                if attempt < attempts - 1:
                    self._sleep(retry_delay(self._config, attempt, None, None))
                    attempt += 1
                    continue
                raise TransportError(f"GET {prepared.url} failed: {exc}") from exc
            try:
                if not response.is_success:
                    response.read()
                    server_time = parse_http_date(response.headers.get("date"))
                    if (
                        not skew_resent
                        and server_time is not None
                        and is_timestamp_out_of_range(response.status_code, response.text)
                    ):
                        # Learn the clock skew once and resend, outside the download attempts.
                        skew_resent = True
                        self._clock_offset = server_time - self._clock()
                        continue
                    raise error_for_response(
                        response.status_code,
                        response.text,
                        parse_retry_after(response.headers.get("retry-after"), self._now()),
                    )
                yield response
            finally:
                response.close()
            return
