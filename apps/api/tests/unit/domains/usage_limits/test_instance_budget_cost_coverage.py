"""Every euro this instance spends must count against its ceiling.

The owner's arbitration is a MAXIMUM: one euro per day. A ceiling that only
sees some of the spending is not a ceiling, it is a comfortable illusion —
and the families it misses are precisely the ones a public demonstrator
invites people to use.

Two escape routes exist, and they fail differently:

- **the sum forgets a field**: the cost reaches ``record_run_summary`` inside
  the run summary, but ``_COST_FIELDS`` does not add it up;
- **the cost never takes the road**: a billing path with its own session
  writes straight to ``user_statistics`` and never touches the ledger.

So this file guards both: the arithmetic (every ``*_cost_eur`` key of a run
summary is counted or deliberately excluded), and the reachability (every
family billed into ``user_statistics`` has a declared way to the ledger).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.usage_limits.instance_budget import (
    _COST_FIELDS,
    InstanceBudgetService,
)

pytestmark = pytest.mark.unit


class TestEveryBilledFamilyCounts:
    """The arithmetic: what the summary carries, the ceiling must see."""

    def test_speech_synthesis_counts_against_the_ceiling(self) -> None:
        # A visitor making the assistant speak spends real provider money.
        summary = {"cost_eur": 0.0, "tts_cost_eur": 0.40}
        assert InstanceBudgetService.total_cost_eur(summary) == Decimal("0.40")

    def test_every_cost_family_of_a_full_summary_is_summed(self) -> None:
        # One cent per family: the total says how many families were counted,
        # so a forgotten one is visible as a number, not as a silence.
        summary = {
            "cost_eur": 0.01,
            "google_api_cost_eur": 0.01,
            "image_generation_cost_eur": 0.01,
            "tts_cost_eur": 0.01,
        }
        assert InstanceBudgetService.total_cost_eur(summary) == Decimal("0.04")

    def test_an_unknown_cost_family_is_not_silently_dropped(self) -> None:
        """The guard: a new ``*_cost_eur`` key must be classified.

        This is the maintenance property. The day someone adds a billing
        family to the run summary, this test fails until they decide — count
        it, or write down why it must not count. Nothing escapes by default.
        """
        from src.domains.usage_limits.instance_budget import _EXCLUDED_COST_FIELDS

        # Every key the tracker publishes as a cost, from the one place that
        # builds it. Read from the source, never re-listed here — a hand-kept
        # copy would drift and the guard would guard nothing.
        published = _published_cost_fields()
        classified = set(_COST_FIELDS) | set(_EXCLUDED_COST_FIELDS)
        unclassified = published - classified
        assert not unclassified, (
            f"unclassified cost families in the run summary: {sorted(unclassified)} — "
            "add them to _COST_FIELDS, or to _EXCLUDED_COST_FIELDS with a reason"
        )

    def test_no_stale_classification(self) -> None:
        """A field that left the summary must leave the classification too."""
        from src.domains.usage_limits.instance_budget import _EXCLUDED_COST_FIELDS

        published = _published_cost_fields()
        stale = (set(_COST_FIELDS) | set(_EXCLUDED_COST_FIELDS)) - published
        assert not stale, f"classified but no longer published: {sorted(stale)}"

    def test_every_exclusion_carries_a_written_reason(self) -> None:
        from src.domains.usage_limits.instance_budget import _EXCLUDED_COST_FIELDS

        for field, reason in _EXCLUDED_COST_FIELDS.items():
            assert reason.strip(), f"{field} is excluded without a reason"


class TestEveryBillingPathReachesTheLedger:
    """Reachability: a cost with its own session must still be recorded."""

    async def test_remote_speech_recognition_reaches_the_ledger(self) -> None:
        """STT bills the owner from the WebSocket handler, session included.

        Its cost never enters a run summary, so unless it records its own
        spend the ceiling is blind to every dictated message.
        """
        from src.domains.chat.service import StatisticsService

        recorded: list[Decimal] = []

        async def _capture(session: object, *, cost_eur: Decimal, **_: object) -> None:
            recorded.append(cost_eur)

        with (
            patch(
                "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
                AsyncMock(side_effect=_capture),
            ),
            patch("src.domains.chat.service.get_db_context", _fake_db_context(AsyncMock())),
            patch(
                "src.domains.users.repository.UserRepository.get_by_id",
                AsyncMock(return_value=_fake_user()),
            ),
            patch(
                "src.domains.chat.repository.UserStatisticsRepository.add_stt_usage",
                AsyncMock(),
            ),
            patch(
                "src.domains.chat.repository.UserStatisticsRepository.get_by_user_id",
                AsyncMock(return_value=None),
            ),
        ):
            await StatisticsService.record_remote_stt(
                user_id=_fake_user().id,
                audio_duration_seconds=12.0,
                cost_eur=Decimal("0.03"),
            )

        assert recorded == [Decimal("0.03")], "remote STT spend never reached the ledger"

    async def test_free_speech_recognition_writes_nothing_to_the_ledger(self) -> None:
        """A local, zero-cost transcription must leave no ledger entry.

        The real recording code runs here on purpose: the property is "nothing
        was written", observed at the session boundary — not "a function was
        not called", which would pin one implementation and pass just as
        happily on a broken one.
        """
        from src.domains.chat.service import StatisticsService

        session = AsyncMock()
        with (
            patch("src.domains.chat.service.get_db_context", _fake_db_context(session)),
            patch(
                "src.domains.users.repository.UserRepository.get_by_id",
                AsyncMock(return_value=_fake_user()),
            ),
            patch(
                "src.domains.chat.repository.UserStatisticsRepository.add_stt_usage",
                AsyncMock(),
            ),
            patch(
                "src.domains.chat.repository.UserStatisticsRepository.get_by_user_id",
                AsyncMock(return_value=None),
            ),
        ):
            await StatisticsService.record_remote_stt(
                user_id=_fake_user().id,
                audio_duration_seconds=0.0,
                cost_eur=Decimal("0"),
            )

        assert session.begin_nested.await_count == 0
        assert session.execute.await_count == 0


def _published_cost_fields() -> set[str]:
    """Cost keys the run summary actually publishes, read from the source.

    Parses ``TrackingContext.get_summary`` rather than trusting a copy: the
    point of the guard is to notice a field this file was never told about.
    """
    import ast
    import inspect
    from textwrap import dedent

    from src.domains.chat.service import TrackingContext

    source = dedent(inspect.getsource(TrackingContext.get_summary))
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if key.value.endswith("_cost_eur"):
                        names.add(key.value)
                elif isinstance(key, ast.Name) and key.id.endswith("_COST_EUR"):
                    names.add(_resolve_field_constant(key.id))
    return names


def _resolve_field_constant(constant_name: str) -> str:
    """Resolve a ``FIELD_*`` constant to the string it names."""
    from src.core import field_names

    value = getattr(field_names, constant_name)
    assert isinstance(value, str)
    return value


def _fake_user() -> object:
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import UUID

    return SimpleNamespace(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _fake_db_context(session: object) -> object:
    """A ``get_db_context()`` yielding the session the test can inspect."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _context():  # type: ignore[no-untyped-def]
        yield session

    return _context
