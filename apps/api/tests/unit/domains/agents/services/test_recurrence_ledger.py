"""Recurrence ledger writer tests (ADR-140, ADR-214, ADR-375).

The contract pinned here:
- the signature is the DOMAIN only (the hour is data, not a key);
- storage is per-day, capped in DAY entries, one hour per clock hour;
- legacy ``{"ts": [...]}`` payloads convert instead of crashing;
- the write obeys the person's switch and the operator's capability, and
  every outcome is counted.
"""

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.recurrence_ledger import (
    build_signature,
    record_occurrence,
    record_occurrence_if_allowed,
)
from src.infrastructure.observability.metrics_agents import recurrence_ledger_writes_total

TODAY = date(2026, 8, 4)  # a Tuesday
#: The operator's habits switch, read by every habit act (ADR-280); its OFF side
#: is pinned in ``tests/unit/domains/habits/test_capability_at_the_act.py``.
HABITS_SWITCH = "src.domains.habits.capability.is_capability_enabled"


def _settings(**overrides):
    defaults = {
        "recurrence_window_days": 28,
        "recurrence_min_distinct_days": 4,
        "recurrence_ledger_max_entries": 28,
        "recurrence_day_hours_cap": 5,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.unit
class TestBuildSignature:
    def test_stable_for_same_shape_any_hour(self):
        # v2: the hour is DATA, never part of the key — a habit straddling a
        # bucket boundary was split in two by the old 4h buckets.
        assert build_signature("email", ["contact"]) == "contact... email".replace(
            "... ", "+"
        ).replace("contact+email", "email+contact")

    def test_secondary_order_is_irrelevant(self):
        assert build_signature("email", ["contact", "file"]) == build_signature(
            "email", ["file", "contact"]
        )

    def test_different_domain_differs(self):
        assert build_signature("email", []) != build_signature("task", [])


def _writes(outcome: str) -> float:
    """Current value of one ``recurrence_ledger_writes_total`` series."""
    return float(recurrence_ledger_writes_total.labels(outcome=outcome)._value.get())


def _redis_with(payload: dict | None):
    redis = MagicMock()
    redis.get = AsyncMock(return_value=json.dumps(payload) if payload else None)
    redis.set = AsyncMock()
    return redis


def _patched(redis):
    return patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        AsyncMock(return_value=redis),
    )


