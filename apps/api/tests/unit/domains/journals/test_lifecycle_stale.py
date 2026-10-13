"""A journal change marks the portrait stale and never wipes the words (ADR-269's
doctrine); an ERASURE withdraws exactly the claims the removed entries supported.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.journals import lifecycle

pytestmark = pytest.mark.unit


async def test_a_journal_change_marks_the_portrait_stale_without_wiping_it() -> None:
    db = AsyncMock()
    await lifecycle.mark_journal_changed(db, uuid4())
    statement = db.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "journal_revision" in compiled
    assert "journal_portrait_full" not in compiled
    assert "journal_portrait_brief" not in compiled
    assert "journal_portrait_compiled_at" not in compiled


async def test_a_confirming_reaction_keeps_a_versioned_portrait_current() -> None:
    db = AsyncMock()
    await lifecycle.mark_journal_changed(db, uuid4(), invalidate_portrait=False)
    compiled = str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": False}))
    assert "journal_portrait_sources" in compiled and "jsonb_set" in compiled
    assert "journal_portrait_full" not in compiled


def _claim(text: str, *supports: str, placement: str = "full") -> dict:
    return {
        "facet": "focus",
        "text": text,
        "placement": placement,
        "supports": [{"source": source, "item_id": "pi_x"} for source in supports],
    }


async def _withdraw(provenance, full, brief, entry_ids):
    """Run the withdrawal on a stub session; return the UPDATE's values (None = no write)."""
    db = AsyncMock()
    db.execute.side_effect = [SimpleNamespace(one=lambda: (provenance, full, brief)), None]
    await lifecycle.withdraw_journal_supports(db, uuid4(), entry_ids)
    if db.execute.await_count < 2:
        return None
    statement = db.execute.await_args_list[1].args[0]
    return {column.name: value for column, value in statement._values.items()}


async def test_a_removed_entry_takes_the_claims_it_supported_and_keeps_the_others() -> None:
    gone, kept = str(uuid4()), str(uuid4())
    provenance = {
        "journal_revision": 3,
        "claims": [
            _claim("Rests on the removed entry.", f"journal:{gone}", "memories"),
            _claim("Rests on another entry.", f"journal:{kept}"),
            _claim("Rests on a memory alone.", "memories", placement="brief"),
        ],
    }
    values = await _withdraw(provenance, "a\n\nb", "c", {gone})
    assert values["journal_portrait_full"].value == "Rests on another entry."
    assert values["journal_portrait_brief"].value == "Rests on a memory alone."
    assert values["journal_portrait_sources"].value["withdrawn_claims"] == 1
    assert [c["text"] for c in values["journal_portrait_sources"].value["claims"]] == [
        "Rests on another entry.",
        "Rests on a memory alone.",
    ]
    assert "journal_portrait_compiled_at" not in values


async def test_deleting_the_whole_journal_withdraws_every_journal_backed_claim() -> None:
    provenance = {
        "claims": [
            _claim("Journal-backed.", f"journal:{uuid4()}"),
            _claim("Memory-backed.", "memories"),
        ]
    }
    values = await _withdraw(provenance, "x", None, None)
    assert values["journal_portrait_full"].value == "Memory-backed."
    assert values["journal_portrait_brief"].value is None


@pytest.mark.parametrize(
    "provenance",
    [None, {"journal_revision": 3}, {"claims": []}, {"claims": ["unreadable"]}],
)
async def test_a_portrait_whose_claims_cannot_be_read_is_wiped_whole(provenance) -> None:
    values = await _withdraw(provenance, "legacy prose", "legacy", {str(uuid4())})
    assert {name: column.value for name, column in values.items()} == {
        "journal_portrait_full": None,
        "journal_portrait_brief": None,
        "journal_portrait_compiled_at": None,
        "journal_portrait_sources": None,
    }


async def test_nothing_is_written_when_no_words_are_stored() -> None:
    assert await _withdraw({"claims": [_claim("x", "memories")]}, None, None, None) is None


async def test_a_claim_resting_on_every_removed_entry_is_recognised() -> None:
    gone = str(uuid4())
    assert lifecycle.cites_removed_entry(_claim("t", f"journal:{gone}"), {gone})
    assert not lifecycle.cites_removed_entry(_claim("t", f"journal:{gone}"), {str(uuid4())})
    assert lifecycle.cites_removed_entry(_claim("t", f"journal:{gone}"), None)
    assert not lifecycle.cites_removed_entry(_claim("t", "memories"), None)
    assert lifecycle.cites_removed_entry("not a claim", None)
