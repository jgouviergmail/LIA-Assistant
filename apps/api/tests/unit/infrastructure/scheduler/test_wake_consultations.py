"""The push-driven wake says which source it probed.

ADR-261: a Google push queues a wake, and the sweep reads the METADATA of the
new mail or the calendar changes to decide whether waking the person is worth
it. Nobody asked for that read, it runs on a scheduler, and — unlike a sweep
that then writes to them — it usually decides NOT to. So there is nothing else
the person could ever consult about it, which is exactly when a register earns
its keep.

ONE row per wake and per source probed, never one per message: the register
names the capability, never the mail (owner arbitration, 2026-09-07, « fais au
plus simple tant que cela ne casse pas la philosophie des registres »).
"""

from __future__ import annotations

import uuid

import pytest

from src.domains.agents.effects.treatments import treatment_collector
from src.infrastructure.scheduler.heartbeat_wake_sweep import _wake_read

pytestmark = pytest.mark.unit


class TestWhatAWakeRecords:
    async def test_a_probe_that_answered_is_recorded(self) -> None:
        with treatment_collector(run_id="wake-1") as rows:
            async with _wake_read(uuid.uuid4(), "emails"):
                pass

        assert [row.tool_name for row in rows] == ["wake:emails"]
        assert rows[0].outcome == "ok"

    async def test_a_probe_that_failed_is_not_recorded_as_read(self) -> None:
        with treatment_collector(run_id="wake-2") as rows, pytest.raises(RuntimeError):
            async with _wake_read(uuid.uuid4(), "calendar"):
                raise RuntimeError("gmail down")

        assert [row.tool_name for row in rows] == ["wake:calendar"]
        assert rows[0].outcome == "failed"

    async def test_nobody_asked_for_it(self) -> None:
        """Which is what puts it in the initiative reading."""
        with treatment_collector(run_id="wake-3") as rows:
            async with _wake_read(uuid.uuid4(), "emails"):
                pass

        assert rows[0].source == "proactive"

    async def test_one_row_per_source_probed_never_one_per_message(self) -> None:
        with treatment_collector(run_id="wake-4") as rows:
            async with _wake_read(uuid.uuid4(), "emails"):
                # Whatever the probe finds — one message or four hundred —
                # the register records that the mailbox was opened, once.
                pass

        assert len(rows) == 1

    async def test_outside_a_run_nothing_is_recorded_and_nothing_raises(self) -> None:
        async with _wake_read(uuid.uuid4(), "emails"):
            pass


class TestTheVocabularyIsReadable:
    def test_each_probe_reads_as_the_source_it_opened(self) -> None:
        from src.domains.agents.effects.treatment_labels import UNKNOWN_DOMAIN, treatment_domain
        from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

        surface = CONSULTATION_SURFACES["wake"]
        assert set(surface.domains) == {"emails", "calendar"}
        for section, domain in surface.domains.items():
            resolved = treatment_domain(surface.capability(section))
            assert resolved != UNKNOWN_DOMAIN
            assert resolved == domain
