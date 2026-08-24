"""Per-field precedence, and the exclusions that are load-bearing."""

from __future__ import annotations

import dataclasses
from datetime import date

from src.infrastructure.llm.catalogue.field_mapping import RegistryFacts, registry_facts


def test_context_window_prefers_the_explicit_input_budget() -> None:
    """models.dev states ``input`` explicitly; LiteLLM sometimes conflates.

    Measured over the 19 models where both state an input budget: 13 agree and
    all six disagreements are ``litellm.max_input_tokens ==
    modelsdev.limit.context``.
    """
    facts = registry_facts("openai", "gpt-5.2")
    assert facts is not None
    assert facts.max_input_tokens == 272_000
    assert facts.sources["max_input_tokens"] == "modelsdev"


def test_litellm_context_conflation_is_not_imported() -> None:
    """``gpt-5-pro``: LiteLLM says 400 000, which is the TOTAL window."""
    facts = registry_facts("openai", "gpt-5-pro")
    assert facts is not None
    assert facts.max_input_tokens == 272_000
    assert facts.sources["max_input_tokens"] == "modelsdev"


def test_litellm_wins_when_modelsdev_states_no_input_budget() -> None:
    """Most models.dev entries publish only ``context``."""
    facts = registry_facts("anthropic", "claude-opus-4-6")
    assert facts is not None
    assert facts.max_input_tokens == 1_000_000
    assert facts.sources["max_input_tokens"] == "litellm"


def test_an_output_cap_equal_to_the_whole_window_is_refused() -> None:
    """A cap equal to the model's own context is not a cap.

    Measured 2026-08-24: models.dev publishes ``output == context`` on nine
    entries. ``openai/gpt-4`` claims 8192 for both while LiteLLM states the
    real 4096; ``google/gemini-3.1-flash-lite-image`` claims 65536 against
    LiteLLM's 4096. The rule falls those through to LiteLLM.
    """
    from src.infrastructure.llm.catalogue.registry_match import match_modelsdev

    for provider, model, expected in (
        ("openai", "gpt-4", 4096),
        ("gemini", "gemini-3.1-flash-lite-image", 4096),
    ):
        entry = match_modelsdev(provider, model)
        assert entry is not None, model
        assert entry["limit"]["output"] == entry["limit"]["context"], model

        facts = registry_facts(provider, model)
        assert facts is not None, model
        assert facts.max_output_tokens == expected, model
        assert facts.sources["max_output_tokens"] == "litellm", model


def test_unknown_model_returns_none() -> None:
    assert registry_facts("ollama", "a-model-that-does-not-exist") is None


def test_non_positive_token_counts_are_treated_as_absent() -> None:
    """models.dev publishes ``limit: {input: 0, output: 0}`` on image models.

    Measured 2026-08-24: five models.dev image entries and five LiteLLM
    moderation entries carry a non-positive token count. Importing a zero
    would set ``max_output_tokens=0`` on LIA's image rows and make every
    downstream budget computation collapse.
    """
    facts = registry_facts("openai", "gpt-image-2")
    assert facts is not None
    assert facts.max_input_tokens is None
    assert facts.max_output_tokens is None


def test_output_cap_prefers_modelsdev_then_litellm() -> None:
    """models.dev ``limit.output`` first, LiteLLM ``max_output_tokens`` next."""
    facts = registry_facts("openai", "gpt-5.2")
    assert facts is not None
    assert facts.max_output_tokens == 128_000
    assert facts.sources["max_output_tokens"] == "modelsdev"


def test_embedding_rows_get_no_output_cap() -> None:
    """models.dev fills ``limit.output`` with the EMBEDDING DIMENSION.

    Measured 2026-08-24: 3072 for ``text-embedding-3-large``, 1536 for
    ``-small`` and ``ada-002``, 1 for ``gemini-embedding-001``. Importing it
    would write a vector width into a token column, so a caller that knows the
    row is an embedding gets no output fact at all.
    """
    unaware = registry_facts("openai", "text-embedding-3-large")
    assert unaware is not None
    assert unaware.max_output_tokens == 3072  # the raw registry claim

    aware = registry_facts("openai", "text-embedding-3-large", kind="embedding")
    assert aware is not None
    assert aware.max_output_tokens is None
    assert "max_output_tokens" not in aware.sources


def test_litellm_max_tokens_is_not_vendored() -> None:
    """It never carried an output cap nothing else did — 0 of 22 (measured)."""
    from src.infrastructure.llm.catalogue.registry_match import match_litellm

    entry = match_litellm("openai", "gpt-5.2")
    assert entry is not None
    assert "max_tokens" not in entry


def test_deprecation_date_is_a_date() -> None:
    facts = registry_facts("anthropic", "claude-opus-4-6")
    assert facts is not None
    assert facts.deprecation_date == date(2027, 2, 5)


def test_registry_status_carries_the_second_deprecation_signal() -> None:
    """models.dev flags previews Google retires without publishing a date."""
    facts = registry_facts("gemini", "gemini-3.1-flash-lite-preview")
    assert facts is not None
    assert facts.registry_status == "deprecated"
    assert facts.deprecation_date is None


def test_facts_carry_no_price_field() -> None:
    names = {f.name for f in dataclasses.fields(RegistryFacts)}
    assert not any("cost" in n or "price" in n for n in names)


def test_facts_carry_no_reasoning_field() -> None:
    """Reasoning metadata is LIA-owned: a naive import invalidated 21 slots."""
    names = {f.name for f in dataclasses.fields(RegistryFacts)}
    assert not any("reasoning" in n or "effort" in n for n in names)


def test_facts_carry_no_streaming_or_sampling_field() -> None:
    names = {f.name for f in dataclasses.fields(RegistryFacts)}
    for forbidden in ("streaming", "temperature", "top_p", "frequency", "presence"):
        assert not any(forbidden in n for n in names)


def test_facts_carry_no_kind_field() -> None:
    """LiteLLM ``mode`` is the API surface; LIA ``kind`` classifies the product.

    Measured over 103 matched rows: ``mode=chat`` maps to ``kind=audio`` six
    times and to ``kind=tts`` once. The divergence is not error, so no correct
    consumer exists and the field is excluded.
    """
    names = {f.name for f in dataclasses.fields(RegistryFacts)}
    assert "kind" not in names
    assert "mode" not in names


#: Fields that describe the match itself rather than a registry claim.
PROVENANCE_FIELDS = {"sources", "matched_registries"}


def test_every_populated_field_records_its_source() -> None:
    facts = registry_facts("openai", "gpt-5.2")
    assert facts is not None
    for field in dataclasses.fields(RegistryFacts):
        if field.name in PROVENANCE_FIELDS:
            continue
        if getattr(facts, field.name) is not None:
            assert field.name in facts.sources


def test_matched_registries_names_who_knew_the_model() -> None:
    both = registry_facts("openai", "gpt-5.2")
    assert both is not None
    assert both.matched_registries == frozenset({"litellm", "modelsdev"})

    litellm_only = registry_facts("openai", "chatgpt-4o-latest")
    assert litellm_only is not None
    assert litellm_only.matched_registries == frozenset({"litellm"})

    modelsdev_only = registry_facts("openai", "gpt-5.3-codex-spark")
    assert modelsdev_only is not None
    assert modelsdev_only.matched_registries == frozenset({"modelsdev"})
