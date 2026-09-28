"""Payload builders and id checks shared by the sync and async resources."""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import Enum
from typing import Any

_ID = re.compile(r"[A-Za-z0-9_-]+")


def path_segment(value: str, label: str) -> str:
    """An id placed in a URL path; anything else would let a caller reach another path."""
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(
            f"{label} must be a ProofAge id (letters, digits, '-' and '_'), got {value!r}"
        )
    return value


def verification_path(verification_id: str, suffix: str = "") -> str:
    """`verifications/{id}{suffix}` with the id checked."""
    return f"verifications/{path_segment(verification_id, 'verification_id')}{suffix}"


def compact(values: Mapping[str, Any]) -> dict[str, Any]:
    """Drop the arguments left at None; turn enum members into their values."""
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in values.items()
        if value is not None
    }
