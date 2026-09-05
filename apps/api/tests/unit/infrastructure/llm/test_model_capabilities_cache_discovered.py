"""The discovered layer of ``ModelCapabilitiesCache`` (ADR-267).

A model's own server (Ollama ``/api/show``) describes what a tag can do; that
description lives in a layer of its own so a catalogue reload cannot wipe it,
and it wins over a catalogue row of the same name because the seed's Ollama rows
are static guesses.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest

from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset() -> Generator[None]:
    ModelCapabilitiesCache.reset()
    yield
    ModelCapabilitiesCache.reset()


def _profile(name: str, **overrides: object) -> ModelProfile:
    return ModelProfile(model_id=name, capability_provenance="discovered", **overrides)  # type: ignore[arg-type]


def test_discovered_models_are_readable_like_catalogue_rows() -> None:
    ModelCapabilitiesCache.merge_discovered("ollama", {"qwen3.8:27b": _profile("qwen3.8:27b")})
    assert ModelCapabilitiesCache.get("qwen3.8:27b") is not None
    assert ModelCapabilitiesCache.get_provider("qwen3.8:27b") == "ollama"
    assert ModelCapabilitiesCache.get_models_grouped_by_provider() == {"ollama": ["qwen3.8:27b"]}


def test_the_server_wins_over_a_catalogue_row_of_the_same_name() -> None:
    ModelCapabilitiesCache._cache = {
        "llama3.2": ModelProfile(model_id="llama3.2", supports_vision=False)
    }
    ModelCapabilitiesCache._provider_by_model = {"llama3.2": "ollama"}
    ModelCapabilitiesCache.merge_discovered(
        "ollama", {"llama3.2": _profile("llama3.2", supports_vision=True)}
    )
    profile = ModelCapabilitiesCache.get("llama3.2")
    assert profile is not None and profile.supports_vision is True
    assert ModelCapabilitiesCache.get_models_grouped_by_provider() == {"ollama": ["llama3.2"]}


def test_a_catalogue_reload_does_not_wipe_the_layer() -> None:
    """``load_from_db`` swaps ``_cache`` wholesale; the layer must survive that."""
    ModelCapabilitiesCache.merge_discovered("ollama", {"qwen3.8:27b": _profile("qwen3.8:27b")})
    ModelCapabilitiesCache._cache = {}
    ModelCapabilitiesCache._provider_by_model = {}
    assert ModelCapabilitiesCache.get("qwen3.8:27b") is not None


def test_a_refresh_replaces_the_provider_layer_and_only_it() -> None:
    ModelCapabilitiesCache.merge_discovered("ollama", {"old:tag": _profile("old:tag")})
    ModelCapabilitiesCache.merge_discovered("other", {"kept": _profile("kept")})
    ModelCapabilitiesCache.merge_discovered("ollama", {"new:tag": _profile("new:tag")})
    assert ModelCapabilitiesCache.get("old:tag") is None
    assert ModelCapabilitiesCache.get("new:tag") is not None
    assert ModelCapabilitiesCache.get("kept") is not None


def test_an_empty_discovery_clears_the_layer() -> None:
    ModelCapabilitiesCache.merge_discovered("ollama", {"gone:tag": _profile("gone:tag")})
    assert ModelCapabilitiesCache.merge_discovered("ollama", {}) is True
    assert ModelCapabilitiesCache.get("gone:tag") is None


def test_a_change_drops_the_llm_instance_cache_and_no_change_does_not() -> None:
    """Capabilities are consulted at instance creation; a stale instance would
    keep the old ``think`` decision."""
    with patch("src.infrastructure.llm.factory.clear_llm_instance_cache") as clear:
        assert ModelCapabilitiesCache.merge_discovered("ollama", {"m": _profile("m")}) is True
        assert clear.call_count == 1
        assert ModelCapabilitiesCache.merge_discovered("ollama", {"m": _profile("m")}) is False
        assert clear.call_count == 1


def test_has_discovered_answers_per_provider() -> None:
    assert ModelCapabilitiesCache.has_discovered("ollama") is False
    ModelCapabilitiesCache.merge_discovered("ollama", {"m": _profile("m")})
    assert ModelCapabilitiesCache.has_discovered("ollama") is True
    assert ModelCapabilitiesCache.has_discovered("openai") is False
    ModelCapabilitiesCache.merge_discovered("ollama", {})
    assert ModelCapabilitiesCache.has_discovered("ollama") is False


def test_reset_clears_the_layer() -> None:
    ModelCapabilitiesCache.merge_discovered("ollama", {"m": _profile("m")})
    ModelCapabilitiesCache.reset()
    assert ModelCapabilitiesCache.get("m") is None
    assert ModelCapabilitiesCache.get_models_grouped_by_provider() == {}
