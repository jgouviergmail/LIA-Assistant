"""The briefing says what it read, not only that it ran.

``record_treatment`` is called from exactly one place — the tool gate in
``effects/runtime.py`` — so a capability that is not a tool records nothing. The
briefing is exactly that: nine direct fetchers, no tools. Its consultations were
absent BY CONSTRUCTION, not by a missing flag, which is why no amount of
enabling would have produced them.

Two properties the design turns on, and both are about honesty rather than
completeness:

- **a cache hit is not a consultation.** Serving a section from Redis reads
  nothing of the person's mailbox, and recording it would inflate the register
  with reads that never happened.
- **a hidden section is not a consultation either.** The user switched it off;
  the fetcher never runs.

What remains — a live fetch — is a real read of a real source, and that is what
the register must be able to say.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.domains.agents.effects.treatments import (
    collected_treatments,
    record_out_of_turn_consultation,
    treatment_collector,
)

pytestmark = pytest.mark.unit


class TestRecordingAConsultationWithoutATurn:
    """The explicit form, for surfaces that never enter the graph."""

    def test_a_consultation_is_collected(self) -> None:
        user_id = uuid.uuid4()
        with treatment_collector(run_id="run-1") as rows:
            record_out_of_turn_consultation(
                user_id=user_id,
                run_id="run-1",
                capability="briefing:mails",
                source="user",
                succeeded=True,
                duration_ms=42,
            )
            assert len(rows) == 1

        row = rows[0]
        assert row.user_id == str(user_id)
        assert row.run_id == "run-1"
        assert row.tool_name == "briefing:mails"
        assert row.source == "user"
        assert row.outcome == "ok"
        assert row.duration_ms == 42

    def test_a_failed_read_is_recorded_as_failed(self) -> None:
        """« I could not look » is not « there was nothing »."""
        with treatment_collector(run_id="run-2") as rows:
            record_out_of_turn_consultation(
                user_id=uuid.uuid4(),
                run_id="run-2",
                capability="briefing:agenda",
                source="user",
                succeeded=False,
                duration_ms=7,
            )
        assert rows[0].outcome == "failed"

    def test_outside_a_collector_nothing_is_recorded_and_nothing_raises(self) -> None:
        """A probe, a script or a test harness must not be able to break."""
        record_out_of_turn_consultation(
            user_id=uuid.uuid4(),
            run_id="run-3",
            capability="briefing:tasks",
            source="user",
            succeeded=True,
            duration_ms=1,
        )
        assert collected_treatments() == ()

    def test_the_execution_mode_says_it_ran_outside_the_graph(self) -> None:
        from src.domains.agents.effects.decisions import OUT_OF_TURN_EXECUTION_MODE

        with treatment_collector(run_id="run-4") as rows:
            record_out_of_turn_consultation(
                user_id=uuid.uuid4(),
                run_id="run-4",
                capability="briefing:health",
                source="user",
                succeeded=True,
                duration_ms=3,
            )
        assert rows[0].execution_mode == OUT_OF_TURN_EXECUTION_MODE


class TestEverySectionReadsAsARealDomain:
    """A consultation with no domain is worse than none: it is unreadable."""

    def test_every_briefing_section_maps_to_a_declared_domain(self) -> None:
        from src.domains.agents.effects.treatment_labels import (
            TREATMENT_DOMAIN_OVERRIDES,
            UNKNOWN_DOMAIN,
        )
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
        from src.domains.briefing.constants import SECTION_NAMES
        from src.domains.briefing.consultations import SECTION_DOMAINS, consultation_capability

        for section in SECTION_NAMES:
            capability = consultation_capability(section)
            domain = TREATMENT_DOMAIN_OVERRIDES.get(capability)
            assert domain is not None, f"{capability} has no declared domain"
            assert domain == SECTION_DOMAINS[section], (
                f"the register reads {capability} as {domain!r} while the briefing "
                f"declares {SECTION_DOMAINS[section]!r} — the two halves have drifted"
            )
            assert domain != UNKNOWN_DOMAIN
            assert (
                domain in DOMAIN_REGISTRY
            ), f"{capability} maps to {domain!r}, which is not a domain of the taxonomy"

    def test_no_declared_briefing_capability_outlives_its_section(self) -> None:
        """A mapping for a section that no longer exists is a stale claim."""
        from src.domains.agents.effects.treatment_labels import TREATMENT_DOMAIN_OVERRIDES
        from src.domains.briefing.constants import SECTION_NAMES
        from src.domains.briefing.consultations import (
            CONSULTATION_PREFIX,
            consultation_capability,
        )

        declared = {
            key for key in TREATMENT_DOMAIN_OVERRIDES if key.startswith(CONSULTATION_PREFIX)
        }
        expected = {consultation_capability(section) for section in SECTION_NAMES}
        assert declared == expected


class TestWhatTheBriefingRecordsAndWhatItDoesNot:
    """Observed at the register boundary, on the real section wrapper."""

    async def test_a_live_fetch_is_recorded(self) -> None:
        rows = await _run_section(cached=False, hidden=False)
        assert [row.tool_name for row in rows] == ["briefing:mails"]

    async def test_a_cache_hit_records_nothing(self) -> None:
        """Redis answered; the mailbox was never opened."""
        rows = await _run_section(cached=True, hidden=False)
        assert rows == []

    async def test_a_hidden_section_records_nothing(self) -> None:
        """The person switched it off, so LIA did not look — on purpose."""
        rows = await _run_section(cached=False, hidden=True)
        assert rows == []


async def _run_section(*, cached: bool, hidden: bool) -> list:
    """Drive ``BriefingService._section`` and return what the register kept."""
    from src.domains.briefing.constants import SECTION_MAILS
    from src.domains.briefing.schemas import CardSection, CardStatus
    from src.domains.briefing.service import BriefingService

    user = _FakeUser()
    service = BriefingService(user)  # type: ignore[arg-type]
    service._hidden_sections = {SECTION_MAILS} if hidden else set()

    served = CardSection(status=CardStatus.OK, generated_at=datetime.now(UTC), data={"items": []})

    async def _read_cache(_key: str) -> CardSection | None:
        return served if cached else None

    async def _fetch_and_map(_name: str, _fetcher: object) -> CardSection:
        return served

    with (
        patch.object(BriefingService, "_read_cache", staticmethod(_read_cache)),
        patch.object(BriefingService, "_fetch_and_map", staticmethod(_fetch_and_map)),
        patch.object(BriefingService, "_write_cache", staticmethod(_noop3)),
        patch.object(BriefingService, "_write_last_good", staticmethod(_noop2)),
        treatment_collector(run_id="briefing-run") as rows,
    ):
        await service._section(
            SECTION_MAILS, lambda: served, ttl=300, force=False  # type: ignore[arg-type]
        )
    return list(rows)


async def _noop2(*_: object, **__: object) -> None:
    return None


async def _noop3(*_: object, **__: object) -> None:
    return None


class _FakeUser:
    id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    language = "fr"
    timezone = "Europe/Paris"


class TestTheBundleFilesItsOwnAct:
    """The collector is published by ``build_cards``, not by its callers."""

    async def test_a_bundle_that_read_something_files_a_turn(self) -> None:
        from unittest.mock import AsyncMock

        from src.domains.briefing.service import BriefingService

        recorded: list[object] = []
        service = BriefingService(_FakeUser())  # type: ignore[arg-type]

        async def _gather(_self: object, _force: object = None) -> object:
            from src.domains.agents.effects.treatments import record_out_of_turn_consultation

            record_out_of_turn_consultation(
                user_id=_FakeUser.id,
                run_id=service._consultation_run_id,
                capability="briefing:mails",
                source="user",
                succeeded=True,
                duration_ms=5,
            )
            return "bundle"

        with (
            patch.object(BriefingService, "_gather_cards", _gather),
            patch(
                "src.domains.agents.effects.treatment_recorder.TreatmentRepository",
                _NullRepository,
            ),
            patch("src.infrastructure.database.session.get_db_context", _null_db()),
            patch(
                "src.domains.agents.effects.decision_recorder.record_decision",
                AsyncMock(side_effect=lambda decision: recorded.append(decision)),
            ),
        ):
            result = await service.build_cards()

        assert result == "bundle"
        assert len(recorded) == 1, "a bundle that opened a source filed no act"
        assert recorded[0].route == "briefing_cards"
        assert recorded[0].source == "user"

    async def test_a_fully_cached_bundle_files_nothing(self) -> None:
        """Nothing was opened, so nothing is claimed.

        This is the property that keeps the register readable: the briefing is
        reached on every home-page load, and most of those are served entirely
        from Redis.
        """
        from unittest.mock import AsyncMock

        from src.domains.briefing.service import BriefingService

        recorded: list[object] = []
        service = BriefingService(_FakeUser())  # type: ignore[arg-type]

        async def _gather(_self: object, _force: object = None) -> object:
            return "bundle"

        with (
            patch.object(BriefingService, "_gather_cards", _gather),
            patch(
                "src.domains.agents.effects.decision_recorder.record_decision",
                AsyncMock(side_effect=lambda decision: recorded.append(decision)),
            ),
        ):
            await service.build_cards()

        assert recorded == []

    async def test_a_joining_caller_files_no_second_act(self) -> None:
        """One page load is one act, even though it takes two requests.

        ``/briefing/cards`` and ``/briefing/synthesis`` are issued in parallel
        and both want the bundle. Each used to gather it, so the register kept
        TWO batches of consultations and TWO decisions for a single reading of
        the person's sources — an honest record of a dishonest behaviour.

        Since the gathering is coalesced (ADR-271) the shared task runs in the
        context of the caller that STARTED it, so its rows land in that
        caller's live list and the joining caller collects nothing. The
        register therefore repairs itself, with no register code involved —
        which is exactly what this test pins.
        """
        import asyncio
        from unittest.mock import AsyncMock

        from src.domains.briefing.service import BriefingService
        from src.infrastructure.utils.single_flight import in_flight_count

        recorded: list[object] = []
        owner = BriefingService(_FakeUser())  # type: ignore[arg-type]
        joiner = BriefingService(_FakeUser())  # type: ignore[arg-type]

        async def _gather(_self: object, _force: object = None) -> object:
            record_out_of_turn_consultation(
                user_id=_FakeUser.id,
                # None: file under whichever collector is open — the owner's.
                run_id=None,
                capability="briefing:mails",
                source="user",
                succeeded=True,
                duration_ms=5,
            )
            # Long enough for the second caller to arrive while this runs,
            # which is the whole situation under test.
            await asyncio.sleep(0.05)
            return "bundle"

        with (
            patch.object(BriefingService, "_gather_cards", _gather),
            patch(
                "src.domains.agents.effects.treatment_recorder.TreatmentRepository",
                _NullRepository,
            ),
            patch("src.infrastructure.database.session.get_db_context", _null_db()),
            patch(
                "src.domains.agents.effects.decision_recorder.record_decision",
                AsyncMock(side_effect=lambda decision: recorded.append(decision)),
            ),
        ):
            bundles = await asyncio.gather(owner.build_cards(), joiner.build_cards())

        assert bundles == ["bundle", "bundle"], "both callers must get the bundle"
        assert len(recorded) == 1, (
            f"one page load filed {len(recorded)} acts — the register is counting callers, "
            "not reads"
        )
        assert in_flight_count() == 0

    async def test_a_broken_register_never_costs_the_dashboard(self) -> None:
        """The cards are already built when the register writes."""
        from unittest.mock import AsyncMock

        from src.domains.briefing.service import BriefingService

        service = BriefingService(_FakeUser())  # type: ignore[arg-type]

        async def _gather(_self: object, _force: object = None) -> object:
            from src.domains.agents.effects.treatments import record_out_of_turn_consultation

            record_out_of_turn_consultation(
                user_id=_FakeUser.id,
                run_id=service._consultation_run_id,
                capability="briefing:tasks",
                source="user",
                succeeded=True,
                duration_ms=5,
            )
            return "bundle"

        with (
            patch.object(BriefingService, "_gather_cards", _gather),
            patch(
                "src.domains.agents.effects.treatment_recorder.TreatmentRepository",
                _NullRepository,
            ),
            patch("src.infrastructure.database.session.get_db_context", _null_db()),
            patch(
                "src.domains.agents.effects.decision_recorder.record_decision",
                AsyncMock(side_effect=RuntimeError("register down")),
            ),
        ):
            assert await service.build_cards() == "bundle"


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


class TestTheReaderSeesADomainNotAPath:
    """The register's headline is a noun the person recognises.

    The API resolves the domain server-side; the interface shows a translated
    noun and keeps the capability name as a technical detail. A section whose
    domain fell through to `unknown` would headline every briefing read as
    "Unknown", which is worse than not recording it.
    """

    def test_every_section_resolves_through_the_registers_own_resolver(self) -> None:
        from src.domains.agents.effects.treatment_labels import UNKNOWN_DOMAIN, treatment_domain
        from src.domains.briefing.constants import SECTION_NAMES
        from src.domains.briefing.consultations import (
            SECTION_DOMAINS,
            consultation_capability,
        )

        for section in SECTION_NAMES:
            resolved = treatment_domain(consultation_capability(section))
            assert resolved != UNKNOWN_DOMAIN, f"{section} headlines as Unknown"
            assert resolved == SECTION_DOMAINS[section]


class TestTheRegisterNeverCostsTheDashboard:
    """``_section`` is documented « Never raises. » — including now."""

    async def test_a_broken_register_still_returns_the_card(self) -> None:
        from src.domains.agents.effects import treatments as treatments_module
        from src.domains.briefing.constants import SECTION_MAILS
        from src.domains.briefing.schemas import CardSection, CardStatus
        from src.domains.briefing.service import BriefingService

        service = BriefingService(_FakeUser())  # type: ignore[arg-type]
        served = CardSection(
            status=CardStatus.OK, generated_at=datetime.now(UTC), data={"items": []}
        )

        async def _read_cache(_key: str) -> CardSection | None:
            return None

        async def _fetch_and_map(_name: str, _fetcher: object) -> CardSection:
            return served

        def _explode(**_: object) -> None:
            raise RuntimeError("register down")

        with (
            patch.object(BriefingService, "_read_cache", staticmethod(_read_cache)),
            patch.object(BriefingService, "_fetch_and_map", staticmethod(_fetch_and_map)),
            patch.object(BriefingService, "_write_cache", staticmethod(_noop3)),
            patch.object(BriefingService, "_write_last_good", staticmethod(_noop2)),
            patch.object(treatments_module, "record_out_of_turn_consultation", _explode),
        ):
            section = await service._section(
                SECTION_MAILS,
                lambda: served,  # type: ignore[arg-type]
                ttl=300,
                force=False,
            )

        assert section.status is CardStatus.OK
