"""Real SQL/claims/context/finance/archive flow; sources, model and transports fictional."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.domains.conversations.service as conversation_service
import src.domains.proactive_discussions.finance_permit as finance_permit
from src.core.config import settings
from src.domains.conversations.models import ConversationMessage
from src.domains.proactive_discussions.finance_models import DiscussionSpendReservation
from src.domains.proactive_discussions.llm_contracts import ContextInterpretation
from src.domains.proactive_discussions.models import (
    DiscussionOpeningRecord,
    DiscussionOutbox,
    DiscussionRun,
)
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.schemas import EngageDecision
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey, source_snapshot
from src.infrastructure.proactive import (
    discussion_activity,
    discussion_attention,
    discussion_context,
    discussion_run_setup,
    discussion_runner,
)

pytestmark = pytest.mark.integration


class FakeSource:
    async def read(self, request):
        return source_snapshot(
            request,
            status="ok",
            items=(
                DiscussionEvidence(
                    reference="calendar:fiction",
                    source=SourceKey.CALENDAR,
                    object_id="fiction",
                    version="v1",
                    observed_at=request.now,
                    excerpt="A fictional appointment",
                    assertion="planned",
                ),
            ),
        )


#: What the run's publication claimed and settled in the action register, in order.
RECORDED_ACTS: list[tuple[str, object]] = []


@asynccontextmanager
async def recorded_discussion_effect(*, user_id, run_id):
    """The register's door, recorded: the ledger itself is the effects tests' subject."""

    class Effect:
        delivered = False

    RECORDED_ACTS.append(("claim", run_id))
    effect = Effect()
    try:
        yield effect
    finally:
        RECORDED_ACTS.append(("settle", effect.delivered))


def _offered(content: str) -> list[str]:
    """The references a context call was offered, read from its payload's facts."""
    facts = content.split('"facts":', 1)[1].split('"knowledge":', 1)[0]
    return [part.split('"', 1)[0] for part in facts.split('"reference":"')[1:]]


class FakeModel:
    topic = ()
    hook = None
    calls = []
    sources = []
    offered = []

    def __init__(self, owner, run, permit, *, authorize, source):
        self.permit, self.authorize = permit, authorize
        self.sources.append(source)

    async def spend(self, phase):
        await self.authorize()
        await self.permit.reserve_external(Decimal("0.001"))
        self.permit.external_receipt(Decimal("0.001"), uncertain=False)
        self.calls.append(phase)

    async def interpret(self, content):
        await self.spend("context")
        offered = _offered(content)
        self.offered.append(tuple(offered))
        known = "calendar:fiction" in offered
        return ContextInterpretation.model_validate(
            {
                "classifications": [
                    {"reference": reference, "sensitive_topics": self.topic}
                    for reference in offered
                ],
                "proposals": (
                    [
                        {
                            "kind": "observation",
                            "summary": "A fictional planned appointment",
                            "qualification": "planned",
                            "anchor": "calendar:fiction",
                            "references": ["calendar:fiction"],
                            "sensitive_topics": self.topic,
                        }
                    ]
                    if known
                    else []
                ),
                "resolution": {
                    "status": "ready",
                    "references": ["calendar:fiction"] if known else offered,
                },
            }
        )

    async def decide(self, content):
        await self.spend("decision")
        return EngageDecision(
            action="engage",
            reason="a grounded invitation",
            topic="appointment",
            references=("calendar:fiction",),
        )

    async def message(self, content):
        await self.spend("message")
        if self.hook is not None:
            await self.hook()
        await self.authorize()
        return "Would you like to talk about your appointment?"


@pytest.fixture
async def producer(async_engine, discussion_owner, monkeypatch):
    @asynccontextmanager
    async def context():
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    for module in (
        discussion_runner,
        discussion_run_setup,
        discussion_attention,
        discussion_context,
    ):
        monkeypatch.setattr(module, "get_db_context", context)

    @asynccontextmanager
    async def tracking(*args):
        class Tracker:
            def get_google_api_calls_breakdown(self):
                return []

        yield Tracker()

    monkeypatch.setattr(finance_permit, "enforce_usage_limit", AsyncMock())
    monkeypatch.setattr(discussion_runner, "out_of_turn_spend", tracking)
    # Transports are the outbox tests' subject; here the run only hands the opening over.
    monkeypatch.setattr(discussion_runner, "dispatch_discussion", AsyncMock(return_value=True))
    monkeypatch.setattr(discussion_runner, "DiscussionLLM", FakeModel)
    monkeypatch.setattr(
        discussion_runner, "proactive_discussion_effect", recorded_discussion_effect
    )
    RECORDED_ACTS.clear()
    monkeypatch.setattr(discussion_runner, "fits_context", lambda _: True)
    # The fake model costs 0.001 a call; the bound of its first call says so.
    for module in (discussion_run_setup, discussion_activity):
        monkeypatch.setattr(module, "first_call_bound", lambda *args, **kwargs: Decimal("0.001"))
    monkeypatch.setattr(
        discussion_runner,
        "discussion_readers",
        lambda **kwargs: {key: FakeSource() for key in SourceKey},
    )
    monkeypatch.setattr(discussion_run_setup, "attention_available", AsyncMock(return_value=True))
    monkeypatch.setattr(discussion_attention, "attention_available", AsyncMock(return_value=True))
    monkeypatch.setattr(conversation_service, "arm_after_archive", AsyncMock())
    for name in (
        "discussion_owner_daily_budget_usd",
        "discussion_instance_daily_budget_usd",
        "discussion_run_budget_usd",
    ):
        monkeypatch.setattr(settings, name, Decimal("0.1"))
    monkeypatch.setattr(settings, "discussion_instance_daily_budget_usd", Decimal("10"))
    monkeypatch.setattr(settings, "discussion_run_budget_usd", Decimal("0.02"))
    monkeypatch.setattr(settings, "proactive_discussions_enabled", True)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = cls(2026, 10, 20, 12, tzinfo=UTC)
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    for module in (
        discussion_runner,
        discussion_run_setup,
        discussion_attention,
        discussion_context,
        finance_permit,
    ):
        monkeypatch.setattr(module, "datetime", FixedClock)
    FakeModel.calls = []
    FakeModel.sources = []
    FakeModel.offered = []
    FakeModel.topic = ()
    FakeModel.hook = None
    async with context() as db:
        await DiscussionRepository(db).update_policy(
            discussion_owner,
            DiscussionPolicyPatch(
                enabled=True, start_hour=0, end_hour=23, sources=(SourceKey.CALENDAR,)
            ),
            expected_revision=0,
        )
    return context


