"""One door to a fresh OAuth token: one exchange per token, never a false revocation (AC-029).

Two refreshes of one token in flight are a hazard: a provider that rotates its refresh
token answers the second one ``invalid_grant``, and that refusal used to disconnect a
person whose consent was intact. The door is proven here against a holder whose store is
in memory — its rules, not one store's SQL (the stores are proven on PostgreSQL).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.connectors import oauth_refresh
from src.domains.connectors.oauth_refresh import (
    Refreshed,
    StoredToken,
    ensure_fresh_credentials,
)
from src.domains.connectors.oauth_refresh_exchange import RefreshRefusal, RefreshRefused
from src.infrastructure.utils import shared_flight
from tests.helpers.redis_double import InMemoryRedis

pytestmark = pytest.mark.unit


class Inactive(LookupError):
    """The holder is gone or no longer active."""


class Revoked(PermissionError):
    """The person's consent is gone."""


class Failed(TimeoutError):
    """The provider could not refresh, for now."""


class _DriverError(Exception):
    """What the driver raises: its SQLSTATE is the only fact the door may read."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _database_error(sqlstate: str) -> DBAPIError:
    """A statement refused by the server with ``sqlstate``, as SQLAlchemy wraps it."""
    return DBAPIError("UPDATE connectors", None, _DriverError(sqlstate))


#: The server's verdict when a row stayed held past ``lock_timeout``.
_LOCK_NOT_AVAILABLE = "55P03"


@dataclass
class _Sessions:
    """The short sessions the door opened, and what each one executed."""

    opened: int = 0
    statements: dict[int, list[str]] = field(default_factory=dict)


@dataclass
class _Store:
    """One token holder's row: ``old`` needs a refresh, anything else is fresh."""

    ciphertext: str = "c-old"
    credentials: str = "old"
    active: bool = True
    writes: int = 0


@dataclass
class _Target:
    """A holder whose store is in memory and whose provider a test scripts."""

    store: _Store
    answers: list[str | RefreshRefusal] = field(default_factory=lambda: ["fresh"])
    exchanges: int = 0
    gate: asyncio.Event | None = None
    during_exchange: Callable[[], None] | None = None
    write_gate: asyncio.Event | None = None
    owner: UUID = field(default_factory=uuid4)
    #: A failure the exchange raises that is no provider refusal (a client that changed).
    exchange_error: BaseException | None = None
    write_error: BaseException | None = None
    revoke_error: BaseException | None = None
    sessions: _Sessions | None = None
    #: What each transition's session had executed when the transition ran.
    executed_before_transition: list[list[str]] = field(default_factory=list)
    #: This caller's own link to the token (a service of a shared grant): its admission.
    link_active: bool = True
    read_gate: asyncio.Event | None = None
    read_started: asyncio.Event = field(default_factory=asyncio.Event)
    reads: int = 0

    @property
    def kind(self) -> str:
        return "connector"

    @property
    def flight_key(self) -> str:
        return f"connector:{id(self.store)}"

    @property
    def user_id(self) -> UUID:
        return self.owner

    async def read(self, db: AsyncSession) -> StoredToken[str] | None:
        self.reads += 1
        self.read_started.set()
        if self.read_gate is not None:
            await self.read_gate.wait()
        servable = self.store.active and self.link_active
        return StoredToken(self.store.ciphertext, self.store.credentials, servable)

    def needs_refresh(self, credentials: str, refresh_before: datetime | None) -> bool:
        return credentials == "old"

    async def exchange(self, credentials: str) -> Refreshed[str]:
        self.exchanges += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.during_exchange is not None:
            self.during_exchange()
        if self.exchange_error is not None:
            raise self.exchange_error
        answer = self.answers[min(self.exchanges, len(self.answers)) - 1]
        if isinstance(answer, RefreshRefusal):
            raise RefreshRefused(answer, status_code=400)
        return Refreshed(answer, frozenset())

    def _transition_starts(self, db: AsyncSession) -> None:
        if self.sessions is not None:
            self.executed_before_transition.append(list(self.sessions.statements[id(db)]))

    async def write_if_unchanged(
        self, db: AsyncSession, expected_ciphertext: str, refreshed: Refreshed[str]
    ) -> bool:
        self._transition_starts(db)
        if self.write_gate is not None:
            await self.write_gate.wait()
        if self.write_error is not None:
            raise self.write_error
        if self.store.ciphertext != expected_ciphertext or not self.store.active:
            return False
        self.store.writes += 1
        self.store.ciphertext = f"c-{refreshed.credentials}"
        self.store.credentials = refreshed.credentials
        return True

    async def revoke_if_unchanged(self, db: AsyncSession, expected_ciphertext: str) -> bool:
        self._transition_starts(db)
        if self.revoke_error is not None:
            raise self.revoke_error
        if self.store.ciphertext != expected_ciphertext:
            return False
        self.store.active = False
        return True

    def inactive_error(self) -> Exception:
        return Inactive("inactive")

    def revoked_error(self, status_code: int | None) -> Exception:
        return Revoked(f"revoked ({status_code})")

    def failed_error(self) -> Exception:
        return Failed("failed")


