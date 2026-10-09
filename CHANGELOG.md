# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org/); while the version is 0.x, a minor
release may change the API and a patch release never does.

## 0.9.0 — 2026-10-09

- **Changed:** the default `base_url` is `https://api.proofage.net`, where ProofAge moved on
  9 October 2026. `https://api.proofage.xyz` keeps answering the same API with the same keys and
  signatures, so a client that pins `base_url` (or `PROOFAGE_BASE_URL`) to it keeps working. No
  other behaviour changes.
- **Changed:** the bundled `openapi.json` is synced from `https://docs.proofage.net/openapi.json`,
  which `scripts/sync_spec.py` now reads by default; the only differences are the hostnames.

## 0.8.0 — 2026-10-09

- **Added:** `client.verifications.list(status=, external_id=, limit=, cursor=)` → `VerificationList`
  (`data`, `next_cursor`): the workspace's verifications, newest first, a page at a time. `status`
  takes one status, a list or a comma-separated string. The query string is built, signed and sent
  in the form the API normalises (keys sorted, RFC 3986).
- **Added:** `client.webhook_subscriptions.create(url=, statuses=, include_document_data=)`,
  `list()` and `delete(subscription_id)`, for REST hooks such as Zapier. DELETE follows the POST
  retry rules: never retried on a 5xx.
- **Added:** `client.verifications.set_test_outcome(verification_id, status=, reason=)` and the
  `VerificationOutcome` enum: finish a verification in a test workspace without a person.
- **Fixed:** `ManualModeration.performed_by` is optional. A webhook subscription created without
  `include_document_data` receives `manual_moderation` without it, which `verify_webhook` rejected
  as `INVALID_PAYLOAD`.

## 0.7.0 — 2026-10-08

- **Added:** `WebhookEvent.event` (`WebhookEventType.STATUS_UPDATED` or `DATA_UPDATED`, an unknown
  value as a plain string) and `WebhookEvent.changed_fields`. `data.updated` is sent when a tenant
  corrects document fields the reader got wrong: `status` is the current one, unchanged, `document`
  holds the corrected values and `changed_fields` names what changed. Both default to `None`, so a
  body without `event` (a retry of an older delivery, which means `status.updated`) still parses.
  Read `event` before `status`; the examples and `AGENTS.md` do.

## 0.6.0 — 2026-10-02

- **Added:** `Document.issuing_subdivision`, the state or province of issuance as a bare code
  (`FL` with `US`), or `None`; filled today for US driving licences and ID cards. It defaults to
  `None`, so an older body still parses, and it also arrives on `WebhookEvent.document`.

## 0.5.0 — 2026-10-01

- **Added:** `DocumentFields.address` on identity (KYC) workspaces: the printed text as read,
  trimmed, `None` when empty, not parsed and possibly several lines. It defaults to `None`, so an
  age-workspace body (where the key is absent) still parses. `DocumentGender.X` now means the
  document states that the sex is unspecified.
- **Added:** `WebhookEvent.document`, the `Document` model `verifications.document()` returns, on
  every decision webhook (no media). It defaults to `None`, so a body sent before it existed, or one
  from a retry after erasure, still parses; the FastAPI, Django and Flask integrations hand it on.

## 0.4.0 — 2026-09-30

- **Added:** `verifications.document()` returns `document.type` and `document.issuing_country` on
  every workspace, and on identity (KYC) workspaces six more `DocumentFields`: `middle_name`,
  `gender`, `nationality`, `place_of_birth`, `issue_date` and `expiry_date`. All default to `None`,
  so an older API body and an age-workspace body (where the six keys are absent) still parse.
  `type` and `gender` are open enums (`DocumentResultType`, `DocumentGender`): an unknown value
  arrives as a plain string.

## 0.3.1 — 2026-09-29

- **Deprecated:** the keyword arguments only the ProofAge widget sends: `fingerprint` and `page_url`
  on `create()`, the browser fields of `accept_consent()` (`device`, `in_app_browser`,
  `camera_permission`, `camera_policy_allowed`, `in_iframe`, `referrer`), and the capture fields and
  `type="liveness_selfie"` of `upload_media()`. They are not part of the public API; the API still
  accepts them, so they keep working and now raise `DeprecationWarning`. They will be removed in a
  future minor release. `AGENTS.md` documents only the public contract.
- **Changed:** the bundled `openapi.json` is synced from the published docs, and
  `scripts/sync_spec.py` reads `https://docs.proofage.xyz/openapi.json` by default.

## 0.3.0 — 2026-09-28

- **Added:** webhook integrations as extras: `proofage[fastapi]`, `proofage[django]` and
  `proofage[flask]` (`proofage.integrations.*`). Each verifies the request and hands the handler a
  typed `WebhookEvent`; a failed verification is answered 401, 400 or 500 before your code runs.
- **Added:** runnable examples in `examples/`: an aiogram Telegram bot, a FastAPI app and Django
  views.

## 0.2.0 — 2026-09-28

- **Changed:** `ConsentInfo.version` is an `int`, the type the API has always sent. 0.1.0
  typed it `str` after the API's own documentation, and turned the number into a string.

## 0.1.0 — 2026-09-28

First release.

- `ProofAge` and `AsyncProofAge` clients for every `/v1` endpoint.
- Pydantic v2 response models; unknown fields and statuses never break parsing.
- Typed errors for the API's four error body shapes.
- Retries that never repeat a POST the server may already have acted on.
- Webhook verification (`verify_webhook`, `verify_webhook_signature`).
- `X-ProofAge-Sdk` and User-Agent identification on every request.
- Supports Python 3.10–3.14.