async def test_funded_context_decision_wording_archive_and_outbox_commit_as_one_flow(
    producer, discussion_owner
):
    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    assert FakeModel.calls == ["context", "decision", "message"]
    assert FakeModel.sources == ["proactive"]
    async with producer() as db:
        opening = await db.scalar(
            select(DiscussionOpeningRecord).where(
                DiscussionOpeningRecord.user_id == discussion_owner
            )
        )
        assert opening is not None
        message = await db.get(ConversationMessage, opening.message_id)
        assert (
            message.role == "assistant"
            and message.message_metadata["type"] == "proactive_discussion"
        )
        assert (
            await db.scalar(
                select(DiscussionOutbox).where(DiscussionOutbox.opening_id == opening.id)
            )
        ).state == "pending"
        spend = await db.scalar(
            select(DiscussionSpendReservation).where(
                DiscussionSpendReservation.user_id == discussion_owner
            )
        )
        assert spend.state == "settled" and spend.actual_usd == Decimal("0.003")
        # The publication settles the run itself: it keeps the run's reason and counts.
        run = await db.get(DiscussionRun, opening.run_id)
        assert (run.state, run.reason) == ("completed", "published")
        assert run.stats is not None and run.stats["context_calls"] == 1
    # The opening is LIA's own act: claimed before its message is posted, settled once
    # the commit that posts it returned (« Actions menées d'elle-même »).
    assert RECORDED_ACTS == [("claim", str(opening.run_id)), ("settle", True)]


@pytest.mark.parametrize("busy", [False, True])
async def test_manual_rebuild_builds_empty_context_outside_discussion_hours_without_a_message(
    producer, discussion_owner, monkeypatch, busy
):
    from src.domains.proactive_discussions.context_store.repository import ContextRepository

    monkeypatch.setattr(
        discussion_run_setup, "attention_available", AsyncMock(return_value=not busy)
    )
    monkeypatch.setattr(
        discussion_attention, "attention_available", AsyncMock(return_value=not busy)
    )
    async with producer() as db:
        await DiscussionRepository(db).update_policy(
            discussion_owner,
            DiscussionPolicyPatch(start_hour=20, end_hour=21),
            expected_revision=1,
        )
        state = await ContextRepository(db).request_rebuild(
            discussion_owner, expected_epoch=0, now=discussion_runner.datetime.now(UTC)
        )
    assert await discussion_runner.run_for_owner(discussion_owner) == "ineligible"
    assert FakeModel.calls == []
    assert (
        await discussion_runner.run_for_owner(discussion_owner, rebuild_epoch=state.context_epoch)
        == "completed"
    )
    assert FakeModel.calls == ["context"]
    # The person asked for this rebuild: its spend is theirs, not LIA's initiative.
    assert FakeModel.sources == ["user"]
    assert (
        await discussion_runner.run_for_owner(discussion_owner, rebuild_epoch=state.context_epoch)
        == "ineligible"
    )
    assert FakeModel.calls == ["context"]
    async with producer() as db:
        result = await ContextRepository(db).read_generation(
            discussion_owner, now=discussion_runner.datetime.now(UTC)
        )
        assert result.total > 0 and not result.refresh_requested
        assert await db.scalar(select(DiscussionOpeningRecord.id)) is None
        assert await db.scalar(select(DiscussionOutbox.id)) is None
        spend = await db.scalar(select(DiscussionSpendReservation))
        assert spend.state == "settled" and spend.actual_usd == Decimal("0.001")


@pytest.mark.parametrize("owner_budget", [None, Decimal("0.0001")])
async def test_manual_rebuild_retains_financial_admission(
    producer, discussion_owner, monkeypatch, owner_budget
):
    from src.domains.proactive_discussions.context_store.repository import ContextRepository

    async with producer() as db:
        state = await ContextRepository(db).request_rebuild(
            discussion_owner, expected_epoch=0, now=discussion_runner.datetime.now(UTC)
        )
    monkeypatch.setattr(settings, "discussion_owner_daily_budget_usd", owner_budget)
    outcome = await discussion_runner.run_for_owner(
        discussion_owner, rebuild_epoch=state.context_epoch
    )
    # A requested rebuild answers to the same ceilings: a day whose room cannot pay
    # its first call starts nothing, and says when it can.
    assert outcome == ("budget_unconfigured" if owner_budget is None else "budget_exhausted")
    assert FakeModel.calls == []
    if owner_budget is not None:
        async with producer() as db:
            run = await db.scalar(select(DiscussionRun))
            assert (run.state, run.reason) == ("skipped", "budget_exhausted")
            assert run.retry_after == datetime(2026, 10, 21, tzinfo=UTC)


