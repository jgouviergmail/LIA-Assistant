"""Recurrence ledger v2 tests (P12 ADR-140, locks ADR-214).

The v2 contract pinned here:
- the signature is the DOMAINS only (the hour is data, not a key);
- storage is per-day, capped in DAY entries (the occurrence cap starved the
  spread lock for multi-daily domains — counter-review finding);
- a suggestion fires ONLY on a shape lock (weekly / workdays / daily) — the
  split-half test keeps sporadic usage at 0% false locks;
- legacy ``{"ts": [...]}`` payloads convert instead of crashing;
- the fired suggestion carries the learned schedule, localized ×6, and
  promotes a persisted habit.
"""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.recurrence_ledger import (
    RECURRENCE_SHAPES,
    SHAPE_INTERMITTENT,
    RecurrenceLock,
    build_signature,
    evaluate_locks,
    evaluate_suggestion,
    record_occurrence,
    record_occurrence_if_allowed,
)
from src.infrastructure.observability.metrics_agents import recurrence_ledger_writes_total

SUPPORTED = ("fr", "en", "es", "de", "it", "zh-CN")
TODAY = date(2026, 8, 4)  # a Tuesday


def _settings(**overrides):
    defaults = {
        "recurrence_suggestion_enabled": True,
        "recurrence_window_days": 28,
        "recurrence_min_distinct_days": 4,
        "recurrence_suggestion_cooldown_days": 30,
        "recurrence_ledger_max_entries": 28,
        "recurrence_day_hours_cap": 5,
        "recurrence_lock_min_occurrences": 8,
        "recurrence_lock_min_spread_days": 10,
        "recurrence_lock_r_min": 0.8,
        "recurrence_lock_half_r_min": 0.7,
        "recurrence_lock_half_agree_hours": 2.0,
        "recurrence_shape_min_span_days": 14,
        "recurrence_daily_density_min": 0.6,
        "recurrence_intermittent_r_min": 0.9,
        "recurrence_weekend_tolerance": 1,
        "recurrence_weekly_min_same_dow": 4,
        "recurrence_weekly_dow_fraction": 0.75,
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


@pytest.mark.unit
class TestEvaluateLocks:
    def test_below_min_distinct_days_is_silent(self):
        days = {TODAY - timedelta(days=k): [9.0] for k in range(3)}
        assert evaluate_locks(days, TODAY, _settings()) is None

    def test_weekly_habit_locks_with_day_and_hour(self):
        # Four Tuesdays around 9h — mathematically invisible to the old
        # 14-day window (never 3 same-weekday days inside it).
        days = {TODAY - timedelta(days=7 * k): [9.0 + 0.2 * k] for k in range(4)}
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "weekly"
        assert lock.modal_weekday == TODAY.weekday()
        assert lock.trigger_hour is not None
        assert abs(lock.trigger_hour - 9.3) < 1.0
        assert lock.days_of_week() == [TODAY.weekday()]

    def test_workdays_habit_locks_after_the_labeling_span(self):
        days = {}
        d = TODAY
        while len(days) < 15:
            if d.weekday() < 5:
                days[d] = [9.0]
            d -= timedelta(days=1)
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "workdays"
        assert lock.days_of_week() == [0, 1, 2, 3, 4]

    def test_daily_habit_locks_as_daily(self):
        days = {TODAY - timedelta(days=k): [21.5] for k in range(16)}
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "daily"
        assert lock.days_of_week() == [0, 1, 2, 3, 4, 5, 6]

    def test_daily_habit_not_labeled_before_the_labeling_span(self):
        # 12 consecutive days = a 12-day span under this suite's 14-day
        # labeling span: time-locked but not yet labeled (early labeling
        # mislabeled daily as workdays — measured).
        days = {TODAY - timedelta(days=k): [9.0] for k in range(12)}
        assert evaluate_locks(days, TODAY, _settings()) is None

    def test_spread_hours_never_lock(self):
        # Daily usage at scattered hours: recurrence EXISTS internally but no
        # user-facing lock — the claim would invent a schedule.
        hours = [8.0, 13.0, 19.0, 10.5, 16.0, 21.0, 9.5, 15.0]
        days = {
            TODAY - timedelta(days=k): [hours[k % len(hours)], hours[(k + 3) % len(hours)]]
            for k in range(16)
        }
        assert evaluate_locks(days, TODAY, _settings()) is None

    def test_multi_daily_domain_reaches_the_spread_lock(self):
        """Counter-review regression: with per-day storage a domain hit 3×/day
        still accumulates the 10-day spread (the 20-occurrence cap used to
        keep only ~7 days)."""
        days = {TODAY - timedelta(days=k): [9.0, 9.2, 9.4] for k in range(16)}
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.occurrences == 48

    def test_occurrences_outside_window_ignored(self):
        old = {TODAY - timedelta(days=40 + k): [9.0] for k in range(20)}
        assert evaluate_locks(old, TODAY, _settings()) is None

    def test_few_times_a_week_locks_as_intermittent(self):
        """The 2026-09-11 correction: a steady hour proven ~3x/week used to be
        UNLABELABLE forever (12 distinct days never reach the 14-distinct-day
        bar in a 28-day window) — and once the bar was lowered it came out
        labeled "daily", a false promise. The calendar HAS spoken (span >= 14)
        and the density (~0.46) says the truth: intermittent."""
        days = {
            TODAY - timedelta(days=k): [9.0 + 0.1 * (k % 3)]
            for k in range(28)
            if k % 7 in (0, 2, 4)
        }
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "intermittent"
        assert lock.trigger_hour is not None
        assert abs(lock.trigger_hour - 9.1) < 1.0
        assert lock.days_of_week() == []  # no calendar is implied

    def test_lucky_arc_concentration_is_refused_the_intermittent_label(self):
        """Waking-arc uniform hours carry R~0.53 intrinsically and clear the
        0.8 gate by luck at light volume (measured: 3 % of sparse controls).
        An hour promised WITHOUT a calendar must be tighter: R in [0.8, 0.9)
        locks nothing on the intermittent path."""
        from src.domains.agents.services.recurrence_ledger import circular_r

        hours = [6.8, 9.0, 11.2]
        days = {TODAY - timedelta(days=2 * k): [hours[k % 3]] for k in range(12)}
        r_all, _mean = circular_r([h for hs in days.values() for h in hs])
        assert 0.8 <= r_all < 0.9  # the premise this test exists for
        assert evaluate_locks(days, TODAY, _settings()) is None

    def test_tight_hour_keeps_the_intermittent_label(self):
        """The twin premise: a genuinely steady hour (R >= 0.9) still locks."""
        from src.domains.agents.services.recurrence_ledger import circular_r

        hours = [8.4, 9.0, 9.6]
        days = {TODAY - timedelta(days=2 * k): [hours[k % 3]] for k in range(12)}
        r_all, _mean = circular_r([h for hs in days.values() for h in hs])
        assert r_all >= 0.9
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "intermittent"

    def test_reliable_workdays_is_not_demoted_to_intermittent(self):
        """Density is measured over the ELIGIBLE span (weekdays only for a
        workdays candidate): a Mon-Fri habit must not read as intermittent
        just because weekends dilute the raw calendar."""
        days = {}
        d = TODAY
        while len(days) < 15:
            if d.weekday() < 5:
                days[d] = [9.0]
            d -= timedelta(days=1)
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "workdays"


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


def _fire_patch():
    """Patch safe_fire_and_forget with a double that OWNS the coroutine.

    A no-op mock of a fire-and-forget boundary is forbidden (CLAUDE.md): the
    double closes the received coroutine explicitly so no unawaited-coroutine
    warning can leak past the test summary.
    """
    return patch(
        "src.infrastructure.async_utils.safe_fire_and_forget",
        side_effect=lambda coro, **_kw: coro.close(),
    )


@pytest.mark.unit
class TestRecordOccurrence:
    async def test_appends_hour_per_day_and_caps(self):
        payload = {
            "days": {(TODAY - timedelta(days=k)).isoformat(): [9.0] for k in range(40)},
            "suggested_at": None,
        }
        redis = _redis_with(payload)
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.5,
                settings=_settings(),
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert len(stored["days"]) == 28  # capped in DAY entries
        assert 9.5 in stored["days"][TODAY.isoformat()]

    async def test_the_intent_is_recorded_as_data_never_as_key(self):
        """Q4 (2026-09-11): the request descriptor travels INSIDE the payload
        so a missed-routine offer has an object; the key stays the domain."""
        redis = _redis_with({"days": {}, "suggested_at": None, "intents": {"search": 1}})
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
        redis = _redis_with({"days": {}, "suggested_at": None, "intents": {"send": 3}})
        with _patched(redis):
            await record_occurrence(
                str(uuid4()), "email", local_date=TODAY, local_hour=9.5, settings=_settings()
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert stored["intents"] == {"send": 3}

    async def test_per_day_hours_cap(self):
        payload = {
            "days": {TODAY.isoformat(): [8.0, 8.1, 8.2, 8.3, 8.4]},
            "suggested_at": None,
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
        redis = _redis_with({"ts": ts, "suggested_at": None})
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


def _weekly_payload() -> dict:
    return {
        "days": {(TODAY - timedelta(days=7 * k)).isoformat(): [9.0] for k in range(4)},
        "suggested_at": None,
    }


@pytest.mark.unit
class TestEvaluateSuggestion:
    async def test_the_promotion_is_handed_the_dominant_intent(self):
        days = {(TODAY - timedelta(days=7 * k)).isoformat(): [9.0] for k in range(4)}
        redis = _redis_with(
            {"days": days, "suggested_at": None, "intents": {"send": 1, "search": 4}}
        )
        with (
            _patched(redis),
            patch(
                "src.domains.agents.services.recurrence_ledger._promote_recurring_habit",
                new=AsyncMock(),
            ) as promote,
            patch(
                "src.infrastructure.async_utils.safe_fire_and_forget",
                side_effect=lambda coro, **_: asyncio.ensure_future(coro),
            ),
        ):
            text = await evaluate_suggestion(
                str(uuid4()), "email", language="en", local_today=TODAY, settings=_settings()
            )
            await asyncio.sleep(0)
        assert text
        assert promote.await_args.kwargs["usual_intent"] == "search"

    async def test_locked_weekly_fires_with_schedule_text(self):
        redis = _redis_with(_weekly_payload())
        with _patched(redis), _fire_patch() as fire:
            text = await evaluate_suggestion(
                str(uuid4()),
                "email",
                language="fr",
                local_today=TODAY,
                settings=_settings(),
            )
        assert text is not None
        assert "09:00" in text  # the learned hour is in the suggestion
        assert "mardi" in text.lower()  # and the learned weekday
        fire.assert_called_once()  # habit promotion scheduled
        stored = json.loads(redis.set.await_args.args[1])
        assert stored["suggested_at"] is not None

    async def test_unlocked_recurrence_stays_silent(self):
        # 5 distinct days at scattered hours: exists internally, no lock →
        # NO user-facing suggestion (0% false suggestions — the v2 point).
        payload = {
            "days": {
                (TODAY - timedelta(days=k)).isoformat(): [float(8 + (k * 5) % 12)] for k in range(6)
            },
            "suggested_at": None,
        }
        redis = _redis_with(payload)
        with _patched(redis):
            text = await evaluate_suggestion(
                str(uuid4()),
                "email",
                language="fr",
                local_today=TODAY,
                settings=_settings(),
            )
        assert text is None

    async def test_cooldown_blocks_second_suggestion(self):
        payload = _weekly_payload()
        payload["suggested_at"] = int((datetime.now(UTC) - timedelta(days=5)).timestamp())
        redis = _redis_with(payload)
        with _patched(redis):
            text = await evaluate_suggestion(
                str(uuid4()),
                "email",
                language="fr",
                local_today=TODAY,
                settings=_settings(),
            )
        assert text is None

    async def test_flag_off_never_fires(self):
        redis = _redis_with(_weekly_payload())
        with _patched(redis):
            text = await evaluate_suggestion(
                str(uuid4()),
                "email",
                language="fr",
                local_today=TODAY,
                settings=_settings(recurrence_suggestion_enabled=False),
            )
        assert text is None

    async def test_localized_in_all_languages(self):
        for lang in SUPPORTED:
            redis = _redis_with(_weekly_payload())
            with _patched(redis), _fire_patch():
                text = await evaluate_suggestion(
                    str(uuid4()),
                    "email",
                    language=lang,
                    local_today=TODAY,
                    settings=_settings(),
                )
            assert text, f"no suggestion text for '{lang}'"
            assert "{" not in text, f"unresolved placeholder for '{lang}': {text}"


@pytest.mark.unit
class TestScheduleText:
    def test_daily_shape_text_carries_time(self):
        from src.core.i18n_automation import get_recurrence_schedule_suggestion_text

        lock = RecurrenceLock(
            shape="daily",
            trigger_hour=7.4,
            modal_weekday=None,
            distinct_days=16,
            occurrences=20,
        )
        text = get_recurrence_schedule_suggestion_text("en", lock)
        assert "07:30" in text
        assert "Every day" in text

    def test_weekly_without_hour_omits_time(self):
        from src.core.i18n_automation import get_recurrence_schedule_suggestion_text

        lock = RecurrenceLock(
            shape="weekly",
            trigger_hour=None,
            modal_weekday=0,
            distinct_days=4,
            occurrences=4,
        )
        text = get_recurrence_schedule_suggestion_text("fr", lock)
        assert "lundi" in text.lower()
        assert ":" not in text.replace("récurrente", "")  # no HH:MM

    def test_intermittent_shape_promises_no_calendar(self):
        from src.core.i18n_automation import get_recurrence_schedule_suggestion_text

        lock = RecurrenceLock(
            shape="intermittent",
            trigger_hour=9.0,
            modal_weekday=None,
            distinct_days=12,
            occurrences=13,
        )
        en = get_recurrence_schedule_suggestion_text("en", lock)
        assert "several times a week" in en.lower()
        assert "09:00" in en
        assert "every day" not in en.lower()
        fr = get_recurrence_schedule_suggestion_text("fr", lock)
        assert "plusieurs fois par semaine" in fr.lower()

    def test_intermittent_localized_in_all_languages(self):
        from src.core.i18n_automation import get_recurrence_schedule_suggestion_text

        lock = RecurrenceLock(
            shape="intermittent",
            trigger_hour=9.0,
            modal_weekday=None,
            distinct_days=12,
            occurrences=13,
        )
        for lang in SUPPORTED:
            text = get_recurrence_schedule_suggestion_text(lang, lock)
            assert text, f"no text for '{lang}'"
            assert "{" not in text, f"unresolved placeholder for '{lang}': {text}"


@pytest.mark.unit
class TestPromotionCap:
    async def test_new_signature_beyond_cap_is_dropped(self, monkeypatch):
        """A declared bound must be enforced: the per-kind cap drops NEW
        signatures with a log while existing ones keep updating."""
        from src.domains.agents.services.recurrence_ledger import (
            _promote_recurring_habit,
        )

        lock = RecurrenceLock(
            shape="weekly",
            trigger_hour=9.0,
            modal_weekday=0,
            distinct_days=4,
            occurrences=4,
        )

        upserts: list[str] = []

        class _Repo:
            def __init__(self, db):
                pass

            async def list_habits(self, uid, kind=None):
                rows = []
                for key in ("a", "b"):
                    row = MagicMock()
                    row.key = key
                    rows.append(row)
                return rows

            async def upsert_habit(self, **kwargs):
                upserts.append(kwargs["key"])
                return "created"

        import src.domains.habits.repository as repo_module
        from src.core.config import settings as app_settings

        monkeypatch.setattr(repo_module, "HabitsRepository", _Repo)
        monkeypatch.setattr(app_settings, "habits_enabled", True, raising=False)
        monkeypatch.setattr(app_settings, "habits_max_habits_per_kind", 2, raising=False)

        user = MagicMock()
        user.habits_enabled = True
        session = MagicMock()
        session.get = AsyncMock(return_value=user)
        session.commit = AsyncMock()

        from contextlib import asynccontextmanager

        import src.infrastructure.database as db_module

        @asynccontextmanager
        async def _ctx():
            yield session

        monkeypatch.setattr(db_module, "get_db_context", _ctx)

        # New signature "c" at cap 2 → dropped.
        await _promote_recurring_habit(str(uuid4()), "c", lock)
        assert upserts == []
        # Existing signature "a" → still updated.
        await _promote_recurring_habit(str(uuid4()), "a", lock)
        assert upserts == ["a"]


@pytest.mark.unit
class TestPromotionCarriesTheUsualIntent:
    async def test_the_row_payload_names_what_the_person_usually_asks(self, monkeypatch):
        """The chat promotion and the nightly sync write ONE payload builder;
        both hand it the ledger's dominant intent (Q4)."""
        from src.domains.agents.services.recurrence_ledger import (
            _promote_recurring_habit,
        )

        lock = RecurrenceLock(
            shape="daily", trigger_hour=8.5, modal_weekday=None, distinct_days=6, occurrences=7
        )
        payloads: list[dict] = []

        class _Repo:
            def __init__(self, db):
                pass

            async def list_habits(self, uid, kind=None):
                return []

            async def upsert_habit(self, **kwargs):
                payloads.append(kwargs["payload"])
                return "created"

        import src.domains.habits.repository as repo_module
        from src.core.config import settings as app_settings

        monkeypatch.setattr(repo_module, "HabitsRepository", _Repo)
        monkeypatch.setattr(app_settings, "habits_enabled", True, raising=False)
        monkeypatch.setattr(app_settings, "habits_max_habits_per_kind", 8, raising=False)
        user = MagicMock()
        user.habits_enabled = True
        session = MagicMock()
        session.get = AsyncMock(return_value=user)
        session.commit = AsyncMock()
        from contextlib import asynccontextmanager

        import src.infrastructure.database as db_module

        @asynccontextmanager
        async def _ctx():
            yield session

        monkeypatch.setattr(db_module, "get_db_context", _ctx)

        await _promote_recurring_habit(str(uuid4()), "email", lock, usual_intent="search")
        await _promote_recurring_habit(str(uuid4()), "email", lock, usual_intent=None)
        assert payloads[0]["usual_intent"] == "search"
        # Unknown stays ABSENT, never a placeholder the panel would translate.
        assert "usual_intent" not in payloads[1]


@pytest.mark.unit
class TestShapeVocabularyIsClosed:
    """Five readers consume the shape (``days_of_week``, the backend
    suggestion text in six languages, the settings row in six locales, the
    heartbeat's missed-slot detector, the explanation). A fifth shape added
    to the producer and forgotten by one reader renders a raw key or a wrong
    calendar — this pins every reader to the ONE tuple."""

    def test_every_shape_has_a_days_of_week_answer(self):
        for shape in RECURRENCE_SHAPES:
            lock = RecurrenceLock(
                shape=shape, trigger_hour=9.0, modal_weekday=0, distinct_days=8, occurrences=9
            )
            days = lock.days_of_week()
            assert all(0 <= d <= 6 for d in days), shape
            if shape == SHAPE_INTERMITTENT:
                assert days == []  # no calendar promised
            else:
                assert days, shape

    def test_every_shape_is_worded_in_every_language(self):
        from src.core.i18n_automation import get_recurrence_schedule_suggestion_text

        for shape in RECURRENCE_SHAPES:
            lock = RecurrenceLock(
                shape=shape, trigger_hour=9.0, modal_weekday=2, distinct_days=8, occurrences=9
            )
            for lang in SUPPORTED:
                text = get_recurrence_schedule_suggestion_text(lang, lock)
                assert text and "{" not in text, (shape, lang, text)

    def test_every_shape_has_a_settings_row_label_in_every_locale(self):
        """The web settings row renders ``settings.habits.shape.<shape>``."""
        from tests._repo_paths import repo_root_or_skip

        locales = repo_root_or_skip() / "apps" / "web" / "locales"
        for lang in ("en", "fr", "de", "es", "it", "zh"):
            path = locales / lang / "translation.json"
            if not path.exists():  # pragma: no cover - the frontend tree is absent
                pytest.skip("apps/web is not checked out beside apps/api")
            labels = json.loads(path.read_text(encoding="utf-8"))["settings"]["habits"]["shape"]
            for shape in RECURRENCE_SHAPES:
                assert shape in labels, f"{lang}: settings.habits.shape.{shape}"

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

    def test_the_heartbeat_handles_every_shape_deliberately(self):
        """The heartbeat offers a missed slot for the calendar shapes and
        deliberately skips ``intermittent`` (no slot to miss). Its literal
        tuple is a contract with this vocabulary — importing the tuple would
        add a heartbeat→agents edge, so the test holds the two together."""
        from src.domains.heartbeat import habit_context

        handled = habit_context.SLOTTED_SHAPES
        assert set(handled) | {SHAPE_INTERMITTENT} == set(RECURRENCE_SHAPES)
        assert SHAPE_INTERMITTENT not in handled


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
