"""The extended cache horizon is a scope around ONE call, never a state (ADR-362)."""

from __future__ import annotations

import asyncio

import pytest

from src.infrastructure.llm.prompt_cache_horizon import (
    extended_horizon_requested,
    extended_prompt_cache_horizon,
)

pytestmark = pytest.mark.unit


def test_nothing_asked_means_the_short_lifetime() -> None:
    assert extended_horizon_requested() is False


def test_the_request_holds_inside_its_scope_only() -> None:
    with extended_prompt_cache_horizon(True):
        assert extended_horizon_requested() is True
    assert extended_horizon_requested() is False


def test_a_scope_that_declines_is_explicit_too() -> None:
    with extended_prompt_cache_horizon(True), extended_prompt_cache_horizon(False):
        assert extended_horizon_requested() is False


def test_an_exception_never_leaks_the_scope() -> None:
    with pytest.raises(RuntimeError), extended_prompt_cache_horizon(True):
        raise RuntimeError("boom")
    assert extended_horizon_requested() is False


async def test_two_concurrent_calls_never_see_each_other() -> None:
    """A gathered call runs in its own context copy: one turn's request never
    lends its lifetime to a neighbour."""
    seen: dict[str, bool] = {}
    started = asyncio.Event()

    async def extended_call() -> None:
        with extended_prompt_cache_horizon(True):
            started.set()
            await asyncio.sleep(0)
            seen["extended"] = extended_horizon_requested()

    async def plain_call() -> None:
        await started.wait()
        seen["plain"] = extended_horizon_requested()

    await asyncio.gather(extended_call(), plain_call())
    assert seen == {"extended": True, "plain": False}
