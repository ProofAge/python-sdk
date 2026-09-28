# Working in this repo

## Releasing

Take the next version from PyPI, never from `git tag`:
`uv run python scripts/check_release.py X.Y.Z` prints what PyPI serves and refuses a
number already taken or below the latest.

Steps: edit `src/proofage/_version.py` and the CHANGELOG heading → commit
`chore: release X.Y.Z` → push `main` → `git tag vX.Y.Z` → push the tag. The tag runs
`.github/workflows/publish.yml` (Trusted Publishing, environment `pypi`). Never upload by hand.

## Changing the API surface

The contract lives in the app repo: `proofageapp/developer-docs/README.md`, "Keeping the
SDK clients in sync". Here: `uv run python scripts/sync_spec.py`, then make
`tests/test_api_contract.py` pass by updating `OPERATIONS`, the resource methods, the models
and `AGENTS.md` together. `AGENTS.md` ships in the wheel; this file does not.

## HMAC vectors

`tests/fixtures/hmac-vectors.json` is a verbatim copy of `resources/hmac-vectors.json` from
`proofage/php-sdk`, the file the app also runs through its real middleware. Refresh it by
copying when that file changes; never edit it by hand.

## Supported Python versions

See the README table. A version leaves on its dated line, in a minor release announced a
release ahead. When one leaves: update `requires-python`, the classifiers, the CI matrix,
the README table and `[tool.ruff] target-version` / `[tool.mypy] python_version` together.
