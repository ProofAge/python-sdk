# ProofAge Python SDK — `proofage` on PyPI

**Date:** 2026-09-28
**Status:** Draft, for owner review
**Scope:** New package `proofage` (import `proofage`, repo `github.com/ProofAge/python-sdk`, local checkout `proofage-python-sdk/`), plus two small follow-ups in `proofageapp` (developer docs and the SDK sync runbook).

**Drivers, as stated by the owner:**

1. Reach. Python is where Telegram bots (aiogram, python-telegram-bot), AI agents (LangChain, CrewAI, PydanticAI, the OpenAI and Anthropic SDKs) and a large share of backends (FastAPI, Django, Flask) are written. ProofAge has Node, PHP and Laravel SDKs and nothing for Python.
2. "Connect in five minutes." A developer should go from `pip install proofage` to a created verification and a verified webhook without reading the HTTP reference.

All paths are relative to `/Users/nikolay/Projects/ProofAge/` unless absolute. The sibling SDKs this design follows were read on 2026-09-28: `proofage-node-client` (`@proofage/node` 0.6.0, `AGENTS.md`, `src/`), `proofage-php-sdk` (`proofage/php-sdk` 0.2.0, `docs/superpowers/specs/2026-09-02-php-sdk-design.md`).

---

## 1. Decisions

### 1.1 Approved by the owner in the design conversation

| # | Decision |
|---|---|
| D1 | Distribution and import name `proofage` (`pip install proofage`, `import proofage`). GitHub repo `ProofAge/python-sdk`, following `ProofAge/php-sdk`. |
| D2 | Responses are **Pydantic v2 models**, not dicts or TypedDicts. Pydantic is already a dependency of aiogram, FastAPI, LangChain and both LLM vendor SDKs, so it costs the target audience nothing. |
| D3 | Models are **lenient**: unknown fields are kept, unknown enum values arrive as plain strings, nothing raises on a field the API adds later. An SDK must never turn an additive API change into a crash on `get()` (§4). |
| D4 | Both a **sync** `ProofAge` and an **async** `AsyncProofAge` client with identical surfaces. aiogram and FastAPI are async; Django views, scripts and Celery tasks are mostly sync. |
| D5 | **Full `/v1` parity** with the Node and PHP SDKs, drift-tested against the app's OpenAPI document (§8). Parity is not optional: the contract test fails on any spec operation without an SDK method. |
| D6 | **0.1.0 ships as soon as the core is green** (golden vectors, contract test, both clients), to claim the name on PyPI. The webhook integrations follow in **0.1.x** as extras: `proofage[fastapi]`, `proofage[django]`, `proofage[flask]`, with an aiogram bot in `examples/`. |
| D7 | **0.2.0** ships `proofage.agents`: one framework-neutral set of tool definitions with thin exporters for the OpenAI and Anthropic tool formats. No per-framework wrappers for LangChain or CrewAI; they take the neutral definitions (documented) or connect to the ProofAge MCP server directly. |
| D8 | The ready-to-deploy Telegram bot is a **separate repository** built on this SDK, not part of the package. |
| D9 | Publishing uses **PyPI Trusted Publishing** from GitHub Actions on `v*` tags. No API tokens anywhere. The project starts on the owner's PyPI account with a second maintainer as a backup; a PyPI organisation `ProofAge` is optional (free only for community projects, a monthly fee for companies) and the project can be moved into one later. |
| D10 | Every request **identifies the SDK and its version** with `X-ProofAge-Sdk: python/{version}` and a `ProofAge-Python/{version} (Python {x.y.z})` User-Agent, the contract every ProofAge client follows since 2026-09-28 (php-sdk 0.3.0, laravel-client 0.9.0, @proofage/node 0.7.0, the WordPress plugin, the Shopify app, browser SDK 1.3). It is how support tells SDK traffic from a hand-written client and which version a customer runs (§3.3). |
| D11 | **Support slightly older Pythons, with a published limit.** People upgrade late, so a Python version stays supported for **12 months after its upstream end of life**, or until a runtime dependency (httpx, Pydantic) stops shipping for it, whichever comes first. The floor today is **3.10** (§10.1). The README lists every supported version with the date it leaves, so the limit is never a surprise. |

### 1.2 Defaults this spec assumes (owner to confirm or override)

