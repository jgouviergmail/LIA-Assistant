"""The registers as figures, against real rows (ADR-263).

Every property here is one this programme already lives by, applied to a chart:
counts are exact aggregates and never page lengths (ADR-185), axes are bounded
before a free-text value can reach a reader, the scope is a parameter of the
query, and the period filters five differently-named timestamp columns the same
way.

Only PostgreSQL can prove them: they are about what ``GROUP BY`` returns, and a
mock would assert that the code calls SQLAlchemy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.decision_repository import DecisionRepository
from src.domains.agents.effects.decisions import TurnDecision
from src.domains.agents.effects.models import (
    AgentTreatment,
    DecisionOutcome,
    EffectSource,
    TreatmentOutcome,
)
from src.domains.agents.effects.statistics import TOP_N, register_statistics
from src.domains.chat.models import TokenUsageLog
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_START = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """The account the figures describe."""
    row = User(
        email=f"stats-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Statistics Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


@pytest.fixture
async def other(async_session: AsyncSession) -> User:
    """A second account, so scoping can be proven rather than assumed."""
    row = User(
        email=f"stats-b-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Other Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _call(
    user: User, *, node: str, model: str = "gpt-5-mini", at: datetime = _START
) -> TokenUsageLog:
    return TokenUsageLog(
        user_id=user.id,
        run_id="run-1",
        node_name=node,
        model_name=model,
        prompt_tokens=10,
        completion_tokens=5,
        cached_tokens=0,
        created_at=at,
    )


def _consultation(user: User, *, tool: str, ms: int = 10, at: datetime = _START) -> AgentTreatment:
    return AgentTreatment(
        user_id=user.id,
        thread_id="thread-A",
        run_id="run-1",
        source=EffectSource.USER,
        execution_mode="pipeline",
        tool_name=tool,
        mutation_policy="read",
        outcome=TreatmentOutcome.OK,
        duration_ms=ms,
        occurred_at=at,
    )


class TestNoFreeTextReachesAnAxis:
    async def test_a_users_own_sub_agent_title_is_collapsed(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The chart the owner asked for groups by node. Two of that column's
        families are written by somebody else, and one of them is the account
        holder themselves."""
        async_session.add(_call(user, node="sub-agent: Rapport confidentiel Marie Dupont"))
        async_session.add(_call(user, node="MCP Iterative: GITHUB REPOS"))
        async_session.add(_call(user, node="planner"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        labels = {one.label for one in figures.calls_by_node.slices}

        assert labels == {"sub-agent", "mcp", "planner"}
        assert not any("Marie" in label for label in labels)

    async def test_several_collapsed_values_ADD_UP_under_one_bar(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Collapsing maps many stored values onto one label; a bar that showed
        only the first would understate itself."""
        for index in range(3):
            async_session.add(_call(user, node=f"sub-agent: assistant {index}"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        bar = next(one for one in figures.calls_by_node.slices if one.label == "sub-agent")

        assert bar.count == 3

    async def test_consultations_are_grouped_by_the_readers_own_vocabulary(
        self, async_session: AsyncSession, user: User
    ) -> None:
        async_session.add(_consultation(user, tool="get_emails_tool"))
        async_session.add(_consultation(user, tool="get_events_tool"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        labels = {one.label for one in figures.consultations_by_domain.slices}

        assert "get_emails_tool" not in labels, "a tool name reached the domain axis"
        assert labels == {"email", "event"}


class TestEveryCountIsEXACT:
    async def test_the_total_covers_what_the_top_n_folded_away(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A chart is a claim, and a claim is exact or it does not exist."""
        for index in range(TOP_N + 5):
            async_session.add(_call(user, node=f"node_{index:02d}", model=f"model-{index:02d}"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        series = figures.calls_by_model

        assert series.total == TOP_N + 5
        assert sum(one.count for one in series.slices) == series.total, "the bars lost rows"

    async def test_the_remainder_is_COUNTED_under_one_explicit_bar(
        self, async_session: AsyncSession, user: User
    ) -> None:
        for index in range(TOP_N + 5):
            async_session.add(_call(user, node="planner", model=f"model-{index:02d}"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        folded = next(one for one in figures.calls_by_model.slices if one.label == "other")

        assert folded.count == 5
        assert len(figures.calls_by_model.slices) == TOP_N + 1

    async def test_a_small_set_is_not_folded_at_all(
        self, async_session: AsyncSession, user: User
    ) -> None:
        async_session.add(_call(user, node="planner"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])

        assert [one.label for one in figures.calls_by_model.slices] == ["gpt-5-mini"]

    async def test_tokens_carry_both_measures_on_one_bar(
        self, async_session: AsyncSession, user: User
    ) -> None:
        async_session.add(_call(user, node="planner"))
        async_session.add(_call(user, node="response"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        bar = figures.tokens_by_model.slices[0]

        assert (bar.count, bar.secondary) == (20, 10)


class TestTheScopeIsAParameterOfTheQUERY:
    async def test_a_readers_figures_hold_nobody_elses_rows(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        async_session.add(_call(user, node="planner"))
        async_session.add(_call(other, node="response"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])

        assert [one.label for one in figures.calls_by_node.slices] == ["planner"]

    async def test_an_omitted_scope_covers_the_instance(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        """An operator asking about the instance is asking about the instance."""
        async_session.add(_call(user, node="planner"))
        async_session.add(_call(other, node="response"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=None)
        labels = {one.label for one in figures.calls_by_node.slices}

        assert {"planner", "response"} <= labels

    async def test_several_accounts_are_summed_not_listed(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        """The figures answer « what is happening », never « who did what »."""
        async_session.add(_call(user, node="planner"))
        async_session.add(_call(other, node="planner"))
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id, other.id])
        bar = next(one for one in figures.calls_by_node.slices if one.label == "planner")

        assert bar.count == 2


class TestThePeriodFiltersFiveTablesTheSameWay:
    async def test_a_window_excludes_what_falls_outside_it(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = DecisionRepository(async_session)
        for hours in (0, 5):
            moment = _START + timedelta(hours=hours)
            async_session.add(_call(user, node="planner", at=moment))
            async_session.add(_consultation(user, tool="get_emails_tool", at=moment))
            await repository.record(
                TurnDecision(
                    run_id=f"run-{hours}",
                    user_id=user.id,
                    thread_id="thread-A",
                    execution_mode="pipeline",
                    started_at=moment,
                ),
                ended_at=moment + timedelta(seconds=1),
            )
        await async_session.flush()

        figures = await register_statistics(
            async_session, user_ids=[user.id], since=_START + timedelta(hours=2)
        )

        assert figures.calls_by_node.total == 1
        assert figures.consultations_by_domain.total == 1
        assert figures.turns_by_outcome.total == 1


class TestATimelineIsReadFORWARD:
    async def test_the_days_come_back_in_order(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Every other series is largest first; a chronology sorted by size is
        not a chronology."""
        repository = DecisionRepository(async_session)
        for days in (2, 0, 1):
            moment = _START + timedelta(days=days)
            await repository.record(
                TurnDecision(
                    run_id=f"run-{days}",
                    user_id=user.id,
                    thread_id="thread-A",
                    execution_mode="pipeline",
                    started_at=moment,
                ),
                ended_at=moment + timedelta(seconds=1),
            )
        await async_session.flush()

        days = [
            one.label
            for one in (
                await register_statistics(async_session, user_ids=[user.id])
            ).activity_by_day.slices
        ]

        assert days == sorted(days)
        assert len(days) == 3


class TestAnEmptyPeriodIsAnANSWER:
    async def test_every_series_is_present_and_empty(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A quiet week is a valid answer, not a missing chart."""
        figures = await register_statistics(async_session, user_ids=[user.id])

        for name, series in vars(figures).items():
            assert series.slices == [], f"{name} invented a bar"
            assert series.total == 0, f"{name} invented a total"


class TestTheOutcomesAreREADABLE:
    async def test_a_stored_enum_is_charted_by_its_value(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A label reading ``DecisionOutcome.ANSWERED`` would be the member
        name leaking through, which no reader recognises."""
        await DecisionRepository(async_session).record(
            TurnDecision(
                run_id="run-1",
                user_id=user.id,
                thread_id="thread-A",
                execution_mode="react",
                outcome=DecisionOutcome.ANSWERED,
                started_at=_START,
            ),
            ended_at=_START + timedelta(seconds=1),
        )
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])

        assert [one.label for one in figures.turns_by_outcome.slices] == ["answered"]
        assert [one.label for one in figures.turns_by_mode.slices] == ["react"]


class TestATotalMeansWhatTheBarsDraw:
    """ADR-185, applied to a chart: a figure beside bars is checkable or absent.

    Two series do not draw a plain count, and each was silently answered with a
    number that could not be checked against them:

    - the tokens chart STACKS prompt and completion on one bar, so a total that
      counts only prompt tokens is shorter than the bars it sits beside;
    - the latency chart draws AVERAGES, and a sum of averages is not a
      quantity — neither for the folded « other » bar nor for the badge.
    """

    async def test_the_tokens_total_covers_BOTH_measures_on_the_bar(
        self, async_session: AsyncSession, user: User
    ) -> None:
        async_session.add_all([_call(user, node="response"), _call(user, node="planner")])
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        series = figures.tokens_by_model

        drawn = sum(one.count + one.secondary for one in series.slices)
        assert series.total == drawn
        assert series.total == 2 * (10 + 5)

    async def test_the_latency_badge_is_an_AVERAGE_not_a_sum_of_averages(
        self, async_session: AsyncSession, user: User
    ) -> None:
        # Two tools, four consultations: the honest overall figure is weighted
        # by observations (3×100 + 1×20) / 4 = 80 ms — never 100 + 20.
        async_session.add_all(
            [
                _consultation(user, tool="get_emails_tool", ms=100),
                _consultation(user, tool="get_emails_tool", ms=100),
                _consultation(user, tool="get_emails_tool", ms=100),
                _consultation(user, tool="get_events_tool", ms=20),
            ]
        )
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        series = figures.consultation_latency_by_tool

        assert series.total == 80
        assert {one.label: one.count for one in series.slices} == {
            "get_emails_tool": 100,
            "get_events_tool": 20,
        }

    async def test_the_folded_latency_bar_is_an_AVERAGE_of_what_it_folded(
        self, async_session: AsyncSession, user: User
    ) -> None:
        # One fast tool beyond the top-N, and one slow one: folding by SUM
        # would draw a bar taller than either of the values it stands for.
        rows = [
            _consultation(user, tool=f"tool_{index:02d}", ms=1000 - index) for index in range(TOP_N)
        ]
        rows += [
            _consultation(user, tool="tail_a", ms=10),
            _consultation(user, tool="tail_b", ms=20),
        ]
        async_session.add_all(rows)
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        folded = [
            one for one in figures.consultation_latency_by_tool.slices if one.label == "other"
        ]

        assert folded, "the tail must be counted, not dropped"
        assert folded[0].count == 15

    async def test_a_series_says_what_its_total_MEANS(
        self, async_session: AsyncSession, user: User
    ) -> None:
        # The reader's screen must not have to guess: a chart of averages and a
        # chart of counts cannot wear the same badge.
        from src.domains.agents.effects.statistics import SeriesKind

        async_session.add_all([_call(user, node="response"), _consultation(user, tool="get_x")])
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])

        assert figures.calls_by_model.kind is SeriesKind.COUNT
        assert figures.tokens_by_model.kind is SeriesKind.STACKED
        assert figures.consultation_latency_by_tool.kind is SeriesKind.AVERAGE


class TestAToolNameIsBoundedBeforeItReachesAnAxis:
    async def test_third_party_tools_collapse_and_their_means_are_WEIGHTED(
        self, async_session: AsyncSession, user: User
    ) -> None:
        # Two MCP tools from different servers, with different observation
        # counts: merging pre-averaged values would give (100 + 20) / 2 = 60,
        # where the truth is (3×100 + 1×20) / 4 = 80.
        from src.domains.agents.registry.catalogue import MCP_TOOL_NAME_PREFIX

        async_session.add_all(
            [
                _consultation(user, tool=f"{MCP_TOOL_NAME_PREFIX}_github_a", ms=100),
                _consultation(user, tool=f"{MCP_TOOL_NAME_PREFIX}_github_a", ms=100),
                _consultation(user, tool=f"{MCP_TOOL_NAME_PREFIX}_github_a", ms=100),
                _consultation(user, tool=f"{MCP_TOOL_NAME_PREFIX}_era_b", ms=20),
            ]
        )
        await async_session.flush()

        figures = await register_statistics(async_session, user_ids=[user.id])
        bars = {one.label: one.count for one in figures.consultation_latency_by_tool.slices}

        assert bars == {"mcp": 80}
        assert all("github" not in one.label for one in figures.consultation_latency_by_tool.slices)
