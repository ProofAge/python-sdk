# Changelog

All notable changes to this project are documented here. The project follows
[Semantic Versioning](https://semver.org/); while the version is 0.x, a minor
release may change the API and a patch release never does.

## 0.1.0 — 2026-09-28

First release.

- `ProofAge` and `AsyncProofAge` clients for every `/v1` endpoint.
- Pydantic v2 response models; unknown fields and statuses never break parsing.
- Typed errors for the API's four error body shapes.
- Retries that never repeat a POST the server may already have acted on.
- Webhook verification (`verify_webhook`, `verify_webhook_signature`).
- `X-ProofAge-Sdk` and User-Agent identification on every request.
- Supports Python 3.10–3.14.