| # | Assumption | Why |
|---|---|---|
| A2 | Transport is **httpx** (`>=0.27,<1`). | One library for sync and async with the same request model; it is what openai and anthropic use, so most Python agent projects already have it. |
| A3 | Build with **hatchling**, develop with **uv**, lint with **ruff**, type-check with **mypy --strict**, test with **pytest** + **respx**. | The current mainstream toolchain; `py.typed` ships so consumers get the types. |
| A4 | Licence **MIT**, as `proofage-php-sdk/LICENSE.md` and `proofage-node-client/LICENSE`. | Consistency. |

### 1.3 Non-goals

- **No capture UI.** Camera, liveness and document capture stay in the hosted page and the browser SDK. The SDK exposes `accept_consent`, `upload_media` and `submit` only because the API has them and parity is enforced (D5); the README steers integrators to the hosted flow.
- **No CLI.** The Node package ships one; for Python the owner judged an AI agent on the ProofAge MCP server to cover the same ground.
- **No MCP server in the package.** Agents that speak MCP use the hosted one.
- **No Pydantic v1 support.** v1 is end-of-life and none of the target frameworks need it.
- **No request-side validation beyond types.** Field limits (lengths, URL formats) are the API's to enforce; the SDK surfaces the API's 422 as `ValidationError` (§6).

---

## 2. Package layout

```
proofage-python-sdk/
  pyproject.toml
  README.md                     Quick start, bots, FastAPI, Django, Flask, agents
  AGENTS.md                     The API contract for agents and developers (ships in the wheel)
  CHANGELOG.md
  CLAUDE.md                     Maintainer notes (does NOT ship)
  LICENSE
  src/proofage/
    __init__.py                 ProofAge, AsyncProofAge, errors, models, verify_webhook
    _version.py                 __version__ (single source)
    _config.py                  ClientConfig, env resolution, base URL normalisation
    _signing.py                 JSON and multipart canonical strings, HMAC
    _transport.py               Request building, retry policy, error mapping (shared by both clients)
    _client.py                  ProofAge (sync)
    _async_client.py            AsyncProofAge (async)
    resources/
      verifications.py          Verifications / AsyncVerifications
      workspace.py              Workspace / AsyncWorkspace
    models.py                   Response and request models, open enums
    errors.py                   Exception hierarchy
    webhooks.py                 verify_webhook(), WebhookEvent
    integrations/
      fastapi.py                Dependency for FastAPI / Starlette
      django.py                 View decorator
      flask.py                  View decorator
    agents/                     0.2.0 (§7)
      __init__.py
      _tools.py
    py.typed
    openapi.json                Bundled copy of the app's spec (ships; read by the contract test)
  tests/
    fixtures/hmac-vectors.json  Verbatim copy of proofage-php-sdk/resources/hmac-vectors.json
    ...
  examples/
    aiogram_bot/                Bot that creates a link and reports the result via webhook
    fastapi_app/
    django_view/
  scripts/
    sync_spec.py                Pulls developer-docs/public/openapi.json from proofageapp
    check_release.py            Refuses a version PyPI already serves or one below latest
  .github/workflows/
    ci.yml
    publish.yml
```

Runtime dependencies: `httpx`, `pydantic>=2.6,<3`. Extras add only the framework they integrate (`fastapi`, `django`, `flask`), with version floors at the oldest release upstream still supports.

---

## 3. Client surface

### 3.1 Construction

```python
from proofage import ProofAge, AsyncProofAge

client = ProofAge()                      # reads the environment
client = ProofAge(api_key="pk_...", secret_key="sk_...")

async with AsyncProofAge() as client:
    verification = await client.verifications.create(external_id="candidate-42")
```

Configuration, resolved argument → environment variable → default. The environment variables have the **same names and the same units as the Laravel and PHP SDKs**, so a `.env` written for them works here unchanged; constructor arguments take Python's natural units (seconds, as floats) and the SDK converts:

