"""What the initial correction writes, decided once and tested without a database."""

from __future__ import annotations

from datetime import date

from src.infrastructure.llm.catalogue.sync_diff import CatalogueRow, plan_correction

TODAY = date(2026, 8, 24)


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


def _only(rows: list[CatalogueRow]) -> object:
    plan = plan_correction(rows, today=TODAY, referenced=frozenset())
    assert len(plan) == 1, plan
    return plan[0]


def test_declared_row_is_corrected_and_becomes_imported() -> None:
    correction = _only([_row()])
    assert correction.capability_updates["max_input_tokens"] == 272_000
    assert correction.capability_updates["supports_vision"] is True
    assert correction.set_provenance == "imported"


def test_curated_row_keeps_its_capabilities_and_its_provenance() -> None:
    plan = plan_correction([_row(provenance="verified")], today=TODAY, referenced=frozenset())
    assert plan == [], "a human decided; the migration may not overwrite"


def test_deprecation_is_stamped_even_on_a_curated_row() -> None:
    """The date records what the provider announced; nobody curates it."""
    correction = _only(
        [
            _row(
                model_name="claude-opus-4-6",
                provider="anthropic",
                provenance="verified",
                max_input_tokens=1_000_000,
            )
        ]
    )
    assert correction.capability_updates == {}
    assert correction.set_provenance is None
    assert correction.deprecation_date == date(2027, 2, 5)


def test_already_stamped_row_is_not_rewritten() -> None:
    plan = plan_correction(
        [
            _row(
                model_name="claude-opus-4-6",
                provider="anthropic",
                provenance="verified",
                max_input_tokens=1_000_000,
                deprecation_date=date(2027, 2, 5),
            )
        ],
        today=TODAY,
        referenced=frozenset(),
    )
    assert plan == []


def test_retired_and_unreferenced_row_is_deactivated() -> None:
    correction = _only([_row(model_name="gemini-2.0-flash", provider="gemini")])
    assert correction.deactivate is True
    assert correction.kept_because_referenced is False


def test_retired_but_referenced_row_stays_active() -> None:
    """Deactivating it would fall back to CONSERVATIVE_DEFAULT and 400."""
    plan = plan_correction(
        [_row(model_name="gemini-2.0-flash", provider="gemini")],
        today=TODAY,
        referenced=frozenset({"gemini-2.0-flash"}),
    )
    assert len(plan) == 1
    assert plan[0].deactivate is False
    assert plan[0].kept_because_referenced is True


def test_disputed_row_is_never_deactivated() -> None:
    """models.dev still lists ``gpt-5.2-chat-latest`` as healthy (measured)."""
    plan = plan_correction(
        [_row(model_name="gpt-5.2-chat-latest")], today=TODAY, referenced=frozenset()
    )
    assert all(c.deactivate is False for c in plan)


def test_announced_row_is_never_deactivated() -> None:
    """``gpt-4.1-nano`` retires 2026-10-23 — announced, still answering."""
    plan = plan_correction([_row(model_name="gpt-4.1-nano")], today=TODAY, referenced=frozenset())
    assert all(c.deactivate is False for c in plan)


def test_unknown_model_is_left_alone() -> None:
    assert (
        plan_correction(
            [_row(model_name="edge-tts", provider="edge")], today=TODAY, referenced=frozenset()
        )
        == []
    )


def test_embedding_row_keeps_its_output_column() -> None:
    """models.dev publishes the vector dimension there (A9)."""
    plan = plan_correction(
        [_row(model_name="text-embedding-3-large", kind="embedding", max_output_tokens=4096)],
        today=TODAY,
        referenced=frozenset(),
    )
    assert all("max_output_tokens" not in c.capability_updates for c in plan)


def test_corroborated_row_is_promoted_even_without_a_value_change() -> None:
    """Provenance follows corroboration, not change.

    ``get_effective_context_window`` trusts a row only when its provenance is
    not ``declared``. A row whose values already matched the registry would
    otherwise stay uncurated and the runtime would fall back to
    ``MODEL_CONTEXT_WINDOWS``, wrong on 10 of its 56 entries. Measured
    2026-08-24: 15 rows were in that state, ``deepseek-v4-flash`` — the model
    the ``response`` slot runs on — among them.
    """
    correction = _only(
        [
            _row(
                model_name="deepseek-v4-flash",
                provider="deepseek",
                max_input_tokens=1_000_000,
                max_output_tokens=384_000,
                supports_tools=True,
                supports_structured_output=True,
                supports_vision=False,
            )
        ]
    )
    assert correction.capability_updates == {}
    assert correction.set_provenance == "imported"


def test_a_row_with_nothing_to_do_is_absent_from_the_plan() -> None:
    """An already-imported, already-stamped, healthy row yields no work."""
    plan = plan_correction(
        [
            _row(
                model_name="deepseek-v4-flash",
                provider="deepseek",
                provenance="imported",
                max_input_tokens=1_000_000,
                max_output_tokens=384_000,
            )
        ],
        today=TODAY,
        referenced=frozenset(),
    )
    assert plan == []
