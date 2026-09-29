from __future__ import annotations

import io
from pathlib import Path

import pytest
import respx

from proofage import ProofAge

from .conftest import API_KEY, SECRET_KEY, VERIFICATION_ID, Harness

VID = VERIFICATION_ID


def test_upload_bytes_as_a_document(sdk: Harness, api: respx.MockRouter) -> None:
    route = api.post(f"/verifications/{VID}/media").respond(200)
    with pytest.warns(DeprecationWarning, match="device_info"):
        result = sdk.call(
            lambda c: c.verifications.upload_media(
                VID,
                file=b"jpeg",
                type="document",
                side="front",
                document="passport",
                device_info={"os": "iOS"},
            )
        )
    assert result is None
    content = route.calls.last.request.content
    assert b'filename="upload.bin"' in content
    assert b'name="side"\r\n\r\nfront' in content
    assert b'name="device_info"\r\n\r\n{"os":"iOS"}' in content


def test_upload_a_path_takes_its_name(tmp_path: Path, api: respx.MockRouter) -> None:
    picture = tmp_path / "selfie.jpg"
    picture.write_bytes(b"jpeg")
    route = api.post(f"/verifications/{VID}/media").respond(200)
    with ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url="https://api.test") as c:
        c.verifications.upload_media(VID, file=picture, type="selfie")
    assert b'filename="selfie.jpg"' in route.calls.last.request.content
    assert b"Content-Type: image/jpeg" in route.calls.last.request.content


def test_upload_a_binary_file_object(tmp_path: Path, api: respx.MockRouter) -> None:
    picture = tmp_path / "front.png"
    picture.write_bytes(b"png")
    route = api.post(f"/verifications/{VID}/media").respond(200)
    with (
        ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url="https://api.test") as c,
        picture.open("rb") as handle,
    ):
        c.verifications.upload_media(VID, file=handle, type="document", side="back", document="id")
    assert b'filename="front.png"' in route.calls.last.request.content


def test_a_text_mode_file_is_refused_before_any_request(api: respx.MockRouter) -> None:
    with (
        ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url="https://api.test") as c,
        pytest.raises(TypeError, match="binary mode"),
    ):
        c.verifications.upload_media(VID, file=io.StringIO("text"), type="selfie")
    assert not api.calls


@pytest.mark.parametrize(
    "kwargs", [{"type": "document"}, {"type": "document", "side": "front"}, {"type": "passport"}]
)
def test_invalid_combinations_are_refused(api: respx.MockRouter, kwargs: dict[str, str]) -> None:
    with (
        ProofAge(api_key=API_KEY, secret_key=SECRET_KEY, base_url="https://api.test") as c,
        pytest.raises(ValueError),
    ):
        c.verifications.upload_media(VID, file=b"x", **kwargs)
    assert not api.calls


def test_a_media_rejection_is_a_validation_error(sdk: Harness, api: respx.MockRouter) -> None:
    from proofage.errors import ValidationError

    api.post(f"/verifications/{VID}/media").respond(
        422, json={"code": "FACE_NOT_FOUND", "message": "No face found"}
    )
    with pytest.raises(ValidationError) as raised:
        sdk.call(lambda c: c.verifications.upload_media(VID, file=b"x", type="selfie"))
    assert raised.value.code == "FACE_NOT_FOUND"