| Argument | Environment | Default | Notes |
|---|---|---|---|
| `api_key` | `PROOFAGE_API_KEY` | required | Workspace API key |
| `secret_key` | `PROOFAGE_SECRET_KEY` | required | Used only to sign; never sent |
| `base_url` | `PROOFAGE_BASE_URL` | `https://api.proofage.xyz` | API origin **without** the version; a trailing `/v1` (as in the OpenAPI `servers` entry) is stripped; anything that is not an absolute http(s) URL, or carries a query or fragment, raises at construction |
| `version` | `PROOFAGE_VERSION` | `v1` | |
| `timeout` | `PROOFAGE_TIMEOUT` (seconds, as in Laravel) | `30.0` | Seconds, passed to httpx as `httpx.Timeout(timeout)`: a limit on **each operation** (connect, each read, each write, pool), not a deadline for the whole request, so a slowly trickling response can take longer. The README says so. (Node reads this variable in milliseconds; the Laravel/PHP unit is the one followed here, and the README names the clash.) |
| `retry_attempts` | `PROOFAGE_RETRY_ATTEMPTS` | `3` | Attempts for interactive requests (§5) |
| `retry_delay` | `PROOFAGE_RETRY_DELAY` (**milliseconds**, as in Laravel and Node) | `1.0` | Seconds between attempts when no `Retry-After` is sent; the environment value is divided by 1000, so a shared `PROOFAGE_RETRY_DELAY=1000` means one second, not a thousand |
| `download_retry_attempts` | `PROOFAGE_DOWNLOAD_RETRY_ATTEMPTS` | `1` | Media downloads; only a transport failure is retried, never a status (§5) |
| `http_client` | — | owned | An `httpx.Client` / `httpx.AsyncClient` the caller already manages (proxies, custom TLS). When passed, the SDK never closes it. |

Missing keys raise `ConfigurationError` naming the environment variable to set. Both clients are context managers and have `close()` / `aclose()`.

**The secret key never leaves the object.** `repr()` of `ProofAge`, `AsyncProofAge` and the internal config shows the base URL, version and the api key's first characters, and `secret_key` only as `'***'`; no exception message, event or log line contains it. A test asserts this for `repr`, `str` of every error raised at construction, and the request the transport sends.

Every request identifies the SDK (§3.3).

Two more arguments, for a package that wraps this SDK (a framework plugin, the Telegram bot template of D8); neither has an environment variable:

| Argument | Default | Notes |
|---|---|---|
| `sdk_tokens` | `()` | `name/version` tokens prepended to the SDK's own in `X-ProofAge-Sdk`, outermost first (§3.3) |
| `user_agent` | SDK default | Replaces the default User-Agent; `X-ProofAge-Sdk` is still sent |

### 3.2 Resources

Method names are Python's (`snake_case`), arguments are keyword-only and typed, and the verification id is a positional argument rather than Node's `verifications(id)` builder, which reads oddly in Python. Request bodies are snake_case, as the API expects.

| Method | Endpoint | Returns |
|---|---|---|
| `workspace.get()` | `GET /workspace` | `WorkspaceInfo` |
| `workspace.consent()` | `GET /consent` | `ConsentInfo` |
| `verifications.create(*, callback_url=None, external_id=None, external_metadata=None, metadata=None, fingerprint=None, page_url=None)` | `POST /verifications` | `CreatedVerification` (has `url`) |
| `verifications.get(verification_id)` | `GET /verifications/{id}` | `Verification` |
| `verifications.accept_consent(verification_id, *, consent_version_id, text_sha256, device=None, in_app_browser=None, camera_permission=None, camera_policy_allowed=None, in_iframe=None, referrer=None)` | `POST /verifications/{id}/consent` | `AcceptConsentResult` |
| `verifications.upload_media(verification_id, *, file, type, side=None, document=None, filename=None, fingerprint=None, head_turn_step=None, capture_resolution=None, device_info=None, liveness_telemetry=None)` | `POST /verifications/{id}/media` (multipart) | `None` |
| `verifications.submit(verification_id)` | `POST /verifications/{id}/submit` | `None` |
| `verifications.document(verification_id)` | `GET /verifications/{id}/document` | `VerificationDocument` |
| `verifications.download_media(verification_id, media_id)` | `GET /verifications/{id}/media/{media}` | context manager yielding a byte iterator (`AsyncIterator[bytes]` on the async client). A transport retry (§5.2) happens only before the first byte is yielded; a failure mid-stream raises `TransportError` |
| `verifications.download_media_to(verification_id, media_id, path)` | same | `pathlib.Path`; streams to a temporary file and renames only after a 2xx, so a failure never leaves a partial file |
| `verifications.estimation(verification_id)` | `GET /verifications/{id}/estimation` | `AgeEstimation` |
| `verifications.block_face(verification_id, *, reason_code=None, reason=None)` | `POST /verifications/{id}/blocked-face` | `None` |

`upload_media(file=...)` accepts `bytes`, a binary file object or a `pathlib.Path`; `filename` defaults to the path's name, else `upload.bin` as in the Node SDK. The full request and response field lists are those of `proofage-node-client/AGENTS.md` and are reproduced in this package's `AGENTS.md`; the contract test (§8) keeps them honest.

### 3.3 SDK identification

The same contract as every other ProofAge client, so the API and the people reading its logs see one format:

