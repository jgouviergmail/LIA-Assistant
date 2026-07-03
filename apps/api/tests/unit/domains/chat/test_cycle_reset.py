"""Multi-silo billing-cycle reset tests (audit wave 2, C2).

Three code paths can cross a billing-cycle boundary:

1. A chat message  → ``UserStatisticsRepository.create_or_update(is_new_cycle=True)``
2. An STT call     → ``UserStatisticsRepository.add_stt_usage(is_new_cycle=True)``
3. A dashboard read → ``StatisticsService.reset_cycle_if_needed``

Whichever event crosses the boundary first, NO counter from the previous
cycle may leak into the new one — tokens, cost, messages, Google API, image
generation, TTS and STT alike. The single source of truth is
``UserStatistics.reset_cycle()``, which introspects the model's ``cycle_*``
columns so any future silo is reset automatically.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.core.field_names import (
    FIELD_COST_EUR,
    FIELD_MESSAGE_COUNT,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
)
from src.domains.chat.models import UserStatistics
from src.domains.chat.repository import UserStatisticsRepository
from src.domains.chat.service import StatisticsService

OLD_CYCLE_START = datetime(2026, 5, 15, tzinfo=UTC)
NEW_CYCLE_START = datetime(2026, 6, 15, tzinfo=UTC)

# Every cycle_* column of the model, with a non-default "dirty" value that a
# leaked counter would carry over from the previous cycle.
DIRTY_CYCLE_VALUES: dict[str, object] = {
    "cycle_prompt_tokens": 111,
    "cycle_completion_tokens": 222,
    "cycle_cached_tokens": 333,
    "cycle_cost_eur": Decimal("9.99"),
    "cycle_messages": 44,
    "cycle_google_api_requests": 55,
    "cycle_google_api_cost_eur": Decimal("1.11"),
    "cycle_image_generation_requests": 66,
    "cycle_image_generation_cost_eur": Decimal("2.22"),
    "cycle_stt_audio_seconds": Decimal("77.70"),
    "cycle_stt_cost_eur": Decimal("3.33"),
    "cycle_tts_characters": Decimal("8888"),
    "cycle_tts_cost_eur": Decimal("4.44"),
}


def _dirty_stats() -> UserStatistics:
    """Build a stats row full of previous-cycle counters."""
    stats = UserStatistics(
        user_id=uuid.uuid4(),
        current_cycle_start=OLD_CYCLE_START,
        total_prompt_tokens=1000,
        total_completion_tokens=1000,
        total_cached_tokens=1000,
        total_cost_eur=Decimal("100"),
        total_messages=100,
        total_google_api_requests=10,
        total_google_api_cost_eur=Decimal("1"),
        total_image_generation_requests=10,
        total_image_generation_cost_eur=Decimal("1"),
        total_stt_audio_seconds=Decimal("10"),
        total_stt_cost_eur=Decimal("1"),
        total_tts_characters=Decimal("10"),
        total_tts_cost_eur=Decimal("1"),
        last_updated_at=OLD_CYCLE_START,
        created_at=OLD_CYCLE_START,
        updated_at=OLD_CYCLE_START,
        id=uuid.uuid4(),
        **DIRTY_CYCLE_VALUES,
    )
    return stats


def _model_cycle_columns() -> set[str]:
    return {
        column.name
        for column in UserStatistics.__table__.columns
        if column.name.startswith("cycle_")
    }


def _repo_with(stats: UserStatistics) -> UserStatisticsRepository:
    repo = UserStatisticsRepository(AsyncMock())
    repo.get_by_user_id = AsyncMock(return_value=stats)
    return repo


class TestDirtyValuesCoverage:
    """The test fixture itself must cover every cycle_* column (guard)."""

    def test_dirty_values_cover_all_cycle_columns(self):
        missing = _model_cycle_columns() - set(DIRTY_CYCLE_VALUES)
        assert not missing, (
            f"New cycle_* columns not covered by this test: {sorted(missing)} — "
            "add them to DIRTY_CYCLE_VALUES (reset_cycle() already handles them "
            "automatically via column introspection)."
        )


class TestResetCycleModelMethod:
    """UserStatistics.reset_cycle() zeroes every cycle_* column."""

    def test_reset_cycle_zeroes_every_cycle_column(self):
        stats = _dirty_stats()

        stats.reset_cycle(NEW_CYCLE_START)

        assert stats.current_cycle_start == NEW_CYCLE_START
        for column in sorted(_model_cycle_columns()):
            value = getattr(stats, column)
            assert value == 0, f"{column} leaked from previous cycle: {value!r}"

    def test_reset_cycle_preserves_lifetime_totals(self):
        stats = _dirty_stats()

        stats.reset_cycle(NEW_CYCLE_START)

        assert stats.total_prompt_tokens == 1000
        assert stats.total_cost_eur == Decimal("100")
        assert stats.total_stt_audio_seconds == Decimal("10")
        assert stats.total_tts_characters == Decimal("10")


class TestCycleBoundaryViaMessage:
    """Path 1: a chat message crosses the cycle boundary."""

    @pytest.mark.asyncio
    async def test_message_new_cycle_resets_all_silos(self):
        stats = _dirty_stats()
        repo = _repo_with(stats)

        await repo.create_or_update(
            user_id=stats.user_id,
            current_cycle_start=NEW_CYCLE_START,
            summary_data={
                FIELD_TOKENS_IN: 10,
                FIELD_TOKENS_OUT: 20,
                FIELD_TOKENS_CACHE: 5,
                FIELD_COST_EUR: Decimal("0.5"),
                FIELD_MESSAGE_COUNT: 1,
            },
            is_new_cycle=True,
        )

        # The new cycle carries ONLY this message's contribution
        assert stats.current_cycle_start == NEW_CYCLE_START
        assert stats.cycle_prompt_tokens == 10
        assert stats.cycle_completion_tokens == 20
        assert stats.cycle_cached_tokens == 5
        assert stats.cycle_cost_eur == Decimal("0.5")
        assert stats.cycle_messages == 1
        assert stats.cycle_google_api_requests == 0
        assert stats.cycle_google_api_cost_eur == 0
        assert stats.cycle_image_generation_requests == 0
        assert stats.cycle_image_generation_cost_eur == 0
        # STT silo must NOT leak (previous bug: untouched by this path)
        assert stats.cycle_stt_audio_seconds == 0
        assert stats.cycle_stt_cost_eur == 0
        assert stats.cycle_tts_characters == 0
        assert stats.cycle_tts_cost_eur == 0
        # Lifetime totals still accumulate
        assert stats.total_prompt_tokens == 1010
        assert stats.total_cost_eur == Decimal("100.5")


class TestCycleBoundaryViaSTT:
    """Path 2: an STT call crosses the cycle boundary."""

    @pytest.mark.asyncio
    async def test_stt_new_cycle_resets_all_silos(self):
        stats = _dirty_stats()
        repo = _repo_with(stats)

        await repo.add_stt_usage(
            user_id=stats.user_id,
            audio_duration_seconds=12.5,
            cost_eur=Decimal("0.05"),
            current_cycle_start=NEW_CYCLE_START,
            is_new_cycle=True,
        )

        assert stats.current_cycle_start == NEW_CYCLE_START
        # The new cycle carries ONLY this STT call's contribution
        assert stats.cycle_stt_audio_seconds == Decimal("12.5")
        assert stats.cycle_stt_cost_eur == Decimal("0.05")
        assert stats.cycle_cost_eur == Decimal("0.05")
        # Every other silo must be zero (previous bug: tokens/messages/
        # google/image/TTS leaked through the STT path)
        assert stats.cycle_prompt_tokens == 0
        assert stats.cycle_completion_tokens == 0
        assert stats.cycle_cached_tokens == 0
        assert stats.cycle_messages == 0
        assert stats.cycle_google_api_requests == 0
        assert stats.cycle_google_api_cost_eur == 0
        assert stats.cycle_image_generation_requests == 0
        assert stats.cycle_image_generation_cost_eur == 0
        assert stats.cycle_tts_characters == 0
        assert stats.cycle_tts_cost_eur == 0
        # Lifetime totals still accumulate
        assert stats.total_stt_audio_seconds == Decimal("22.5")
        assert stats.total_cost_eur == Decimal("100.05")


class TestCycleBoundaryViaDashboard:
    """Path 3: a dashboard read crosses the cycle boundary."""

    def test_dashboard_reset_zeroes_all_silos(self):
        stats = _dirty_stats()

        was_reset = StatisticsService.reset_cycle_if_needed(stats, NEW_CYCLE_START, stats.user_id)

        assert was_reset is True
        assert stats.current_cycle_start == NEW_CYCLE_START
        for column in sorted(_model_cycle_columns()):
            value = getattr(stats, column)
            assert value == 0, f"{column} leaked from previous cycle: {value!r}"

    def test_dashboard_no_reset_within_same_cycle(self):
        stats = _dirty_stats()

        was_reset = StatisticsService.reset_cycle_if_needed(
            stats, OLD_CYCLE_START - timedelta(days=1), stats.user_id
        )

        assert was_reset is False
        assert stats.cycle_prompt_tokens == 111  # untouched
