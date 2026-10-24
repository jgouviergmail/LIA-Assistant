"""A form streamed from disk is the form httpx would send, and never a changed file (AC-035).

``multipart_upload`` replaces httpx's ``files=`` for the STT uploads, so the bytes a
vendor receives must not move by one: the body is compared, byte for byte, with
httpx's own encoding of the same form under the same boundary — escaped names and
filenames included — and the declared length with the length httpx declares.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import httpx
import pytest

from src.infrastructure.file_transfer import LocalFileRead
from src.infrastructure.multipart_upload import FormFile, MultipartUpload, multipart_upload

pytestmark = pytest.mark.unit

# A quote, a backslash and line breaks are escaped by httpx; "été" travels as UTF-8.
FIELDS = {"model": "proof-model", "language": "fr", "note": 'say "hi"\\\r\nété'}
FILE = FormFile(field="file", filename='réunion "du\nlundi".ogg', content_type="audio/ogg")
AUDIO = bytes(range(256)) * 600  # 153 600 bytes: three reads of 64 KiB


async def _sent(upload: MultipartUpload) -> bytes:
    return b"".join([chunk async for chunk in upload.content])


def _httpx_encoding(upload: MultipartUpload, content: bytes | Path) -> tuple[bytes, str]:
    """The body and length httpx frames for the same form, under the boundary ``upload`` drew."""
    with ExitStack() as stack:
        payload = content if isinstance(content, bytes) else stack.enter_context(content.open("rb"))
        request = httpx.Request(
            "POST",
            "https://stt.invalid/v1",
            headers={"Content-Type": upload.headers["Content-Type"]},
            data=FIELDS,
            files={FILE.field: (FILE.filename, payload, FILE.content_type)},
        )
        return request.read(), request.headers["Content-Length"]


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "meeting.ogg"
    path.write_bytes(AUDIO)
    return path


async def test_a_file_on_disk_is_framed_exactly_as_httpx_frames_it(audio: Path) -> None:
    reader = await LocalFileRead.async_open(audio)
    try:
        upload = multipart_upload(FIELDS, FILE, reader)
        sent = await _sent(upload)
    finally:
        await reader.close()

    body, length = _httpx_encoding(upload, audio)
    assert sent == body
    assert upload.headers["Content-Length"] == length == str(len(sent))
    assert upload.headers["Content-Type"].startswith("multipart/form-data; boundary=")


async def test_bytes_held_in_memory_are_framed_exactly_as_httpx_frames_them() -> None:
    upload = multipart_upload(FIELDS, FILE, AUDIO)

    sent = await _sent(upload)

    body, length = _httpx_encoding(upload, AUDIO)
    assert sent == body
    assert upload.headers["Content-Length"] == length == str(len(sent))


def test_every_upload_draws_its_own_boundary() -> None:
    first = multipart_upload(FIELDS, FILE, b"a").headers["Content-Type"]
    second = multipart_upload(FIELDS, FILE, b"a").headers["Content-Type"]

    assert first != second


@pytest.mark.parametrize("change", ["grown", "shrunk"])
async def test_a_file_that_changes_under_the_upload_is_refused(audio: Path, change: str) -> None:
    reader = await LocalFileRead.async_open(audio)
    try:
        upload = multipart_upload(FIELDS, FILE, reader)
        with audio.open("r+b") as handle:
            if change == "grown":
                handle.seek(0, 2)
                handle.write(b"bytes written after the length was declared")
            else:
                handle.truncate(1000)
        with pytest.raises(OSError, match="changed"):
            await _sent(upload)
    finally:
        await reader.close()


async def test_framing_a_body_leaves_the_file_to_its_opener(
    audio: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []
    real_close = LocalFileRead.close

    async def close(reader: LocalFileRead) -> None:
        await real_close(reader)
        closed.append(reader.closed)

    monkeypatch.setattr(LocalFileRead, "close", close)
    reader = await LocalFileRead.async_open(audio)
    await _sent(multipart_upload(FIELDS, FILE, reader))

    assert closed == [], "a body that was sent whole never closes the file it read"
    await reader.close()
    assert closed == [True]
