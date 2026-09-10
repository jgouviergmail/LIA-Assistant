"""The context window is a property of the configured SLOT (ADR-278).

`OLLAMA_NUM_CTX` was one instance-wide number handed to every Ollama tag,
whatever its size: a production instance set 128 000 and every local model —
27 B or 4 B — was asked to allocate the same window. It is gone.

What replaces it is a chain with one number at the end, because ADR-267's
invariant is that **what LIA accounts with is what LIA requests**:

1. the slot's own `context_window` override, when an operator set one;
2. what the server said about that model, capped for a LOCAL tag by
   `OLLAMA_NUM_CTX_DEFAULT_CAP` and left whole for a cloud one;
3. a `verified`/`imported` catalogue row;
4. the hand-maintained table, then `DEFAULT_CONTEXT_WINDOW`.

The four readers of the window — the compaction threshold, the ReAct budget,
the summarisation middleware and the meetings synthesis — all start from a
SLOT, so they read it through `get_effective_context_window_for_slot` and the
per-model reader stays for the catalogue surfaces.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.core.llm_config_helper import (
    get_effective_context_window,
    get_effective_context_window_for_slot,
)
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile

pytestmark = pytest.mark.unit


def _profile(window: int, provenance: str = "discovered") -> ModelProfile:
    return ModelProfile(
        max_input_tokens=window,
        max_output_tokens=4096,
        model_id="qwen3.8:27b",
        capability_provenance=provenance,
    )


@pytest.fixture(autouse=True)
def _clean_cache() -> Any:
    ModelCapabilitiesCache.reset()
    yield
    ModelCapabilitiesCache.reset()


def _slot(model: str, *, window: int | None = None) -> Any:
    """Patch the slot resolver to answer one configuration."""
    from src.core.llm_agent_config import LLMAgentConfig

    config = LLMAgentConfig(
        provider="ollama",
        model=model,
        temperature=0.3,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        max_tokens=2048,
        context_window=window,
    )
    return patch(
        "src.core.llm_config_helper.get_llm_config_for_agent",
        return_value=config,
    )


class TestTheSlotOverrideWins:
    def test_an_operator_number_beats_what_the_server_said(self) -> None:
        ModelCapabilitiesCache.merge_discovered("ollama", {"qwen3.8:27b": _profile(32768)})

        with _slot("qwen3.8:27b", window=8192):
            assert get_effective_context_window_for_slot("response") == 8192

    def test_two_slots_on_the_same_model_may_disagree(self) -> None:
        """The whole point of moving the number off the instance."""
        ModelCapabilitiesCache.merge_discovered("ollama", {"qwen3.8:27b": _profile(32768)})

        with _slot("qwen3.8:27b", window=4096):
            small = get_effective_context_window_for_slot("router")
        with _slot("qwen3.8:27b", window=65536):
            large = get_effective_context_window_for_slot("response")

        assert (small, large) == (4096, 65536)

    def test_no_override_falls_through_to_the_model(self) -> None:
        ModelCapabilitiesCache.merge_discovered("ollama", {"qwen3.8:27b": _profile(32768)})

        with _slot("qwen3.8:27b"):
            assert get_effective_context_window_for_slot("response") == 32768

    def test_a_zero_window_cannot_even_be_CONSTRUCTED(self) -> None:
        """Stronger than refusing it at read time: a window of zero would make
        every turn look over budget, so the effective config's own bound
        rejects it and no reader has to defend against it."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            _slot("qwen3.8:27b", window=0)

    def test_a_negative_window_cannot_be_constructed_either(self) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            _slot("qwen3.8:27b", window=-1)


class TestThePerModelReaderIsUnchanged:
    def test_a_discovered_profile_is_trusted(self) -> None:
        ModelCapabilitiesCache.merge_discovered("ollama", {"qwen3.8:27b": _profile(32768)})

        assert get_effective_context_window("qwen3.8:27b") == 32768

    def test_a_declared_row_is_not(self) -> None:
        """`declared` means "nobody curated this": the table stays the net."""
        ModelCapabilitiesCache.merge_discovered(
            "ollama", {"qwen3.8:27b": _profile(8192, provenance="declared")}
        )

        assert get_effective_context_window("qwen3.8:27b") != 8192


class TestTheSlotReaderNeverReturnsSomethingUnusable:
    def test_an_unknown_model_still_answers_a_positive_window(self) -> None:
        with _slot("a-model-nobody-seeded"):
            assert get_effective_context_window_for_slot("response") > 0