@pytest.mark.unit
class TestRecordOccurrence:
    async def test_appends_hour_per_day_and_caps(self):
        payload = {
            "days": {(TODAY - timedelta(days=k)).isoformat(): [9.0] for k in range(40)},
        }
        redis = _redis_with(payload)
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=10.5,
                settings=_settings(),
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert len(stored["days"]) == 28  # capped in DAY entries
        assert stored["days"][TODAY.isoformat()] == [9.0, 10.5]

    async def test_a_second_ask_in_the_same_clock_hour_adds_nothing(self):
        """ADR-375: one hour per clock hour, so a busy morning cannot fill the day."""
        redis = _redis_with({"days": {TODAY.isoformat(): [9.0]}})
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.75,
                settings=_settings(),
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert stored["days"][TODAY.isoformat()] == [9.0]

    async def test_the_intent_is_recorded_as_data_never_as_key(self):
        """Q4 (2026-09-11): the request descriptor travels INSIDE the payload
        so a missed-routine offer has an object; the key stays the domain."""
        redis = _redis_with({"days": {}, "intents": {"search": 1}})
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.5,
                settings=_settings(),
                intent="Search",
            )
        assert redis.set.await_args.args[0].endswith(":email")
        stored = json.loads(redis.set.await_args.args[1])
        assert stored["intents"] == {"search": 2}

    async def test_no_intent_leaves_the_histogram_alone(self):
        redis = _redis_with({"days": {}, "intents": {"send": 3}})
        with _patched(redis):
            await record_occurrence(
                str(uuid4()), "email", local_date=TODAY, local_hour=9.5, settings=_settings()
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert stored["intents"] == {"send": 3}

    async def test_per_day_hours_cap(self):
        payload = {
            "days": {TODAY.isoformat(): [8.0, 8.1, 8.2, 8.3, 8.4]},
        }
        redis = _redis_with(payload)
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.9,
                settings=_settings(),
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert len(stored["days"][TODAY.isoformat()]) == 5  # cap held

    async def test_legacy_ts_payload_converts(self):
        ts = [
            int(datetime(2026, 8, 1, 9, 30, tzinfo=UTC).timestamp()),
            int(datetime(2026, 8, 2, 9, 0, tzinfo=UTC).timestamp()),
        ]
        redis = _redis_with({"ts": ts})
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.0,
                settings=_settings(),
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert "ts" not in stored
        assert "2026-08-01" in stored["days"]
        assert stored["days"]["2026-08-01"] == [9.5]

    async def test_a_landed_write_is_counted_as_written(self):
        """The gate counts ``scheduled`` when it HANDS the write to the
        background; only the write itself can say it landed. The alert reads
        this counter — a broken Redis must not hide behind a green gate."""
        before = _writes("written")
        redis = _redis_with(None)
        with _patched(redis):
            await record_occurrence(
                str(uuid4()), "email", local_date=TODAY, local_hour=9.0, settings=_settings()
            )
        assert _writes("written") == before + 1

    async def test_no_redis_is_counted_not_swallowed(self):
        before = _writes("redis_unavailable")
        with _patched(None):
            await record_occurrence(
                str(uuid4()), "email", local_date=TODAY, local_hour=9.0, settings=_settings()
            )
        assert _writes("redis_unavailable") == before + 1

    async def test_a_failed_write_is_counted_and_logged_at_warning(self, caplog):
        """Advisory never meant invisible: production ships INFO and above, so
        a debug line here was a trace nobody could read (2026-09-11)."""
        import logging

        before = _writes("failed")
        redis = _redis_with(None)
        redis.set = AsyncMock(side_effect=RuntimeError("redis down"))
        with _patched(redis), caplog.at_level(logging.WARNING):
            await record_occurrence(
                str(uuid4()), "email", local_date=TODAY, local_hour=9.0, settings=_settings()
            )
        assert _writes("failed") == before + 1
        assert any("recurrence_record_failed" in r.getMessage() for r in caplog.records)


@pytest.mark.unit
class TestSignatureHasOneProducer:
    def test_domain_only_is_the_default(self):
        """The live gate and the seed write the same key for the same domain:
        the key format has ONE producer (``build_signature``), and the
        domain-only decision is its default, not a ``[]`` repeated at every
        call site."""
        assert build_signature("email") == "email"
        assert build_signature("email") == build_signature("email", [])


@pytest.mark.unit
class TestRecordOccurrenceIfAllowed:
    """The write obeys « Apprendre mes habitudes » (measured violated
    2026-09-11, sim C5): a refusal is counted as the person's own, never as a
    starved ledger, and the store is never touched."""

    @pytest.fixture(autouse=True)
    def _habits_on(self):
        """The habits capability is on: these tests are about the person's gate.

        Unpatched, the capability read reached the real settings store — and,
        a switch nobody wrote being cached as absent, wrote to the very Redis
        double these tests count the ledger's writes on.
        """
        with patch(
            "src.domains.habits.capability.habits_capability_enabled",
            AsyncMock(return_value=True),
        ):
            yield

    async def test_switch_off_writes_nothing_and_counts_user_disabled(self):
        from src.domains.habits.learning_gate import CLOSED

        redis = _redis_with(None)
        before = _writes("user_disabled")
        with (
            _patched(redis),
            patch(
                "src.domains.habits.learning_gate.read_learning_gate",
                AsyncMock(return_value=CLOSED),
            ) as gate,
        ):
            await record_occurrence_if_allowed(
                str(uuid4()), "email", local_date=TODAY, local_hour=9.5, settings=_settings()
            )
        redis.set.assert_not_awaited()
        gate.assert_awaited_once()
        assert _writes("user_disabled") == before + 1

    async def test_switch_on_delegates_to_the_write(self):
        from src.domains.habits.learning_gate import LearningGate

        redis = _redis_with(None)
        before = _writes("written")
        with (
            _patched(redis),
            patch(
                "src.domains.habits.learning_gate.read_learning_gate",
                AsyncMock(return_value=LearningGate(allowed=True)),
            ),
        ):
            await record_occurrence_if_allowed(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.5,
                settings=_settings(),
                intent="send",
            )
        redis.set.assert_awaited_once()
        assert _writes("written") == before + 1
        # The descriptor crosses the gate with the occurrence it describes.
        assert json.loads(redis.set.await_args.args[1])["intents"] == {"send": 1}


@pytest.mark.unit
class TestIntentVocabulary:
    def test_every_intent_has_a_settings_label_in_every_locale(self):
        """Q4: the habit row opens with the usual request through
        ``settings.habits.intent.<intent>`` — one label per vocabulary entry,
        six languages, and no label for a value the analyzer never produces."""
        from src.domains.agents.analysis.query_intelligence import IMMEDIATE_INTENTS
        from src.infrastructure.cache.recurrence_store import INTENT_MAX_DISTINCT
        from tests._repo_paths import repo_root_or_skip

        # The histogram can hold the whole vocabulary: a cap below it would
        # evict a legitimate request the moment the person varies.
        assert INTENT_MAX_DISTINCT >= len(IMMEDIATE_INTENTS)
        locales = repo_root_or_skip() / "apps" / "web" / "locales"
        for lang in ("en", "fr", "de", "es", "it", "zh"):
            path = locales / lang / "translation.json"
            if not path.exists():  # pragma: no cover - the frontend tree is absent
                pytest.skip("apps/web is not checked out beside apps/api")
            labels = json.loads(path.read_text(encoding="utf-8"))["settings"]["habits"]["intent"]
            assert set(labels) == set(IMMEDIATE_INTENTS), lang