async def test_a_medical_topic_is_consented_until_the_person_withdraws_it(
    producer, discussion_owner
):
    # Owner decision 2026-10-21: every sensitive topic is consented by default.
    FakeModel.topic = ("health",)
    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    assert FakeModel.calls == ["context", "decision", "message"]


async def test_refused_medical_topic_stops_after_classification_but_keeps_known_cost(
    producer, discussion_owner
):
    async with producer() as db:
        await DiscussionRepository(db).update_policy(
            discussion_owner, DiscussionPolicyPatch(sensitive_topics=()), expected_revision=1
        )
    FakeModel.topic = ("health",)
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    assert FakeModel.calls == ["context"]
    async with producer() as db:
        assert (
            await db.scalar(
                select(DiscussionOpeningRecord.id).where(
                    DiscussionOpeningRecord.user_id == discussion_owner
                )
            )
            is None
        )
        spend = await db.scalar(
            select(DiscussionSpendReservation).where(
                DiscussionSpendReservation.user_id == discussion_owner
            )
        )
        assert spend.state == "settled" and spend.actual_usd == Decimal("0.001")


async def test_opt_out_after_wording_discards_message_and_settles_all_paid_work(
    producer, discussion_owner
):
    async def withdraw():
        async with producer() as db:
            await DiscussionRepository(db).update_policy(
                discussion_owner, DiscussionPolicyPatch(enabled=False), expected_revision=1
            )

    FakeModel.hook = staticmethod(withdraw)
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    async with producer() as db:
        assert (
            await db.scalar(
                select(DiscussionOpeningRecord.id).where(
                    DiscussionOpeningRecord.user_id == discussion_owner
                )
            )
            is None
        )
        spend = await db.scalar(
            select(DiscussionSpendReservation).where(
                DiscussionSpendReservation.user_id == discussion_owner
            )
        )
        assert spend.state == "settled" and spend.actual_usd == Decimal("0.003")


async def test_reply_controls_are_retained_until_the_matching_memory_extraction_receipt(
    producer, discussion_owner
):
    from datetime import timedelta

    from src.domains.proactive_discussions.replies import (
        acknowledge_reply,
        correction_guard,
        synchronize_replies,
    )

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    async with producer() as db:
        opening = await db.scalar(
            select(DiscussionOpeningRecord).where(
                DiscussionOpeningRecord.user_id == discussion_owner
            )
        )
        db.add(
            ConversationMessage(
                conversation_id=opening.conversation_id,
                role="user",
                content="Do not bring up that appointment again.",
                message_metadata={"run_id": "fictional-reply-turn"},
                created_at=opening.created_at + timedelta(seconds=1),
            )
        )
    now = opening.created_at + timedelta(minutes=5)
    async with producer() as db:
        await synchronize_replies(db, discussion_owner, now=now)
        assert "Do not bring up" in await correction_guard(
            db, discussion_owner, memory_enabled=True, now=now
        )
        await acknowledge_reply(db, discussion_owner, "another-turn", now=now)
        assert "Do not bring up" in await correction_guard(
            db, discussion_owner, memory_enabled=True, now=now
        )
        await acknowledge_reply(db, discussion_owner, "fictional-reply-turn", now=now)
        assert await correction_guard(db, discussion_owner, memory_enabled=True, now=now) == ""


async def test_model_defer_suppresses_repeated_paid_evaluation_until_retry_after(
    producer, discussion_owner, monkeypatch
):
    from src.domains.proactive_discussions.schemas import DeferDecision

    async def defer(self, content):
        await self.spend("decision")
        return DeferDecision(action="defer", reason="Leave some space", retry_after_seconds=7200)

    monkeypatch.setattr(FakeModel, "decide", defer)
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    assert FakeModel.calls == ["context", "decision"]
    calls = list(FakeModel.calls)
    assert await discussion_runner.run_for_owner(discussion_owner) == "ineligible"
    assert FakeModel.calls == calls


async def test_topic_feedback_is_exact_idempotent_and_does_not_touch_other_alerts(
    producer, discussion_owner
):
    from src.domains.proactive_discussions.openings import apply_feedback

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    async with producer() as db:
        opening = await db.scalar(
            select(DiscussionOpeningRecord).where(
                DiscussionOpeningRecord.user_id == discussion_owner
            )
        )
        result = await apply_feedback(
            db, discussion_owner, opening.id, "avoid_topic", expected=None
        )
        assert result.feedback == "avoid_topic"
        policy = await DiscussionRepository(db).get_policy(discussion_owner)
        assert policy.forbidden_topics == ("appointment",)
        revision = policy.revision
        again = await apply_feedback(db, discussion_owner, opening.id, "avoid_topic", expected=None)
        assert again.feedback == "avoid_topic"
        assert (await DiscussionRepository(db).get_policy(discussion_owner)).revision == revision


async def test_source_erasure_removes_only_supported_derived_context_and_fences_pending_delivery(
    producer, discussion_owner
):
    from src.domains.proactive_discussions.context_store.repository import ContextRepository
    from src.infrastructure.discussion_invalidation import invalidate_discussion_sources

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    async with producer() as db:
        before = await ContextRepository(db).read_generation(
            discussion_owner, now=datetime.now(UTC)
        )
        assert before.total == 1
        await invalidate_discussion_sources(db, discussion_owner, (SourceKey.CALENDAR,))
        after = await ContextRepository(db).read_generation(discussion_owner, now=datetime.now(UTC))
        assert after.total == 0 and after.context_epoch > before.context_epoch
        opening = await db.scalar(
            select(DiscussionOpeningRecord).where(
                DiscussionOpeningRecord.user_id == discussion_owner
            )
        )
        assert opening.state == "expired"