#: A deadlock fails the test in seconds, never at the suite's watchdog.
_BOUND_SECONDS = 5


@pytest.fixture
def sessions() -> _Sessions:
    return _Sessions()


@pytest.fixture
def redis(monkeypatch: pytest.MonkeyPatch, sessions: _Sessions) -> InMemoryRedis:
    """One Redis shared by every simulated worker; no database session is real."""
    cache = InMemoryRedis()

    async def shared() -> InMemoryRedis:
        if cache.broken:
            raise ConnectionError("redis unavailable")
        return cache

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        sessions.opened += 1
        db = AsyncMock(spec=AsyncSession)
        executed: list[str] = []
        sessions.statements[id(db)] = executed

        async def execute(statement: object, *_args: object, **_kwargs: object) -> None:
            executed.append(str(statement))

        db.execute = AsyncMock(side_effect=execute)
        yield db

    monkeypatch.setattr(oauth_refresh, "get_redis_cache", shared)
    monkeypatch.setattr(shared_flight, "get_redis_cache", shared)
    monkeypatch.setattr(oauth_refresh, "get_db_context", session)
    return cache


def _granted(verdict: oauth_refresh._Granted[str] | oauth_refresh._Refused) -> str:
    """The credentials a verdict carries; a refusal here fails the test."""
    assert isinstance(verdict, oauth_refresh._Granted), verdict
    credentials: str = verdict.credentials
    return credentials


def _rotate_elsewhere(store: _Store, credentials: str) -> Callable[[], None]:
    """Another worker stores its own refresh while this exchange is in flight."""

    def rotate() -> None:
        store.ciphertext = f"c-{credentials}"
        store.credentials = credentials

    return rotate


class TestTheFastPath:
    async def test_a_fresh_token_the_caller_holds_costs_nothing(
        self, redis: InMemoryRedis, sessions: _Sessions
    ) -> None:
        """Not an exchange, not a read, not a claim: every tool call takes this path."""
        target = _Target(_Store(ciphertext="c-ok", credentials="ok"))

        served = await ensure_fresh_credentials(target, current=StoredToken("c-ok", "ok", True))

        assert served == "ok"
        assert (target.exchanges, sessions.opened, redis.store) == (0, 0, {})

    async def test_an_expiring_token_is_refreshed_and_stored(self, redis: InMemoryRedis) -> None:
        target = _Target(_Store())

        served = await ensure_fresh_credentials(target)

        assert served == "fresh"
        assert (target.store.credentials, target.store.writes) == ("fresh", 1)

    async def test_an_inactive_holder_is_never_refreshed(self, redis: InMemoryRedis) -> None:
        target = _Target(_Store(active=False))

        with pytest.raises(Inactive):
            await ensure_fresh_credentials(target)

        assert target.exchanges == 0


