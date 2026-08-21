"""Every compiled (native-wheel) runtime dependency imports on the current interpreter.

A new interpreter invalidates every cpXY wheel at once, and a missing/broken wheel
otherwise surfaces only at the first runtime use of its subsystem (STT, PDF, images,
LangGraph checkpointing…). `audioop` is here because the stdlib module was removed in
Python 3.13 and is now provided by `audioop-lts` — its absence broke `import pydub`
invisibly for months (audited 2026-07-29, closed by ADR-241). Pure-Python deps are
excluded on purpose: they cannot break this way.
"""

from __future__ import annotations

import importlib
import sys

import pytest

NATIVE_MODULES = [
    "aiohttp",
    "asyncpg",
    "audioop",  # audioop-lts on Python >= 3.13 (pydub's hard dependency)
    "bcrypt",
    "cffi",
    "cryptography.fernet",
    "frozenlist",
    "google.protobuf",
    "greenlet",
    "grpc",
    "jiter",
    "lxml.etree",
    "maxminddb",
    "msgpack",
    "multidict",
    "numpy",
    "orjson",
    "ormsgpack",
    "PIL",
    "psycopg",
    "pydantic_core",
    "pymupdf",
    "regex",
    "rpds",
    "sherpa_onnx",
    "tiktoken",
    "watchfiles",
    "websockets",
    "xxhash",
    "yarl",
    "zstandard",
]


@pytest.mark.parametrize("module", NATIVE_MODULES)
def test_native_module_imports(module: str) -> None:
    """Importing the module proves a working wheel exists for this interpreter/platform."""
    importlib.import_module(module)


def test_posix_only_native_modules_import() -> None:
    """uvloop/httptools are excluded on win32 by lock markers — assert them elsewhere."""
    if sys.platform == "win32":
        pytest.skip("uvloop/httptools are not installed on win32 (lockfile markers)")
    importlib.import_module("uvloop")
    importlib.import_module("httptools")
