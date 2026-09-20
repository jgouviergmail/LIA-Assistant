"""Unit tests for TrackingContext persistence semantics (ADR-117, ADR-272).

Records present at exit correspond to calls that actually happened (and were
billed by the provider). They must be persisted whatever the exit path:
normal, exception, or task cancellation. Before ADR-117 Lot 1, an interrupted
run silently dropped its pending records (billing leak).

And EVERY billable family counts as « pending », not only the model's. Both
persistence doors used to decide on ``len(_node_records)`` alone (``commit()``
had learnt TTS one incident later, ``__aexit__`` never did), so a tracker
holding only Google Maps Platform records — a phone-call or live-session
lookup on Places or Routes, which makes no model call of its own — wrote
nothing: no usage log, no summary row, no user statistics, no instance
ledger. Measured 2026-09-19: 0,029 € of Places held in memory, 0 persisted,
by both doors.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.chat.service import TrackingContext
from src.domains.chat.tracking_records import (
    GoogleApiRecord,
    ImageGenerationRecord,
    TTSUsageRecord,
)


def _make_tracker(auto_commit: bool = True) -> TrackingContext:
    tracker = TrackingContext(
        run_id="run_test",
        user_id=uuid.uuid4(),
        session_id="session_test",
        conversation_id=uuid.uuid4(),
        auto_commit=auto_commit,
    )
    # One pending record so __aexit__ has something to persist
    # (__aexit__ only checks len(); the record content is never touched
    # because _persist_to_database is mocked).
    tracker._node_records.append(MagicMock())
    tracker._persist_to_database = AsyncMock()  # type: ignore[method-assign]
    return tracker


@pytest.mark.unit
class TestTrackingContextExitPersistence:
    async def test_persists_on_normal_exit(self):
        tracker = _make_tracker()
        await tracker.__aexit__(None, None, None)
        tracker._persist_to_database.assert_awaited_once()

    async def test_persists_on_exception(self):
        tracker = _make_tracker()
        await tracker.__aexit__(RuntimeError, RuntimeError("boom"), None)
        tracker._persist_to_database.assert_awaited_once()

    async def test_persists_on_cancellation(self):
        tracker = _make_tracker()
        await tracker.__aexit__(asyncio.CancelledError, asyncio.CancelledError(), None)
        tracker._persist_to_database.assert_awaited_once()

    async def test_skips_when_auto_commit_disabled(self):
        tracker = _make_tracker(auto_commit=False)
        await tracker.__aexit__(None, None, None)
        tracker._persist_to_database.assert_not_awaited()

    async def test_persistence_failure_is_swallowed(self):
        # Tracking failure must never break the chat path (existing contract,
        # must hold on the new on-exception branch too).
        tracker = _make_tracker()
        tracker._persist_to_database = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("db down")
        )
        await tracker.__aexit__(RuntimeError, RuntimeError("boom"), None)
        tracker._persist_to_database.assert_awaited_once()


def _bare_tracker() -> TrackingContext:
    tracker = TrackingContext(
        run_id="phone_call_test",
        user_id=uuid.uuid4(),
        session_id="phone_call_test",
        conversation_id=None,
    )
    tracker._persist_to_database = AsyncMock()  # type: ignore[method-assign]
    return tracker


def _google(cached: bool = False) -> GoogleApiRecord:
    return GoogleApiRecord(
        api_name="places",
        endpoint="/places:searchText",
        cost_usd=Decimal("0") if cached else Decimal("0.032"),
        cost_eur=Decimal("0") if cached else Decimal("0.029"),
        usd_to_eur_rate=Decimal("0.91"),
        cached=cached,
    )


def _image() -> ImageGenerationRecord:
    return ImageGenerationRecord(
        model="gpt-image-1",
        quality="medium",
        size="1024x1024",
        image_count=1,
        cost_usd=Decimal("0.04"),
        cost_eur=Decimal("0.036"),
        usd_to_eur_rate=Decimal("0.91"),
        prompt_preview="a lighthouse",
    )


def _tts() -> TTSUsageRecord:
    return TTSUsageRecord(
        provider="openai",
        model="tts-1",
        characters=120,
        cost_usd=Decimal("0.0018"),
        cost_eur=Decimal("0.0016"),
        usd_to_eur_rate=Decimal("0.91"),
    )


_NON_LLM_FAMILIES = [
    ("_google_api_records", _google()),
    ("_image_generation_records", _image()),
    ("_tts_records", _tts()),
]
_NON_LLM_IDS = ["google-only", "image-only", "tts-only"]


@pytest.mark.unit
class TestEveryBillableFamilyIsPending:
    """A tracker holding ANY billed record persists, through either door."""

    @pytest.mark.parametrize(("bucket", "record"), _NON_LLM_FAMILIES, ids=_NON_LLM_IDS)
    async def test_aexit_persists_a_non_llm_family_alone(self, bucket: str, record: object) -> None:
        tracker = _bare_tracker()
        getattr(tracker, bucket).append(record)
        await tracker.__aexit__(None, None, None)
        tracker._persist_to_database.assert_awaited_once()

    @pytest.mark.parametrize(("bucket", "record"), _NON_LLM_FAMILIES, ids=_NON_LLM_IDS)
    async def test_commit_persists_a_non_llm_family_alone(
        self, bucket: str, record: object
    ) -> None:
        tracker = _bare_tracker()
        getattr(tracker, bucket).append(record)
        await tracker.commit()
        tracker._persist_to_database.assert_awaited_once()

    async def test_a_cached_google_call_alone_is_not_a_spend(self) -> None:
        """A cache hit costs nothing and counts no request: nothing to file."""
        tracker = _bare_tracker()
        tracker._google_api_records.append(_google(cached=True))
        await tracker.__aexit__(None, None, None)
        await tracker.commit()
        tracker._persist_to_database.assert_not_awaited()

    async def test_an_empty_tracker_persists_nothing(self) -> None:
        tracker = _bare_tracker()
        await tracker.__aexit__(None, None, None)
        await tracker.commit()
        tracker._persist_to_database.assert_not_awaited()

    async def test_a_committed_message_count_is_not_pending_twice(self) -> None:
        """The message count is filed once; a later exit must not re-persist it."""
        tracker = _bare_tracker()
        await tracker.increment_message_count()
        assert tracker.pending_families()["message"] == 1
        tracker._message_count_committed = True
        assert tracker.pending_families()["message"] == 0

    def test_pending_families_names_every_family(self) -> None:
        tracker = _bare_tracker()
        tracker._google_api_records.append(_google())
        tracker._google_api_records.append(_google(cached=True))
        tracker._image_generation_records.append(_image())
        assert tracker.pending_families() == {
            "llm": 0,
            "google_api": 1,
            "image_generation": 1,
            "tts": 0,
            "message": 0,
        }


@pytest.mark.unit
class TestThePredicateCoversEveryBucketByConstruction:
    """The list of record buckets IS the guard.

    ``commit()`` had learnt TTS one incident after ``__aexit__`` was written and
    Google API never — each family found one at a time. So every list the
    constructor creates under ``self._<family>_records`` must be READ by the
    one predicate, and both doors must read the predicate rather than a
    bucket.
    """

    @staticmethod
    def _buckets_created_by_init() -> set[str]:
        """Every ``self._<family>_records: list[...] = []`` the constructor creates.

        A bucket is an annotated LIST; ``_total_committed_records`` is a
        counter and ``_committed_*`` copies serve the debug panel.
        """
        tree = ast.parse(textwrap.dedent(inspect.getsource(TrackingContext.__init__)))
        return {
            node.target.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr.endswith("_records")
            and not node.target.attr.startswith("_committed")
            and isinstance(node.annotation, ast.Subscript)
            and getattr(node.annotation.value, "id", None) == "list"
        }

    @staticmethod
    def _attributes_read_by(function: object) -> set[str]:
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))  # type: ignore[arg-type]
        return {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
        }

    def test_every_record_bucket_is_read_by_the_predicate(self) -> None:
        buckets = self._buckets_created_by_init()
        assert buckets >= {
            "_node_records",
            "_google_api_records",
            "_image_generation_records",
            "_tts_records",
        }
        unread = buckets - self._attributes_read_by(TrackingContext.pending_families)
        assert not unread, f"record buckets the persistence predicate never reads: {unread}"

    @pytest.mark.parametrize(
        "door", [TrackingContext.__aexit__, TrackingContext.commit], ids=["aexit", "commit"]
    )
    def test_each_door_reads_the_predicate_and_no_bucket(self, door: object) -> None:
        read = self._attributes_read_by(door)
        assert "pending_families" in read
        assert not (
            read & self._buckets_created_by_init()
        ), "a persistence door reads a record bucket directly instead of the predicate"
