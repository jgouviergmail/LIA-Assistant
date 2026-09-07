"""One verdict, two ways to receive it — and both refuse the same things.

A model call is paid with the deployment's provider key, so it answers to two
bounds: what one account may consume, and what the instance may spend in a day.
Only what a person pays with their OWN connector key is outside them.

How a caller RECEIVES that refusal depends on its transport, not on its own
opinion of the rule:

- a request path raises, and the client gets a 429 saying which bound and,
  for a deployment pause, when it lifts;
- a background path degrades — a reminder still has to fire and a dashboard
  still has a page to render — and says it SKIPPED rather than that it failed.

What must never differ is the verdict itself.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.usage_limits.enforcement import spend_blocked
from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.usage_limits.service import UsageLimitCheckResult

pytestmark = [pytest.mark.unit]


def _allowed() -> UsageLimitCheckResult:
    return UsageLimitCheckResult(
        allowed=True, status=UsageLimitStatus.OK, blocked_reason=None, exceeded_limit=None
    )


def _over_account_limit() -> UsageLimitCheckResult:
    return UsageLimitCheckResult(
        allowed=False,
        status=UsageLimitStatus.BLOCKED_LIMIT,
        blocked_reason="cycle cost exceeded",
        exceeded_limit="cycle_cost",
    )


def _instance_paused() -> UsageLimitCheckResult:
    return UsageLimitCheckResult(
        allowed=False,
        status=UsageLimitStatus.BLOCKED_INSTANCE_BUDGET,
        blocked_reason="instance daily budget exhausted",
        exceeded_limit="instance_daily_budget",
    )


class TestTheNonRaisingShape:
    async def test_an_account_over_its_own_limit_is_blocked(self) -> None:
        with patch(
            "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
            AsyncMock(return_value=_over_account_limit()),
        ):
            assert await spend_blocked(uuid4()) is True

    async def test_an_account_within_its_limit_may_spend(self) -> None:
        with patch(
            "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
            AsyncMock(return_value=_allowed()),
        ):
            assert await spend_blocked(uuid4()) is False

    async def test_a_call_with_no_owner_still_answers_to_the_instance(self) -> None:
        """The platform's key paid for it either way."""
        with patch(
            "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
            AsyncMock(return_value=_instance_paused()),
        ):
            assert await spend_blocked(None) is True

    async def test_an_ownerless_call_passes_when_the_instance_may_spend(self) -> None:
        with patch(
            "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
            AsyncMock(return_value=None),
        ):
            assert await spend_blocked(None) is False

    async def test_the_system_placeholder_is_not_an_account(self) -> None:
        """It resolves to nobody, so the instance ceiling is what applies."""
        with patch(
            "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
            AsyncMock(return_value=None),
        ) as instance:
            assert await spend_blocked("system") is False
        instance.assert_awaited()


class TestTheBackgroundSurfacesActuallySkip:
    """Calling the gate is not enough — the model call must not happen."""

    async def test_the_briefing_writes_no_text_and_calls_no_model(self) -> None:
        from datetime import UTC, datetime
        from types import SimpleNamespace
        from zoneinfo import ZoneInfo

        from src.domains.briefing.llm import generate_synthesis
        from src.domains.briefing.schemas import CardsBundle, CardSection, CardStatus

        def _empty() -> CardSection:
            return CardSection(status=CardStatus.NOT_CONFIGURED, generated_at=datetime.now(UTC))

        bundle = CardsBundle(**{name: _empty() for name in CardsBundle.model_fields})
        user = SimpleNamespace(id=uuid4(), full_name="Jean", email="j@e.c", language="fr")

        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
                AsyncMock(return_value=_over_account_limit()),
            ),
            patch("src.domains.briefing.llm.get_llm") as model,
        ):
            text, usage = await generate_synthesis(
                user=user,  # type: ignore[arg-type]
                user_tz=ZoneInfo("Europe/Paris"),
                cards=bundle,
                language="fr",
            )

        assert (text, usage) == (None, None)
        model.assert_not_called()

    async def test_a_reminder_still_fires_with_its_written_sentence(self) -> None:
        """The quota bounds what LIA may COMPOSE, never whether the person is
        told. A reminder that stopped firing on a quota would lose the very
        instruction they left for themselves."""
        from datetime import UTC, datetime

        from src.infrastructure.scheduler.reminder_notification import (
            generate_reminder_message,
        )

        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
                AsyncMock(return_value=_over_account_limit()),
            ),
            patch("src.infrastructure.llm.get_llm") as model,
        ):
            result = await generate_reminder_message(
                original_message="rappelle-moi d'appeler Ana",
                reminder_content="appeler Ana",
                created_at=datetime.now(UTC),
                user_timezone="Europe/Paris",
                personality=None,
                memories=[],
                language="fr",
                user_id=str(uuid4()),
            )

        assert result.message, "the reminder went out with no text at all"
        model.assert_not_called()

    async def test_an_mcp_server_can_still_be_described_without_a_model(self) -> None:
        """A quota must not stop someone registering a server."""
        from src.domains.user_mcp.description_generation import generate_domain_description

        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
                AsyncMock(return_value=_over_account_limit()),
            ),
            patch("src.infrastructure.llm.get_llm") as model,
        ):
            description = await generate_domain_description(
                tool_list=[{"name": "search_repos", "description": "Search repositories"}],
                server_name="github",
                user_id=uuid4(),
            )

        assert description, "the server was left with no description at all"
        model.assert_not_called()


class TestWhatHappensWhenTheCeilingCannotBeRead:
    """The layer below owns its failure semantics, and they differ ON PURPOSE.

    The per-account check fails OPEN (a database outage must not lock everyone
    out of their assistant). The INSTANCE budget fails CLOSED, with a written
    argument: if the deployment cannot tell whether it is over its daily bound,
    it must not keep spending. ``spend_blocked`` must therefore NOT wrap either
    of them in a rescue of its own — a fail-open swallow here would quietly
    overturn that decision, which is exactly the mistake this test exists to
    make expensive.
    """

    async def test_an_unreadable_instance_budget_blocks_rather_than_crashes(self) -> None:
        from decimal import Decimal

        from src.domains.usage_limits.instance_budget import (
            InstanceBudgetDecision,
            InstanceBudgetService,
        )

        # A configured ceiling, and a ledger the deployment cannot read: the
        # exact state a database outage produces.
        unavailable = InstanceBudgetDecision(
            allowed=False,
            ceiling_eur=Decimal("5"),
            error_code="instance_budget_unavailable",
        )
        with (
            patch(
                "src.domains.system_settings.service.get_instance_daily_budget_eur",
                AsyncMock(return_value=Decimal("5")),
            ),
            patch.object(InstanceBudgetService, "check", AsyncMock(return_value=unavailable)),
            patch(
                "src.infrastructure.database.session.get_db_context",
            ),
        ):
            blocked = await spend_blocked(None)

        assert blocked is True, (
            "an unreadable deployment budget let the call through — the "
            "instance fails CLOSED here, by an argued decision"
        )