- **`X-ProofAge-Sdk`** on every request: space-separated `name/version` tokens, outermost wrapper first, the SDK's own `python/{__version__}` always last. A wrapper passing `sdk_tokens=["telegram-bot/1.2.0"]` sends `telegram-bot/1.2.0 python/0.1.0`. Names are lowercase.
- **`User-Agent`**: `ProofAge-Python/{__version__} (Python {platform.python_version()})`, e.g. `ProofAge-Python/0.1.0 (Python 3.12.7)`. It replaces httpx's default `python-httpx/x`. It is kept as the caller set it when they pass `user_agent`, or when a caller-supplied `http_client` already carries a `User-Agent` other than httpx's default.
- **The SDK's own token cannot be removed.** A wrapper token named `python` (any case) is dropped, so it can neither replace nor repeat the SDK's own. The header is set on each request the SDK builds, on every attempt, and per-request headers override an `http_client`'s default headers, so a default cannot remove it. An httpx event hook runs inside `send()` after the request is built and could still rewrite it; that is the caller's deliberate choice and the SDK does not fight it.
- **Validated at construction.** A token must match `^[\x21-\x2E\x30-\x7E]+/[\x21-\x2E\x30-\x7E]+$` (printable ASCII, no space, exactly one slash) and `user_agent` must be printable ASCII (`\x20`–`\x7E`). Anything else raises `ConfigurationError` when the client is built, not on every request after its retries (the lesson the Node SDK learned before 0.7.0).
- **Not part of the HMAC signature.** Signing stays `METHOD + path + body` (§5.1); the golden vectors do not change.
- **One version source.** Both headers read `proofage._version.__version__`, the file hatchling already reads (§10), so a release cannot report a stale number.
- **How the API uses it.** Today the app reads `X-ProofAge-Sdk` only to classify an unsigned create (`web/…` is the browser widget), and SDK requests are always signed, so the header changes nothing about how a request is handled. It is not redacted, so it is visible in the app's API logs; storing it per verification for the landlord console and MCP is planned separately in `proofageapp`.

---

## 4. Models

All response models derive from one base:

```python
class ProofAgeModel(BaseModel):
    model_config = ConfigDict(extra="allow")
```

No `frozen=True`: a frozen model advertises itself as hashable, but `hash()` raises on any model holding a dict (`external_metadata`, `duplicate_check`), so immutability would buy a confusing error and nothing else. No `populate_by_name`: the models use the API's own field names, so there are no aliases to serve.

- **Unknown fields are kept** (`extra="allow"`) and readable through `model.model_extra`. A new API field never breaks parsing.
- **Open enums.** `VerificationStatus`, `BlockFaceReasonCode` and similar are `str, Enum` classes (`StrEnum` is 3.11+ and the floor is 3.10), but every field that holds one is typed `Annotated[VerificationStatus | str, Field(union_mode="left_to_right")]` (a shared alias per enum). The `union_mode` is essential: in Pydantic's default smart mode a JSON string matches `str` exactly, so the enum would **never** materialise. Left to right, a known value becomes the enum member and a value the SDK does not know yet arrives as the raw string instead of raising. A model test asserts both halves. The enum carries the documented set, including `documents_required` (surfaced from the attempt, not a verification status, as `AGENTS.md` in the Node SDK notes).
- **`reason` is an open string.** Decline and resubmission reasons are dotted codes from a growing server catalog; they are not modelled as an enum.
- **Timestamps** parse to aware `datetime`; `date_of_birth` (`YYYY-MM-DD`) parses to `date`. Nullable fields are `X | None`, and fields the API always sends are required, so `None` means the API sent `null`, not "absent".
- **`model_dump(mode="json")`** gives a plain dict, for logs, JSON storage and handing to an LLM.
- **Nested shapes** get their own models: `DuplicateCheck`, `Erasure`, `VerificationDocument` / `DocumentFields` / `MediaItem`, `AgeEstimation` / `AgeThreshold` / `Gender`, `WebhookEvent` / `ManualModeration` / `DuplicateOf`.

Request payloads are keyword arguments, not models, so the common call stays one line. Structured arguments (`device`, `external_metadata`) accept dicts.

---

## 5. Transport, signing and retries

Both clients share one transport module; only the I/O calls differ. The behaviour matches the Node and PHP SDKs exactly.

### 5.1 Signing