class TestOneExchangePerToken:
    async def test_five_callers_of_one_worker_share_one_exchange(
        self, redis: InMemoryRedis
    ) -> None:
        gate = asyncio.Event()
        target = _Target(_Store(), gate=gate)
        callers = [asyncio.create_task(ensure_fresh_credentials(target)) for _ in range(5)]
        await asyncio.sleep(0)
        gate.set()

        served = await asyncio.wait_for(asyncio.gather(*callers), _BOUND_SECONDS)

        assert served == ["fresh"] * 5
        assert target.exchanges == 1

    async def test_two_workers_share_one_exchange_through_the_claim(
        self, redis: InMemoryRedis
    ) -> None:
        """Two workers do not share a flight registry: only the claim can join them."""
        gate = asyncio.Event()
        target = _Target(_Store(), gate=gate)
        start = StoredToken("c-old", "old", True)
        workers = [
            asyncio.create_task(
                oauth_refresh._coalesced(target, start, force=False, refresh_before=None)
            )
            for _ in range(2)
        ]
        await asyncio.sleep(0.05)
        gate.set()

        verdicts = await asyncio.wait_for(asyncio.gather(*workers), _BOUND_SECONDS)

        assert [_granted(verdict) for verdict in verdicts] == ["fresh", "fresh"]
        assert target.exchanges == 1

    @pytest.mark.parametrize("force", [False, True], ids=["unforced", "forced"])
    async def test_a_worker_that_read_before_a_rotation_does_not_exchange_again(
        self, redis: InMemoryRedis, force: bool
    ) -> None:
        """It claims after the first worker released: only its re-read can tell."""
        target = _Target(_Store())
        assert await ensure_fresh_credentials(target) == "fresh"

        verdict = await oauth_refresh._attempt(
            target, StoredToken("c-old", "old", True), force=force, refresh_before=None
        )

        assert verdict == oauth_refresh._Granted("fresh")
        assert target.exchanges == 1

    async def test_a_forced_refresh_joins_a_refresh_in_flight(self, redis: InMemoryRedis) -> None:
        gate = asyncio.Event()
        target = _Target(_Store(), gate=gate)
        unforced = asyncio.create_task(ensure_fresh_credentials(target))
        forced = asyncio.create_task(ensure_fresh_credentials(target, force=True))
        await asyncio.sleep(0)
        gate.set()

        both = await asyncio.wait_for(asyncio.gather(unforced, forced), _BOUND_SECONDS)
        assert list(both) == ["fresh", "fresh"]
        assert target.exchanges == 1

    async def test_a_forced_refresh_of_a_fresh_token_exchanges(self, redis: InMemoryRedis) -> None:
        target = _Target(_Store(ciphertext="c-ok", credentials="ok"), answers=["fresh"])

        assert await ensure_fresh_credentials(target, force=True) == "fresh"
        assert target.exchanges == 1


class TestTheWriteIsConditional:
    async def test_a_token_rotated_during_the_exchange_wins(self, redis: InMemoryRedis) -> None:
        store = _Store()
        target = _Target(store, during_exchange=_rotate_elsewhere(store, "theirs"))

        served = await ensure_fresh_credentials(target)

        assert served == "theirs"
        assert (store.credentials, store.writes) == ("theirs", 0)

    async def test_a_holder_revoked_during_the_exchange_stays_revoked(
        self, redis: InMemoryRedis
    ) -> None:
        store = _Store()

        def revoke() -> None:
            store.active = False

        target = _Target(store, during_exchange=revoke)

        with pytest.raises(Inactive):
            await ensure_fresh_credentials(target)

        assert (store.active, store.writes) == (False, 0)

    async def test_the_write_survives_the_caller_s_cancellation(self, redis: InMemoryRedis) -> None:
        """A rotated token lost between the provider and the store disconnects the person."""
        gate = asyncio.Event()
        target = _Target(_Store(), write_gate=gate)
        caller = asyncio.create_task(ensure_fresh_credentials(target))
        async with asyncio.timeout(_BOUND_SECONDS):
            while target.exchanges == 0:
                await asyncio.sleep(0)
        caller.cancel()
        # The caller is released at once, while the write still waits behind its gate:
        # the write goes on in the flight's own task. Observed without cancelling.
        released, _ = await asyncio.wait({caller}, timeout=_BOUND_SECONDS)
        gate.set()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(caller, _BOUND_SECONDS)
        for _ in range(50):
            if target.store.writes:
                break
            await asyncio.sleep(0)

        assert caller in released
        assert caller.cancelled()
        assert (target.store.credentials, target.store.writes) == ("fresh", 1)