async def test_complete_read_directive_precedes_source_io_and_is_cached(
    producer, discussion_owner, monkeypatch
):
    from uuid import uuid4

    from src.domains.proactive_discussions.rule_controls import ControlSupport, RuleCompilation
    from src.infrastructure.proactive.discussion_control import ControlSnapshot

    original = discussion_run_setup.load_controls
    support = ControlSupport(id=f"memory:{uuid4()}", text="Never consult my calendar.")

    async def controls(db, owner, *, now):
        native = await original(db, owner, now=now)
        return ControlSnapshot(native.revision, native.text, (support,))

    async def compile_rules(self, content):
        await self.spend("rules")
        return RuleCompilation.model_validate(
            {
                "abstain": False,
                "denied": [{"source": "calendar", "support_id": support.id, "quote": support.text}],
            }
        )

    monkeypatch.setattr(discussion_run_setup, "load_controls", controls)
    monkeypatch.setattr(FakeModel, "compile_rules", compile_rules, raising=False)
    read = AsyncMock(side_effect=AssertionError("refused source opened"))
    monkeypatch.setattr(FakeSource, "read", read)
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    assert FakeModel.calls == ["rules"]
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    assert FakeModel.calls == ["rules"]
    read.assert_not_awaited()


async def test_busy_conversation_refuses_publication_after_model_work(
    producer, discussion_owner, monkeypatch
):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def busy(*args, **kwargs):
        yield False

    monkeypatch.setattr(discussion_runner, "active_run_lease", busy)
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    assert FakeModel.calls == ["context", "decision", "message"]
    # Nothing was posted, so nothing was claimed as done.
    assert RECORDED_ACTS == []
    async with producer() as db:
        assert (
            await db.scalar(
                select(DiscussionOpeningRecord.id).where(
                    DiscussionOpeningRecord.user_id == discussion_owner
                )
            )
            is None
        )
        spend = await db.scalar(
            select(DiscussionSpendReservation).where(
                DiscussionSpendReservation.user_id == discussion_owner
            )
        )
        assert spend.actual_usd == Decimal("0.003")


async def test_incorrect_feedback_removes_known_wrong_derivatives_and_requests_reanalysis(
    producer, discussion_owner
):
    from src.domains.proactive_discussions.context_store.repository import ContextRepository
    from src.domains.proactive_discussions.openings import apply_feedback

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    async with producer() as db:
        opening = await db.scalar(
            select(DiscussionOpeningRecord).where(
                DiscussionOpeningRecord.user_id == discussion_owner
            )
        )
        before = await ContextRepository(db).read_generation(
            discussion_owner, now=datetime.now(UTC)
        )
        await apply_feedback(db, discussion_owner, opening.id, "incorrect", expected=None)
        after = await ContextRepository(db).read_generation(discussion_owner, now=datetime.now(UTC))
        assert before.total == 1 and after.total == 0
        assert after.refresh_requested and after.context_epoch > before.context_epoch


class FakeSmsSource:
    async def read(self, request):
        return source_snapshot(
            request,
            status="ok",
            items=(
                DiscussionEvidence(
                    reference="sms:fiction",
                    source=SourceKey.SMS,
                    object_id="fiction",
                    version="v1",
                    observed_at=request.now,
                    excerpt="Literal sender: Fictional\nSMS content: A fictional text message",
                    assertion="reported",
                ),
            ),
        )


def _calendar_fact() -> DiscussionEvidence:
    return DiscussionEvidence(
        reference="calendar:fiction",
        source=SourceKey.CALENDAR,
        object_id="fiction",
        version="v1",
        observed_at=datetime(2026, 10, 20, 12, tzinfo=UTC),
        excerpt="A fictional appointment",
        assertion="planned",
    )


async def _published(producer, owner):
    async with producer() as db:
        opening = await db.scalar(
            select(DiscussionOpeningRecord).where(DiscussionOpeningRecord.user_id == owner)
        )
        return opening, await db.get(ConversationMessage, opening.message_id)


async def test_an_opening_without_sms_is_ordinary_and_returns_as_prior_wording(
    producer, discussion_owner
):
    from src.core.notification_privacy import PRIVATE_NOTIFICATION_MARKER
    from src.domains.proactive_discussions.history import relevant_opening_history

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    opening, message = await _published(producer, discussion_owner)
    assert opening.sensitive_context is False
    assert message.message_metadata[PRIVATE_NOTIFICATION_MARKER] is False
    async with producer() as db:
        history = await relevant_opening_history(db, discussion_owner, (_calendar_fact(),))
    assert [item.content for item in history] == [message.content]


