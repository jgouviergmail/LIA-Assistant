"""What a listener already heard, across sessions: a memory in Redis, dated per item.

The antenna never airs a fact twice in a session (its own memory), nor in the
next sessions: every segment adds what it said to three sorted sets, each member
scored with the instant it aired, and each forgotten on its OWN date — a write
renews nobody else's.

- A STORY — its news keys, and its fingerprint across outlets — is remembered as
  long as any news format may still air it: the oldest a shortlist reads
  (``NEWS_MAX_AGE_S``, from publication, and a story airs after it is
  published). The ledger used to live one day, renewed at each write, while a
  column and an analysis read stories two days old: a story heard one evening
  came back the next.
- A fact of the person's DAY is remembered a day (a setting): a task still open
  deserves tomorrow's mention.
- The HEADLINES of the stories heard, in the order they aired, as long as their
  stories: the next session's news writer is shown them, because the same event
  retold from another article escapes every key and fingerprint (measured on dev
  2026-09-27: a mass told in one session came back in the next).
- What each ANGLE programme took (its keys, fingerprints and headlines, filed
  under the programme), as long as the stories: an angle may come back to a story
  heard, never to one the same programme already took (decision 39).

What is filed is what the listener HEARD (ADR-324 decision 35): a produced segment
says, line by line, what each of its lines tells (:class:`HeardLine`), and the
session's loop files a line once the player has passed it. Filed at production,
a session stopped after its opening had filed the programmes produced ahead of it
— measured on dev 2026-09-27, at least four news programmes in ten filed as heard
had never aired.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from src.domains.radio.editorial import NEWS_MAX_AGE_S, Subjects
from src.domains.radio.formats import RadioFormat

#: How a subject an angle took is filed: ``{format}:{kind}:{value}``, one kind per way a
#: story is told again (its key, its fingerprint, its headline).
_ANGLE_KINDS: Final[tuple[str, ...]] = ("k", "s", "h")


@dataclass(frozen=True, slots=True)
class HeardLine:
    """What one voiced line tells the listener — filed once the player has passed it.

    Attributes:
        offset_s: Where the line starts in its segment.
        personal: The keys of the person's facts it says.
        news: The keys of the news facts it says (a story's own and its analyses').
        stories: The fingerprints of the stories it tells.
        headlines: The headlines of the stories it tells first, in the order it tells them.
        angle: The angle programme it belongs to, which files what it tells as taken
            (decision 39); ``None`` for a programme that renews its stories.
    """

    offset_s: float
    personal: frozenset[str] = frozenset()
    news: frozenset[str] = frozenset()
    stories: frozenset[str] = frozenset()
    headlines: tuple[str, ...] = ()
    angle: RadioFormat | None = None


def _angle_members(line: HeardLine) -> list[str]:
    """What an angle programme's line files as taken, by the three ways a story comes back."""
    if line.angle is None:
        return []
    fmt = line.angle.value
    return [
        *(f"{fmt}:k:{key}" for key in sorted(line.news)),
        *(f"{fmt}:s:{story}" for story in sorted(line.stories)),
        *(f"{fmt}:h:{headline}" for headline in line.headlines),
    ]


def _taken(members: Iterable[str]) -> dict[RadioFormat, Subjects]:
    """The subjects each angle took, a member this release cannot read left out."""
    found: dict[RadioFormat, tuple[set[str], set[str], list[str]]] = {}
    for member in members:
        name, kind, value = (member.split(":", 2) + ["", ""])[:3]
        try:
            fmt = RadioFormat(name)
        except ValueError:
            continue
        if kind not in _ANGLE_KINDS or not value:
            continue
        keys, stories, headlines = found.setdefault(fmt, (set(), set(), []))
        if kind == "k":
            keys.add(value)
        elif kind == "s":
            stories.add(value)
        elif value not in headlines:
            headlines.append(value)
    return {
        fmt: Subjects(keys=frozenset(keys), stories=frozenset(stories), headlines=tuple(heads))
        for fmt, (keys, stories, heads) in found.items()
    }


def _texts(members: Iterable[Any]) -> frozenset[str]:
    return frozenset(
        member.decode() if isinstance(member, bytes) else str(member) for member in members
    )