class TestARevocationIsVerified:
    async def test_a_refusal_of_the_stored_token_disconnects(self, redis: InMemoryRedis) -> None:
        target = _Target(_Store(), answers=[RefreshRefusal.REVOKED])

        with pytest.raises(Revoked, match="400"):
            await ensure_fresh_credentials(target)

        assert target.store.active is False

    async def test_a_refusal_of_a_token_rotated_meanwhile_is_no_revocation(
        self, redis: InMemoryRedis
    ) -> None:
        """The second exchange of a rotating provider answers invalid_grant: not a revocation."""
        store = _Store()
        target = _Target(
            store,
            answers=[RefreshRefusal.REVOKED],
            during_exchange=_rotate_elsewhere(store, "theirs"),
        )

        assert await ensure_fresh_credentials(target) == "theirs"
        assert store.active is True

    async def test_an_outage_is_a_failure_that_keeps_the_holder(self, redis: InMemoryRedis) -> None:
        target = _Target(_Store(), answers=[RefreshRefusal.TRANSIENT])

        with pytest.raises(Failed):
            await ensure_fresh_credentials(target)

        assert (target.store.active, target.store.credentials) == (True, "old")


class TestWaitersLearnTheVerdict:
    async def test_a_waiter_learns_a_revocation_without_its_own_exchange(
        self, redis: InMemoryRedis
    ) -> None:
        gate = asyncio.Event()
        target = _Target(_Store(), answers=[RefreshRefusal.REVOKED], gate=gate)
        start = StoredToken("c-old", "old", True)
        workers = [
            asyncio.create_task(
                oauth_refresh._coalesced(target, start, force=False, refresh_before=None)
            )
            for _ in range(2)
        ]
        await asyncio.sleep(0.05)
        gate.set()

        verdicts = await asyncio.wait_for(asyncio.gather(*workers), _BOUND_SECONDS)

        assert target.exchanges == 1
        for verdict in verdicts:
            assert isinstance(verdict, oauth_refresh._Refused)
            with pytest.raises(Revoked):
                raise verdict.error()

    async def test_a_waiter_learns_an_unexpected_failure_without_sitting_out_the_claim(
        self, redis: InMemoryRedis
    ) -> None:
        """No verdict published, a waiter of another worker waited the whole claim first.

        The claim outlives the worst exchange (about 40 s at the defaults), far past this
        test's bound: the holder's own failure must reach the waiter, as a failure.
        """
        gate = asyncio.Event()
        target = _Target(_Store(), gate=gate, exchange_error=ValueError("client changed"))
        start = StoredToken("c-old", "old", True)
        workers = [
            asyncio.create_task(
                oauth_refresh._coalesced(target, start, force=False, refresh_before=None)
            )
            for _ in range(2)
        ]
        await asyncio.sleep(0.05)
        gate.set()

        outcomes = await asyncio.wait_for(
            asyncio.gather(*workers, return_exceptions=True), _BOUND_SECONDS
        )

        assert target.exchanges == 1
        assert [type(outcome) for outcome in outcomes].count(ValueError) == 1
        refused = [outcome for outcome in outcomes if isinstance(outcome, oauth_refresh._Refused)]
        assert len(refused) == 1
        with pytest.raises(Failed):
            raise refused[0].error()

    async def test_a_verdict_older_than_the_wait_is_not_this_wait_s(
        self, redis: InMemoryRedis
    ) -> None:
        target = _Target(_Store())
        await redis.set(oauth_refresh._marker_key(target), "earlier:revoked")

        assert await oauth_refresh._published(target, "earlier:revoked") is None

    async def test_without_redis_the_conditional_write_still_keeps_one_token(
        self, redis: InMemoryRedis
    ) -> None:
        """No claim can be taken: both workers exchange, the second write loses."""
        redis.broken = True
        store = _Store()
        gate = asyncio.Event()
        target = _Target(store, answers=["first", "second"], gate=gate)
        start = StoredToken("c-old", "old", True)
        workers = [
            asyncio.create_task(
                oauth_refresh._coalesced(target, start, force=False, refresh_before=None)
            )
            for _ in range(2)
        ]
        await asyncio.sleep(0)
        gate.set()

        verdicts = await asyncio.wait_for(asyncio.gather(*workers), _BOUND_SECONDS)

        assert target.exchanges == 2
        assert store.writes == 1
        assert {_granted(verdict) for verdict in verdicts} == {store.credentials}