async def test_an_sms_the_run_read_leaves_the_opening_ordinary_and_it_returns_as_prior_wording(
    producer, discussion_owner, monkeypatch
):
    """The run READ an SMS; the decision cites the calendar alone.

    An SMS is personal data like a mail (ADR-357 amendment 2026-10-23): having read
    one makes the opening neither private nor absent from the next decision window.
    """
    from src.core.notification_privacy import PRIVATE_NOTIFICATION_MARKER
    from src.domains.proactive_discussions.history import relevant_opening_history

    async def interpret(self, content):
        await self.spend("context")
        return ContextInterpretation.model_validate(
            {
                "classifications": [
                    {"reference": "calendar:fiction", "sensitive_topics": ()},
                    {"reference": "sms:fiction", "sensitive_topics": ()},
                ],
                "proposals": [
                    {
                        "kind": "observation",
                        "summary": "A fictional planned appointment",
                        "qualification": "planned",
                        "anchor": "calendar:fiction",
                        "references": ["calendar:fiction"],
                    }
                ],
                "resolution": {"status": "ready", "references": ["calendar:fiction"]},
            }
        )

    monkeypatch.setattr(FakeModel, "interpret", interpret)
    monkeypatch.setattr(
        discussion_runner,
        "discussion_readers",
        lambda **kwargs: {
            key: FakeSmsSource() if key is SourceKey.SMS else FakeSource() for key in SourceKey
        },
    )
    async with producer() as db:
        await DiscussionRepository(db).update_policy(
            discussion_owner,
            DiscussionPolicyPatch(sources=(SourceKey.CALENDAR, SourceKey.SMS)),
            expected_revision=1,
        )
    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    opening, message = await _published(producer, discussion_owner)
    assert opening.references == ["calendar:fiction"]
    assert opening.sensitive_context is False
    assert message.message_metadata[PRIVATE_NOTIFICATION_MARKER] is False
    async with producer() as db:
        history = await relevant_opening_history(db, discussion_owner, (_calendar_fact(),))
    assert [item.content for item in history] == [message.content]


async def test_a_message_after_the_opening_closed_is_not_its_reply_and_the_opening_expires(
    producer, discussion_owner
):
    """ADR-358: a late, unrelated message is never attached to the old opening."""
    from datetime import timedelta

    from src.domains.proactive_discussions.replies import (
        REPLY_TO,
        correction_guard,
        synchronize_replies,
    )

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    opening, _ = await _published(producer, discussion_owner)
    late = ConversationMessage(
        conversation_id=opening.conversation_id,
        role="user",
        content="Unrelated question asked days later.",
        message_metadata={"run_id": "fictional-late-turn"},
        created_at=opening.expires_at + timedelta(minutes=1),
    )
    async with producer() as db:
        db.add(late)
    now = opening.expires_at + timedelta(minutes=2)
    async with producer() as db:
        await synchronize_replies(db, discussion_owner, now=now)
        assert await correction_guard(db, discussion_owner, memory_enabled=True, now=now) == ""
    async with producer() as db:
        assert (await db.get(DiscussionOpeningRecord, opening.id)).state == "expired"
        assert REPLY_TO not in (await db.get(ConversationMessage, late.id)).message_metadata


async def test_an_unacknowledged_reply_guard_lapses_after_its_lifetime(producer, discussion_owner):
    """ADR-359: the guard is transient; an extraction that never came cannot hold for ever."""
    from datetime import timedelta

    from src.domains.proactive_discussions.replies import correction_guard, synchronize_replies

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    opening, _ = await _published(producer, discussion_owner)
    replied = opening.created_at + timedelta(seconds=1)
    async with producer() as db:
        db.add(
            ConversationMessage(
                conversation_id=opening.conversation_id,
                role="user",
                content="Please never mention that appointment.",
                message_metadata={"run_id": "fictional-unextracted-turn"},
                created_at=replied,
            )
        )
    lifetime = timedelta(hours=settings.discussion_reply_guard_ttl_hours)
    async with producer() as db:
        await synchronize_replies(db, discussion_owner, now=replied)
        assert "never mention" in await correction_guard(
            db, discussion_owner, memory_enabled=True, now=replied + lifetime - timedelta(minutes=1)
        )
        assert (
            await correction_guard(
                db,
                discussion_owner,
                memory_enabled=True,
                now=replied + lifetime + timedelta(minutes=1),
            )
            == ""
        )


async def test_controls_that_cannot_all_be_read_defer_the_run_before_any_claim_or_spend(
    producer, discussion_owner, monkeypatch
):
    from src.domains.proactive_discussions.models import DiscussionRun
    from src.domains.shared.discussion_directives import DirectiveBudgetExceeded

    async def oversized(db, owner, *, now):
        raise DirectiveBudgetExceeded("complete pending reply controls exceed their budget")

    monkeypatch.setattr(discussion_run_setup, "load_controls", oversized)
    assert await discussion_runner.run_for_owner(discussion_owner) == "controls_over_budget"
    assert FakeModel.calls == []
    async with producer() as db:
        assert await db.scalar(select(DiscussionRun.id)) is None
        assert await db.scalar(select(DiscussionSpendReservation.id)) is None


async def _request_rebuild(producer, owner):
    from src.domains.proactive_discussions.context_store.repository import ContextRepository

    async with producer() as db:
        return await ContextRepository(db).request_rebuild(
            owner, expected_epoch=0, now=discussion_runner.datetime.now(UTC)
        )


async def _activity(producer, owner):
    from src.infrastructure.proactive.discussion_activity import read_activity

    async with producer() as db:
        return await read_activity(db, owner, now=discussion_runner.datetime.now(UTC))


async def test_a_requested_rebuild_reads_as_running_once_a_rebuild_run_holds_the_lease(
    producer, discussion_owner
):
    idle = await _activity(producer, discussion_owner)
    assert idle.rebuild == "idle" and idle.last_rebuild is None and idle.obstacle is None
    state = await _request_rebuild(producer, discussion_owner)
    assert (await _activity(producer, discussion_owner)).rebuild == "requested"
    async with producer() as db:
        await DiscussionRepository(db).claim_run(
            discussion_owner,
            now=discussion_runner.datetime.now(UTC),
            lease_seconds=300,
            rebuild_epoch=state.context_epoch,
        )
    running = await _activity(producer, discussion_owner)
    assert running.rebuild == "running" and running.last_rebuild.state == "claimed"


