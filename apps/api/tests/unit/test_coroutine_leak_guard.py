"""Self-test for the F028 un-awaited-AsyncMock guard.

Proves the guard (``tests/_coroutine_leak_guard.py``) fails a test that leaks an
AsyncMock coroutine, stays silent on a clean test, ignores driver-internal
coroutines, and — crucially — does NOT swallow unrelated warnings out of pytest's
report. Without these, the guard could rot into a no-op (false green about false
greens) or start hiding legitimate deprecations.
"""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock

import pytest

from tests._coroutine_leak_guard import _is_asyncmock_leak, assert_no_unawaited_asyncmock


def _drive(body) -> None:
    """Run ``body()`` through the guard generator exactly as the autouse fixture does."""
    gen = assert_no_unawaited_asyncmock()
    next(gen)
    try:
        body()
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_classifier_flags_only_asyncmock_never_awaited() -> None:
    assert _is_asyncmock_leak(
        RuntimeWarning, "coroutine 'AsyncMockMixin._execute_mock_call' was never awaited"
    )
    # Driver teardown coroutine — must NOT be flagged (separate infra concern).
    assert not _is_asyncmock_leak(
        RuntimeWarning, "coroutine 'Connection._cancel' was never awaited"
    )
    # Right marker, wrong category.
    assert not _is_asyncmock_leak(
        UserWarning, "coroutine 'AsyncMockMixin._execute_mock_call' was never awaited"
    )


def test_guard_fails_on_leaked_asyncmock_coroutine() -> None:
    async def _leak() -> None:
        snap = await AsyncMock()()  # snap is an AsyncMock child
        snap.values.get("x")  # synthesises a coroutine nobody awaits

    def _body() -> None:
        import asyncio

        asyncio.run(_leak())

    with pytest.raises(pytest.fail.Exception, match="F028"):
        _drive(_body)


def test_guard_silent_on_clean_test() -> None:
    def _body() -> None:
        import asyncio

        async def _ok() -> str:
            return await AsyncMock(return_value="ok")()

        assert asyncio.run(_ok()) == "ok"

    _drive(_body)  # must not raise


def test_guard_does_not_intercept_driver_coroutine_warning() -> None:
    def _body() -> None:
        warnings.warn(
            "coroutine 'Connection._cancel' was never awaited", RuntimeWarning, stacklevel=1
        )

    # A driver coroutine warning is not an AsyncMock leak → guard stays silent.
    _drive(_body)


def test_guard_passes_unrelated_warnings_through() -> None:
    seen: list[str] = []

    def _capture(message, category, *a, **k):  # type: ignore[no-untyped-def]
        seen.append(str(message))

    # DeprecationWarning is ignored by default outside __main__ and dedup'd by
    # the "default"/"once" actions, so under an ambient filter it may never
    # reach showwarning — making the delegation assertion vacuous. Force
    # "always" (restored by catch_warnings) so the warning deterministically
    # reaches the shim regardless of the session's filter state.
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        original = warnings.showwarning
        warnings.showwarning = _capture
        try:
            _drive(lambda: warnings.warn("a-deprecation", DeprecationWarning, stacklevel=1))
        finally:
            warnings.showwarning = original
    assert "a-deprecation" in seen, "guard must delegate non-AsyncMock warnings to pytest"
