"""Deterministic guard against un-awaited AsyncMock coroutines (F028).

When a mock returns a coroutine that production code (correctly) never awaits —
e.g. a ``MagicMock(spec=SomeClass)`` async attribute, or a bare ``AsyncMock()``
whose *nested* attribute call is synthesised as async — the dangling
``AsyncMockMixin._execute_mock_call`` coroutine is only reported by CPython at
garbage-collection time. Left to chance it lands on a later, innocent test: the
leaking test passes and an unrelated one flakily fails (or the warning is lost at
session teardown). That mis-attribution is the "false green" the audit flagged.

``assert_no_unawaited_asyncmock`` is a generator meant to back an autouse fixture:
it records warnings around the test, forces a cheap generation-0 collection in
teardown, and fails the test *here* if it finalized an un-awaited AsyncMock
coroutine — so the leak is attributed to (and fixed in) its creator.

Design choices:
- **Scoped to AsyncMock** (``_execute_mock_call``): driver-internal teardown
  coroutines such as asyncpg's ``Connection._cancel`` are a separate
  infrastructure concern (a GC artifact at process teardown, not a test-code
  await bug) and must not make the gate flaky.
- **``gc.collect(0)``**: an AsyncMock coroutine leaked by *this* test is retained
  by the young mock's call-tracking cycle (a gen-0 object), so a generation-0
  sweep reclaims it. A full ``gc.collect()`` multiplied the agents suite's
  wall-clock ~6x (regressing F049) for zero extra coverage.
- **A ``showwarning`` shim, not ``catch_warnings(record=True)``**: the latter would
  swallow EVERY per-test warning out of pytest's summary (hiding deprecations and
  defeating the project's ``filterwarnings`` observability). The shim intercepts
  ONLY the AsyncMock coroutine warning and delegates everything else to the
  handler pytest installed, so normal warning reporting is untouched.
"""

from __future__ import annotations

import gc
import warnings
from collections.abc import Iterator
from typing import Any

import pytest

_ASYNCMOCK_COROUTINE_MARKER = "_execute_mock_call"


def _is_asyncmock_leak(category: type, text: str) -> bool:
    return (
        isinstance(category, type)
        and issubclass(category, RuntimeWarning)
        and "was never awaited" in text
        and _ASYNCMOCK_COROUTINE_MARKER in text
    )


def assert_no_unawaited_asyncmock() -> Iterator[None]:
    """Back an autouse fixture with ``yield from assert_no_unawaited_asyncmock()``."""
    leaked: list[str] = []
    original_showwarning = warnings.showwarning

    def _shim(
        message: Warning | str,
        category: type,
        filename: str,
        lineno: int,
        file: Any = None,
        line: str | None = None,
    ) -> None:
        text = str(message)
        if _is_asyncmock_leak(category, text):
            leaked.append(text)
            return  # intercept: this one becomes a hard failure below
        # Everything else flows to pytest's own handler (summary stays intact).
        original_showwarning(message, category, filename, lineno, file, line)

    warnings.showwarning = _shim
    try:
        yield
        # A coroutine leaked by THIS test is a young (gen-0) object held by the
        # mock's call-tracking cycle; reclaim it now so the warning is attributed
        # here rather than to a later, innocent test.
        gc.collect(0)
    finally:
        warnings.showwarning = original_showwarning

    if leaked:
        pytest.fail(
            "Un-awaited AsyncMock coroutine(s) leaked by this test (F028): "
            f"{leaked}. A mock returned a coroutine that production code never "
            "awaits; configure the mock's return value to a real (sync) object so "
            "the nested attribute access does not synthesise a coroutine.",
            pytrace=False,
        )