async def test_the_last_rebuild_shows_its_own_ledger_row_and_no_ceiling_reached(
    producer, discussion_owner
):
    from src.domains.chat.models import MessageTokenSummary
    from src.domains.proactive_discussions.models import DiscussionRun

    state = await _request_rebuild(producer, discussion_owner)
    outcome = await discussion_runner.run_for_owner(
        discussion_owner, rebuild_epoch=state.context_epoch
    )
    assert outcome == "completed"
    async with producer() as db:
        run = await db.scalar(select(DiscussionRun).where(DiscussionRun.context_only.is_(True)))
        db.add(
            MessageTokenSummary(
                user_id=discussion_owner,
                session_id="proactive_discussions",
                run_id=str(run.id),
                total_prompt_tokens=1200,
                total_completion_tokens=300,
                total_cached_tokens=100,
                total_cost_eur=Decimal("0.004"),
                google_api_requests=1,
                google_api_cost_eur=Decimal("0.001"),
            )
        )
    activity = await _activity(producer, discussion_owner)
    assert activity.rebuild == "idle"
    last = activity.last_rebuild
    assert last.state == "completed" and last.settled_at is not None
    assert (last.usage.tokens_in, last.usage.tokens_out, last.usage.tokens_cache) == (
        1200,
        300,
        100,
    )
    # Every euro of the run, in one figure (the model's and Google's).
    assert last.usage.google_requests == 1 and last.usage.cost_eur == pytest.approx(0.005)
    # The rebuild is also the last run, and the run that last updated the context:
    # the figures the page shows are that run's own.
    assert activity.last_run == last and activity.last_update == last
    assert last.kind == "rebuild" and last.stats.context_updates >= 1
    # Amounts are never shown: only whether a ceiling stops the next run.
    assert activity.budget.configured and activity.budget.reached is None
    assert activity.budget.resets_at is None


async def test_a_rebuild_that_interprets_nothing_says_why_instead_of_passing_for_done(
    producer, discussion_owner, monkeypatch
):
    # Production 2026-10-21: a rebuild read its sources, interpreted nothing and
    # settled « completed »; the person saw a finished rebuild and an empty context.
    class EmptySource:
        async def read(self, request):
            return source_snapshot(request, status="empty", items=())

    monkeypatch.setattr(
        discussion_runner,
        "discussion_readers",
        lambda **kwargs: {key: EmptySource() for key in SourceKey},
    )
    state = await _request_rebuild(producer, discussion_owner)
    outcome = await discussion_runner.run_for_owner(
        discussion_owner, rebuild_epoch=state.context_epoch
    )
    assert outcome == "skipped" and FakeModel.calls == []
    activity = await _activity(producer, discussion_owner)
    # The request is answered (no tick re-reads every source forever)...
    assert activity.rebuild == "idle"
    last = activity.last_rebuild
    # ...and the run says why it built nothing, in counts only.
    assert (last.state, last.reason) == ("skipped", "no_fact")
    assert last.stats.pages == {"empty": 1}
    assert (last.stats.facts_read, last.stats.context_calls, last.stats.items) == (0, 0, 0)


async def test_a_rebuild_offers_each_fact_once_a_pass_after_another(
    producer, discussion_owner, monkeypatch
):
    # Production 2026-10-21: during a rebuild every pass re-offered the same first
    # facts. The rebuild's new epoch makes every fact due once; each pass then
    # checkpoints what it analysed in PostgreSQL, and the next offers the rest.
    class ThreeFacts:
        async def read(self, request):
            return source_snapshot(
                request,
                status="ok",
                items=tuple(
                    DiscussionEvidence(
                        reference=f"calendar:fiction-{index}",
                        source=SourceKey.CALENDAR,
                        object_id=f"fiction-{index}",
                        version="v1",
                        observed_at=request.now,
                        excerpt=f"Fictional appointment {index}",
                        assertion="planned",
                    )
                    for index in range(3)
                ),
            )

    monkeypatch.setattr(
        discussion_runner,
        "discussion_readers",
        lambda **kwargs: {key: ThreeFacts() for key in SourceKey},
    )
    monkeypatch.setattr(settings, "discussion_context_facts_per_pass", 1)
    state = await _request_rebuild(producer, discussion_owner)
    outcome = await discussion_runner.run_for_owner(
        discussion_owner, rebuild_epoch=state.context_epoch
    )
    assert outcome == "completed"
    assert FakeModel.offered == [
        ("calendar:fiction-0",),
        ("calendar:fiction-1",),
        ("calendar:fiction-2",),
    ]
    last = (await _activity(producer, discussion_owner)).last_rebuild
    assert last.reason == "context_ready" and last.stats.context_calls == 3


async def test_an_exhausted_day_is_shown_before_any_run_is_refused(
    producer, discussion_owner, monkeypatch
):
    monkeypatch.setattr(settings, "discussion_owner_daily_budget_usd", Decimal("0.0035"))
    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    activity = await _activity(producer, discussion_owner)
    # 0.003 spent leaves 0.0005, under the 0.001 the next first call may cost: the
    # day is shown reached BEFORE a run is refused, with the day it renews.
    assert activity.budget.reached == "owner_day"
    assert activity.budget.resets_at == datetime(2026, 10, 21, tzinfo=UTC)
    # The published opening is the last run, its reason and counts kept by the commit.
    assert activity.last_run.kind == "opening"
    assert activity.last_run.reason == "published" and activity.last_run.stats is not None
    assert await discussion_runner.run_for_owner(discussion_owner) == "budget_exhausted"
    assert FakeModel.calls == ["context", "decision", "message"]