class TestAnAdmissionIsTheCallersOwn:
    """One token, several holders: the services of a shared grant share its refresh, but
    whether a caller may be served is its OWN link's question. A service detached from the
    grant while a refresh runs is refused for itself — never for the others (AC-029)."""

    async def test_a_caller_joining_a_detached_service_s_flight_is_still_served(
        self, redis: InMemoryRedis
    ) -> None:
        store = _Store()
        gate = asyncio.Event()
        detached = _Target(store, link_active=False, read_gate=gate)
        linked = _Target(store)
        start = StoredToken("c-old", "old", True)
        leaving = asyncio.create_task(ensure_fresh_credentials(detached, current=start))
        await asyncio.wait_for(detached.read_started.wait(), _BOUND_SECONDS)
        staying = asyncio.create_task(ensure_fresh_credentials(linked, current=start))
        await asyncio.sleep(0.05)
        gate.set()

        left, served = await asyncio.wait_for(
            asyncio.gather(leaving, staying, return_exceptions=True), _BOUND_SECONDS
        )

        assert isinstance(left, Inactive)
        assert served == "fresh"
        assert (detached.exchanges, linked.exchanges, store.writes) == (0, 1, 1)

    async def test_a_waiter_told_another_holder_left_asks_for_itself(
        self, redis: InMemoryRedis
    ) -> None:
        """Another worker's verdict on ITS holder is no verdict on this one."""
        store = _Store()
        gate = asyncio.Event()
        detached = _Target(store, link_active=False, read_gate=gate)
        linked = _Target(store)
        start = StoredToken("c-old", "old", True)
        other_worker = asyncio.create_task(
            oauth_refresh._coalesced(detached, start, force=False, refresh_before=None)
        )
        await asyncio.wait_for(detached.read_started.wait(), _BOUND_SECONDS)
        this_worker = asyncio.create_task(ensure_fresh_credentials(linked, current=start))
        await asyncio.sleep(0.05)
        gate.set()

        verdict = await asyncio.wait_for(other_worker, _BOUND_SECONDS)
        served = await asyncio.wait_for(this_worker, _BOUND_SECONDS)

        assert isinstance(verdict, oauth_refresh._Refused)
        assert served == "fresh"
        assert linked.exchanges == 1

    async def test_a_caller_detached_too_reads_its_own_link_once(
        self, redis: InMemoryRedis
    ) -> None:
        store = _Store()
        gate = asyncio.Event()
        first = _Target(store, link_active=False, read_gate=gate)
        also_detached = _Target(store, link_active=False)
        start = StoredToken("c-old", "old", True)
        leaving = asyncio.create_task(ensure_fresh_credentials(first, current=start))
        await asyncio.wait_for(first.read_started.wait(), _BOUND_SECONDS)
        joining = asyncio.create_task(ensure_fresh_credentials(also_detached, current=start))
        await asyncio.sleep(0.05)
        gate.set()

        results = await asyncio.wait_for(
            asyncio.gather(leaving, joining, return_exceptions=True), _BOUND_SECONDS
        )

        assert all(isinstance(result, Inactive) for result in results)
        assert also_detached.reads == 1

    async def test_two_refusals_of_other_holders_are_reported_as_a_failure(
        self, redis: InMemoryRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Never « reconnect » for a link this caller still holds, and never a loop."""
        target = _Target(_Store())
        flights = 0

        async def another_holder_s_refusal(
            *_args: object, **_kwargs: object
        ) -> oauth_refresh._Refused:
            nonlocal flights
            flights += 1
            return oauth_refresh._Refused(Inactive, oauth_refresh.RefreshOutcome.INACTIVE.value)

        monkeypatch.setattr(oauth_refresh, "_flown", another_holder_s_refusal)

        with pytest.raises(Failed):
            await ensure_fresh_credentials(target, current=StoredToken("c-old", "old", True))

        assert flights == 2

    async def test_a_holder_that_left_is_refused_for_itself(self, redis: InMemoryRedis) -> None:
        """The caller whose own link is gone is told so — never served the token."""
        target = _Target(_Store(), link_active=False)

        with pytest.raises(Inactive):
            await ensure_fresh_credentials(target, current=StoredToken("c-old", "old", True))

        assert (target.exchanges, target.reads) == (0, 1)


class TestAHeldRowNeverHangsTheDoor:
    """The door writes on its OWN session: a caller whose open transaction holds the row
    waits on the door, which would wait on that lock — a cycle neither PostgreSQL nor
    the caller can see. Every transition is bounded, and its refusal is never a guess."""

    async def test_every_transition_bounds_its_lock_wait_first(
        self, redis: InMemoryRedis, sessions: _Sessions
    ) -> None:
        bound = f"SET LOCAL lock_timeout = {settings.oauth_refresh_write_lock_timeout_ms}"
        written = _Target(_Store(), sessions=sessions)
        revoked = _Target(_Store(), answers=[RefreshRefusal.REVOKED], sessions=sessions)

        await ensure_fresh_credentials(written)
        with pytest.raises(Revoked):
            await ensure_fresh_credentials(revoked)

        assert written.executed_before_transition == [[bound]]
        assert revoked.executed_before_transition == [[bound]]

    async def test_a_write_that_cannot_take_its_row_serves_the_exchange_unstored(
        self, redis: InMemoryRedis
    ) -> None:
        """The person's request goes on with the token the provider just issued."""
        target = _Target(_Store(), write_error=_database_error(_LOCK_NOT_AVAILABLE))

        served = await asyncio.wait_for(ensure_fresh_credentials(target), _BOUND_SECONDS)

        assert served == "fresh"
        assert (target.store.credentials, target.store.writes) == ("old", 0)

    async def test_a_waiter_is_never_served_the_token_a_contended_write_left_stored(
        self, redis: InMemoryRedis
    ) -> None:
        """The stored token is the expired one: served, its 401 would disconnect."""
        gate = asyncio.Event()
        target = _Target(_Store(), gate=gate, write_error=_database_error(_LOCK_NOT_AVAILABLE))
        start = StoredToken("c-old", "old", True)
        workers = [
            asyncio.create_task(
                oauth_refresh._coalesced(target, start, force=False, refresh_before=None)
            )
            for _ in range(2)
        ]
        await asyncio.sleep(0.05)
        gate.set()

        verdicts = await asyncio.wait_for(asyncio.gather(*workers), _BOUND_SECONDS)

        assert target.exchanges == 1
        granted = [v for v in verdicts if isinstance(v, oauth_refresh._Granted)]
        refused = [v for v in verdicts if isinstance(v, oauth_refresh._Refused)]
        assert [verdict.credentials for verdict in granted] == ["fresh"]
        assert len(refused) == 1
        with pytest.raises(Failed):
            raise refused[0].error()

    async def test_a_contended_revocation_is_a_failure_never_a_disconnection(
        self, redis: InMemoryRedis
    ) -> None:
        """Unverified, an ``invalid_grant`` may concern a token the holder is replacing."""
        target = _Target(
            _Store(),
            answers=[RefreshRefusal.REVOKED],
            revoke_error=_database_error(_LOCK_NOT_AVAILABLE),
        )

        with pytest.raises(Failed):
            await asyncio.wait_for(ensure_fresh_credentials(target), _BOUND_SECONDS)

        assert (target.store.active, target.store.credentials) == (True, "old")

    @pytest.mark.parametrize("transition", ["write", "revocation"])
    async def test_any_other_database_failure_still_surfaces(
        self, redis: InMemoryRedis, transition: str
    ) -> None:
        """Only a lock wait past its bound is contention: nothing else is swallowed."""
        broken = _database_error("23505")
        target = (
            _Target(_Store(), write_error=broken)
            if transition == "write"
            else _Target(_Store(), answers=[RefreshRefusal.REVOKED], revoke_error=broken)
        )

        with pytest.raises(DBAPIError):
            await asyncio.wait_for(ensure_fresh_credentials(target), _BOUND_SECONDS)


def _highest_allowed_write_bound_ms() -> int:
    """The largest bound an operator may configure: the field's own ``le``."""
    field_info = type(settings).model_fields["oauth_refresh_write_lock_timeout_ms"]
    return max(int(le) for item in field_info.metadata if (le := getattr(item, "le", None)))


def test_the_claim_outlives_the_worst_exchange_and_its_bounded_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A claim that expires during the write lets a second worker exchange the same token."""
    from src.domains.connectors.oauth_refresh_exchange import worst_case_refresh_seconds

    highest = _highest_allowed_write_bound_ms()
    monkeypatch.setattr(settings, "oauth_refresh_write_lock_timeout_ms", highest)

    assert oauth_refresh.claim_ttl_seconds() > worst_case_refresh_seconds() + highest / 1000
