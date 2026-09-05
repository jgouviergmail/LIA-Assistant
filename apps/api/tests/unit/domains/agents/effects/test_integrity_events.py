"""When the record itself is incomplete (ADR-263, lot 8).

Four situations mean the registers are not telling the whole truth, and each of
them already had a metric. What a counter cannot say is WHICH account and WHICH
turn — the question a user and a regulator actually ask — so each detection now
writes a row beside the counter it already increments.

The properties below are the ones that make that safe rather than merely
present: one detection with two destinations (never a second detector), bounded
kinds (never a free-text event log), no content, and — the one that matters most
— observing must never break the observed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects.integrity import IntegrityKind, record_integrity_event

pytestmark = [pytest.mark.unit]


class TestObservingNeverBreaksTheObserved:
    async def test_a_database_failure_is_swallowed(self) -> None:
        """This is called from the gate's own path. An integrity note that
        could fail a turn would be a worse defect than the one it records."""
        with patch(
            "src.infrastructure.database.session.get_db_context",
            side_effect=RuntimeError("no database"),
        ):
            await record_integrity_event(IntegrityKind.EFFECT_UNRECORDED)

    async def test_a_repository_failure_is_swallowed_too(self) -> None:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _session():  # type: ignore[no-untyped-def]
            yield AsyncMock()

        with (
            patch("src.infrastructure.database.session.get_db_context", _session),
            patch(
                "src.domains.agents.effects.integrity_repository.IntegrityRepository.record",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            await record_integrity_event(IntegrityKind.CHAIN_BROKEN, detail="payload@3")


class TestTheVocabularyIsBOUNDED:
    def test_there_are_exactly_four_kinds(self) -> None:
        """A fifth is a decision someone takes here, not a string someone
        passes — which is what keeps this a register and not a second log."""
        assert {kind.value for kind in IntegrityKind} == {
            "effect_unrecorded",
            "treatments_uncollected",
            "chain_broken",
            "notary_failed",
        }

    def test_every_kind_names_a_gap_in_the_RECORD(self) -> None:
        """Not « something went wrong » — the registers already hold failures.
        These four all mean: what you are reading may be incomplete."""
        from src.domains.agents.effects.models import AgentIntegrityEvent

        assert "detail" in AgentIntegrityEvent.__table__.columns
        assert AgentIntegrityEvent.__table__.c.detail.type.length == 200


class TestTheRowHoldsNoCONTENT:
    @pytest.mark.parametrize(
        "forbidden", ["label", "args", "content", "prompt", "result", "message"]
    )
    def test_no_column_can_carry_what_was_asked(self, forbidden: str) -> None:
        from src.domains.agents.effects.models import AgentIntegrityEvent

        assert forbidden not in AgentIntegrityEvent.__table__.columns

    def test_the_account_may_be_UNKNOWN_and_that_is_the_finding(self) -> None:
        """One of the four detections fires precisely when no run context named
        a user. Inventing one would erase the interesting half."""
        from src.domains.agents.effects.models import AgentIntegrityEvent

        assert AgentIntegrityEvent.__table__.c.user_id.nullable
        assert AgentIntegrityEvent.__table__.c.run_id.nullable

    def test_a_named_account_still_takes_its_gaps_with_it(self) -> None:
        from src.domains.agents.effects.models import AgentIntegrityEvent

        keys = list(AgentIntegrityEvent.__table__.c.user_id.foreign_keys)

        assert keys[0].column.table.name == "users"
        assert keys[0].ondelete == "CASCADE"


class TestOneDetectionTwoDestinations:
    def test_every_kind_is_written_where_its_metric_already_fires(self) -> None:
        """A second detector would be a second opinion on when a gap happened.
        Read from the source: each module that increments one of the four
        counters must also record the matching kind."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[5] / "src"
        pairs = {
            "effect_unrecorded_total": "EFFECT_UNRECORDED",
            "treatments_uncollected_total": "TREATMENTS_UNCOLLECTED",
            "ledger_chain_breaks_total": "CHAIN_BROKEN",
            "ledger_chain_pass_failures_total": "NOTARY_FAILED",
        }
        for metric, kind in pairs.items():
            emitters = [
                path
                for path in root.rglob("*.py")
                if f"{metric}.labels" in path.read_text(encoding="utf-8")
                or f"{metric}.inc" in path.read_text(encoding="utf-8")
            ]
            assert emitters, f"{metric} is emitted nowhere"
            assert any(
                kind in path.read_text(encoding="utf-8") for path in emitters
            ), f"{metric} fires without recording IntegrityKind.{kind}"
