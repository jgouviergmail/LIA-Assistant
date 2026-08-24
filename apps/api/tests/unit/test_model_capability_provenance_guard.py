"""Systemic guard: no configured slot may point at a model nobody can curate.

A ``declared`` provenance means the row still carries the column defaults
(``max_input_tokens=8192``). Measured 2026-08-23: 89 of 114 active rows were in
that state, which is why ``get_effective_context_window`` answered 8 192 for
``gpt-5.2`` against a real 272 000 — and why the compaction threshold on such a
model collapses by a factor of 33. Since ADR-244 the runtime refuses to believe
a ``declared`` row, so a configured model the registries do not know silently
falls back to ``MODEL_CONTEXT_WINDOWS``.

``ALLOWED_DECLARED_MODELS`` is **shrink-only**: entries come out as registries
start covering them, and none may be added. A model absent from both public
registries belongs here with its reason, not in the catalogue unmarked.
"""

from __future__ import annotations

import pytest

from src.domains.llm_config.constants import LLM_DEFAULTS
from src.infrastructure.llm.catalogue.field_mapping import registry_facts

pytestmark = pytest.mark.unit

#: Models neither registry knows — voice vendors with no public registry entry.
#: Shrink-only. Each entry names why no registry can curate it.
ALLOWED_DECLARED_MODELS: frozenset[str] = frozenset(
    {
        "edge-tts",  # Microsoft Edge TTS bridge — no public registry entry
        "scribe_v2",  # ElevenLabs STT — audio-hour pricing, absent from both
    }
)


def test_every_default_model_is_registry_known_or_allowlisted() -> None:
    unknown = sorted(
        {
            config.model
            for config in LLM_DEFAULTS.values()
            if config.model
            and config.model not in ALLOWED_DECLARED_MODELS
            and registry_facts(config.provider, config.model) is None
        }
    )
    assert unknown == [], (
        "these LLM_DEFAULTS models are unknown to both registries and not "
        f"allowlisted: {unknown}. Curate the row or add it with its reason."
    )


def test_allowlist_is_shrink_only() -> None:
    """A self-check: the allowlist must not grow past its audited size.

    Measured 2026-08-24: ``LLM_DEFAULTS``' 58 slots name 10 distinct
    ``(provider, model)`` pairs and exactly two are unknown to both registries.
    """
    assert len(ALLOWED_DECLARED_MODELS) <= 2, (
        "ALLOWED_DECLARED_MODELS is shrink-only — curate the row instead of " "adding an entry"
    )


def test_no_allowlist_entry_has_become_registry_known() -> None:
    """When a registry starts covering an entry, it leaves the allowlist."""
    from src.domains.llm.models import LLMProviderEnum

    now_known = sorted(
        model
        for model in ALLOWED_DECLARED_MODELS
        if any(registry_facts(provider.value, model) is not None for provider in LLMProviderEnum)
    )
    assert now_known == [], (
        f"a registry now covers {now_known} — remove the allowlist entry and "
        "let the catalogue sync curate the row"
    )
