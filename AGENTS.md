# ProofAge Python SDK — API contract for agents

This package wraps the ProofAge v1 HTTP API. Methods live on `client.workspace` and
`client.verifications`; `AsyncProofAge` has the same methods, awaited. Responses are Pydantic
models from `proofage.models`, and they are lenient: a field the SDK does not know yet is kept in
`model.model_extra`, and a status the SDK does not know yet arrives as a plain `str` instead of a
`VerificationStatus` member (compare with `==`, not `is`). `model.model_dump(mode="json")` gives a
plain dict. A machine-readable spec ships next to this file as `openapi.json` (authoritative for
endpoints and request bodies; where it does not describe a response, the shapes below are
authoritative).

All requests send `X-API-Key` and `X-HMAC-Signature`. Request bodies use **snake_case** to match
the API. Responses are never wrapped in `data`.

## Configuration

Argument → environment variable → default. The environment variables use the **Laravel/PHP
SDK's units**, so one `.env` serves both; constructor arguments are seconds as floats.

| Argument | Environment | Default | Notes |
|---|---|---|---|
| `api_key` | `PROOFAGE_API_KEY` | required | Workspace API key |
| `secret_key` | `PROOFAGE_SECRET_KEY` | required | Used only to sign; never sent, never in `repr` |
| `base_url` | `PROOFAGE_BASE_URL` | `https://api.proofage.xyz` | API origin without the version; a trailing `/v1` is stripped; a non-http(s) URL, a query or a fragment raises `ConfigurationError` |
| `version` | `PROOFAGE_VERSION` | `v1` | |
| `timeout` | `PROOFAGE_TIMEOUT` (seconds) | `30.0` | httpx per-operation timeout (connect, each read, each write), not a deadline for the whole request. Node reads this variable in milliseconds |
| `retry_attempts` | `PROOFAGE_RETRY_ATTEMPTS` | `3` | Attempts for interactive requests |
| `retry_delay` | `PROOFAGE_RETRY_DELAY` (**milliseconds**) | `1.0` s | Linear backoff unit; `PROOFAGE_RETRY_DELAY=1000` is one second |
| `download_retry_attempts` | `PROOFAGE_DOWNLOAD_RETRY_ATTEMPTS` | `1` | Media downloads; only transport failures are retried |
| `http_client` | — | owned | Your `httpx.Client` / `httpx.AsyncClient`; the SDK never closes it |
| `sdk_tokens` | — | `()` | `name/version` tokens for a package wrapping this SDK (see "SDK identification") |
| `user_agent` | — | SDK default | Replaces the User-Agent; `X-ProofAge-Sdk` is still sent |

## Errors

