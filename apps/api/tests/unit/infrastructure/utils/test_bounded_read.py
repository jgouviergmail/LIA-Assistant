"""The ceiling of a streamed body holds DURING decompression, not after it.

httpx 0.28 inflates each raw chunk whole before anyone can count it: measured in
the API image, a 6 419-byte zstd body became 209 715 200 bytes in memory, and
under the former reader one decoded gzip chunk already weighed 67 MiB by the time
the ceiling fired (F2 of the dependency programme). These tests stream real
encoded bodies through a real httpx response, chunk by chunk, and hold the
reader to what it allocates — not only to what it returns.
"""

from __future__ import annotations

import gzip
import tracemalloc
import zlib
from collections.abc import AsyncIterator
from compression import zstd

import httpx
import pytest

from src.infrastructure.utils.bounded_read import (
    ACCEPT_ENCODING_HEADER,
    ACCEPTED_ENCODINGS,
    BodyTooLargeError,
    UnsupportedEncodingError,
    read_bounded,
)

pytestmark = pytest.mark.unit

_MIB = 1 << 20
#: The ceiling the bomb tests read under.
_CEILING = _MIB
#: What one read may allocate in all: the ceiling, a raw chunk, the decoder's
#: own state and httpx's — far below what one inflated chunk weighs (64 MiB+).
_PEAK_BOUND = 8 * _MIB
#: What the bombs inflate to.
_BOMB_SIZE = 200 * _MIB
#: The raw chunk size a real connection hands over.
_RAW_CHUNK = 64 * 1024


class _Chunks(httpx.AsyncByteStream):
    """A body as the network delivers it: raw bytes, one chunk at a time."""

    def __init__(self, data: bytes, size: int) -> None:
        self._data = data
        self._size = size

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self._data), self._size):
            yield self._data[start : start + self._size]


async def _read(
    data: bytes,
    *,
    encoding: str | None = None,
    max_bytes: int = _CEILING,
    chunk: int = _RAW_CHUNK,
) -> bytes:
    """Serve ``data`` as-is under ``encoding`` and read it through ``read_bounded``."""
    headers = {"content-type": "text/html"}
    if encoding is not None:
        headers["content-encoding"] = encoding

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, stream=_Chunks(data, chunk))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async with client.stream("GET", "https://example.test/page") as response:
            return await read_bounded(response, max_bytes)


