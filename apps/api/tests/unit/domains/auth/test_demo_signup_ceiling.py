"""How many strangers may this demonstrator enrol in one day?

Measured 2026-08-07 against the running instance: thirty accounts created in
6,4 seconds, zero refusals, thirty-three verification emails attempted. The
per-address limiter (five registrations a minute) had not fired once, because
the identity it keys on comes from ``CF-Connecting-IP`` and that request came
in without traversing Cloudflare.

Even with the limiter intact, five a minute is three hundred verification
emails an hour from a single address. What pays for those is the operator's
smarthost quota and their domain's sending reputation — and the daily SPEND
ceiling is blind to them, because mail is not a cost family.

So the bound that actually holds is one the caller cannot rotate: a ceiling
on how many accounts this INSTANCE creates per UTC day, counted from the
accounts themselves. Same doctrine as the spend ceiling (ADR-216): the
authority is the database, an unknown count denies, and the ceiling resets on
the UTC day boundary so "come back tomorrow" is computable rather than a
guess.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestRegistrationRefusesOverTheCeiling:
    async def test_a_demonstrator_over_its_ceiling_refuses_to_register(self) -> None:
        from src.domains.auth import service as auth_service
        from src.domains.auth.demo_signup_ceiling import DemoSignupDecision

        demo = MagicMock()
        demo.demo_mode_enabled = True
        demo.demo_daily_signup_limit = 10
        demo.demo_terms_version = "2026-08-06"

        refused = DemoSignupDecision(
            allowed=False, created_today=10, limit=10, retry_after_seconds=3600
        )

        svc = auth_service.AuthService(MagicMock())
        payload = MagicMock()
        payload.terms_accepted = True
        payload.email = "visitor@example.com"

        with (
            patch.object(auth_service, "settings", demo),
            patch.object(auth_service, "reserve_demo_signup", AsyncMock(return_value=refused)),
            pytest.raises(Exception) as raised,
        ):
            await svc.register(payload)

        assert "demo_signup_limit_reached" in str(raised.value)

    async def test_a_private_instance_never_counts_anything(self) -> None:
        """The check is a demonstrator behaviour, not a product behaviour."""
        from src.domains.auth import service as auth_service

        private = MagicMock()
        private.demo_mode_enabled = False

        checker = AsyncMock()
        svc = auth_service.AuthService(MagicMock())
        svc.repository = MagicMock()
        svc.repository.get_by_email = AsyncMock(return_value=MagicMock())

        payload = MagicMock()
        payload.terms_accepted = False
        payload.email = "owner@example.com"

        with (
            patch.object(auth_service, "settings", private),
            patch.object(auth_service, "reserve_demo_signup", checker),
            pytest.raises(Exception),
        ):
            await svc.register(payload)

        checker.assert_not_awaited()


class TestTheSettingIsDeclaredAndBounded:
    def test_the_default_is_a_real_ceiling_not_infinity(self) -> None:
        from src.core.config.demo import DemoSettings

        field = DemoSettings.model_fields["demo_daily_signup_limit"]

        assert field.default is not None, (
            "a demonstrator ships with a mail bound by default; an operator "
            "who wants none removes it deliberately"
        )

    def test_the_default_lives_in_constants(self) -> None:
        from src.core.config.demo import DemoSettings
        from src.core.constants import DEMO_DAILY_SIGNUP_LIMIT_DEFAULT

        assert (
            DemoSettings.model_fields["demo_daily_signup_limit"].default
            == DEMO_DAILY_SIGNUP_LIMIT_DEFAULT
        )


class TestTheDayBoundaryIsTheOneTheLedgerUses:
    def test_it_reuses_the_spend_ceiling_helper(self) -> None:
        """Two definitions of "tomorrow" would drift the day one moves."""
        from src.domains.auth import demo_signup_ceiling

        assert demo_signup_ceiling.seconds_until_next_utc_day is not None

        seconds = demo_signup_ceiling.seconds_until_next_utc_day(
            datetime(2026, 8, 7, 23, 59, 30, tzinfo=UTC)
        )
        assert seconds == 30


class TestTheReservationIsAtomicNotCheckThenAct:
    """A ceiling read before the write is a ceiling a burst walks through.

    Measured 2026-08-07 against the running instance: ceiling of 5, forty
    registrations released together by a thread barrier — **37 accounts
    created**, three refused. Every request read ``COUNT(*)`` before any of
    them committed, so every request passed. The bound overshot 7,6x, and the
    thing it bounds is the verification mail billed to the operator.

    Sequential probing had hidden it: password hashing is deliberately slow,
    so `curl` loops serialise themselves and the window never opens.

    The fix is the codebase's own doctrine for concurrent counters (CLAUDE.md):
    a server-side atomic UPSERT with column arithmetic, never SELECT then
    INSERT. The reservation is CONDITIONAL — ``ON CONFLICT DO UPDATE ...
    WHERE count < limit`` — so a refused attempt does not consume a slot, and
    Postgres's row lock on the conflicting row serialises the decision.
    """

    def test_the_statement_reserves_and_bounds_in_one_round_trip(self) -> None:
        from src.domains.auth import demo_signup_ceiling as module

        source = (
            pathlib.Path(module.__file__).read_text(encoding="utf-8")
            if hasattr(module, "__file__")
            else ""
        )
        assert "on_conflict_do_update" in source, (
            "the reservation must be a single atomic statement; a SELECT "
            "followed by an INSERT lets a simultaneous burst through"
        )
        assert (
            "func.count()" not in source
        ), "counting rows is the check-then-act shape this replaced"

    async def test_a_refused_attempt_does_not_consume_a_slot(self) -> None:
        """Otherwise a burst of refusals burns the day for honest visitors."""
        from src.domains.auth.demo_signup_ceiling import reserve_demo_signup

        session = MagicMock()
        # No row returned = the conditional UPDATE did not fire = refused.
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

        decision = await reserve_demo_signup(session, limit=5)

        assert decision.allowed is False
        assert decision.created_today is None

    async def test_a_granted_reservation_reports_its_rank(self) -> None:
        from src.domains.auth.demo_signup_ceiling import reserve_demo_signup

        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: 3))

        decision = await reserve_demo_signup(session, limit=5)

        assert decision.allowed is True
        assert decision.created_today == 3

    async def test_an_absent_limit_reserves_nothing(self) -> None:
        from src.domains.auth.demo_signup_ceiling import reserve_demo_signup

        session = MagicMock()
        session.execute = AsyncMock()

        decision = await reserve_demo_signup(session, limit=None)

        assert decision.allowed is True
        session.execute.assert_not_awaited()

    async def test_an_unreadable_ledger_refuses(self) -> None:
        from src.domains.auth.demo_signup_ceiling import reserve_demo_signup

        session = MagicMock()
        session.execute = AsyncMock(side_effect=RuntimeError("database unreachable"))

        decision = await reserve_demo_signup(session, limit=5)

        assert decision.allowed is False
