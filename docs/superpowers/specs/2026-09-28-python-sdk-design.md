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
| D6 | **0.1.0** ships the core plus webhook integrations as extras: `proofage[fastapi]`, `proofage[django]`, `proofage[flask]`, and an aiogram bot in `examples/`. |
| D7 | **0.2.0** ships `proofage.agents`: one framework-neutral set of tool definitions with thin exporters for the OpenAI and Anthropic tool formats. No per-framework wrappers for LangChain or CrewAI; they take the neutral definitions (documented) or connect to the ProofAge MCP server directly. |
| D8 | The ready-to-deploy Telegram bot is a **separate repository** built on this SDK, not part of the package. |
| D9 | Publishing uses **PyPI Trusted Publishing** from GitHub Actions on `v*` tags, under a PyPI organisation `ProofAge`. No API tokens anywhere. |
| D10 | Every request **identifies the SDK and its version** with `X-ProofAge-Sdk: python/{version}` and a `ProofAge-Python/{version} (Python {x.y.z})` User-Agent, the contract every ProofAge client follows since 2026-09-28 (php-sdk 0.3.0, laravel-client 0.9.0, @proofage/node 0.7.0, the WordPress plugin, the Shopify app, browser SDK 1.3). It is how support tells SDK traffic from a hand-written client and which version a customer runs (§3.3). |

### 1.2 Defaults this spec assumes (owner to confirm or override)

| # | Assumption | Why |
|---|---|---|
| A1 | `requires-python = ">=3.11"`. | 3.10 leaves security support in October 2026, weeks after 0.1.0. The sibling SDKs test only versions upstream still supports. |
| A2 | Transport is **httpx** (`>=0.27,<1`). | One library for sync and async with the same request model; it is what openai and anthropic use, so most Python agent projects already have it. |
| A3 | Build with **hatchling**, develop with **uv**, lint with **ruff**, type-check with **mypy --strict**, test with **pytest** + **respx**. | The current mainstream toolchain; `py.typed` ships so consumers get the types. |
| A4 | Licence **MIT**, as `proofage-php-sdk/LICENSE.md` and `proofage-node-client/LICENSE`. | Consistency. |
| A5 | Claim the name early: publish `0.1.0` as soon as the core passes the golden vectors and the contract test, even if extras land in `0.1.x`. | A pending publisher on PyPI does not reserve a name; only a first upload does. |

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

Configuration, resolved argument → environment variable → default, with the **same names as the Node and Laravel SDKs** so one `.env` serves every language:

