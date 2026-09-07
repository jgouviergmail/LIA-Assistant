"""What reaches a chat turn that names a debriefed person — and what must not.

The dangerous property of this block is that it READS like the peer block next
to it while being something else entirely. That one states live facts read this
very turn; this one carries a synthesis written days ago. Applying the peer
block's directive to it — *"these facts are EXACT, answer without looking"* —
turns every date, count and status in a stale text into an assertion the
assistant makes with confidence. So the template is tested for its wording, not
only for its shape.

The second property is negative: with a directory of every relationship the
reader has ever opened, a false positive does not degrade an answer, it hands
one person's file to a question about somebody else.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.core.constants import RELATION_DEBRIEF_BODY_VERSION
from src.domains.relations.debrief import injection as injection_module
from src.domains.relations.debrief.injection import build_debrief_context
from src.domains.relations.debrief.models import DebriefState
from src.domains.relations.debrief.prompts import load_debrief_prompt

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 7)


def _row(
    display_name: str = "Gérard Dupont",
    *,
    generated_for: date = TODAY,
    body: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        display_name=display_name,
        generated_for=generated_for,
        generated_at=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
        state=DebriefState.READY,
        held_until=None,
        sections_used=["open_commitments"],
        unavailable=["emails"],
        # The real row carries what it cost; a stub that omits a read column
        # would let this harness pass where production raises.
        usage={"tokens_in": 900, "tokens_out": 120, "tokens_cache": 0, "cost_eur": 0.004},
        body=(
            body
            if body is not None
            else {
                "version": RELATION_DEBRIEF_BODY_VERSION,
                "headline": "Vous lui devez une réponse.",
                "where_we_stand": "Deux échanges cette semaine.",
                "open_points": ["Répondre au devis", "Confirmer la date"],
                "suggested_next_step": "Lui envoyer le devis signé.",
                "notable_facts": ["Architecte chez ACME"],
            }
        ),
    )


async def _build(texts, rows, *, today: date = TODAY) -> str:
    with patch.object(
        injection_module, "_directory", AsyncMock(return_value=(rows, today if rows else None))
    ):
        return await build_debrief_context(SimpleNamespace(), texts)


class TestItInjectsTheDebriefOfTheOnePersonNamed:
    async def test_a_named_person_brings_their_debrief(self) -> None:
        block = await _build(["Tu peux me rappeler où j'en suis avec Gérard ?"], [_row()])

        assert "Gérard Dupont" in block
        assert "Vous lui devez une réponse." in block
        assert "Répondre au devis" in block
        assert "Confirmer la date" in block

    async def test_the_block_states_when_it_was_written(self) -> None:
        """A synthesis without its date is a claim about now."""
        block = await _build(["Des nouvelles de Gérard ?"], [_row(generated_for=date(2026, 9, 1))])
        assert "2026-09-01" in block

    async def test_a_field_the_model_left_empty_renders_no_heading(self) -> None:
        """An empty heading reads as "there is nothing here"."""
        body = {
            "version": RELATION_DEBRIEF_BODY_VERSION,
            "headline": "Rien d'ouvert.",
            "where_we_stand": "Calme.",
            "open_points": [],
            "suggested_next_step": None,
            "notable_facts": [],
        }
        block = await _build(["Gérard ?"], [_row(body=body)])

        assert "Rien d'ouvert." in block
        assert "STILL OPEN" not in block
        assert "WORTH DOING NEXT" not in block

    async def test_nobody_named_injects_nothing(self) -> None:
        assert await _build(["Quel temps fait-il ?"], [_row()]) == ""

    async def test_an_empty_directory_injects_nothing(self) -> None:
        assert await _build(["Gérard ?"], []) == ""


class TestAmbiguityResolvesToSilence:
    """A false positive here hands one person's file to a question about another."""

    async def test_two_matching_people_inject_nothing(self) -> None:
        rows = [_row("Gérard Dupont"), _row("Gérard Martin")]
        assert await _build(["Un point sur Gérard ?"], rows) == ""

    async def test_the_unambiguous_half_still_works(self) -> None:
        rows = [_row("Gérard Dupont"), _row("Alice Vernier")]
        block = await _build(["Un point sur Alice ?"], rows)
        assert "Alice Vernier" in block
        assert "Gérard" not in block

    async def test_a_name_is_matched_on_whole_words_only(self) -> None:
        """ "Gérardin" is not "Gérard"."""
        assert await _build(["J'ai vu Gérardine hier"], [_row("Gérard Dupont")]) == ""


class TestTheDirectiveIsTheOppositeOfThePeerBlocks:
    """The wording IS the safety property — a shape test would not see it."""

    def test_it_never_claims_the_content_is_exact(self) -> None:
        template = load_debrief_prompt("relation_debrief_context_template")
        assert "EXACT" not in template

    def test_it_names_the_facts_that_must_be_verified(self) -> None:
        template = load_debrief_prompt("relation_debrief_context_template").lower()
        for movable in ("date", "count", "status", "still open"):
            assert movable in template, movable

    def test_it_sends_movable_facts_to_the_tools(self) -> None:
        template = load_debrief_prompt("relation_debrief_context_template").lower()
        assert "use the tools" in template

    def test_it_says_the_debrief_is_dated_not_live(self) -> None:
        template = load_debrief_prompt("relation_debrief_context_template").lower()
        assert "not a live reading" in template

    def test_it_forbids_reading_absence_as_nothing(self) -> None:
        """The scope may simply have excluded a subject (ADR-184)."""
        template = load_debrief_prompt("relation_debrief_context_template").lower()
        assert 'not "nothing"' in template

    def test_the_peer_block_still_states_its_own_facts_are_exact(self) -> None:
        """The two directives must stay opposite: same wording = same trap."""
        from src.domains.agents.prompts.prompt_loader import load_prompt

        assert "EXACTS" in load_prompt("peer_context_template")


class TestItNeverBreaksTheTurn:
    """An injection is an enrichment, not a dependency."""

    async def test_a_failing_read_injects_nothing(self) -> None:
        with patch.object(
            injection_module, "_directory", AsyncMock(side_effect=RuntimeError("db down"))
        ):
            assert await build_debrief_context(SimpleNamespace(), ["Gérard ?"]) == ""

    async def test_a_body_this_version_cannot_read_injects_nothing(self) -> None:
        assert await _build(["Gérard ?"], [_row(body={"version": 99})]) == ""

    async def test_the_flag_off_injects_nothing_and_reads_nothing(self) -> None:
        directory = AsyncMock(return_value=([_row()], TODAY))
        with (
            patch.object(settings, "relation_debrief_injection_enabled", False),
            patch.object(injection_module, "_directory", directory),
        ):
            assert await build_debrief_context(SimpleNamespace(), ["Gérard ?"]) == ""
        directory.assert_not_awaited()


class TestNoPiiAtInfo:
    """Counters and an age, never the person nor a line of what was written."""

    async def test_the_log_carries_no_name_and_no_content(self, caplog) -> None:
        import logging

        with caplog.at_level(logging.INFO):
            await _build(["Un point sur Gérard ?"], [_row()])

        emitted = " ".join(record.getMessage() for record in caplog.records)
        assert "Gérard" not in emitted
        assert "devis" not in emitted
