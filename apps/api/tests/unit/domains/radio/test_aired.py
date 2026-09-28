"""What a listener already heard: a story as long as it can air, a fact of their day a day."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.domains.radio.aired import HeardLine, RedisAiredLedger
from src.domains.radio.editorial import NEWS_MAX_AGE_S, Subjects
from src.domains.radio.formats import RadioFormat
from tests.unit.domains.radio.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = UUID("00000000-0000-4000-8000-0000000000aa")
T0 = datetime(2026, 9, 26, 21, 0, tzinfo=UTC)
DAY_S = 86_400


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def ledger(redis: FakeRedis, clock: Clock) -> RedisAiredLedger:
    return RedisAiredLedger(redis, user_id=USER, personal_ttl_s=DAY_S, clock=clock)


async def test_a_story_is_remembered_as_long_as_a_shortlist_may_still_offer_it() -> None:
    """A column reads stories two days old: forgotten after a day, one came back
    the next evening (the ledger used to live a day, renewed at each write)."""
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).record(
        personal=frozenset(), news=frozenset({"story-key"}), stories=frozenset({"rain"})
    )
    clock.now = T0 + timedelta(seconds=DAY_S + 3600)
    keys, stories = await ledger(redis, clock).heard()
    assert "story-key" in keys and "rain" in stories
    clock.now = T0 + timedelta(seconds=NEWS_MAX_AGE_S + 1)
    keys, stories = await ledger(redis, clock).heard()
    assert "story-key" not in keys and "rain" not in stories


async def test_the_headlines_heard_are_kept_in_air_order_as_long_as_their_stories() -> None:
    """The next session's writer is shown what the listener heard before: the same event
    retold from ANOTHER article escapes every key and fingerprint (measured on dev
    2026-09-27, a mass told in one session came back in the next)."""
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).record(
        personal=frozenset(),
        news=frozenset({"k1"}),
        stories=frozenset(),
        headlines=("Rain over the capital", "A vote in the north"),
    )
    clock.now = T0 + timedelta(minutes=5)
    await ledger(redis, clock).record(
        personal=frozenset(), news=frozenset({"k2"}), stories=frozenset(), headlines=("A bridge",)
    )
    assert await ledger(redis, clock).headlines() == (
        "Rain over the capital",
        "A vote in the north",
        "A bridge",
    )
    clock.now = T0 + timedelta(seconds=NEWS_MAX_AGE_S + 1)
    assert await ledger(redis, clock).headlines() == ("A bridge",)
    assert redis.ttls[f"radio:aired:{USER}:headlines"] == NEWS_MAX_AGE_S


async def test_nothing_heard_yet_has_no_headline() -> None:
    assert await ledger(FakeRedis(), Clock()).headlines() == ()


async def test_a_fact_of_the_day_is_remembered_a_day() -> None:
    """An open task heard yesterday deserves today's mention."""
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).record(
        personal=frozenset({"task:7"}), news=frozenset(), stories=frozenset()
    )
    clock.now = T0 + timedelta(seconds=DAY_S - 1)
    assert "task:7" in (await ledger(redis, clock).heard())[0]
    clock.now = T0 + timedelta(seconds=DAY_S + 1)
    assert "task:7" not in (await ledger(redis, clock).heard())[0]


async def test_each_story_leaves_on_its_own_date() -> None:
    """A listener who comes back every day no longer keeps every story for ever:
    a write renews nobody else's date."""
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).record(
        personal=frozenset(), news=frozenset({"old"}), stories=frozenset({"old-story"})
    )
    clock.now = T0 + timedelta(seconds=NEWS_MAX_AGE_S - 60)
    await ledger(redis, clock).record(
        personal=frozenset(), news=frozenset({"new"}), stories=frozenset({"new-story"})
    )
    clock.now = T0 + timedelta(seconds=NEWS_MAX_AGE_S + 60)
    keys, stories = await ledger(redis, clock).heard()
    assert keys == frozenset({"new"}) and stories == frozenset({"new-story"})
    # What left is hidden from the reading at once, and gone from the store at the
    # next write — the set never grows with what it no longer remembers.
    await ledger(redis, clock).record(
        personal=frozenset(), news=frozenset({"newest"}), stories=frozenset()
    )
    assert set(redis.zsets[f"radio:aired:{USER}:news"]) == {"new", "newest"}


async def test_the_store_lives_as_long_as_what_it_holds() -> None:
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).record(
        personal=frozenset({"event:1"}), news=frozenset({"n"}), stories=frozenset({"s"})
    )
    assert redis.ttls[f"radio:aired:{USER}:personal"] == DAY_S
    assert redis.ttls[f"radio:aired:{USER}:news"] == NEWS_MAX_AGE_S
    assert redis.ttls[f"radio:aired:{USER}:fingerprints"] == NEWS_MAX_AGE_S


