"""Opaque references retain exact private evidence through real SQL publication."""

import pytest

from src.domains.journals.lifecycle import portrait_is_current
from src.domains.journals.portrait_catalogue import journal_item_id
from tests.integration.domains.journals.test_consolidation_integrity import (
    _answer,
    _claim,
    _entry,
    _run,
    _user,
)
from tests.integration.domains.journals.test_consolidation_integrity import (
    isolated_runtime as isolated_runtime,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_catalogue_reference_publishes_and_stores_the_canonical_quote(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    canonical_claim = _claim(entry)
    reference_claim = {
        **canonical_claim,
        "supports": [{"source": f"journal:{entry.id}", "item_id": journal_item_id(entry)}],
    }
    call = _answer(monkeypatch, {"actions": [], "portrait_claims": [reference_claim]})

    assert await _run(user) == 0
    await db.refresh(user)
    assert user.journal_last_attempt_status == "success"
    assert user.journal_portrait_full == canonical_claim["text"]
    assert user.journal_portrait_sources["claims"] == [canonical_claim]
    assert await portrait_is_current(db, user)
    assert call.await_count == 1  # one model call: no semantic review any more
    assert journal_item_id(entry) in call.await_args_list[0].kwargs["messages"]
    # The reference was resolved to the entry's own words and revision at publication.
    stored = user.journal_portrait_sources["claims"][0]["supports"][0]
    assert stored == {"source": f"journal:{entry.id}", "quote": entry.content}