class RedisAiredLedger:
    """The aired ledger of one account (ADR-260 family ``radio``, per-user runtime)."""

    def __init__(
        self,
        redis: Any,
        *,
        user_id: UUID,
        personal_ttl_s: int,
        clock: Callable[[], datetime],
    ) -> None:
        """Bind the ledger.

        Args:
            redis: The cache client.
            user_id: The listener.
            personal_ttl_s: How long a fact of the person's day is remembered.
            clock: The current instant (timezone-aware).
        """
        self._redis = redis
        self._clock = clock
        # No name of the first ledger (never shipped: plain sets under ``keys`` and
        # ``stories``): a sorted-set call on one of its keys answers WRONGTYPE, and
        # the whole ledger read as unavailable (measured on dev 2026-09-27).
        self._personal = f"radio:aired:{user_id}:personal"
        self._news = f"radio:aired:{user_id}:news"
        self._stories = f"radio:aired:{user_id}:fingerprints"
        self._headlines = f"radio:aired:{user_id}:headlines"
        self._angles = f"radio:aired:{user_id}:angles"
        self._horizons: dict[str, int] = {
            self._personal: personal_ttl_s,
            self._news: NEWS_MAX_AGE_S,
            self._stories: NEWS_MAX_AGE_S,
            self._headlines: NEWS_MAX_AGE_S,
            self._angles: NEWS_MAX_AGE_S,
        }

    async def _recent(self, name: str, now: float) -> frozenset[str]:
        return _texts(await self._redis.zrangebyscore(name, now - self._horizons[name], "+inf"))

    async def heard(self) -> tuple[frozenset[str], frozenset[str]]:
        """The fact keys and the story fingerprints still remembered."""
        now = self._clock().timestamp()
        personal = await self._recent(self._personal, now)
        news = await self._recent(self._news, now)
        return personal | news, await self._recent(self._stories, now)

    async def headlines(self) -> tuple[str, ...]:
        """The headlines of the stories still remembered, oldest first."""
        now = self._clock().timestamp()
        members = await self._redis.zrangebyscore(
            self._headlines, now - self._horizons[self._headlines], "+inf"
        )
        return tuple(
            member.decode() if isinstance(member, bytes) else str(member) for member in members
        )

    async def treated(self) -> dict[RadioFormat, Subjects]:
        """What each angle programme took, still remembered (decision 39)."""
        return _taken(await self._recent(self._angles, self._clock().timestamp()))

    async def record(
        self,
        *,
        personal: frozenset[str],
        news: frozenset[str],
        stories: frozenset[str],
        headlines: Sequence[str] = (),
        angles: Sequence[str] = (),
    ) -> None:
        """Add what a segment aired, dated now; forget what passed its horizon.

        Args:
            personal: The keys of the person's facts it said.
            news: The keys of the news facts it said (the stories' own and
                their analyses').
            stories: The fingerprints of the stories it told.
            headlines: The headlines of the stories it told, in the order it told them.
            angles: What angle programmes took, filed under each (``_angle_members``).
        """
        now = self._clock().timestamp()
        members: dict[str, dict[str, float]] = {
            self._personal: dict.fromkeys(sorted(personal), now),
            self._news: dict.fromkeys(sorted(news), now),
            self._stories: dict.fromkeys(sorted(stories), now),
            # A millisecond apart, so a segment's headlines read back in air order.
            self._headlines: {title: now + rank / 1000 for rank, title in enumerate(headlines)},
            self._angles: dict.fromkeys(angles, now),
        }
        if not any(members.values()):
            return
        async with self._redis.pipeline(transaction=False) as pipe:
            for name, scored in members.items():
                if not scored:
                    continue
                horizon = self._horizons[name]
                pipe.zadd(name, scored)
                pipe.zremrangebyscore(name, "-inf", now - horizon)
                pipe.expire(name, horizon)
            await pipe.execute()

    async def forget(self) -> None:
        """Forget everything the listener heard: every story, every fact of their day,
        every headline may air again (« forget what I heard », ADR-324 decision 38)."""
        await self._redis.delete(*self._horizons)

    async def remember(self, lines: Sequence[HeardLine]) -> None:
        """File the lines the listener just heard, in one write, in the order they aired.

        Args:
            lines: The lines heard since the last write.
        """
        await self.record(
            personal=frozenset().union(*(line.personal for line in lines)),
            news=frozenset().union(*(line.news for line in lines)),
            stories=frozenset().union(*(line.stories for line in lines)),
            headlines=list(dict.fromkeys(title for line in lines for title in line.headlines)),
            angles=list(dict.fromkeys(member for line in lines for member in _angle_members(line))),
        )


__all__ = ["HeardLine", "RedisAiredLedger"]