async def test_a_key_left_by_the_first_ledger_is_never_read() -> None:
    """The first ledger — never shipped — kept plain sets under ``keys`` and
    ``stories``, and dev instances still hold them for two days. A sorted-set call
    on one of those names answers WRONGTYPE, and the whole ledger read as
    unavailable: no story marked heard, every one eligible again (measured on dev
    2026-09-27). The ledger's names share none of the first one's."""
    redis, clock = FakeRedis(), Clock()
    redis.sets[f"radio:aired:{USER}:keys"] = {"old-key"}
    redis.sets[f"radio:aired:{USER}:stories"] = {"old-story"}
    await ledger(redis, clock).record(
        personal=frozenset({"event:1"}), news=frozenset({"n"}), stories=frozenset({"s"})
    )
    assert await ledger(redis, clock).heard() == (frozenset({"event:1", "n"}), frozenset({"s"}))


async def test_nothing_heard_writes_nothing() -> None:
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).record(personal=frozenset(), news=frozenset(), stories=frozenset())
    assert redis.ops["zadd"] == 0 and redis.zsets == {}
    assert await ledger(redis, clock).heard() == (frozenset(), frozenset())


async def test_the_lines_heard_are_filed_in_one_write_their_headlines_in_air_order() -> None:
    """The loop files what the listener heard since its last report (ADR-324 decision 35)."""
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).remember(
        [
            HeardLine(
                offset_s=1.0,
                news=frozenset({"k1"}),
                stories=frozenset({"rain"}),
                headlines=("Rain over the capital",),
            ),
            HeardLine(offset_s=6.0, personal=frozenset({"event:dentist"})),
            HeardLine(
                offset_s=9.0,
                news=frozenset({"k2", "k2#a1"}),
                stories=frozenset({"vote"}),
                headlines=("A vote in the north", "Rain over the capital"),
            ),
        ]
    )
    keys, stories = await ledger(redis, clock).heard()
    assert keys == {"k1", "k2", "k2#a1", "event:dentist"} and stories == {"rain", "vote"}
    assert await ledger(redis, clock).headlines() == (
        "Rain over the capital",
        "A vote in the north",
    )


async def test_no_line_heard_files_nothing() -> None:
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).remember([])
    assert redis.ops["zadd"] == 0 and redis.zsets == {}


async def test_forgetting_what_was_heard_empties_the_whole_ledger() -> None:
    """« Forget what I heard » (ADR-324 decision 38): every story may air again."""
    redis, clock = FakeRedis(), Clock()
    await ledger(redis, clock).record(
        personal=frozenset({"day-key"}),
        news=frozenset({"story-key"}),
        stories=frozenset({"rain"}),
        headlines=("Rain over the capital",),
    )
    await ledger(redis, clock).forget()
    assert await ledger(redis, clock).heard() == (frozenset(), frozenset())
    assert await ledger(redis, clock).headlines() == ()
    assert await ledger(redis, clock).treated() == {}


class TestWhatEachAngleTook:
    """ADR-324 decision 39: an angle programme never takes a subject it already took — as
    long as the story may air, across sessions."""

    async def test_what_an_angle_told_is_remembered_for_that_programme_alone(self) -> None:
        redis, clock = FakeRedis(), Clock()
        await ledger(redis, clock).remember(
            [
                HeardLine(
                    offset_s=1.0,
                    news=frozenset({"k1", "k1#a1"}),
                    stories=frozenset({"rain"}),
                    headlines=("Rain: a city under water",),
                    angle=RadioFormat.DEBATE,
                ),
                HeardLine(offset_s=2.0, news=frozenset({"k2"}), stories=frozenset({"vote"})),
            ]
        )
        assert await ledger(redis, clock).treated() == {
            RadioFormat.DEBATE: Subjects(
                keys=frozenset({"k1", "k1#a1"}),
                stories=frozenset({"rain"}),
                headlines=("Rain: a city under water",),
            )
        }
        keys, _ = await ledger(redis, clock).heard()
        assert {"k1", "k2"} <= keys  # heard all the same

    async def test_it_is_forgotten_with_its_story(self) -> None:
        redis, clock = FakeRedis(), Clock()
        await ledger(redis, clock).remember(
            [HeardLine(offset_s=1.0, news=frozenset({"k1"}), angle=RadioFormat.COLUMN)]
        )
        clock.now = T0 + timedelta(seconds=NEWS_MAX_AGE_S + 1)
        assert await ledger(redis, clock).treated() == {}

    async def test_a_member_this_release_cannot_read_is_left_out(self) -> None:
        redis, clock = FakeRedis(), Clock()
        await ledger(redis, clock).remember(
            [HeardLine(offset_s=1.0, news=frozenset({"k1"}), angle=RadioFormat.COLUMN)]
        )
        name = f"radio:aired:{USER}:angles"
        await redis.zadd(
            name, {"retired_format:k:k9": T0.timestamp(), "column:x:k8": T0.timestamp()}
        )
        assert await ledger(redis, clock).treated() == {
            RadioFormat.COLUMN: Subjects(keys=frozenset({"k1"}))
        }
