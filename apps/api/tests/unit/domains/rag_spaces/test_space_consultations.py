"""A documentary space says which of the person's sources it opened.

A space is a STANDING INSTRUCTION — « keep this Drive folder indexed », «
follow this Gmail label » (ADR-262) — and honouring it means opening the
person's Drive and their mailbox through the connector CLIENTS, never through
the ``@tool`` layer. So the gate that fills the consultation register never saw
any of it (measured 2026-09-07, with the enumeration of every direct client
caller).

The silence was loudest where it mattered most: a Google push can trigger a
reindex at four in the morning, and the person had no way at all to learn their
mail had been read.

The authorship is ``scheduled`` and not ``proactive`` on purpose: LIA did not
decide to open their mailbox — they asked for it once, and it keeps being
honoured. It is the word this codebase already uses for a reminder.
"""

from __future__ import annotations

import pytest

from src.domains.agents.effects.treatments import treatment_collector
from src.domains.rag_spaces.consultations import (
    SECTION_DRIVE,
    SECTION_MAIL,
    record_space_read,
    space_read,
)

pytestmark = pytest.mark.unit

_USER = "11111111-1111-1111-1111-111111111111"


class TestWhatASpaceRecords:
    """One row per source opened, under the capability it used."""

    def test_a_drive_read_is_recorded(self) -> None:
        with treatment_collector(run_id="space-1") as rows:
            record_space_read(user_id=_USER, section=SECTION_DRIVE, duration_ms=12)

        assert [row.tool_name for row in rows] == ["space:drive"]
        assert rows[0].outcome == "ok"

    def test_a_mail_read_is_recorded(self) -> None:
        with treatment_collector(run_id="space-2") as rows:
            record_space_read(user_id=_USER, section=SECTION_MAIL, duration_ms=8)

        assert [row.tool_name for row in rows] == ["space:mail"]

    def test_a_source_that_refused_is_not_recorded_as_read(self) -> None:
        """« Unreadable » is never « empty »: a folder that could not be
        listed must not read as a folder with nothing in it."""
        with treatment_collector(run_id="space-3") as rows:
            record_space_read(user_id=_USER, section=SECTION_DRIVE, failed=True, duration_ms=3)

        assert rows[0].outcome == "failed"

    def test_the_authorship_is_the_persons_standing_instruction(self) -> None:
        with treatment_collector(run_id="space-4") as rows:
            record_space_read(user_id=_USER, section=SECTION_MAIL, duration_ms=1)

        assert rows[0].source == "scheduled"

    def test_outside_a_run_nothing_is_recorded_and_nothing_raises(self) -> None:
        record_space_read(user_id=_USER, section=SECTION_DRIVE, duration_ms=1)


class TestTheContextManagerAroundEachRead:
    """One line per site, so a new read cannot arrive in a different shape."""

    async def test_a_read_that_succeeded_is_recorded_as_read(self) -> None:
        with treatment_collector(run_id="space-5") as rows:
            async with space_read(user_id=_USER, section=SECTION_DRIVE):
                pass

        assert [row.tool_name for row in rows] == ["space:drive"]
        assert rows[0].outcome == "ok"

    async def test_a_read_that_raised_is_recorded_and_still_raises(self) -> None:
        """Observing must never change what it observes."""
        with treatment_collector(run_id="space-6") as rows, pytest.raises(RuntimeError):
            async with space_read(user_id=_USER, section=SECTION_MAIL):
                raise RuntimeError("drive down")

        assert rows[0].outcome == "failed"

    async def test_the_duration_is_measured_around_the_call(self) -> None:
        with treatment_collector(run_id="space-7") as rows:
            async with space_read(user_id=_USER, section=SECTION_DRIVE):
                pass

        assert rows[0].duration_ms >= 0


class TestTheVocabularyIsReadable:
    """A consultation nobody can name is worse than none (ADR-263)."""

    def test_each_section_reads_as_the_source_it_opened(self) -> None:
        from src.domains.agents.effects.treatment_labels import UNKNOWN_DOMAIN, treatment_domain
        from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

        surface = CONSULTATION_SURFACES["space"]
        for section, domain in surface.domains.items():
            resolved = treatment_domain(surface.capability(section))
            assert resolved != UNKNOWN_DOMAIN, f"{section} headlines as Unknown"
            assert resolved == domain

    def test_the_module_declares_exactly_the_sections_it_can_record(self) -> None:
        from src.domains.rag_spaces.consultations import sections

        assert set(sections()) == {SECTION_DRIVE, SECTION_MAIL}