| Argument | Environment | Default | Notes |
|---|---|---|---|
| `api_key` | `PROOFAGE_API_KEY` | required | Workspace API key |
| `secret_key` | `PROOFAGE_SECRET_KEY` | required | Used only to sign; never sent |
| `base_url` | `PROOFAGE_BASE_URL` | `https://api.proofage.xyz` | API origin **without** the version; a trailing `/v1` (as in the OpenAPI `servers` entry) is stripped; anything that is not an absolute http(s) URL, or carries a query or fragment, raises at construction |
| `version` | `PROOFAGE_VERSION` | `v1` | |
| `timeout` | `PROOFAGE_TIMEOUT` | `30.0` | Seconds per attempt (float, unlike Node's milliseconds, because that is what httpx and every Python HTTP library take) |
| `retry_attempts` | `PROOFAGE_RETRY_ATTEMPTS` | `3` | Attempts for interactive requests (§5) |
| `retry_delay` | `PROOFAGE_RETRY_DELAY` | `1.0` | Seconds between attempts when no `Retry-After` is sent |
| `download_retry_attempts` | — | `1` | Media downloads; only a transport failure is retried, never a status (§5) |
| `http_client` | — | owned | An `httpx.Client` / `httpx.AsyncClient` the caller already manages (proxies, custom TLS). When passed, the SDK never closes it. |

Missing keys raise `ConfigurationError` naming the environment variable to set. Both clients are context managers and have `close()` / `aclose()`.

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
| `verifications.accept_consent(verification_id, *, consent_version_id, text_sha256, device=None, ...)` | `POST /verifications/{id}/consent` | `AcceptConsentResult` |
| `verifications.upload_media(verification_id, *, file, type, side=None, document=None, filename=None, ...)` | `POST /verifications/{id}/media` (multipart) | `None` |
| `verifications.submit(verification_id)` | `POST /verifications/{id}/submit` | `None` |
| `verifications.document(verification_id)` | `GET /verifications/{id}/document` | `VerificationDocument` |
| `verifications.download_media(verification_id, media_id)` | `GET /verifications/{id}/media/{media}` | context manager yielding a byte iterator (`AsyncIterator[bytes]` on the async client) |
| `verifications.download_media_to(verification_id, media_id, path)` | same | `pathlib.Path`; streams to a temporary file and renames only after a 2xx, so a failure never leaves a partial file |
| `verifications.estimation(verification_id)` | `GET /verifications/{id}/estimation` | `AgeEstimation` |
| `verifications.block_face(verification_id, *, reason_code=None, reason=None)` | `POST /verifications/{id}/blocked-face` | `None` |

`upload_media(file=...)` accepts `bytes`, a binary file object or a `pathlib.Path`. The full request and response field lists are those of `proofage-node-client/AGENTS.md` and are reproduced in this package's `AGENTS.md`; the contract test (§8) keeps them honest.

### 3.3 SDK identification

The same contract as every other ProofAge client, so the API and the people reading its logs see one format:

- **`X-ProofAge-Sdk`** on every request: space-separated `name/version` tokens, outermost wrapper first, the SDK's own `python/{__version__}` always last. A wrapper passing `sdk_tokens=["telegram-bot/1.2.0"]` sends `telegram-bot/1.2.0 python/0.1.0`. Names are lowercase.
- **`User-Agent`**: `ProofAge-Python/{__version__} (Python {platform.python_version()})`, e.g. `ProofAge-Python/0.1.0 (Python 3.12.7)`. It replaces httpx's default `python-httpx/x`. It is kept as the caller set it when they pass `user_agent`, or when a caller-supplied `http_client` already carries a `User-Agent` other than httpx's default.
- **The SDK's own token cannot be removed.** A wrapper token named `python` (any case) is dropped, so it can neither replace nor repeat the SDK's own. The header is set per request on every attempt, after any caller hook, so an `http_client` default header or event hook cannot remove it.
- **Validated at construction.** A token must match `^[\x21-\x2E\x30-\x7E]+/[\x21-\x2E\x30-\x7E]+$` (printable ASCII, no space, exactly one slash) and `user_agent` must be printable ASCII (`\x20`–`\x7E`). Anything else raises `ConfigurationError` when the client is built, not on every request after its retries (the lesson the Node SDK learned before 0.7.0).
- **Not part of the HMAC signature.** Signing stays `METHOD + path + body` (§5.1); the golden vectors do not change.
- **One version source.** Both headers read `proofage._version.__version__`, the file hatchling already reads (§10), so a release cannot report a stale number.
- **How the API uses it.** Today the app reads `X-ProofAge-Sdk` only to classify an unsigned create (`web/…` is the browser widget), and SDK requests are always signed, so the header changes nothing about how a request is handled. It is not redacted, so it is visible in the app's API logs; storing it per verification for the landlord console and MCP is planned separately in `proofageapp`.

---

## 4. Models

All response models derive from one base:

```python
class ProofAgeModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)
```

- **Unknown fields are kept** (`extra="allow"`) and readable through `model.model_extra`. A new API field never breaks parsing.
- **Open enums.** `VerificationStatus`, `BlockFaceReasonCode` and similar are `StrEnum`s, but every field that holds one is typed `VerificationStatus | str`. A value the SDK does not know yet arrives as the raw string instead of raising. The enum carries the documented set, including `documents_required` (surfaced from the attempt, not a verification status, as `AGENTS.md` in the Node SDK notes).
- **`reason` is an open string.** Decline and resubmission reasons are dotted codes from a growing server catalog; they are not modelled as an enum.
- **Timestamps** parse to aware `datetime`. Nullable fields are `X | None`, and fields the API always sends are required, so `None` means the API sent `null`, not "absent".
- **`model_dump(mode="json")`** gives a plain dict, for logs, JSON storage and handing to an LLM.
- **Nested shapes** get their own models: `DuplicateCheck`, `Erasure`, `VerificationDocument` / `DocumentFields` / `MediaItem`, `AgeEstimation` / `AgeThreshold` / `Gender`, `WebhookEvent` / `ManualModeration` / `DuplicateOf`.

Request payloads are keyword arguments, not models, so the common call stays one line. Structured arguments (`device`, `external_metadata`) accept dicts.

---

## 5. Transport, signing and retries

Both clients share one transport module; only the I/O calls differ. The behaviour matches the Node and PHP SDKs exactly.

### 5.1 Signing

- **JSON and body-less requests:** `HMAC-SHA256(secret, METHOD + "/{version}/{path}" + body)`, hex. The body is serialised **once** with `json.dumps(data, separators=(",", ":"), ensure_ascii=False)` (byte-identical to `JSON.stringify` for the payloads the API takes), encoded UTF-8, signed, and sent as those exact bytes via `content=`. An empty payload is the empty string, never `{}`, as in `proofage-node-client/src/hmac.ts:6-11`.
- **Multipart:** `METHOD/{version}/{path}\n{fields}\n{comma-joined sorted sha256(file) hex}`, where `{fields}` is PHP's `http_build_query(ksort($fields), '', '&', PHP_QUERY_RFC3986)`: keys sorted, values percent-encoded as `rawurlencode` does (`! ' ( ) *` encoded too). Field normalisation before signing **and** sending: `None` dropped, `bool` → `"1"`/`"0"`, numbers → `str`, dicts and lists → compact JSON strings.
- **Golden vectors are the authority.** `tests/fixtures/hmac-vectors.json` is a verbatim copy of `proofage-php-sdk/resources/hmac-vectors.json` (sections `json`, `multipart`, `webhook`), the file the app also runs through its real `VerifyHmacSignature` middleware. The signing tests are written first and must pass before any resource code (§9).

### 5.2 Retries

| Request | Retried on | Never retried on |
|---|---|---|
| `GET` | 408, 429, 5xx, timeouts, connection errors | 4xx other than 408/429 |
| `POST` | 429; connection errors raised **before** the request was sent (DNS failure, connection refused) | 5xx, read timeouts: the server may already have created the verification or stored the upload |
| Media download | Transport failures only, up to `download_retry_attempts` | Any HTTP status, 429 included: downloads usually run from a queue whose own backoff owns the wait |

A 429 waits for `Retry-After` when present, otherwise `retry_delay × attempt`. The rule set is the Node SDK's (`AGENTS.md` "Retries") and the PHP SDK's (spec §4.5), so a request behaves the same in every language.

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
                                   INVALID_AUTH_CLIENT, TIMESTAMP_TOO_OLD, INVALID_SIGNATURE, CONFIGURATION_ERROR
```

Python callers branch on exception type far more than on status codes, so this hierarchy is finer than Node's (which has only `AuthenticationError` and `ValidationError`). Every class still exposes `status_code` and `code`, so a Node-style `if e.code == ...` works too.

The error body is parsed in all four shapes the API sends (`proofageapp` developer-docs, and `proofage-node-client/AGENTS.md` "Errors"):

1. `{"error": {"code", "message"}}`: `error_data` is the inner object.
2. Flat `{"code", "message", ...extra}` (402, media-quality 422, 500 `VALIDATION_SERVICE_UNAVAILABLE`): `error_data` is the whole body.
3. `{"message", "errors"}` (request validation 422): `code` is `None`, `errors` has the fields.
4. `{"message"}` (403, 404).

A 2xx with an empty body returns `None`. A non-empty 2xx that is not JSON raises `ProofAgeError` whose message says that `base_url` most likely points at a website rather than the API; this is the most common first-run mistake.

---

## 7. Webhooks and integrations

### 7.1 Core

```python
from proofage import verify_webhook

event = verify_webhook(raw_body, headers)          # -> WebhookEvent, or raises WebhookVerificationError
```

- `raw_body` is `bytes` exactly as received. `headers` is any case-insensitive mapping.
- Checks, in order: `X-HMAC-Signature`, `X-Timestamp`, `X-Auth-Client` present; `X-Auth-Client` equals the api key; timestamp within `tolerance` seconds (argument → `PROOFAGE_WEBHOOK_TOLERANCE` → 300); signature equals hex `HMAC-SHA256(secret, f"{timestamp}.{raw_body}")`, compared with `hmac.compare_digest`. If the raw body does not match, the canonical re-serialisation of the JSON is tried once, as the Node SDK does (`src/webhook.ts`).
- `WebhookEvent` exposes `delivery_id` from `X-ProofAge-Webhook-Delivery-Id`: the same on every automatic retry of one delivery, new on a manual resend. The README tells integrators to de-duplicate on it.

### 7.2 Extras (0.1.0)

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
| `create_verification`, `get_verification`, `get_workspace` | on | What an agent that onboards people needs |
| `get_verification_document`, `get_age_estimation` | **off**; `include_personal_data=True` | Names, dates of birth and document numbers should not flow into a model's context unless the integrator decides so |
| `block_face` | **off**; `include_destructive=True` | Irreversible for the person; the ProofAge consoles require a reason code for the same reason |
| capture endpoints, media download | never | Binary data and camera steps are not agent work |

---

## 8. Contract with the API

The same three layers as the other SDKs (`proofage-node-client/CLAUDE.md` "Changing the API surface", and the Laravel client's `docs/superpowers/specs/2026-06-29-laravel-client-api-contract-design.md`):

1. **Bundled spec.** `src/proofage/openapi.json`, refreshed by `scripts/sync_spec.py` from `proofageapp/developer-docs/public/openapi.json` (the Scramble export).
2. **`AGENTS.md`** ships in the wheel and is the authoritative response contract where the spec is thin.
3. **Contract test.** `tests/test_api_contract.py` asserts that every operation in the bundled spec maps to exactly one SDK method, that every request field in the spec is accepted by that method, and that for the operations Scramble fully describes, every response field exists on the model. A new API endpoint therefore fails CI here until the SDK method, the model and `AGENTS.md` land together.

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

- **CI** (`ci.yml`, on push and pull request): Python 3.11, 3.12, 3.13, 3.14 on Linux; one extra leg per integration at the framework's oldest supported version; ruff and mypy on the newest Python only, so a tool-version drift cannot break the whole matrix (the lesson the PHP SDK learned when an unpinned Pint reddened one matrix leg). A Python version leaves the matrix when its **security** window closes.
- **Versioning**: `src/proofage/_version.py` is the single source; hatchling reads it.
- **Release**: `scripts/check_release.py X.Y.Z` reads `https://pypi.org/pypi/proofage/json` and refuses a version already served or below the latest, because the registry, not `git tag`, is the truth (the laravel-client tags were once missing published releases). Then: bump, commit `chore: release X.Y.Z`, push, tag `vX.Y.Z`, push the tag. `publish.yml` builds sdist and wheel and publishes through Trusted Publishing, environment `pypi`. Never `twine upload` by hand.
- **One-time setup, by the owner:** PyPI account with 2FA; PyPI organisation `ProofAge`; a pending publisher for owner `ProofAge`, repo `python-sdk`, workflow `publish.yml`, environment `pypi`; the matching `pypi` environment in the GitHub repo settings. Optionally the same on test.pypi.org for a dry run.

---

## 11. Changes outside this repo

In `proofageapp` (separate, small commits):

1. `developer-docs`: add Python to the published-SDKs page and to the quick start, next to Node and PHP.
2. `developer-docs/README.md` § "Keeping the SDK clients in sync": add `proofage-python-sdk` and its `scripts/sync_spec.py` to the list of SDKs refreshed after an API change.

Later, not part of this spec: the Telegram bot template repository (D8), built on 0.1.0.

---

## 12. Release plan

| Release | Contents | Done when |
|---|---|---|
| **0.1.0** | Config, signing, transport, both clients, all `/v1` methods, models, errors, `verify_webhook`, FastAPI/Django/Flask extras, `examples/`, `AGENTS.md`, README, CI, publish workflow | Golden vectors, contract test and the full suite pass on 3.11–3.14; a real verification created against a test workspace and its webhook verified end to end with the FastAPI example |
| **0.2.0** | `proofage.agents` with the tool policy of §7.3, OpenAI and Anthropic exporters, LangChain/CrewAI/PydanticAI adapter snippets in the README | A tool loop with each vendor SDK creates a verification against a test workspace |

---

## 13. Open questions

1. **A1**: is 3.11 the right floor, or does a known prospect need 3.10 until its October 2026 end of life?
2. **A5**: publish 0.1.0 the moment the core is green (name claimed sooner, extras in 0.1.x), or hold it for the extras?
3. Should `proofage.agents` also offer a `get_verification_status` tool that returns only `status` and `reason`, so the default set exposes even less than `get_verification`'s `external_metadata`?
