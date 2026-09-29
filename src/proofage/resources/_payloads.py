"""Payload builders and id checks shared by the sync and async resources."""

from __future__ import annotations

import os
import re
import warnings
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO

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


MEDIA_TYPES = ("selfie", "liveness_selfie", "document")


def read_upload(
    file: bytes | bytearray | os.PathLike[str] | BinaryIO, filename: str | None
) -> tuple[bytes, str]:
    """The bytes to upload and the filename to send with them."""
    if isinstance(file, (bytes, bytearray)):
        return bytes(file), filename or "upload.bin"
    if isinstance(file, os.PathLike):
        path = Path(file)
        return path.read_bytes(), filename or path.name
    read = getattr(file, "read", None)
    if read is None:
        raise TypeError("upload_media(file=...) takes bytes, a pathlib.Path or a binary file")
    data = read()
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("upload_media(file=...) needs bytes: open the file in binary mode ('rb')")
    raw_name = getattr(file, "name", None)
    default_name = Path(raw_name).name if isinstance(raw_name, str) else "upload.bin"
    return bytes(data), filename or default_name


def upload_fields(
    *,
    type: str,
    side: str | None,
    document: str | None,
    fingerprint: str | None,
    head_turn_step: int | None,
    capture_resolution: str | dict[str, Any] | None,
    device_info: str | dict[str, Any] | None,
    liveness_telemetry: str | list[Any] | None,
) -> dict[str, Any]:
    """The multipart fields of a media upload; `document` uploads need `side` and `document`."""
    if type not in MEDIA_TYPES:
        raise ValueError(f"type must be one of {', '.join(MEDIA_TYPES)}, got {type!r}")
    if type == "document" and (side is None or document is None):
        raise ValueError("a document upload needs side= ('front'/'back') and document=")
    return {
        "type": type,
        "side": side,
        "document": document,
        "fingerprint": fingerprint,
        "head_turn_step": head_turn_step,
        "capture_resolution": capture_resolution,
        "device_info": device_info,
        "liveness_telemetry": liveness_telemetry,
    }


def warn_widget_fields(method: str, values: dict[str, Any]) -> None:
    """Warn about arguments only the ProofAge widget sends: the API accepts them, but they are not
    part of its public contract and will leave these signatures in a future minor release."""
    passed = [name for name, value in values.items() if value is not None]
    if not passed:
        return
    verb = "is" if len(passed) == 1 else "are"
    warnings.warn(
        f"{method}(): {', '.join(passed)} {verb} sent by the ProofAge widget, not part of the "
        "public API, and will be removed in a future minor release.",
        DeprecationWarning,
        stacklevel=3,
    )
