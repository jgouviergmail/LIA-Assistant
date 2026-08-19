"""Every pricing column must travel through the reference pricing seed.

The seed (``infrastructure/database/seeds/llm_pricing_seed.sql``) is a manual
extraction of the production catalogue, and the demo instance rebuilds its
database from it at EVERY boot (tmpfs, ADR-215/216) — whatever the extraction
drops is silently absent from the demo and from fresh installs. That loss has
happened twice for real: the pre-2026-08-15 generation hardcoded
``pricing_unit`` and dropped the audio-hour rows, and the ``time_slots``
windowed tariffs (ADR-223) would vanish the same way if a future extraction
carried only the historical column list.

This guard makes the requirement executable instead of a header comment:
every column of ``llm_model_pricing`` must be REFERENCED somewhere in the
seed file (INSERT column list, UPDATE block — the mechanism is free, the
mention is not). A new pricing column that ships without seed support fails
here, in the same commit, with the remediation in the message.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domains.llm.models import LLMModelPricing

pytestmark = pytest.mark.unit

_SEED_PATH = (
    Path(__file__).resolve().parents[3].parent
    / "infrastructure"
    / "database"
    / "seeds"
    / "llm_pricing_seed.sql"
)


def _missing_columns(seed_text: str) -> list[str]:
    """Columns of llm_model_pricing that the seed text never mentions."""
    return sorted(
        name for name in LLMModelPricing.__table__.columns.keys() if name not in seed_text
    )


def test_seed_file_references_every_pricing_column() -> None:
    """A pricing column absent from the seed is data the next extraction loses.

    ``time_slots`` is the live example: the INSERT keeps the historical
    column list (NULL = flat pricing) and a dedicated UPDATE block carries
    the DeepSeek windowed tariff — either mechanism satisfies this guard,
    but a regenerated seed that mentions the column nowhere fails it.
    """
    assert _SEED_PATH.is_file(), f"pricing seed not found at {_SEED_PATH}"
    missing = _missing_columns(_SEED_PATH.read_text(encoding="utf-8"))
    assert not missing, (
        f"llm_model_pricing column(s) {missing} are never referenced in "
        f"{_SEED_PATH.name}. The seed is what the demo instance boots from and "
        "what fresh installs receive: re-extract it WITH these columns (or add "
        "a dedicated UPDATE block, as done for time_slots) so admin-entered "
        "data does not silently revert on the next reseed."
    )


def test_the_guard_actually_bites() -> None:
    """Prove the checker fails on a seed stripped of a pricing column."""
    stripped = _SEED_PATH.read_text(encoding="utf-8").replace("time_slots", "removed")
    assert "time_slots" in _missing_columns(stripped)


def _statement_order(seed_text: str) -> tuple[int, int]:
    """Offsets of (retire pre-existing actives, insert the bundle)."""
    return (
        seed_text.index("UPDATE llm_model_pricing p\n   SET is_active = false"),
        seed_text.index("INSERT INTO llm_model_pricing ("),
    )


def test_the_bundle_retires_superseded_tariffs_before_inserting_its_own() -> None:
    """Order is the whole invariant, and it broke a demo boot for real.

    ``alembic upgrade head`` runs ``seed_openai_pricing``, so a freshly
    migrated database already holds ONE active tariff per model. Inserting the
    bundle's row on top left BOTH active — silently, until ADR-228 added
    ``uq_llm_model_pricing_active``, which turned it into a hard failure at
    ``demo:prod:up`` (measured 2026-08-19). Retiring AFTER the insert cannot
    work: the index refuses the second active row before any cleanup runs.
    """
    retire_at, insert_at = _statement_order(_SEED_PATH.read_text(encoding="utf-8"))
    assert retire_at < insert_at, (
        "the pricing bundle must deactivate the tariffs it supersedes BEFORE "
        "inserting its own rows, or uq_llm_model_pricing_active rejects the "
        "insert on any database that already ran the seeding migrations."
    )


def test_the_bundle_overwrites_a_row_it_just_retired_instead_of_skipping_it() -> None:
    """``DO NOTHING`` here would leave a model with NO active tariff.

    When a row already stands at the SAME ``effective_from``, the retire step
    above has just set ``is_active = false`` on it. Skipping the insert would
    leave that row inactive and add nothing — the model would be billed zero
    in silence, which is the very defect ADR-228 makes the workbook state in
    words.
    """
    seed_text = _SEED_PATH.read_text(encoding="utf-8")
    conflict_at = seed_text.index("ON CONFLICT (model_id, effective_from)")
    clause = seed_text[conflict_at : conflict_at + 120]
    assert "DO UPDATE" in clause, (
        "the pricing bundle must upsert on (model_id, effective_from): with "
        "DO NOTHING, a row retired by the preceding UPDATE is never replaced "
        "and the model ends up with no active tariff at all."
    )
