"""A faithful stand-in for one Today-dashboard page load.

Why this exists as a harness rather than as per-test mocks: every question
asked of the briefing's concurrency ("how many times was the mailbox opened
for one page load?") needs the SAME four things — a Redis that honours TTL,
fetchers that count their calls, connector latency, and two requests issued
the way the browser issues them. Written per test, those four drifted twice
while this fix was being measured, and both drifts produced a GREEN test over
broken behaviour:

- fetchers with no latency let ``/cards`` fill the cache before ``/synthesis``
  reads it, so the race the harness exists to observe never happened;
- a counter read AFTER its own ``await`` is observed at its final value by
  both concurrent fetches, hiding a divergence the test was written to catch.

So latency is not optional here, and every counter is snapshotted before the
first suspension point.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from src.domains.briefing.exceptions import ConnectorNotConfiguredError
from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    BirthdaysData,
    CardsBundle,
    DocumentItem,
    DocumentsData,
    ForYouData,
    HealthData,
    HealthSummaryItem,
    MailItem,
    MailsData,
    ReminderItem,
    RemindersData,
    TaskItem,
    TasksData,
    WeatherData,
)
from src.domains.briefing.service import BriefingService
from src.domains.connectors.birthdays import BirthdayItem

#: Every section the service builds, in the order it gathers them.
SECTION_NAMES: tuple[str, ...] = (
    "weather",
    "agenda",
    "mails",
    "birthdays",
    "reminders",
    "health",
    "for_you",
    "tasks",
    "documents",
)

#: What a real connector costs. Far below a real round trip, far above zero:
#: the point is only that a fetch cannot complete within the same event-loop
#: step as the request that started it.
CONNECTOR_LATENCY_SECONDS = 0.05


class Clock:
    """A virtual clock, so a test can skip a TTL without sleeping."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def advance(self, seconds: float) -> None:
        """Move the clock forward.

        Args:
            seconds: How far to jump.
        """
        self.now += seconds


class FakeRedis:
    """The two methods the briefing cache uses, with real expiry semantics."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._store: dict[str, tuple[str, float]] = {}
        self.ops: Counter[str] = Counter()

    async def get(self, key: str) -> str | None:
        """Read a key, honouring its expiry against the virtual clock.

        Args:
            key: The cache key.

        Returns:
            The stored payload, or None when absent or expired.
        """
        self.ops["get"] += 1
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self._clock.now >= expires_at:
            del self._store[key]
            return None
        return value

    async def set(
        self, key: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        """Write a key with an expiry, honouring SET NX.

        ``nx`` is not decoration: the cross-worker build claim is taken with
        it, and a double that ignored it would let every test take the claim
        and hide the very sharing the seam exists for.

        Args:
            key: The cache key.
            value: The serialized payload.
            ex: Time to live in seconds; None means effectively forever.
            nx: Only set when the key is absent.

        Returns:
            True when written, None when NX refused.
        """
        self.ops["set"] += 1
        if nx and (await self.get(key)) is not None:
            return None
        self._store[key] = (value, self._clock.now + (ex if ex else 10**9))
        return True

    async def eval(self, script: str, numkeys: int, *args: str) -> int:
        """Compare-and-delete, as the claim's release uses it."""
        self.ops["eval"] += 1
        key, token = args[0], args[1]
        entry = self._store.get(key)
        if entry is not None and entry[0] == token:
            del self._store[key]
            return 1
        return 0

    def keys(self) -> list[str]:
        """Every live key, for assertions about what was cached."""
        return [k for k, (_, exp) in self._store.items() if self._clock.now < exp]

    def drop(self, suffix: str) -> None:
        """Forget every key ending with ``suffix`` (a single section).

        Args:
            suffix: The section name the key ends with.
        """
        for key in [k for k in self._store if k.endswith(f":{suffix}")]:
            del self._store[key]


def make_user(
    *,
    language: str = "fr",
    timezone: str = "Europe/Paris",
    hidden: tuple[str, ...] = (),
    user_id: UUID | None = None,
) -> SimpleNamespace:
    """Build the User stand-in the service reads.

    Args:
        language: The account language.
        timezone: The account display timezone.
        hidden: Sections the person has hidden from their grid.
        user_id: Reuse an id across services, as two requests of one page load do.

    Returns:
        A namespace carrying exactly the attributes ``BriefingService`` reads.
    """
    return SimpleNamespace(
        id=user_id or uuid4(),
        full_name="Jean",
        email="jean@example.com",
        language=language,
        timezone=timezone,
        health_metrics_agents_enabled=True,
        briefing_preferences=({"hidden": list(hidden), "order": []} if hidden else None),
    )


