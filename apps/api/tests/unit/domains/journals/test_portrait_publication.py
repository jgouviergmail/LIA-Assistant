"""Omitted synthesis is not completion; zero-effect maintenance keeps approved prose."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.journals.consolidation_lifecycle import ConsolidationSnapshot
from src.domains.journals.consolidation_output import MaintenanceAction, MaintenanceOutput
from src.domains.journals.consolidation_settlement import _publish_portrait
from src.domains.journals.portrait_sources import PortraitSourceBundle

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _publish(
    *,
    pending=False,
    current=True,
    actions=None,
    claims=None,
    rejected=None,
    applied_count=0,
    sections=None,
):
    stamp = datetime.now(UTC)
    source_state = {"_rendering": {"portrait_policy": "synthetic-current"}}
    snapshot = ConsolidationSnapshot(uuid4(), 8, 3, stamp, source_state)
    previous = {
        "journal_revision": 8,
        "source_state": source_state,
        "portrait_pending": pending,
        "claims": ["synthetic existing accepted claim"],
    }
    user = SimpleNamespace(
        id=uuid4(),
        journal_portrait_full=None if pending else "Existing approved natural prose.",
        journal_portrait_brief=None if pending else "Existing approved natural prose.",
        journal_portrait_compiled_at=None if pending else stamp,
        journal_portrait_sources=previous,
    )
    output = MaintenanceOutput(
        actions=actions or [],
        portrait_claims=claims,
        rejected_claims=rejected or [],
        valid=True,
    )
    service = SimpleNamespace(get_all_active=AsyncMock(return_value=[]))
    await _publish_portrait(
        user,
        service,
        output,
        PortraitSourceBundle(sections or {}, {}),
        snapshot,
        8,
        current,
        previous,
        applied_count,
    )
    return user, previous, service


async def test_omitted_compilation_does_not_consume_existing_pending_synthesis():
    user, _, service = await _publish(pending=True)
    assert user.journal_portrait_sources["portrait_pending"] is True
    service.get_all_active.assert_not_awaited()


async def test_zero_effect_update_preserves_current_approved_portrait():
    action = MaintenanceAction(
        action="update", entry_id=str(uuid4()), title="Already current title"
    )
    user, previous, service = await _publish(actions=[action])
    assert user.journal_portrait_full == "Existing approved natural prose."
    assert user.journal_portrait_brief == "Existing approved natural prose."
    assert user.journal_portrait_compiled_at is not None
    assert user.journal_portrait_sources == previous
    service.get_all_active.assert_not_awaited()


async def test_omitted_compilation_keeps_the_words_under_their_own_provenance():
    user, previous, service = await _publish(current=False)
    # The previous synthesis STAYS under the provenance it was compiled with: a
    # rewritten one would read the old words as CURRENT (review 2026-10-12).
    assert user.journal_portrait_full == "Existing approved natural prose."
    assert user.journal_portrait_brief == "Existing approved natural prose."
    assert user.journal_portrait_compiled_at is not None
    assert user.journal_portrait_sources == {**previous, "portrait_pending": True}
    service.get_all_active.assert_not_awaited()


@pytest.mark.parametrize("current", [True, False])
async def test_a_batch_whose_every_claim_was_dropped_keeps_the_words(current):
    from src.domains.journals.consolidation_output import PortraitClaim, PortraitSupport

    unprovable = PortraitClaim(
        facet="focus",
        text="Une affirmation que l'instantané ne peut pas prouver.",
        supports=[PortraitSupport(source="memories", item_id="pi_" + "0" * 20)],
    )
    user, previous, service = await _publish(claims=[unprovable], current=current)
    # Nothing was published: the words stay under their own provenance, nothing is
    # stamped, and a refresh is owed exactly when the previous words are not current.
    assert user.journal_portrait_full == "Existing approved natural prose."
    assert user.journal_portrait_sources == {**previous, "portrait_pending": not current}
    service.get_all_active.assert_awaited_once()


@pytest.mark.parametrize("applied_count", [0, 1])
async def test_explicit_empty_compilation_consumes_follow_up_only_without_new_mutation(
    applied_count,
):
    user, _, service = await _publish(pending=True, claims=[], applied_count=applied_count)
    assert user.journal_portrait_sources["portrait_pending"] is bool(applied_count)
    assert user.journal_portrait_full is None and user.journal_portrait_brief is None
    assert user.journal_portrait_compiled_at is not None
    assert user.journal_portrait_sources["claims"] == []
    service.get_all_active.assert_awaited_once_with(user.id)


async def test_a_brief_alone_is_no_publication_the_words_stay():
    from src.domains.journals.consolidation_output import PortraitClaim, PortraitSupport

    line = "- [personal] Une observation complète qui fonde une lecture brève. (2026-10-01)"
    brief_only = PortraitClaim(
        facet="interaction",
        placement="brief",
        text="Une lecture brève fondée sur plusieurs observations réunies.",
        supports=[PortraitSupport(source="memories", quote=line)],
    )
    user, previous, service = await _publish(claims=[brief_only], sections={"memories": line})
    # The brief resolved, the full did not: writing the brief alone would replace a good
    # full with nothing (review 2026-10-12 b) — nothing is written, the words stay.
    assert user.journal_portrait_full == "Existing approved natural prose."
    assert user.journal_portrait_brief == "Existing approved natural prose."
    assert user.journal_portrait_sources == {**previous, "portrait_pending": False}
    service.get_all_active.assert_awaited_once()


async def test_a_batch_whose_every_claim_was_unreadable_keeps_the_words():
    # The parser rejected every proposed claim: the readable list is empty, which is NOT
    # the model saying « the material is insufficient » — the words stay.
    rejected = [{"claim_index": 0, "reason": "unreadable portrait claim", "codes": ["value_error"]}]
    user, previous, _ = await _publish(claims=[], rejected=rejected)
    assert user.journal_portrait_full == "Existing approved natural prose."
    assert user.journal_portrait_brief == "Existing approved natural prose."
    assert user.journal_portrait_sources == {**previous, "portrait_pending": False}
