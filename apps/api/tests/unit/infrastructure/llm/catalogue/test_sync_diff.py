"""The sync proposes; it never decides for a human-curated row."""

from __future__ import annotations

from datetime import date, timedelta

from src.infrastructure.llm.catalogue.field_mapping import (
    RETIREMENT_NOTICE,
    RegistryFacts,
    is_retiring,
)
from src.infrastructure.llm.catalogue.sync_diff import (
    COMPARED_FIELDS,
    CatalogueRow,
    compute_diff,
)


def _row(**kwargs: object) -> CatalogueRow:
    base: dict[str, object] = {
        "model_name": "gpt-5.2",
        "provider": "openai",
        "kind": "chat",
        "max_input_tokens": 8192,
        "max_output_tokens": 4096,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_vision": False,
        "provenance": "declared",
        "deprecation_date": None,
        "is_active": True,
    }
    base.update(kwargs)
    return CatalogueRow(**base)  # type: ignore[arg-type]


def test_declared_row_change_is_auto() -> None:
    changes = compute_diff([_row()])
    windows = [c for c in changes if c.field == "max_input_tokens"]
    assert windows, "the 8192 placeholder must be proposed for correction"
    assert windows[0].proposed == 272_000
    assert windows[0].severity == "auto"


def test_verified_row_change_needs_review() -> None:
    changes = compute_diff([_row(provenance="verified")])
    windows = [c for c in changes if c.field == "max_input_tokens"]
    assert windows[0].severity == "review"


def test_imported_row_change_needs_review() -> None:
    """Once curated, a row is never silently overwritten again."""
    changes = compute_diff([_row(provenance="imported")])
    assert all(c.severity == "review" for c in changes)


def test_no_change_proposed_when_values_agree() -> None:
    changes = compute_diff([_row(max_input_tokens=272_000)])
    assert not [c for c in changes if c.field == "max_input_tokens"]


def test_unknown_model_yields_no_change() -> None:
    assert compute_diff([_row(model_name="not-a-real-model")]) == []


def test_embedding_row_is_never_given_an_output_cap() -> None:
    """models.dev publishes the vector dimension in ``limit.output`` (A9)."""
    changes = compute_diff(
        [_row(model_name="text-embedding-3-large", kind="embedding", max_output_tokens=4096)]
    )
    assert not [c for c in changes if c.field == "max_output_tokens"]


def test_no_price_or_reasoning_field_is_ever_proposed() -> None:
    fields = {c.field for c in compute_diff([_row()])}
    for forbidden in ("cost", "price", "reasoning", "effort", "streaming", "temperature", "kind"):
        assert not any(forbidden in f for f in fields)


def test_compared_fields_all_exist_on_the_row() -> None:
    """A typo in the mapping would silently compare nothing."""
    import dataclasses

    row_fields = {f.name for f in dataclasses.fields(CatalogueRow)}
    fact_fields = {f.name for f in dataclasses.fields(RegistryFacts)}
    for column, attribute in COMPARED_FIELDS:
        assert column in row_fields, column
        assert attribute in fact_fields, attribute


def test_retirement_reads_both_signals() -> None:
    """One implementation of the policy, shared by the CLI, the migration and the guard."""
    today = date(2026, 8, 24)
    dated = RegistryFacts(deprecation_date=date(2026, 9, 1))
    flagged = RegistryFacts(registry_status="deprecated")
    healthy = RegistryFacts(deprecation_date=date(2027, 12, 1))

    assert is_retiring(dated, today=today) is True
    assert is_retiring(flagged, today=today) is True
    assert is_retiring(healthy, today=today) is False

    # With no notice window, only what is already past counts.
    assert is_retiring(dated, today=today, notice=timedelta(0)) is False
    assert is_retiring(flagged, today=today, notice=timedelta(0)) is True


def test_retirement_notice_is_thirty_days() -> None:
    assert RETIREMENT_NOTICE == timedelta(days=30)


def test_retirement_requires_corroboration() -> None:
    """A date alone never retires a model when models.dev contradicts it.

    Measured 2026-08-24: of the 71 LiteLLM entries past their date, models.dev
    still lists four as healthy — ``gpt-5.2-chat-latest``,
    ``gpt-5.3-chat-latest`` and two Gemini image previews. Deactivating a live
    model falls back to ``CONSERVATIVE_DEFAULT`` and makes the adapter send
    sampling parameters to a reasoning model.
    """
    from src.infrastructure.llm.catalogue.field_mapping import is_retired

    today = date(2026, 8, 24)
    gone = RegistryFacts(
        deprecation_date=date(2026, 6, 1), matched_registries=frozenset({"litellm"})
    )
    contradicted = RegistryFacts(
        deprecation_date=date(2026, 6, 1),
        registry_status=None,
        matched_registries=frozenset({"litellm", "modelsdev"}),
    )
    corroborated = RegistryFacts(
        deprecation_date=date(2026, 6, 1),
        registry_status="deprecated",
        matched_registries=frozenset({"litellm", "modelsdev"}),
    )
    announced = RegistryFacts(
        deprecation_date=date(2026, 10, 23),
        registry_status="deprecated",
        matched_registries=frozenset({"litellm", "modelsdev"}),
    )
    flag_only = RegistryFacts(
        registry_status="deprecated", matched_registries=frozenset({"modelsdev"})
    )

    assert is_retired(gone, today=today) is True
    assert is_retired(contradicted, today=today) is False
    assert is_retired(corroborated, today=today) is True
    assert is_retired(announced, today=today) is False, "announced is not gone"
    assert is_retired(flag_only, today=today) is False, "a flag without a date proves nothing"


def test_the_real_false_positives_are_refused() -> None:
    """The four measured contradictions, against the live snapshot."""
    from src.infrastructure.llm.catalogue.field_mapping import is_retired, registry_facts

    today = date(2026, 8, 24)
    for model in ("gpt-5.2-chat-latest", "gpt-5.3-chat-latest"):
        facts = registry_facts("openai", model)
        assert facts is not None
        assert facts.deprecation_date is not None and facts.deprecation_date < today
        assert is_retired(facts, today=today) is False, model
