"""A failover chain that cannot fail over must say so, not pretend."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from src.infrastructure.llm.failover import usable_fallback_models
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile


@pytest.fixture(autouse=True)
def _restore_cache() -> Generator[None]:
    saved = dict(ModelCapabilitiesCache._cache)
    yield
    ModelCapabilitiesCache._cache = saved


def test_a_reachable_chain_survives_intact() -> None:
    ModelCapabilitiesCache._cache["alive"] = ModelProfile(model_id="alive")
    ModelCapabilitiesCache._cache["also-alive"] = ModelProfile(model_id="also-alive")
    assert usable_fallback_models("alive,also-alive") == ["alive", "also-alive"]


def test_an_unreachable_entry_is_dropped_not_kept() -> None:
    """The chain that mounts is the chain that can actually fire."""
    ModelCapabilitiesCache._cache["alive"] = ModelProfile(model_id="alive")
    ModelCapabilitiesCache._cache.pop("ghost", None)
    assert usable_fallback_models("ghost,alive") == ["alive"]


def test_an_entirely_unreachable_chain_returns_empty() -> None:
    """Empty disables the middleware — it never raises, a boot must not fail."""
    ModelCapabilitiesCache._cache.clear()
    assert usable_fallback_models("ghost,phantom") == []


def test_an_empty_setting_is_not_an_error() -> None:
    assert usable_fallback_models("") == []
    assert usable_fallback_models("  ,  ") == []


def test_order_is_preserved() -> None:
    """Priority order is the point of a chain."""
    for name in ("a", "b", "c"):
        ModelCapabilitiesCache._cache[name] = ModelProfile(model_id=name)
    assert usable_fallback_models("c, b ,a") == ["c", "b", "a"]


def test_the_shipped_default_is_reachable_in_principle() -> None:
    """The constant names models, not placeholders — the live check is at boot."""
    from src.core.constants import FALLBACK_MODELS_DEFAULT

    names = [part.strip() for part in FALLBACK_MODELS_DEFAULT.split(",") if part.strip()]
    assert len(names) >= 2
    for name in names:
        ModelCapabilitiesCache._cache[name] = ModelProfile(model_id=name)
    assert usable_fallback_models(FALLBACK_MODELS_DEFAULT) == names