async def test_a_usage_limit_reached_starts_no_run_and_says_so(
    producer, discussion_owner, monkeypatch
):
    # Every model call asks the person's usage limit, but a run that started anyway
    # read every source (a paid weather read included) before its first call was
    # refused, and was filed « the provider asked to wait ».
    from src.domains.usage_limits.schemas import UsageLimitStatus
    from src.domains.usage_limits.service import UsageLimitCheckResult, UsageLimitService

    blocked = UsageLimitCheckResult(
        allowed=False,
        status=UsageLimitStatus.BLOCKED_LIMIT,
        blocked_reason="cycle cost limit",
        exceeded_limit="cycle_cost",
    )
    monkeypatch.setattr(UsageLimitService, "check_user_allowed", AsyncMock(return_value=blocked))
    reads = Mock(return_value={})
    monkeypatch.setattr(discussion_runner, "discussion_readers", reads)
    assert await discussion_runner.run_for_owner(discussion_owner) == "usage_limit_reached"
    assert FakeModel.calls == [] and reads.call_count == 0
    async with producer() as db:
        run = await db.scalar(select(DiscussionRun))
        assert (run.state, run.reason, run.retry_after) == ("skipped", "usage_limit_reached", None)
        assert await db.scalar(select(DiscussionSpendReservation.id)) is None
    activity = await _activity(producer, discussion_owner)
    # Said plainly, with no renewal date the discussions cannot know.
    assert (activity.budget.reached, activity.budget.resets_at) == ("usage_limit", None)
    assert activity.last_run.reason == "usage_limit_reached"


async def test_a_run_ceiling_below_one_call_is_named_and_starts_nothing(
    producer, discussion_owner, monkeypatch
):
    # The fake's first call may cost 0.001; a ceiling of 0.0005 can never pay it,
    # whatever the day holds, and the settings must not call it a day without room.
    monkeypatch.setattr(settings, "discussion_run_budget_usd", Decimal("0.0005"))
    assert await discussion_runner.run_for_owner(discussion_owner) == "budget_exhausted"
    assert FakeModel.calls == []
    async with producer() as db:
        run = await db.scalar(select(DiscussionRun))
        assert (run.state, run.reason) == ("skipped", "run_ceiling_too_low")
    budget = (await _activity(producer, discussion_owner)).budget
    # No day fixes it: no renewal date is promised.
    assert (budget.reached, budget.resets_at) == ("run_ceiling", None)


async def test_a_day_with_room_left_starts_another_run(producer, discussion_owner, monkeypatch):
    # Before 2026-10-21 each run held the whole run ceiling, so a day whose ceiling
    # equalled it served one run and refused every other.
    monkeypatch.setattr(settings, "discussion_owner_daily_budget_usd", Decimal("0.02"))
    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    assert (await _activity(producer, discussion_owner)).budget.reached is None
    from src.domains.proactive_discussions.finance_repository import SpendRepository
    from src.infrastructure.proactive.discussion_run_setup import configured_limits

    limits = configured_limits()
    assert limits is not None
    async with producer() as db:
        availability = await SpendRepository(db).availability(
            discussion_owner,
            limits=limits,
            now=discussion_runner.datetime.now(UTC),
            minimum=Decimal("0.001"),
        )
    # What is left of the day still funds a first call: the next run starts (the
    # size it then holds is ``test_a_reservation_takes_the_room_the_day_has_left_never_more``).
    assert availability.owner_available and availability.instance_available


async def test_controls_that_cannot_fit_hold_a_requested_rebuild_and_say_so(
    producer, discussion_owner
):
    from datetime import timedelta

    from src.domains.proactive_discussions.context_store.repository import ContextRepository
    from src.domains.proactive_discussions.replies import synchronize_replies

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    opening, _ = await _published(producer, discussion_owner)
    async with producer() as db:
        db.add(
            ConversationMessage(
                conversation_id=opening.conversation_id,
                role="user",
                content="Fictional long correction. " * 600,
                message_metadata={"run_id": "fictional-long-reply"},
                created_at=opening.created_at + timedelta(seconds=1),
            )
        )
    async with producer() as db:
        await synchronize_replies(
            db, discussion_owner, now=opening.created_at + timedelta(seconds=2)
        )
    async with producer() as db:
        current = await ContextRepository(db).read_generation(
            discussion_owner, now=discussion_runner.datetime.now(UTC)
        )
        state = await ContextRepository(db).request_rebuild(
            discussion_owner,
            expected_epoch=current.context_epoch,
            now=discussion_runner.datetime.now(UTC),
        )
    activity = await _activity(producer, discussion_owner)
    assert activity.rebuild == "requested" and activity.obstacle == "controls_over_budget"
    outcome = await discussion_runner.run_for_owner(
        discussion_owner, rebuild_epoch=state.context_epoch
    )
    assert outcome == "controls_over_budget"


