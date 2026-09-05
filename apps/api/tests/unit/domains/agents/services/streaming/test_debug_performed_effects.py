"""The debug panel shows the REGISTER's answer, not its own (ADR-263).

An admin looking at a turn and a user looking at their journal must see the
same facts, or the register is worth nothing: both read the same rows through
``performed_effects``. This stage is async on purpose — ``DebugMetricsBuilder``
performs no I/O at all, and a database read inside it would cost that property.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.services.streaming import debug_metrics_stages as stages

pytestmark = [pytest.mark.unit]


class TestTheSectionReportsWhatWasRecorded:
    async def test_it_carries_the_entries_and_their_counts(self) -> None:
        payload: dict[str, Any] = {}
        entries = [
            {"label_key": "effects.labels.draft.email", "values": {}, "status": "succeeded"},
            {
                "label_key": "effects.labels.control_hue_light_tool",
                "values": {},
                "status": "failed",
            },
        ]

        with patch(
            "src.domains.agents.effects.turn_summary.performed_effects",
            AsyncMock(return_value=entries),
        ):
            await stages.add_performed_effects(payload, "run-1")

        section = payload["performed_effects"]
        assert section["count"] == 2
        assert section["failed_count"] == 1
        assert section["entries"] == entries

    async def test_a_turn_with_no_effect_still_declares_the_section(self) -> None:
        """Zero is an answer; an absent section reads as "unknown"."""
        payload: dict[str, Any] = {}

        with patch(
            "src.domains.agents.effects.turn_summary.performed_effects",
            AsyncMock(return_value=[]),
        ):
            await stages.add_performed_effects(payload, "run-1")

        assert payload["performed_effects"] == {"entries": [], "count": 0, "failed_count": 0}

    async def test_no_run_id_adds_nothing(self) -> None:
        payload: dict[str, Any] = {}
        await stages.add_performed_effects(payload, "")
        assert payload == {}


class TestItReadsTheSameSourceAsTheUser:
    def test_it_delegates_to_the_turn_summary(self) -> None:
        """One reader, so the panel and the journal cannot disagree."""
        import inspect

        source = inspect.getsource(stages.add_performed_effects)
        assert "performed_effects" in source
        assert (
            "EffectLedgerRepository" not in source
        ), "the stage must go through the shared reader, not query the ledger itself"
