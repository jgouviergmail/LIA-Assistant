"""The answer states what the REGISTER recorded (ADR-263).

Not the graph state, not a counter kept along the way: the point of the whole
programme is that a reader need not trust the executor. So the turn summary
reads the ledger back by ``run_id``, and everything else follows from what a
row can honestly support.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects.models import EffectStatus
from src.domains.agents.effects.turn_summary import performed_effects

pytestmark = [pytest.mark.unit]


def _row(status: EffectStatus, tool_name: str = "control_hue_light_tool") -> Any:
    return SimpleNamespace(status=status, tool_name=tool_name, label=b"whatever")


class _Repository:
    """Stands in for the ledger repository; the session is never real here."""

    def __init__(self, rows: list[Any], labels: dict[str, Any] | None = None) -> None:
        self._rows = rows
        self._labels = labels or {}

    async def list_for_run(self, run_id: str) -> list[Any]:
        self.seen_run_id = run_id
        return self._rows

    def decrypted_label_for(self, row: Any) -> dict[str, Any] | None:
        return self._labels.get(row.tool_name)


def _patched(repository: _Repository) -> Any:
    """Patch the repository class and the module's DB context together."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _context() -> Any:
        yield object()

    return (
        patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository",
            side_effect=lambda _db: repository,
        ),
        patch("src.infrastructure.database.session.get_db_context", _context),
    )


class TestOnlyWhatHappenedIsReported:
    async def test_a_succeeded_effect_is_reported(self) -> None:
        repository = _Repository([_row(EffectStatus.SUCCEEDED)])
        with _patched(repository)[0], _patched(repository)[1]:
            entries = await performed_effects("run-1")

        assert len(entries) == 1
        assert entries[0]["status"] == "succeeded"
        assert entries[0]["tool_name"] == "control_hue_light_tool"

    async def test_a_failed_effect_is_reported_too(self) -> None:
        """Honesty cuts both ways: an attempt that failed still happened."""
        repository = _Repository([_row(EffectStatus.FAILED)])
        with _patched(repository)[0], _patched(repository)[1]:
            entries = await performed_effects("run-1")

        assert [entry["status"] for entry in entries] == ["failed"]

    @pytest.mark.parametrize("status", [EffectStatus.REFUSED, EffectStatus.CLAIMED])
    async def test_a_refusal_or_an_open_claim_is_not_reported(self, status: EffectStatus) -> None:
        """A refusal changed nothing; an open claim cannot be described yet."""
        repository = _Repository([_row(status)])
        with _patched(repository)[0], _patched(repository)[1]:
            entries = await performed_effects("run-1")

        assert entries == []

    async def test_a_turn_with_no_effect_reports_nothing(self) -> None:
        repository = _Repository([])
        with _patched(repository)[0], _patched(repository)[1]:
            assert await performed_effects("run-1") == []

    async def test_no_run_id_asks_the_database_nothing(self) -> None:
        """The pure-conversation case must not pay for a query."""
        touched: list[str] = []

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _context() -> Any:
            touched.append("opened")
            yield object()

        with patch("src.infrastructure.database.session.get_db_context", _context):
            assert await performed_effects("") == []

        assert touched == []


class TestTheEntryCarriesKeysNotSentences:
    async def test_the_label_key_and_values_travel(self) -> None:
        repository = _Repository([_row(EffectStatus.SUCCEEDED)])
        label = {"i18n_key": "effects.labels.control_hue_light_tool", "values": {"target": "Salon"}}

        with (
            _patched(repository)[0],
            _patched(repository)[1],
            patch(
                "src.domains.agents.effects.repository.EffectLedgerRepository.decrypted_label",
                staticmethod(lambda _row: label),
            ),
        ):
            entries = await performed_effects("run-1")

        assert entries[0]["label_key"] == "effects.labels.control_hue_light_tool"
        assert entries[0]["values"] == {"target": "Salon"}
        assert "label" not in entries[0], "a translated sentence must never travel"

    async def test_an_unreadable_label_degrades_to_the_generic_wording(self) -> None:
        """A row from an older version, or a rotated key: the line survives."""
        repository = _Repository([_row(EffectStatus.SUCCEEDED)])

        with (
            _patched(repository)[0],
            _patched(repository)[1],
            patch(
                "src.domains.agents.effects.repository.EffectLedgerRepository.decrypted_label",
                staticmethod(lambda _row: None),
            ),
        ):
            entries = await performed_effects("run-1")

        assert entries[0]["label_key"] == "effects.labels.generic"
        assert entries[0]["values"] == {"tool": "control_hue_light_tool"}


class TestItNeverCostsTheUserTheirAnswer:
    async def test_a_database_failure_is_swallowed_and_logged(self) -> None:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _exploding() -> Any:
            raise RuntimeError("no database")
            yield  # pragma: no cover

        with patch("src.infrastructure.database.session.get_db_context", _exploding):
            assert await performed_effects("run-1") == []
