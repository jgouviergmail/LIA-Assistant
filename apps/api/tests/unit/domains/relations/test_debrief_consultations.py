"""A debrief says which sources it opened, or it is mistaken for its neighbour.

Reported from production, 2026-09-07: a debrief was generated on a contact and
the reader could not find it in the register. What they found instead, at the
top of the consultation list, was a briefing card read from a few seconds
later — and reasonably concluded the debrief had been filed under the wrong
name. It had not: it had been filed under no name at all.

The cause is the one the briefing already paid for. ``record_treatment`` fires
from exactly one place — the tool gate — and the debrief assembles its evidence
through direct calls (``domains/relations/overview``), not tools. Its
consultations were absent BY CONSTRUCTION.

Two rules the recording inherits from the 360° scope (ADR-269):

- **a section outside the scope records nothing.** « I did not look, on
  purpose » is the reader's own decision; a row saying otherwise would invent
  a read that never happened.
- **unreadable is not empty.** A section the scope asked for and the provider
  refused reads as ``failed``, never as a silent success.
"""

from __future__ import annotations

import pytest

from src.domains.relations.overview_scope import OverviewSection

pytestmark = pytest.mark.unit


class TestTheVocabularyIsReadable:
    """A consultation nobody can name is worse than none."""

    def test_every_section_has_a_capability_and_a_domain(self) -> None:
        from src.domains.relations.overview.consultations import (
            SECTION_DOMAINS,
            consultation_capability,
        )

        for section in OverviewSection:
            assert section.value in SECTION_DOMAINS, f"{section.value} names no domain"
            assert consultation_capability(section.value).startswith("relation:")

    def test_no_declared_section_outlives_the_enum(self) -> None:
        from src.domains.relations.overview.consultations import SECTION_DOMAINS

        assert set(SECTION_DOMAINS) == {section.value for section in OverviewSection}

    def test_the_register_resolves_every_capability_to_that_domain(self) -> None:
        """The two halves agree, and neither headlines as « Unknown »."""
        from src.domains.agents.effects.treatment_labels import (
            UNKNOWN_DOMAIN,
            treatment_domain,
        )
        from src.domains.relations.overview.consultations import (
            SECTION_DOMAINS,
            consultation_capability,
        )

        for section, domain in SECTION_DOMAINS.items():
            resolved = treatment_domain(consultation_capability(section))
            assert resolved != UNKNOWN_DOMAIN, f"{section} headlines as Unknown"
            assert resolved == domain


class TestWhatADebriefRecords:
    """Observed on the collector, from the evidence the build received."""

    def test_a_section_that_answered_is_recorded_as_read(self) -> None:
        from src.domains.agents.effects.treatments import treatment_collector
        from src.domains.relations.overview.consultations import record_evidence_consultations

        with treatment_collector(run_id="debrief-1") as rows:
            record_evidence_consultations(
                user_id="11111111-1111-1111-1111-111111111111",
                run_id="debrief-1",
                requested={OverviewSection.EMAILS.value, OverviewSection.EVENTS.value},
                unavailable=[],
                duration_ms=120,
            )

        assert {row.tool_name for row in rows} == {"relation:emails", "relation:events"}
        assert {row.outcome for row in rows} == {"ok"}

    def test_a_section_the_scope_excluded_records_nothing(self) -> None:
        """« I did not look, on purpose » is not a consultation."""
        from src.domains.agents.effects.treatments import treatment_collector
        from src.domains.relations.overview.consultations import record_evidence_consultations

        with treatment_collector(run_id="debrief-2") as rows:
            record_evidence_consultations(
                user_id="11111111-1111-1111-1111-111111111111",
                run_id="debrief-2",
                requested={OverviewSection.EMAILS.value},
                unavailable=[],
                duration_ms=10,
            )

        assert [row.tool_name for row in rows] == ["relation:emails"]

    def test_an_unreadable_section_is_recorded_as_failed(self) -> None:
        from src.domains.agents.effects.treatments import treatment_collector
        from src.domains.relations.overview.consultations import record_evidence_consultations

        with treatment_collector(run_id="debrief-3") as rows:
            record_evidence_consultations(
                user_id="11111111-1111-1111-1111-111111111111",
                run_id="debrief-3",
                requested={OverviewSection.EMAILS.value, OverviewSection.CALLS.value},
                unavailable=[OverviewSection.CALLS.value],
                duration_ms=55,
            )

        outcomes = {row.tool_name: row.outcome for row in rows}
        assert outcomes == {"relation:emails": "ok", "relation:calls": "failed"}

    def test_the_authorship_is_the_readers_own(self) -> None:
        """They opened the card; the debrief answers that.

        Same reading as the briefing, and the reason both stay in the two main
        lists rather than moving to a tab their owner never opened.
        """
        from src.domains.agents.effects.treatments import treatment_collector
        from src.domains.relations.overview.consultations import record_evidence_consultations

        with treatment_collector(run_id="debrief-4") as rows:
            record_evidence_consultations(
                user_id="11111111-1111-1111-1111-111111111111",
                run_id="debrief-4",
                requested={OverviewSection.CONTACT.value},
                unavailable=[],
                duration_ms=5,
            )

        assert rows[0].source == "user"

    def test_recording_never_breaks_the_build(self) -> None:
        """Outside a collector there is nothing to record and nothing to raise."""
        from src.domains.relations.overview.consultations import record_evidence_consultations

        record_evidence_consultations(
            user_id="11111111-1111-1111-1111-111111111111",
            run_id="debrief-5",
            requested={OverviewSection.EMAILS.value},
            unavailable=[],
            duration_ms=1,
        )


class TestTheBuildPublishesTheCollector:
    """A recording nobody collects is a recording nobody keeps."""

    async def test_the_build_opens_a_collector_the_sources_can_append_to(self) -> None:
        import uuid
        from unittest.mock import patch

        from src.domains.agents.effects.treatments import collected_treatments
        from src.domains.relations.debrief.service import RelationDebriefService

        seen: list[int] = []

        async def _inner(_self: object, run_id: str, **_: object) -> str:
            from src.domains.relations.overview.consultations import (
                record_evidence_consultations,
            )

            record_evidence_consultations(
                user_id=uuid.uuid4(),
                run_id=run_id,
                requested=[OverviewSection.EMAILS.value],
                unavailable=[],
                duration_ms=9,
            )
            seen.append(len(collected_treatments()))
            return "built"

        with (
            patch.object(RelationDebriefService, "_build_within", _inner),
            patch(
                "src.domains.agents.effects.treatment_recorder.TreatmentRepository",
                _NullRepository,
            ),
            patch("src.infrastructure.database.session.get_db_context", _null_db()),
        ):
            result = await RelationDebriefService(uuid.uuid4())._run_build(
                author=object(),  # type: ignore[arg-type]
                name="Marie",
                key="marie",
                owner=uuid.uuid4(),
                scope=object(),  # type: ignore[arg-type]
                language="fr",
                local_date=None,  # type: ignore[arg-type]
                previous=object(),  # type: ignore[arg-type]
            )

        assert result == "built"
        assert seen == [1], "the build published no collector, so nothing was kept"


class _NullRepository:
    def __init__(self, _db: object) -> None: ...

    async def record_batch(self, rows: list) -> int:
        return len(rows)


def _null_db() -> object:
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    @asynccontextmanager
    async def _context():  # type: ignore[no-untyped-def]
        yield AsyncMock()

    return _context