def _gzip_bomb(size: int) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    block = bytes(_MIB)
    parts = [compressor.compress(block) for _ in range(size // _MIB)]
    parts.append(compressor.flush())
    return b"".join(parts)


def _zstd_bomb(size: int) -> bytes:
    compressor = zstd.ZstdCompressor()
    block = bytes(_MIB)
    parts = [compressor.compress(block) for _ in range(size // _MIB)]
    parts.append(compressor.flush())
    return b"".join(parts)


def _deflate(data: bytes, *, raw: bool) -> bytes:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS if raw else zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


@pytest.fixture(scope="module")
def gzip_bomb() -> bytes:
    return _gzip_bomb(_BOMB_SIZE)


@pytest.fixture(scope="module")
def zstd_bomb() -> bytes:
    return _zstd_bomb(_BOMB_SIZE)


class TestABombIsRefusedBeforeItInflates:
    @pytest.mark.parametrize("bomb_name", ["gzip_bomb", "zstd_bomb"])
    async def test_the_ceiling_holds_during_decompression(
        self, bomb_name: str, request: pytest.FixtureRequest
    ) -> None:
        bomb: bytes = request.getfixturevalue(bomb_name)
        encoding = "gzip" if bomb_name == "gzip_bomb" else "zstd"
        # The raw body is tiny: a check on the received size would let it through.
        assert len(bomb) < _CEILING

        tracemalloc.start()
        try:
            with pytest.raises(BodyTooLargeError) as refusal:
                await _read(bomb, encoding=encoding)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert refusal.value.max_bytes == _CEILING
        assert peak < _PEAK_BOUND, f"{peak / _MIB:.0f} MiB allocated under a 1 MiB ceiling"


class TestTheCeilingIsExact:
    @pytest.mark.parametrize("encoding", [None, "gzip"])
    async def test_a_body_at_the_ceiling_is_read_and_one_byte_more_is_not(
        self, encoding: str | None
    ) -> None:
        def encode(data: bytes) -> bytes:
            return gzip.compress(data) if encoding == "gzip" else data

        exact = b"x" * _CEILING

        assert await _read(encode(exact), encoding=encoding) == exact
        with pytest.raises(BodyTooLargeError):
            await _read(encode(exact + b"y"), encoding=encoding)

    async def test_an_unannounced_identity_stream_stops_at_the_ceiling(self) -> None:
        # No Content-Length: only the count of what arrives can stop it.
        with pytest.raises(BodyTooLargeError):
            await _read(bytes(3 * _CEILING), chunk=4096)


class TestWhatTheReaderDecodes:
    _PAGE = ("<html><body>" + "Ceci est une page. " * 2000 + "</body></html>").encode()

    @pytest.mark.parametrize(
        ("encoding", "encode"),
        [
            (None, lambda data: data),
            ("identity", lambda data: data),
            ("gzip", gzip.compress),
            (" GZIP ", gzip.compress),
            # RFC 9110 §8.4.1.3: a recipient SHOULD read "x-gzip" as "gzip".
            ("x-gzip", gzip.compress),
            ("deflate", lambda data: _deflate(data, raw=False)),
            ("deflate", lambda data: _deflate(data, raw=True)),
            ("zstd", zstd.compress),
        ],
        ids=[
            "absent",
            "identity",
            "gzip",
            "gzip-spelled-loosely",
            "x-gzip",
            "deflate",
            "raw-deflate",
            "zstd",
        ],
    )
    async def test_each_accepted_encoding_reads_back_the_page(
        self, encoding: str | None, encode: object
    ) -> None:
        assert callable(encode)
        assert await _read(encode(self._PAGE), encoding=encoding, chunk=1000) == self._PAGE

    async def test_every_frame_of_a_zstd_body_is_read(self) -> None:
        # httpx reads concatenated zstd frames, and so must the reader that replaced it.
        two_frames = zstd.compress(b"first,") + zstd.compress(b"second")

        assert await _read(two_frames, encoding="zstd", chunk=7) == b"first,second"

    @pytest.mark.parametrize("encoding", ["gzip", "zstd", "deflate"])
    async def test_an_empty_body_is_empty_whatever_its_encoding(self, encoding: str) -> None:
        assert await _read(b"", encoding=encoding) == b""

    async def test_bytes_after_the_compressed_stream_are_ignored_without_a_loop(self) -> None:
        trailing = gzip.compress(b"the page") + b"\x00garbage after the stream" * 1000

        assert await _read(trailing, encoding="gzip", chunk=16) == b"the page"

    @pytest.mark.parametrize("encoding", ["gzip", "deflate"])
    async def test_what_follows_the_compressed_stream_is_never_held(self, encoding: str) -> None:
        # The ceiling counts DECODED bytes, and nothing decodes after the end of
        # the stream: a server that keeps sending must not fill the memory.
        page = (
            gzip.compress(b"the page") if encoding == "gzip" else _deflate(b"the page", raw=False)
        )
        body = page + bytes(16 * _MIB)

        tracemalloc.start()
        try:
            read = await _read(body, encoding=encoding)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert read == b"the page"
        assert peak < _PEAK_BOUND, f"{peak / _MIB:.0f} MiB held after the stream ended"


class TestWhatTheReaderRefuses:
    @pytest.mark.parametrize("encoding", ["br", "compress", "x-zstd", "gzip, gzip", "gzip, zstd"])
    async def test_an_encoding_it_cannot_bound_is_refused_before_any_decode(
        self, encoding: str
    ) -> None:
        with pytest.raises(UnsupportedEncodingError) as refusal:
            await _read(b"\xff" * 10, encoding=encoding)

        assert refusal.value.encoding == encoding.lower().replace(" ", "")
        # Every caller already handles transport failures: a refused body is one.
        assert isinstance(refusal.value, httpx.DecodingError)

    @pytest.mark.parametrize(
        ("encoding", "encoded"),
        [("gzip", gzip.compress(b"x" * 50_000)), ("zstd", zstd.compress(b"x" * 50_000))],
    )
    async def test_a_truncated_stream_is_an_error_not_a_short_body(
        self, encoding: str, encoded: bytes
    ) -> None:
        with pytest.raises(httpx.DecodingError):
            await _read(encoded[: len(encoded) // 2], encoding=encoding, chunk=8)

    @pytest.mark.parametrize("encoding", ["gzip", "deflate", "zstd"])
    async def test_corrupt_data_is_a_decoding_error(self, encoding: str) -> None:
        with pytest.raises(httpx.DecodingError):
            await _read(b"this is not compressed at all" * 10, encoding=encoding)


async def test_a_body_already_in_memory_still_answers_to_the_ceiling() -> None:
    """A response built with ``content=`` — as test transports build them — was read
    at construction: nothing is left to stream, the verdict still holds."""
    exact = httpx.Response(200, content=b"x" * _CEILING)
    over = httpx.Response(200, content=b"x" * (_CEILING + 1))

    assert await read_bounded(exact, _CEILING) == b"x" * _CEILING
    with pytest.raises(BodyTooLargeError):
        await read_bounded(over, _CEILING)


def test_what_httpx_advertises_is_what_the_reader_decodes() -> None:
    """A deployment that installs a new decoder (brotli) advertises it on every request.

    The reader would then refuse the answers it invited: the advertisement and the
    decoders are one list, and this test is the moment someone has to decide.
    """
    with httpx.Client() as client:
        advertised = client.headers["accept-encoding"]

    assert {part.strip() for part in advertised.split(",")} == set(ACCEPTED_ENCODINGS)
    assert ACCEPT_ENCODING_HEADER == ", ".join(ACCEPTED_ENCODINGS)
