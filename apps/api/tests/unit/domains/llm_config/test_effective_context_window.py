"""Provenance arbitrates between the catalogue and the hand-maintained table."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from src.core.llm_config_helper import get_effective_context_window
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile


@pytest.fixture(autouse=True)
def _restore_cache() -> Generator[None]:
    saved = dict(ModelCapabilitiesCache._cache)
    yield
    ModelCapabilitiesCache._cache = saved


def _install(model: str, window: int, provenance: str) -> None:
    ModelCapabilitiesCache._cache[model] = ModelProfile(
        max_input_tokens=window,
        model_id=model,
        capability_provenance=provenance,
    )


def test_imported_row_wins_over_the_table() -> None:
    _install("gpt-5.2", 272_000, "imported")
    assert get_effective_context_window("gpt-5.2") == 272_000


def test_verified_row_wins_over_the_table() -> None:
    _install("gpt-5.2", 300_000, "verified")
    assert get_effective_context_window("gpt-5.2") == 300_000


def test_declared_row_falls_back_to_the_table() -> None:
    """A column default must never beat a hand-maintained value.

    ``MODEL_CONTEXT_WINDOWS`` is itself wrong here (1 047 576 against a real
    272 000), but a ``declared`` row carries the 8 192 column default, which is
    wrong by a factor of 33. The table is the lesser error, and the guard on
    ``LLM_DEFAULTS`` keeps configured models out of this branch.
    """
    _install("gpt-5.2", 8_192, "declared")
    assert get_effective_context_window("gpt-5.2") == 1_047_576


def test_unknown_model_uses_the_table() -> None:
    ModelCapabilitiesCache._cache.pop("claude-opus-4-6", None)
    assert get_effective_context_window("claude-opus-4-6") == 200_000


def test_a_zero_window_never_wins() -> None:
    """``scribe_v1`` carries ``max_input_tokens = 0`` in the live catalogue."""
    _install("scribe_v1", 0, "imported")
    assert get_effective_context_window("scribe_v1") > 0


def test_the_profile_default_is_the_untrusted_one() -> None:
    """A profile nobody filled must not be believed over the table."""
    assert ModelProfile().capability_provenance == "declared"