def full_payloads() -> dict[str, Any]:
    """One populated payload per section — a dashboard where everything answers."""
    return {
        "weather": WeatherData(
            temperature_c=18.0,
            condition_code="Clear",
            description="Ensoleille",
            icon_emoji="S",
            location_city="Paris",
            forecast_alert=None,
        ),
        "agenda": AgendaData(
            events=[AgendaEventItem(title="Revue", start_local="14:00", location=None)]
        ),
        "mails": MailsData(
            items=[MailItem(sender_email="a@b.c", subject="Sujet", received_local="09:00")],
            total_unread_today=1,
        ),
        "birthdays": BirthdaysData(
            items=[BirthdayItem(contact_name="Ana", date_iso="--09-12", days_until=3)]
        ),
        "reminders": RemindersData(
            items=[ReminderItem(content="Appeler Ana", trigger_at_local="18:00")]
        ),
        "health": HealthData(
            items=[
                HealthSummaryItem(
                    kind="steps",
                    value_today=8000.0,
                    value_avg_window=7000.0,
                    unit="steps",
                    window_days=14,
                    days_with_data=10,
                )
            ]
        ),
        "for_you": ForYouData(open_loops=[], recent_automations=[]),
        "tasks": TasksData(items=[TaskItem(title="Tache", overdue=False)], overdue_count=0),
        "documents": DocumentsData(items=[DocumentItem(name="Note", modified_local="10:00")]),
    }


@dataclass
class Rig:
    """The instrumented world one page load runs in."""

    clock: Clock = field(default_factory=Clock)
    payloads: dict[str, Any] = field(default_factory=full_payloads)
    failures: dict[str, Exception] = field(default_factory=dict)
    latency_s: float = CONNECTOR_LATENCY_SECONDS
    calls: Counter[str] = field(default_factory=Counter)
    #: The bundle each ``generate_synthesis`` call was handed, newest last.
    summarised: list[CardsBundle] = field(default_factory=list)
    redis: FakeRedis = field(init=False)

    def __post_init__(self) -> None:
        self.redis = FakeRedis(self.clock)

    @property
    def builds(self) -> int:
        """How many times the bundle was gathered.

        ``reminders`` is fetched live on every gather, so its call count IS
        the number of builds — unlike a cacheable section, which a rebuild
        may serve from cache and thus under-report.
        """
        return self.calls["reminders"]

    def _fetcher(self, name: str) -> AsyncMock:
        async def _fetch(*_args: object, **_kwargs: object) -> Any:
            self.calls[name] += 1
            await asyncio.sleep(self.latency_s)
            failure = self.failures.get(name)
            if failure is not None:
                raise failure
            return self.payloads[name]

        return AsyncMock(side_effect=_fetch)

    @contextmanager
    def installed(self) -> Iterator[Rig]:
        """Patch the service's collaborators for the duration of the block."""

        async def _synthesis(*, cards: CardsBundle, **_kwargs: object) -> tuple[str, None]:
            self.summarised.append(cards)
            return ("Belle journee.", None)

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.domains.briefing.service.get_redis_cache",
                    AsyncMock(return_value=self.redis),
                )
            )
            for name in SECTION_NAMES:
                stack.enter_context(
                    patch(f"src.domains.briefing.service.fetch_{name}", self._fetcher(name))
                )
            stack.enter_context(
                patch(
                    "src.domains.briefing.service.generate_greeting",
                    AsyncMock(return_value=("Bonjour.", None)),
                )
            )
            stack.enter_context(
                patch(
                    "src.domains.briefing.service.generate_synthesis",
                    AsyncMock(side_effect=_synthesis),
                )
            )
            # The effect register is NOT under test here, and left live it
            # reaches for a real database: these tests would then depend on
            # ambient schema state and pay a round trip per section to log a
            # failure. What the register does with a coalesced build has its
            # own oracle, in ``test_briefing_consultations.py``.
            stack.enter_context(
                patch(
                    "src.domains.briefing.service.record_surface_consultations",
                    lambda **_kwargs: None,
                )
            )
            stack.enter_context(
                patch(
                    "src.domains.briefing.service.BriefingService._record_cards_turn",
                    AsyncMock(return_value=None),
                )
            )
            yield self

    async def page_load(self, user: SimpleNamespace) -> tuple[CardsBundle, Any]:
        """Issue the two requests the dashboard issues, the way it issues them.

        Args:
            user: The account loading its dashboard.

        Returns:
            The ``/cards`` bundle and the ``/synthesis`` response.
        """
        return await asyncio.gather(
            BriefingService(user).build_cards(),
            BriefingService(user).build_text(),
        )

    def reset_calls(self) -> None:
        """Forget the fetch counters, keeping the cache as it is."""
        self.calls.clear()


def not_configured() -> ConnectorNotConfiguredError:
    """The exception a disconnected connector raises."""
    return ConnectorNotConfiguredError("google")
