"""Compliance test: every LLM_DEFAULTS entry must be valid against the
reasoning matrix for its model.

This mirrors the boot-time check (Task 8) so CI fails before merge if a
future LLM_DEFAULTS edit drifts from the matrix.

The test embeds a static reference matrix (a subset of the production
matrix from llm_pricing_seed.sql) - only the models actually referenced
by LLM_DEFAULTS need to be present. We do this rather than loading the
real ModelCapabilitiesCache to keep the test purely unit-scope (no DB
dependency).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.llm_config.reasoning_validation import validate_reasoning_effort

# Static reference matrix - only the models referenced by LLM_DEFAULTS.
# Mirrors a subset of llm_pricing_seed.sql + spec section 8.1
# (post-migration matrix). Keys: model_name -> (widget, enum_values_or_None,
# budget_range_or_None).
_REFERENCE_MATRIX: dict[str, tuple[str, list[str] | None, dict[str, Any] | None]] = {
    # OpenAI reasoning models used in defaults (widget=enum)
    "gpt-5-mini": ("enum", ["minimal", "low", "medium", "high"], None),
    "gpt-5.4-mini": ("enum", ["none", "low", "medium", "high", "xhigh"], None),
    # OpenAI non-reasoning models used in defaults (widget=none)
    "gpt-4.1": ("none", None, None),
    "gpt-4.1-mini": ("none", None, None),
    "gpt-4.1-nano": ("none", None, None),
    # Anthropic reasoning models used in defaults (widget=enum). The
    # canonical name ``claude-opus-4-6`` matches the llm_models row
    # produced by the seed and the real Anthropic API model id; the spec
    # section 8.1 lists ``["low", "medium", "high", "max"]``.
    "claude-opus-4-6": ("enum", ["low", "medium", "high", "max"], None),
    # OpenAI image model (no reasoning) used by image_generation. gpt-image-1
    # retires 2026-10-23 (ADR-244); the slot now defaults to gpt-image-2, which
    # the reference seed already pinned.
    "gpt-image-2": ("none", None, None),
    # Qwen toggle_budget models used in defaults
    "qwen3.5-plus": ("toggle_budget", None, {"min": 0, "max": 32768}),
    "qwen3.5-flash": ("toggle_budget", None, {"min": 0, "max": 32768}),
    "qwen3-max": ("toggle_budget", None, {"min": 0, "max": 32768}),
    # Voice catalogue defaults (ADR-080 + ADR-081). All audio/tts kinds
    # carry widget=none — voice models do not expose a reasoning effort
    # surface, but they still need to live in this matrix so the boot-time
    # compliance check for LLM_DEFAULTS does not fail on them.
    "scribe_v2": ("none", None, None),
    "edge-tts": ("none", None, None),
}


def _build_caps(model: str) -> SimpleNamespace:
    """Build a SimpleNamespace fake of ModelCapabilities from the reference."""
    if model not in _REFERENCE_MATRIX:
        pytest.fail(
            f"LLM_DEFAULTS references unknown model {model!r}. "
            f"Add it to _REFERENCE_MATRIX in this test file (and to "
            f"llm_pricing_seed.sql / spec section 8.1)."
        )
    widget, enum_values, budget_range = _REFERENCE_MATRIX[model]
    return SimpleNamespace(
        model_id=model,
        reasoning_widget=widget,
        reasoning_enum_values=enum_values,
        reasoning_budget_range=budget_range,
    )


@pytest.mark.unit
@pytest.mark.parametrize("llm_type", sorted(LLM_DEFAULTS.keys()))
def test_llm_default_entry_is_matrix_compliant(llm_type: str) -> None:
    """Every LLM_DEFAULTS entry must validate against the matrix for its model.

    CI fails before merge if a future edit drifts.
    """
    cfg = LLM_DEFAULTS[llm_type]
    caps = _build_caps(cfg.model)
    # Will raise HTTPException if invalid - fails the test with a clear
    # ctx (model + provided + allowed/range).
    validate_reasoning_effort(caps, cfg.reasoning_effort)


@pytest.mark.unit
def test_llm_defaults_cardinality() -> None:
    """Sanity check: at least 30 LLM types must be defined.

    Guards against accidental deletions during refactors.
    """
    assert len(LLM_DEFAULTS) >= 30, f"LLM_DEFAULTS has only {len(LLM_DEFAULTS)} entries"
