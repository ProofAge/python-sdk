# proofage — ProofAge for Python

Python client for [ProofAge](https://proofage.xyz), the age and identity verification API. It
gives you a sync and an async client for every `/v1` endpoint, typed Pydantic models, typed errors
and webhook verification — enough to go from `pip install` to a verified result in a few minutes,
from a backend, a Telegram bot or an AI agent.

## Install

```bash
pip install proofage
# or
uv add proofage
```

## Quick start

Set `PROOFAGE_API_KEY` and `PROOFAGE_SECRET_KEY` (from your workspace in the ProofAge console),
then:

```python
from proofage import ProofAge

with ProofAge() as client:
    verification = client.verifications.create(
        external_id="candidate-42",
        callback_url="https://your-app.example/verified",
    )
    print(verification.url)  # send the person here

    # later, or when the webhook arrives
    print(client.verifications.get(verification.id).status)
```

The person opens `verification.url` on their phone, ProofAge runs the checks, and you learn the
outcome from a webhook (below) or by calling `get()`.

## Async

`AsyncProofAge` has the same methods, awaited — the natural choice in aiogram bots, FastAPI and
other asyncio code:

```python
from proofage import AsyncProofAge

async with AsyncProofAge() as client:
    verification = await client.verifications.create(external_id="tg-12345")
```

## Receiving results (webhooks)

ProofAge POSTs the outcome to your workspace's webhook URL. The framework extras verify it for
you and hand your handler a typed `WebhookEvent`; install the one you use:

```bash
pip install "proofage[fastapi]"   # or proofage[django], proofage[flask]
```

FastAPI:

```python
from fastapi import FastAPI
from proofage.integrations.fastapi import ProofAgeWebhook

app = FastAPI()


@app.post("/webhooks/proofage")
async def proofage_webhook(event: ProofAgeWebhook):
    print(event.verification_id, event.status, event.reason)
```

Django (CSRF-exempt and POST-only; the event is `request.proofage_event`):

```python
from django.http import HttpResponse
from proofage.integrations.django import proofage_webhook


@proofage_webhook
def webhook(request):
    event = request.proofage_event
    return HttpResponse(status=200)
```

Flask:

```python
from proofage.integrations.flask import proofage_webhook


@app.post("/webhooks/proofage")
@proofage_webhook
def webhook(event):
    return "", 200
```

A request that fails verification never reaches your handler: it is answered 401 with the reason
(`INVALID_SIGNATURE`, `TIMESTAMP_TOO_OLD`, …), 400 for a signed body that is not a webhook
event, or 500 when the keys are not configured. The keys come from `PROOFAGE_API_KEY` and
`PROOFAGE_SECRET_KEY`; to pass them explicitly use `@proofage_webhook(api_key=..., secret_key=...)`
or, in FastAPI, `Depends(webhook_dependency(api_key=..., secret_key=...))`. The Django and Flask
decorators are for synchronous views, and nothing in front of them (a middleware, an earlier
`request.body` read in Django) may have consumed the body. A missing key is also logged as a
warning by the `proofage` logger, so it shows in your own logs and not only in ProofAge's.

Any other framework (aiohttp, Starlette, Litestar, …) calls the same check itself. Verify with the
**raw** request body, not a re-serialised copy of its JSON:

```python
from proofage import WebhookVerificationError, verify_webhook

try:
    event = verify_webhook(raw_body, headers)
except WebhookVerificationError as error:
    ...  # answer error.http_status
```

A delivery can arrive more than once: de-duplicate on `event.delivery_id`, which stays the same
on every automatic retry.

Runnable examples live in [`examples/`](https://github.com/ProofAge/python-sdk/tree/main/examples):
a Telegram bot on aiogram, a FastAPI app and Django views.

## Statuses

`event.status` and `verification.status` are `VerificationStatus` members (`APPROVED`,
`DECLINED`, `RESUBMISSION_REQUESTED`, `REVIEW`, …). A status this version does not know yet
arrives as a plain string instead of raising, so compare with `==`:

```python
from proofage import VerificationStatus

if event.status == VerificationStatus.APPROVED:
    ...
```

Unknown fields are kept too, in `model.model_extra`; `model.model_dump(mode="json")` gives a plain
dict.

## Errors

```python
from proofage import PaymentRequiredError, ProofAgeError, RateLimitError, ValidationError

try:
    client.verifications.create(external_id="x" * 300)
except ValidationError as error:
    print(error.errors)  # {"external_id": ["..."]}
except PaymentRequiredError:
    print("Add a payment method to the workspace")
except RateLimitError as error:
    print("Try again in", error.retry_after, "seconds")
except ProofAgeError as error:
    print(error.status_code, error.code, error.message)
```

`AuthenticationError` (401), `PaymentRequiredError` (402), `PermissionDeniedError` (403),
`NotFoundError` (404), `ValidationError` (422), `RateLimitError` (429), `ServerError` (5xx) and
`TransportError` (no response) all extend `ProofAgeError`. `ConfigurationError` is raised when a
client is built with missing or invalid settings. A response whose shape this SDK version does not
recognise raises `ProofAgeError` naming the fields (never their values).

## Configuration

| Argument | Environment | Default |
|---|---|---|
| `api_key` | `PROOFAGE_API_KEY` | required |
| `secret_key` | `PROOFAGE_SECRET_KEY` | required |
| `base_url` | `PROOFAGE_BASE_URL` | `https://api.proofage.xyz` |
| `version` | `PROOFAGE_VERSION` | `v1` |
| `timeout` | `PROOFAGE_TIMEOUT` (seconds) | `30.0` |
| `retry_attempts` | `PROOFAGE_RETRY_ATTEMPTS` | `3` |
| `retry_delay` | `PROOFAGE_RETRY_DELAY` (**milliseconds**) | `1.0` seconds |
| `download_retry_attempts` | `PROOFAGE_DOWNLOAD_RETRY_ATTEMPTS` | `1` |
| `http_client` | — | an owned `httpx` client |

The environment variables use the same names and units as the ProofAge Laravel and PHP SDKs, so
one `.env` serves all of them (the Node SDK reads `PROOFAGE_TIMEOUT` in milliseconds). Constructor
arguments are seconds.

`timeout` limits each network operation (connecting, each read, each write), not the whole
request. Pass your own `httpx.Client` / `httpx.AsyncClient` as `http_client` for proxies or custom
TLS; the SDK never closes a client you pass in.

## Retries

- A GET is retried on 408, 429, 5xx, timeouts and connection failures.
- A POST is retried only on 429 and when the connection never opened. It is never retried on a
  5xx or once sending began, because the server may already have created the verification.
- A 429 waits for its `Retry-After`, up to 60 seconds; a longer `Retry-After` raises `RateLimitError`
  at once (with `retry_after` set) instead of blocking your thread. Otherwise the wait grows by
  `retry_delay` per attempt.
- Media downloads never retry an HTTP status; run them from a queue and let its backoff wait.

## Media

```python
document = client.verifications.document(verification_id)
for item in document.media:
    if item.url is not None:  # None once purged or past retention
        client.verifications.download_media_to(verification_id, item.id, f"{item.id}.jpg")
```

## Hosted flow first

`accept_consent`, `upload_media` and `submit` exist for custom capture flows. Most integrations
only create a session, send the person to its `url`, and read the result.

## For packages that wrap this SDK

A plugin or bot template built on this SDK can name itself in the `X-ProofAge-Sdk` header, which
helps ProofAge support tell integrations apart:

```python
ProofAge(sdk_tokens=["telegram-bot/1.2.0"])  # X-ProofAge-Sdk: telegram-bot/1.2.0 python/0.1.0
```

`user_agent=` replaces the default `ProofAge-Python/<version> (Python <x.y.z>)` User-Agent.

## Supported versions

A Python version stays supported for 12 months after its upstream end of life, or until httpx or
Pydantic stop supporting it, whichever comes first. A version leaves only in a minor release,
announced one release ahead in the changelog.

| Python | Upstream end of life | Supported by `proofage` until |
|---|---|---|
| 3.10 | 2026-10 | 2027-10 |
| 3.11 | 2027-10 | 2028-10 |
| 3.12 | 2028-10 | 2029-10 |
| 3.13 | 2029-10 | 2030-10 |
| 3.14 | 2030-10 | 2031-10 |

The webhook extras follow the same rule against their framework: each supports the oldest release
that still runs on the Python floor. Today that is `fastapi>=0.100`, `flask>=3.0` and
`django>=5.2` (the 5.2 LTS, supported by Django until April 2028; Django 4.2 is out of support).

## AI agents

The package ships `AGENTS.md` next to its code: the full request and response contract of every
method, written for coding agents. Agents that speak MCP can also use the ProofAge MCP server
directly.

## License

MIT