Every non-2xx response raises. All request errors extend `ProofAgeError`, which carries
`status_code`, `message`, `code` (the API's machine-readable code, when sent), `error_data` and the
raw `response_body`:

```
ProofAgeError
├── AuthenticationError     401
├── PaymentRequiredError    402  code PAYMENT_METHOD_REQUIRED; error_data has free_verifications_remaining, trial_ends_at, trial_active
├── PermissionDeniedError   403
├── NotFoundError           404
├── ValidationError         422  .errors: dict[str, list[str]]; media rejections carry .code (e.g. FACE_NOT_FOUND)
├── RateLimitError          429  .retry_after: float | None, raised after the retries run out
├── ServerError             5xx
└── TransportError          no response (DNS, connection, TLS, timeout); __cause__ is the httpx exception
ConfigurationError           raised when a client is built
WebhookVerificationError     see "Outbound webhook"
```

The API uses four error body shapes; the client reads all of them:

- `{ error: { code, message } }` — most errors (401 auth, 429 `RATE_LIMIT`, submit 422, media download 404). `error_data` is the inner object.
- `{ code, message, ...extra }` — flat: `402 PAYMENT_METHOD_REQUIRED` (extra: `free_verifications_remaining`, `trial_ends_at`, `trial_active`) and media-quality rejections on upload (`422`, e.g. `FACE_NOT_FOUND`; `500 VALIDATION_SERVICE_UNAVAILABLE`). `error_data` is the whole body.
- `{ message, errors }` — request validation (`422`). `code` is `None`; `errors` has the fields.
- `{ message }` — `403` (verification not in your workspace) and `404` (`Resource not found`).

A 2xx with an empty body returns `None` from the methods typed `-> None`; where a model is
promised, an empty or non-JSON 2xx raises `ProofAgeError` (a non-JSON one almost always means
`base_url` points at a website rather than the API).

Retries: GETs retry on 408, 429, 5xx, timeouts and transport errors. POSTs retry **only** on 429
and on errors raised before anything was sent (`httpx.ConnectError`, `httpx.ConnectTimeout`) —
never on 5xx or after sending began (`WriteError`, `WriteTimeout`, `ReadError`, `ReadTimeout`,
`RemoteProtocolError`), where the server may already have created the verification or stored the
upload. A 429 waits for `Retry-After` (seconds or an HTTP date) when present, up to 60 seconds —
a longer one raises `RateLimitError` at once with `retry_after` set — else `retry_delay * attempt`.
A 2xx whose body does not match the model raises `ProofAgeError` ("Unexpected response shape from
GET /v1/..."), naming the fields but never their values.

## Auth / HMAC

- `X-API-Key`: workspace API key (plaintext; the server SHA256-hashes it).
- `X-HMAC-Signature`: hex HMAC-SHA256 with the workspace secret key over a canonical string:
  - JSON / no-file requests: `METHOD + /{version}/{path} + ?query + rawJsonBody` (direct
    concatenation, no delimiter; the query part only when there is one, keys sorted and values
    RFC 3986-encoded). The body is serialised once, compact, and sent as exactly the signed bytes;
    an empty payload is the empty string, never `{}`.
  - Multipart (file) requests: `METHOD/{version}/{path}\n{fields}\n{comma-joined sorted sha256(file) hashes}`,
    where `{fields}` is PHP `http_build_query(ksort($fields), '', '&', PHP_QUERY_RFC3986)` — keys
    sorted, values `rawurlencode`d (so `! ' ( ) *` are percent-encoded too). The client signs
    exactly what it sends: `None` fields are dropped, numbers are `str(n)`, booleans `"1"`/`"0"`,
    dicts and lists compact JSON strings. Golden vectors: `tests/fixtures/hmac-vectors.json` in the
    source repository.

## Endpoints

### GET /workspace — `client.workspace.get()` → `WorkspaceInfo`
Request: none.
Response: `{ id: str, name: str, flow_type: str, mode: str, age_mode: str|None, age_threshold: int|None, verification_type: str, redirect_url: str|None, webhook_url: str|None, allow_expired_documents: bool, allow_duplicate_accounts: bool }`

### GET /consent — `client.workspace.consent()` → `ConsentInfo`
Request: none.
Response: `{ id: int, version: int, text_sha256: str, url: str }` (`version` is informational: accept consent with `id` and `text_sha256`)

### POST /verifications — `client.verifications.create(**kwargs)` → `CreatedVerification`
Request (all optional keywords): `fingerprint: str(64), callback_url: url(<=2048), external_id: str(<=255), external_metadata: dict, metadata: dict, page_url: str(<=8192)` (`page_url`: the page the verification was started on; only scheme, host and path are kept).
Response (`201`): `{ id, external_id, external_metadata, redirect_url, status, reason, duplicate_check: DuplicateCheck, erasure: Erasure|None, consent_accepted_at, created_at, updated_at, url }` — `url` is the hosted session the person opens.
Errors: `402` `PaymentRequiredError`; `422` `ValidationError`.

- `DuplicateCheck`: `{ checked: bool, duplicate_count: int, duplicates: [ { verification_id: str, external_id: str|None, similarity_score: float, verified_at: datetime|None } ] }` — always present.
- `Erasure`: `{ erased_at: datetime, scope: "personal_data", reason: str|None, requested_via: "customer"|"proofage"|"retention"|None }` — `None` until the verification's personal data is erased. `reason` is an erasure reason code (`data_subject_request`, `customer_request`, `retention_policy`, `test_data`, `other`) or `None` if unrecorded.

### GET /verifications/{verification} — `client.verifications.get(verification_id)` → `Verification`
Request: none.
Response: same as create **without** `url`.

### POST /verifications/{verification}/consent — `client.verifications.accept_consent(verification_id, *, consent_version_id, text_sha256, ...)` → `AcceptConsentResult`
Request: `consent_version_id: int, text_sha256: str(64 hex)`, optional `device: { platform, screen, language, timezone, hardware_concurrency, device_memory }, in_app_browser: str|None, camera_permission: "granted"|"denied"|"prompt"|"unsupported"|None, camera_policy_allowed: bool|None, in_iframe: bool|None, referrer: str|None`. `consent_version_id` / `text_sha256` are `id` / `text_sha256` from `workspace.consent()`. Custom capture flows only.
Response: `{ consent_version_id: int, consent_accepted_at: datetime }`

### POST /verifications/{verification}/media — `client.verifications.upload_media(verification_id, *, file, type, ...)` → `None`
Request (multipart): `file: bytes | pathlib.Path | binary file object (image, <=10 MB; documents >=200px per edge)`, `type: "selfie"|"liveness_selfie"|"document"`, `side: "front"|"back"` and `document: "id"|"driver_license"|"passport"|"residence_permit"` (both required when `type="document"`), optional `filename` (default: the path's name, else `upload.bin`), `fingerprint: str(64), head_turn_step: int(0..10), capture_resolution: str|dict, device_info: str|dict, liveness_telemetry: str|list`. Dicts and lists are sent as JSON strings. A text-mode file raises `TypeError`; an invalid `type`/`side`/`document` combination raises `ValueError`, both before any request. Requires consent accepted first.
Response: `200` with an **empty body**; returns `None`.
Errors: `422` `ValidationError` with `.code` when the image is rejected (e.g. `FACE_NOT_FOUND`) or `.errors` for invalid fields; `500` `ServerError` `VALIDATION_SERVICE_UNAVAILABLE`.

### POST /verifications/{verification}/submit — `client.verifications.submit(verification_id)` → `None`
Request: none.
Response: `200` with an **empty body**. Error: `422` `{ error: { code, message } }` (e.g. `MISSING_REQUIRED_MEDIA`).

### GET /verifications/{verification}/document — `client.verifications.document(verification_id)` → `VerificationDocument`
Request: none.
Response: `{ document: { fields: { first_name: str|None, last_name: str|None, date_of_birth: date|None, document_number: str|None } }, media: [ { id: str, type: "selfie"|"document_front"|"document_back", url: str|None } ], meta: { attempt_id: str|None } }`. `url` is None once the media has been purged or is past retention.

### GET /verifications/{verification}/media/{media} — `download_media()` / `download_media_to()`
`with client.verifications.download_media(verification_id, media_id) as chunks:` yields the image bytes as an iterator (`async with` and an async iterator on `AsyncProofAge`); `client.verifications.download_media_to(verification_id, media_id, path)` streams to disk and returns the `Path`, writing to a temporary sibling and renaming only after a 2xx, so a failure never leaves a partial file. `media_id` is `media[].id` from `document()`; check its `url` is not None first. Requests send `Accept: application/json, */*;q=0.8` so errors come back as JSON. Error: `404` `NotFoundError` with `code == "MEDIA_NOT_FOUND"`. An HTTP status is never retried, 429 included; a transport failure is retried `download_retry_attempts` times, only before the first byte.

### GET /verifications/{verification}/estimation — `client.verifications.estimation(verification_id)` → `AgeEstimation`
Request: none.
Response: `{ verification_id: str, attempt_id: str|None, age_threshold: { minimum: int|None, passed: bool|None, confidence: float|None }, gender: { value: 0|1|None, confidence: float|None }|None }` (gender value: 0=female, 1=male).

### POST /verifications/{verification}/blocked-face — `client.verifications.block_face(verification_id, *, reason_code=None, reason=None)` → `None`
Request: `reason_code: BlockFaceReasonCode | str`, `reason: str(<=1000)`.
Response: `204 No Content`.

Every `verification_id` and `media_id` must be a ProofAge id (letters, digits, `-`, `_`); anything else raises `ValueError` before a request is built.

## Enums

- `status` (`VerificationStatus`): `created`, `started`, `submitted`, `resubmission_requested`, `approved`, `declined`, `abandoned`, `expired`, `review`, or `documents_required` (the last is surfaced from the latest attempt's state, not a verification status). Open: an unknown value arrives as `str`.
- `reason_code` (`BlockFaceReasonCode`): `presentation_attack` (spoof: screen, print or mask), `fraudulent_document` (forged, edited, or not a real document), `scam_or_abuse` (identity may be genuine — blocked for behaviour on your platform), `underage`, `other` (explain in `reason`). Optional over the API, mandatory in the ProofAge consoles: send it whenever a person made the decision, or the block cannot be told apart from an automated one in reporting.
- `reason` (on `declined` / `resubmission_requested`): dotted codes from the server's reason catalog — illustrative examples: `aml.blocklist.face_match`, `document.face.mismatch`, `verification.age_threshold.failed`. Treat `reason` as an open string.

## Outbound webhook (ProofAge → your `callback_url` / workspace webhook URL)

Headers: `X-Auth-Client` (api key), `X-Timestamp` (unix seconds), `X-HMAC-Signature`
(= hex HMAC-SHA256 of `{timestamp}.{rawJsonBody}` with the active secret key),
`X-ProofAge-Webhook-Delivery-Id` (the same on every automatic retry of one delivery, a new one on a
manual resend — de-duplicate on it).

```python
from proofage import WebhookVerificationError, verify_webhook

try:
    # api_key=, secret_key= and tolerance= fall back to the environment
    event = verify_webhook(raw_body, headers)
except WebhookVerificationError as error:
    ...  # answer error.http_status; error.code says which check failed
```

- `verify_webhook(raw_body, headers, *, api_key=None, secret_key=None, tolerance=None)` → `WebhookEvent`; `verify_webhook_signature(...)` → `None` (checks only). Keys and tolerance fall back to `PROOFAGE_API_KEY`, `PROOFAGE_SECRET_KEY`, `PROOFAGE_WEBHOOK_TOLERANCE` (default 300 seconds, in both directions).
- Pass the body **exactly as received** (`bytes` or `str`). A body whose only change is whitespace is still accepted (the canonical compact JSON is tried once), but one that lost PHP's `\/` escapes is not.
- Error codes, in check order: `MISSING_SIGNATURE`, `MISSING_TIMESTAMP`, `MISSING_AUTH_CLIENT` (401); `CONFIGURATION_ERROR` (500, keys missing — checked after the three headers); `INVALID_AUTH_CLIENT`, `MISSING_TIMESTAMP` for a non-integer timestamp, `TIMESTAMP_TOO_OLD`, `INVALID_SIGNATURE` (401); `INVALID_PAYLOAD` (400, correctly signed but not a webhook event; the message names the fields, never the body's values).
- `WebhookEvent`:

```
{
  "verification_id": str,
  "status": VerificationStatus | str,
  "external_id": str|None,
  "external_metadata": dict|None,
  "reason": str|None,                          # a code only on resubmission_requested / declined
  "timestamp": datetime,
  "duplicate_detected": bool (default False),  # the three duplicate_* keys appear together
  "duplicate_count": int|None,
  "duplicate_of": { "verification_id": str, "external_id": str|None }|None,
  "fingerprint_signals": dict|None,
  "manual_moderation": {                       # after a console approve/decline
    "action": "approve"|"decline", "reason": str, "source": "tenant_admin"|"landlord_admin",
    "performed_by": { "id": int, "name": str|None, "email": str|None, "role": str|None },
    "source_status": str|None, "source_reason": str|None
  }|None,
  "delivery_id": str|None                      # from X-ProofAge-Webhook-Delivery-Id
}
```

## Framework integrations

Extras (floors: `fastapi>=0.100`, `flask>=3.0`, `django>=5.2`) that wrap `verify_webhook` (install `proofage[fastapi]`, `proofage[django]` or
`proofage[flask]`; importing one without its framework raises `ImportError` with the exact
command). Each answers a failed verification itself (401, `INVALID_PAYLOAD` 400, `CONFIGURATION_ERROR`
500) and never calls your handler.

- FastAPI: `from proofage.integrations.fastapi import ProofAgeWebhook` — annotate a parameter
  `event: ProofAgeWebhook`; explicit keys: `Depends(webhook_dependency(api_key=, secret_key=, tolerance=))`.
  Error body: `{"detail": {"code", "message"}}`.
- Django: `@proofage_webhook` (bare or with the keyword arguments) — CSRF-exempt, POST-only, sets
  `request.proofage_event`; synchronous views. Error body: `{"error": {"code", "message"}}`.
- Flask: `@proofage_webhook` (bare or with the keyword arguments) — passes the `WebhookEvent` as the
  view's first argument. Error body: `{"error": {"code", "message"}}`.

## SDK identification

Every request carries `X-ProofAge-Sdk: [wrapper tokens ]python/{version}` (wrappers pass
`sdk_tokens=["telegram-bot/1.2.0"]`, outermost first; a wrapper token named `python` is dropped)
and `User-Agent: ProofAge-Python/{version} (Python {x.y.z})` unless you pass `user_agent` or your
`http_client` carries its own. Neither header is part of the signature.

## Keeping this in sync

This contract is drift-tested against `openapi.json` by `tests/test_api_contract.py`, so it stays
aligned with the API. Maintainers refreshing it after an API change: see the SDK contract-sync
runbook in the ProofAge app repo (`developer-docs/README.md`, "Keeping the SDK clients in sync"),
the single source of truth for all SDKs.