async def test_a_rich_procedural_rule_and_a_long_reply_are_read_whole_by_the_next_run(
    producer, discussion_owner, monkeypatch
):
    """A support is a whole statement: 256 characters used to break every later run."""
    from datetime import timedelta

    from src.domains.memories.models import Memory
    from src.domains.proactive_discussions.rule_controls import RuleCompilation

    compiled = []

    async def compile_rules(self, content):
        await self.spend("rules")
        compiled.append(content)
        return RuleCompilation(abstain=False, denied=())

    monkeypatch.setattr(FakeModel, "compile_rules", compile_rules, raising=False)
    rule = "Before any follow-up about my fictional evening classes, ask me first. " * 6
    nuance = "Fictional nuance: keep it light, never insist, and offer to drop it. " * 4
    async with producer() as db:
        db.add(
            Memory(
                user_id=discussion_owner,
                content=rule.strip(),
                category="procedural",
                pinned=True,
                char_count=len(rule.strip()),
                usage_count=0,
                usage_nuance=nuance.strip()[:300],
                trigger_topic="fictional evening classes",
            )
        )
    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    assert FakeModel.calls[0] == "rules" and "never insist" in compiled[0]
    opening, _ = await _published(producer, discussion_owner)
    reply = "Thanks for asking. " * 30 + "Please do not bring up the fictional classes again."
    async with producer() as db:
        db.add(
            ConversationMessage(
                conversation_id=opening.conversation_id,
                role="user",
                content=reply,
                message_metadata={"run_id": "fictional-sentences-reply"},
                created_at=opening.created_at + timedelta(seconds=1),
            )
        )
    async with producer() as db:
        controls = await discussion_run_setup.load_controls(
            db, discussion_owner, now=opening.created_at + timedelta(minutes=1)
        )
    assert any(item.text == reply for item in controls.supports)


async def test_a_published_opening_is_handed_to_delivery_at_once_not_after_the_batch(
    producer, discussion_owner
):
    """Connector proofs expire within minutes: waiting for a whole batch lost the push."""
    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    opening, _ = await _published(producer, discussion_owner)
    discussion_runner.dispatch_discussion.assert_awaited_once_with(discussion_owner, opening.id)


async def test_a_run_without_an_opening_hands_nothing_to_delivery(producer, discussion_owner):
    state = await _request_rebuild(producer, discussion_owner)
    assert (
        await discussion_runner.run_for_owner(discussion_owner, rebuild_epoch=state.context_epoch)
        == "completed"
    )
    discussion_runner.dispatch_discussion.assert_not_awaited()


async def test_the_same_opening_twice_stops_before_its_wording_is_paid_for(
    producer, discussion_owner
):
    from datetime import timedelta

    from sqlalchemy import update

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    async with producer() as db:
        # The person dismissed it an hour ago: nothing else holds the next run back.
        await db.execute(
            update(DiscussionOpeningRecord)
            .where(DiscussionOpeningRecord.user_id == discussion_owner)
            .values(
                state="dismissed",
                created_at=discussion_runner.datetime.now(UTC) - timedelta(hours=1),
            )
        )
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    assert FakeModel.calls == ["context", "decision", "message", "decision"]
    async with producer() as db:
        assert len((await db.scalars(select(DiscussionOpeningRecord))).all()) == 1


async def test_the_hub_badge_counts_exactly_what_the_history_page_lists(producer, discussion_owner):
    from sqlalchemy import update

    from src.domains.proactive_discussions.openings import (
        OpeningPageRequest,
        count_openings,
        list_openings,
    )

    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    opening, _ = await _published(producer, discussion_owner)
    async with producer() as db:
        page = await list_openings(db, discussion_owner, OpeningPageRequest())
        assert await count_openings(db, discussion_owner) == page.total == 1
        await db.execute(
            update(ConversationMessage)
            .where(ConversationMessage.id == opening.message_id)
            .values(hidden=True)
        )
        page = await list_openings(db, discussion_owner, OpeningPageRequest())
        assert await count_openings(db, discussion_owner) == page.total == 0


async def test_every_run_outcome_reaches_the_operators_counter(producer, discussion_owner):
    from prometheus_client import REGISTRY

    def seen(kind: str, outcome: str) -> float:
        return (
            REGISTRY.get_sample_value(
                "proactive_discussion_runs_total", {"kind": kind, "outcome": outcome}
            )
            or 0.0
        )

    completed, skipped = seen("opening", "completed"), seen("opening", "skipped")
    rebuilt = seen("rebuild", "completed")
    assert await discussion_runner.run_for_owner(discussion_owner) == "completed"
    # The same opening again stops before its wording (the duplicate pre-check).
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    state = await _request_rebuild(producer, discussion_owner)
    assert (
        await discussion_runner.run_for_owner(discussion_owner, rebuild_epoch=state.context_epoch)
        == "completed"
    )
    assert seen("opening", "completed") == completed + 1
    assert seen("opening", "skipped") == skipped + 1
    assert seen("rebuild", "completed") == rebuilt + 1


async def test_a_reservation_that_refuses_to_release_funds_stops_the_run_as_skipped(
    producer, discussion_owner, monkeypatch
):
    """A hold that no longer authorises spending is an abstention, never a failure."""
    monkeypatch.setattr(
        discussion_run_setup.SpendRepository, "issue", AsyncMock(return_value=False)
    )
    assert await discussion_runner.run_for_owner(discussion_owner) == "skipped"
    assert FakeModel.calls == []
    async with producer() as db:
        run = await db.scalar(
            select(DiscussionRun).where(DiscussionRun.user_id == discussion_owner)
        )
        spend = await db.scalar(
            select(DiscussionSpendReservation).where(
                DiscussionSpendReservation.user_id == discussion_owner
            )
        )
    assert run.state == "skipped"
    assert spend.state == "settled" and spend.actual_usd == Decimal(0)