- **JSON and body-less requests:** `HMAC-SHA256(secret, METHOD + "/{version}/{path}" + query + body)`, hex. The server signs the raw bytes it receives (`proofageapp/app/Http/Middleware/VerifyHmacSignature.php`), so the only rule is that the SDK sends exactly what it signed: the body is serialised **once** with `json.dumps(data, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`, encoded UTF-8, signed, and sent as those bytes via `content=`. An empty payload is the empty string, never `{}`, as in `proofage-node-client/src/hmac.ts:6-11`.
- **Query string.** No `/v1` endpoint takes one today, but the server includes it when present (`?` + Symfony's normalised query: parameters sorted, values RFC 3986-encoded, `%20` for spaces), and a golden vector covers it. The signer implements it as `"?" + "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in sorted(parse_qsl(q, keep_blank_values=True)))`, which reproduces the vector.
- **Headers on every normal request:** `Content-Type: application/json` when there is a JSON body (httpx sets none for `content=`, and Laravel reads a body as JSON only when the header says so) and `Accept: application/json`, so errors come back as JSON rather than HTML. Media downloads send `Accept: application/json, */*;q=0.8`, as the Node SDK does.
- **Multipart:** `METHOD/{version}/{path}\n{fields}\n{comma-joined sorted sha256(file) hex}`, where `{fields}` is PHP's `http_build_query(ksort($fields), '', '&', PHP_QUERY_RFC3986)`: keys sorted, values percent-encoded as `rawurlencode` does (`! ' ( ) *` encoded too). Field normalisation before signing **and** sending: `None` dropped, `bool` → `"1"`/`"0"`, numbers → `str`, dicts and lists → compact JSON strings. **Only `str` values ever reach httpx's `data=`**: httpx would otherwise encode `True` as `"true"` and `None` as `""`, sending different bytes from the ones signed. The canonical builder itself stays general (nested fields, several files) because the golden vectors exercise both, even though `upload_media` sends one file and JSON-string fields.
- **Golden vectors are the authority.** `tests/fixtures/hmac-vectors.json` is a verbatim copy of `proofage-php-sdk/resources/hmac-vectors.json` (sections `json`, `multipart`, `webhook`), the file the app also runs through its real `VerifyHmacSignature` middleware. The signing tests are written first and must pass before any resource code (§9).

### 5.2 Retries

| Request | Retried on | Never retried on |
|---|---|---|
| `GET` | 408, 429, 5xx, timeouts, connection errors | 4xx other than 408/429 |
| `POST` | 429; errors raised **before** the request was sent: `httpx.ConnectError` (DNS failure, connection refused, TLS handshake) and `httpx.ConnectTimeout` | 5xx and every error after sending began: `httpx.WriteError`, `WriteTimeout`, `ReadError`, `ReadTimeout`, `RemoteProtocolError`. The server may already have created the verification or stored the upload |
| Media download | Transport failures only, up to `download_retry_attempts` | Any HTTP status, 429 included: downloads usually run from a queue whose own backoff owns the wait |

A 429 waits for `Retry-After` when present (seconds or an HTTP date, as the Node SDK parses both) up to 60 seconds; a longer one raises `RateLimitError` at once rather than blocking the caller's thread (implementation ruling after the final review). Otherwise `retry_delay × attempt`. The rule set is the Node SDK's (`AGENTS.md` "Retries") and the PHP SDK's (spec §4.5), so a request behaves the same in every language.

---

## 6. Errors

```
ProofAgeError                      status_code, message, code, error_data, response_body
├── AuthenticationError            401
├── PermissionDeniedError          403
├── NotFoundError                  404
├── PaymentRequiredError           402  (code PAYMENT_METHOD_REQUIRED; error_data has free_verifications_remaining, trial_ends_at, trial_active)
├── ValidationError                422  (.errors: dict[str, list[str]] for field errors; media rejections carry .code such as FACE_NOT_FOUND)
├── RateLimitError                 429  (.retry_after: float | None), raised after retries are exhausted
├── ServerError                    5xx
└── TransportError                 no response: DNS, connection, TLS, timeout (.__cause__ is the httpx exception)
ConfigurationError                 missing or invalid configuration, raised at construction
WebhookVerificationError           .code in MISSING_SIGNATURE, MISSING_TIMESTAMP, MISSING_AUTH_CLIENT,
                                   INVALID_AUTH_CLIENT, TIMESTAMP_TOO_OLD, INVALID_SIGNATURE (401),
                                   CONFIGURATION_ERROR (500), INVALID_PAYLOAD (400: signed, not an event)
```

Python callers branch on exception type far more than on status codes, so this hierarchy is finer than Node's (which has only `AuthenticationError` and `ValidationError`). Every class still exposes `status_code` and `code`, so a Node-style `if e.code == ...` works too.

The error body is parsed in all four shapes the API sends (`proofageapp` developer-docs, and `proofage-node-client/AGENTS.md` "Errors"):

1. `{"error": {"code", "message"}}`: `error_data` is the inner object.
2. Flat `{"code", "message", ...extra}` (402, media-quality 422, 500 `VALIDATION_SERVICE_UNAVAILABLE`): `error_data` is the whole body.
3. `{"message", "errors"}` (request validation 422): `code` is `None`, `errors` has the fields.
4. `{"message"}` (403, 404).

A 2xx whose body does not match its model raises `ProofAgeError` ("Unexpected response shape from GET /v1/…") naming the fields but never their values, so a Pydantic `ValidationError` never escapes the SDK. A 2xx with an empty body returns `None` from the methods typed `-> None` (`upload_media`, `submit`, `block_face`); for a method that promises a model, an empty body raises `ProofAgeError` rather than returning `None` against its type. A non-empty 2xx that is not JSON raises `ProofAgeError` whose message says that `base_url` most likely points at a website rather than the API; this is the most common first-run mistake.

---

## 7. Webhooks and integrations

### 7.1 Core

```python
from proofage import verify_webhook

event = verify_webhook(raw_body, headers)          # -> WebhookEvent, or raises WebhookVerificationError
verify_webhook_signature(raw_body, headers)        # the checks only, -> None
```

- Signature: `verify_webhook(raw_body, headers, *, api_key=None, secret_key=None, tolerance=None)`. Each keyword falls back to `PROOFAGE_API_KEY`, `PROOFAGE_SECRET_KEY` and `PROOFAGE_WEBHOOK_TOLERANCE`. `raw_body` is `bytes` exactly as received; `headers` is any case-insensitive mapping.
- `CONFIGURATION_ERROR` is raised only **after** the three presence checks, as in the Node SDK (`src/webhook.ts:84`) and the Laravel middleware, so a request missing its headers is reported as such even on a misconfigured server. A timestamp that is not an integer is `MISSING_TIMESTAMP`.
- Checks, in order: `X-HMAC-Signature`, `X-Timestamp`, `X-Auth-Client` present; `X-Auth-Client` equals the api key; timestamp within `tolerance` seconds (argument → `PROOFAGE_WEBHOOK_TOLERANCE` → 300); signature equals hex `HMAC-SHA256(secret, f"{timestamp}.{raw_body}")`, compared with `hmac.compare_digest`. If the raw body does not match, the canonical re-serialisation of the JSON is tried once, as the Node SDK does (`src/webhook.ts`): `json.dumps(obj, ensure_ascii=False, separators=(",", ":"))`, which reproduces PHP's `JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE` output that the vectors' `expected_canonical` holds.
- `WebhookEvent` exposes `delivery_id` from `X-ProofAge-Webhook-Delivery-Id`: the same on every automatic retry of one delivery, new on a manual resend. The README tells integrators to de-duplicate on it.

### 7.2 Extras (0.1.x)

Each integration is a thin shell over `verify_webhook`: it reads the raw body, turns `WebhookVerificationError` into the framework's 401/400 response, and hands the handler a typed `WebhookEvent`. Importing an integration without its framework installed raises `ImportError` with the exact `pip install "proofage[fastapi]"` line.

```python
# FastAPI / Starlette
from proofage.integrations.fastapi import ProofAgeWebhook

@app.post("/webhooks/proofage")
async def proofage_webhook(event: ProofAgeWebhook):
    ...

# Django
from proofage.integrations.django import proofage_webhook

@proofage_webhook                   # csrf_exempt, POST only, sets request.proofage_event
def webhook(request):
    ...

# Flask
from proofage.integrations.flask import proofage_webhook

@app.post("/webhooks/proofage")
@proofage_webhook
def webhook(event):
    ...
```

Implementation notes (0.3.0): the bare forms above read the keys from the environment; for keys held elsewhere (Django settings, a secrets manager) the Django and Flask decorators also take `api_key=`, `secret_key=` and `tolerance=` (`@proofage_webhook(api_key=..., secret_key=...)`), and FastAPI has `webhook_dependency(...)` to use with `Depends`. The extras' floors are `fastapi>=0.100`, `flask>=3.0`, `django>=5.2`. Error bodies follow each framework's habit: FastAPI `{"detail": {"code", "message"}}`, Django and Flask `{"error": {"code", "message"}}`. The Django and Flask decorators are for synchronous views.

aiogram needs no integration of its own: a bot creates links with `AsyncProofAge` and receives results through one of the above, or through `verify_webhook` in an aiohttp handler. `examples/aiogram_bot/` shows the whole loop (a `/verify` command that sends the link, a webhook that messages the user the outcome) and is the seed of the separate bot-template repository (D8).

### 7.3 Agents (0.2.0)

```python
from proofage.agents import proofage_tools

tools = proofage_tools(client)                      # list[ToolSpec]
openai_tools = [t.to_openai() for t in tools]       # {"type": "function", "function": {...}}
anthropic_tools = [t.to_anthropic() for t in tools] # {"name", "description", "input_schema"}

by_name = {t.name: t for t in tools}
result = by_name[call.name](**call.arguments)       # runs the call, returns a JSON-safe dict
```

`ToolSpec` holds a name, an LLM-oriented description, a JSON Schema generated from the method's Pydantic signature, and a callable. There is no LangChain or CrewAI dependency; the README shows the three-line adapter for each (`StructuredTool.from_function`, CrewAI's `BaseTool`) and points MCP-capable frameworks at the hosted server.

The default tool set is deliberately narrow, because an agent loops and reads what it gets:

| Tool | Default | Why |
|---|---|---|
| `create_verification`, `get_verification`, `get_workspace` | on | What an agent that onboards people needs. `get_verification` answers with the status-level fields only (`id`, `status`, `reason`, `external_id`, `created_at`, `updated_at`), a projection of `GET /verifications/{id}` made in the SDK: the API has no status-only endpoint and needs none. `external_metadata` and `duplicate_check` stay out of the model's context unless `include_personal_data=True` |
| `get_verification_document`, `get_age_estimation` | **off**; `include_personal_data=True` | Names, dates of birth and document numbers should not flow into a model's context unless the integrator decides so |
| `block_face` | **off**; `include_destructive=True` | Irreversible for the person; the ProofAge consoles require a reason code for the same reason |
| capture endpoints, media download | never | Binary data and camera steps are not agent work |

---

## 8. Contract with the API

The same three layers as the other SDKs (`proofage-node-client/CLAUDE.md` "Changing the API surface", and the Laravel client's `docs/superpowers/specs/2026-06-29-laravel-client-api-contract-design.md`):

1. **Bundled spec.** `src/proofage/openapi.json`, refreshed by `scripts/sync_spec.py` from `proofageapp/developer-docs/public/openapi.json` (the Scramble export).
2. **`AGENTS.md`** ships in the wheel and is the authoritative response contract where the spec is thin.
3. **Contract test.** `tests/test_api_contract.py` asserts that every operation in the bundled spec maps to an SDK method (both `download_media` and `download_media_to` map to the media operation), that every request field in the spec is accepted by that method, and that for the operations Scramble fully describes, every response field exists on the model. A new API endpoint therefore fails CI here until the SDK method, the model and `AGENTS.md` land together.

The maintainer runbook for regenerating the spec stays in one place, `proofageapp/developer-docs/README.md` § "Keeping the SDK clients in sync"; this repo's `CLAUDE.md` links to it and does not duplicate it.

---

## 9. Testing

Written in this order, each layer green before the next starts:

1. **Golden vectors** (`tests/test_signing.py`): every entry in the `json`, `multipart` and `webhook` sections of the fixture produces the expected signature. Nothing else is written until these pass.
2. **Transport** with respx: retry matrix of §5.2 (including "POST not retried on 5xx", "POST retried on pre-send connection error", `Retry-After` honoured), the four error shapes of §6, the non-JSON-2xx message, and a check that the bytes sent equal the bytes signed. SDK identification (§3.3): `X-ProofAge-Sdk` and `User-Agent` on a JSON request, a body-less request, a multipart upload, a media download and every retry attempt, for both clients; `sdk_tokens` prepended in order; a `python` wrapper token dropped; a caller `http_client` with its own User-Agent kept and one with httpx's default replaced; invalid tokens and a non-ASCII or line-breaking `user_agent` raising `ConfigurationError` at construction; the signature identical with and without the headers.
3. **Resources**: each method against a mocked response taken from `AGENTS.md`. One test module, parametrised over the sync and async client, so the two can never drift apart.
4. **Models**: an unknown field survives; an unknown status parses as `str`; `model_dump(mode="json")` round-trips.
5. **Webhooks**: every error code of `WebhookVerificationError`, tolerance boundary, canonical-JSON fallback; each extra through its framework's own test client (FastAPI `TestClient`, Django `RequestFactory`, Flask `test_client`).
6. **Contract test** (§8).
7. **Examples** import and construct under `pytest --examples` so they cannot rot silently.

`mypy --strict` over `src/` and the examples, and `ruff` over everything, gate CI alongside the tests.

---

## 10. Tooling, CI and release

- **CI** (`ci.yml`, on push and pull request): every supported Python (3.10–3.14 today, §10.1) on Linux; one extra leg per integration at the framework's oldest supported version; ruff and mypy on the newest Python only, so a tool-version drift cannot break the whole matrix (the lesson the PHP SDK learned when an unpinned Pint reddened one matrix leg). A Python version leaves the matrix on the date §10.1 gives for it, not earlier.
- **Versioning**: `src/proofage/_version.py` is the single source; hatchling reads it.
- **Release**: `scripts/check_release.py X.Y.Z` reads `https://pypi.org/pypi/proofage/json` and refuses a version already served or below the latest, because the registry, not `git tag`, is the truth (the laravel-client tags were once missing published releases). Then: bump, commit `chore: release X.Y.Z`, push, tag `vX.Y.Z`, push the tag. `publish.yml` builds sdist and wheel and publishes through Trusted Publishing, environment `pypi`. Never `twine upload` by hand.
- **One-time setup, by the owner:** PyPI account with 2FA and a second maintainer; a pending publisher for owner `ProofAge`, repo `python-sdk`, workflow `publish.yml`, environment `pypi`; the matching `pypi` environment in the GitHub repo settings. Optionally the same on test.pypi.org for a dry run.

---

### 10.1 Supported Python versions (D11)

| Python | Upstream end of life | Supported by `proofage` until | Why that date |
|---|---|---|---|
| 3.10 | 2026-10 | 2027-10 | 12 months after end of life |
| 3.11 | 2027-10 | 2028-10 | same rule |
| 3.12 | 2028-10 | 2029-10 | same rule |
| 3.13 | 2029-10 | 2030-10 | same rule |
| 3.14 | 2030-10 | 2031-10 | same rule |

3.9 is not supported: it reached end of life in October 2025, so its grace year ends weeks after 0.1.0, and supporting it would mean `Optional[...]` in every model because Pydantic cannot evaluate `X | None` on 3.9.

The extras follow the same idea against their own framework: each supports the oldest framework release that upstream still maintains **and** that runs on the Python floor. Django 4.2 is past that line (its LTS ended in April 2026), so `proofage[django]` needs Django 5.2 LTS (Python 3.10+, supported until April 2028); FastAPI and Flask take their current lines. Django 5.2's classifiers stop at Python 3.13, so on 3.14 the extra resolves Django 6.x; the CI matrix runs the Django extra on 3.14 against 6.x and on the older Pythons against 5.2. A floor rises only in a **minor** release, announced a release ahead in `CHANGELOG.md`, never in a patch.

The same table, with dates, goes in the README under "Supported versions".

## 11. Changes outside this repo

In `proofageapp` (separate, small commits):

1. `developer-docs`: add Python to the published-SDKs page and to the quick start, next to Node and PHP.
2. `developer-docs/README.md` § "Keeping the SDK clients in sync": add `proofage-python-sdk` and its `scripts/sync_spec.py` to the list of SDKs refreshed after an API change.

Later, not part of this spec: the Telegram bot template repository (D8), built on 0.1.0.

---

## 12. Release plan

| Release | Contents | Done when |
|---|---|---|
| **0.1.0** | Config, signing, transport, SDK identification, both clients, all `/v1` methods, models, errors, `verify_webhook`, `AGENTS.md`, README, CI, publish workflow | Golden vectors, contract test and the full suite pass on 3.10–3.14; a real verification created against a test workspace and its webhook verified with `verify_webhook`. Published at once, to claim the name |
| **0.1.x** | FastAPI, Django and Flask extras; `examples/` (aiogram bot, FastAPI app, Django view) | Each extra passes through its framework's test client; the FastAPI example verifies a real webhook end to end |
| **0.2.0** | `proofage.agents` with the tool policy of §7.3, OpenAI and Anthropic exporters, LangChain/CrewAI/PydanticAI adapter snippets in the README | A tool loop with each vendor SDK creates a verification against a test workspace |

---

## 13. Resolved questions

1. **Python floor:** 3.10, under the 12-months-after-end-of-life rule (D11, §10.1). The owner wants slightly older versions supported as long as they do not get in the way, and the limit written down everywhere.
2. **When to publish:** 0.1.0 as soon as the core is green; extras in 0.1.x (D6).
3. **A status-only agent tool:** not a separate tool. The API has no status-only endpoint, and `get_verification` already answers with the status-level projection by default (§7.3).
