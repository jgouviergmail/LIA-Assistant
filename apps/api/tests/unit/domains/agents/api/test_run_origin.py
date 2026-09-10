"""What an out-of-turn run says about itself, and how a row carries it (ADR-276).

``AgentService.stream_chat_response`` sits NINE logical lines under its frozen
cap, so a run cannot hand it a parameter: it publishes a ContextVar instead —
the shape ``capability_directive_ctx`` already uses — and two readers consult
it.

Both readers close a specific hole:

- the archive enrichers mark the run's two rows ``hidden``, so the chat stays
  quiet while the RECORD stays whole. Archiving nothing was the first design,
  and it would have left the decision register (ADR-263 lot 6) with two NULL
  pointers — indistinguishable from a deleted conversation;
- the gate records the refusals it issues, so the run's settle reads a CODE and
  never the model's prose.
"""

from __future__ import annotations

import asyncio

import pytest

from src.domains.agents.api.run_origin import (
    RunOrigin,
    current_origin,
    out_of_turn_origin_ctx,
    record_refusal,
    with_hidden_stamp,
)

pytestmark = pytest.mark.unit


def _origin() -> RunOrigin:
    return RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")


class TestOutsideARun:
    """An ordinary chat turn must be untouched by all of this."""

    def test_there_is_no_origin_by_default(self) -> None:
        assert current_origin() is None

    def test_the_stamp_changes_nothing(self) -> None:
        payload = {"type": "answer"}
        assert with_hidden_stamp(payload) is payload

    def test_recording_a_refusal_is_harmless(self) -> None:
        """The gate calls this on every refusal, run or no run."""
        record_refusal("send_email_tool", "confirmation_impossible_unattended")


class TestInsideARun:
    def test_the_stamp_marks_the_row_and_names_its_ticket(self) -> None:
        origin = _origin()
        token = out_of_turn_origin_ctx.set(origin)
        try:
            stamped = with_hidden_stamp({"type": "answer"})
        finally:
            out_of_turn_origin_ctx.reset(token)
        assert stamped["hidden"] is True
        assert stamped["workboard"] == {"ticket_id": "t-1", "run_id": "r-1"}
        assert stamped["type"] == "answer", "the caller's own keys survive"

    def test_the_stamp_returns_a_new_dict(self) -> None:
        """One turn's metadata must never leak into another's — the rule every
        enricher in this package follows."""
        origin = _origin()
        token = out_of_turn_origin_ctx.set(origin)
        original = {"type": "answer"}
        try:
            stamped = with_hidden_stamp(original)
        finally:
            out_of_turn_origin_ctx.reset(token)
        assert stamped is not original
        assert "hidden" not in original

    def test_refusals_accumulate_in_order(self) -> None:
        origin = _origin()
        token = out_of_turn_origin_ctx.set(origin)
        try:
            record_refusal("send_email_tool", "confirmation_impossible_unattended")
            record_refusal("delete_event_tool", "confirmation_missing")
        finally:
            out_of_turn_origin_ctx.reset(token)
        assert origin.refusals == [
            ("send_email_tool", "confirmation_impossible_unattended"),
            ("delete_event_tool", "confirmation_missing"),
        ]

    def test_a_child_task_sees_the_origin(self) -> None:
        """A ContextVar is COPIED into a task at creation, so a refusal raised
        deep inside the graph reaches the settle — which is the whole reason
        the settle can read a code instead of parsing prose."""
        origin = _origin()

        async def inner() -> str | None:
            seen = current_origin()
            return seen.ticket_id if seen else None

        async def outer() -> str | None:
            token = out_of_turn_origin_ctx.set(origin)
            try:
                return await asyncio.create_task(inner())
            finally:
                out_of_turn_origin_ctx.reset(token)

        assert asyncio.run(outer()) == "t-1"

    def test_a_refusal_recorded_in_a_child_task_reaches_the_parent(self) -> None:
        """The mutation goes through the SHARED object, not through the
        ContextVar — setting a value in a child would never reach its parent."""
        origin = _origin()

        async def inner() -> None:
            record_refusal("send_email_tool", "confirmation_impossible_unattended")

        async def outer() -> None:
            token = out_of_turn_origin_ctx.set(origin)
            try:
                await asyncio.create_task(inner())
            finally:
                out_of_turn_origin_ctx.reset(token)

        asyncio.run(outer())
        assert origin.refusals == [("send_email_tool", "confirmation_impossible_unattended")]

    def test_two_concurrent_runs_never_see_each_other(self) -> None:
        """Two tickets can run on two accounts at the same instant."""
        first = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")
        second = RunOrigin(kind="workboard", ticket_id="t-2", run_id="r-2")

        async def run(origin: RunOrigin, delay: float) -> str:
            token = out_of_turn_origin_ctx.set(origin)
            try:
                await asyncio.sleep(delay)
                record_refusal("send_email_tool", "confirmation_impossible_unattended")
                seen = current_origin()
                return seen.ticket_id if seen else "none"
            finally:
                out_of_turn_origin_ctx.reset(token)

        async def both() -> list[str]:
            return list(await asyncio.gather(run(first, 0.01), run(second, 0.0)))

        assert asyncio.run(both()) == ["t-1", "t-2"]
        assert len(first.refusals) == 1
        assert len(second.refusals) == 1


class TestTheGateRecordsItsRefusals:
    """The settle reads a CODE, so the gate must actually put one there."""

    async def test_a_refused_draft_is_collected_on_the_running_origin(self) -> None:
        from unittest.mock import AsyncMock, patch

        from src.domains.agents.effects.gate import ERROR_CONFIRMATION_IMPOSSIBLE
        from src.domains.agents.effects.runtime import _refuse_or_ask
        from src.domains.agents.effects.scope import EffectScope

        decision = type(
            "Decision",
            (),
            {"error_code": ERROR_CONFIRMATION_IMPOSSIBLE, "llm_message": "nope"},
        )()
        scope = EffectScope(run_id="r-1", idempotency_key="c-1", source="scheduled")
        origin = _origin()
        token = out_of_turn_origin_ctx.set(origin)
        try:
            with patch("src.domains.agents.effects.runtime._LEDGER.refuse", AsyncMock()):
                await _refuse_or_ask("send_email_tool", decision, None, scope, {})
        finally:
            out_of_turn_origin_ctx.reset(token)

        assert origin.refusals == [("send_email_tool", ERROR_CONFIRMATION_IMPOSSIBLE)]


class TestTheEnrichersReadIt:
    """The stamp must reach BOTH archived rows, or half a run stays visible."""

    def test_the_assistant_row_is_stamped(self) -> None:
        from unittest.mock import MagicMock

        from src.domains.agents.api.archive_metadata import build_assistant_metadata

        origin = _origin()
        token = out_of_turn_origin_ctx.set(origin)
        try:
            metadata = build_assistant_metadata(
                {"type": "answer"},
                widgets=None,
                trace_capture=MagicMock(snapshot=MagicMock(return_value=None)),
                duration_ms=10,
                run_id="r-1",
                followup_suggestions=None,
                initiative_motivation=None,
                effects=None,
            )
        finally:
            out_of_turn_origin_ctx.reset(token)
        assert metadata["hidden"] is True
        assert metadata["workboard"]["ticket_id"] == "t-1"

    async def test_the_synthetic_user_row_is_stamped_too(self) -> None:
        """Stamping only the answer would leave the run's QUESTION in the chat
        — the half a reader would find hardest to explain."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from uuid import uuid4

        from src.domains.agents.api.archive_first import archive_user_message_first

        conv_service = MagicMock()
        conv_service.archive_message = AsyncMock(return_value=MagicMock(id=uuid4()))
        origin = _origin()
        token = out_of_turn_origin_ctx.set(origin)
        try:
            with patch("src.infrastructure.database.get_db_context"):
                await archive_user_message_first(
                    conv_service=conv_service,
                    conversation_id=uuid4(),
                    user_message="Do the thing",
                    run_id="r-1",
                    is_hitl_resumption=False,
                    attachment_meta={},
                    stt_kwargs={},
                    is_automated_source=True,
                )
        finally:
            out_of_turn_origin_ctx.reset(token)

        metadata = conv_service.archive_message.await_args.args[3]
        assert metadata["hidden"] is True
        assert metadata["workboard"]["ticket_id"] == "t-1"

    def test_the_assistant_row_of_a_chat_turn_is_not(self) -> None:
        from unittest.mock import MagicMock

        from src.domains.agents.api.archive_metadata import build_assistant_metadata

        metadata = build_assistant_metadata(
            {"type": "answer"},
            widgets=None,
            trace_capture=MagicMock(snapshot=MagicMock(return_value=None)),
            duration_ms=10,
            run_id="r-1",
            followup_suggestions=None,
            initiative_motivation=None,
            effects=None,
        )
        assert "hidden" not in metadata


class TestAnApprovalTravelsWithTheRun:
    """Lot 7: the replay is let through on the IDENTITY of what was shown, once."""

    @staticmethod
    def _carrying() -> RunOrigin:
        from src.domains.agents.api.run_origin import ApprovedDraft

        return RunOrigin(
            kind="workboard",
            ticket_id="t-1",
            run_id="r-1",
            can_carry_draft=True,
            approved_draft=ApprovedDraft(draft_type="tool_call", digest="abc"),
        )

    def test_outside_a_run_there_is_nothing_to_spend(self) -> None:
        from src.domains.agents.api.run_origin import consume_approved_draft

        assert consume_approved_draft("tool_call", "abc") is None

    def test_a_run_without_an_approval_has_nothing_to_spend(self) -> None:
        from src.domains.agents.api.run_origin import consume_approved_draft

        token = out_of_turn_origin_ctx.set(_origin())
        try:
            assert consume_approved_draft("tool_call", "abc") is None
        finally:
            out_of_turn_origin_ctx.reset(token)

    def test_the_matching_draft_spends_the_approval_once(self) -> None:
        """A second identical draft in the same run asks again: one approval,
        one execution — the rule the whole register stands on."""
        from src.domains.agents.api.run_origin import consume_approved_draft

        origin = self._carrying()
        token = out_of_turn_origin_ctx.set(origin)
        try:
            assert consume_approved_draft("tool_call", "abc") is True
            assert origin.approved_draft is None
            assert consume_approved_draft("tool_call", "abc") is None
        finally:
            out_of_turn_origin_ctx.reset(token)

    def test_a_different_draft_does_not_spend_it(self) -> None:
        from src.domains.agents.api.run_origin import consume_approved_draft

        origin = self._carrying()
        token = out_of_turn_origin_ctx.set(origin)
        try:
            assert consume_approved_draft("tool_call", "zzz") is False
            assert consume_approved_draft("email", "abc") is False
            assert origin.approved_draft is not None
            assert consume_approved_draft("tool_call", "abc") is True
        finally:
            out_of_turn_origin_ctx.reset(token)

    def test_a_child_task_spends_the_parents_approval(self) -> None:
        """A node runs in a copy of the context: the SHARED object is what
        makes the spend visible to the next node of the same turn."""
        from src.domains.agents.api.run_origin import consume_approved_draft

        origin = self._carrying()

        async def scenario() -> bool | None:
            token = out_of_turn_origin_ctx.set(origin)
            try:
                return await asyncio.create_task(
                    asyncio.to_thread(consume_approved_draft, "tool_call", "abc")
                )
            finally:
                out_of_turn_origin_ctx.reset(token)

        assert asyncio.run(scenario()) is True
        assert origin.approved_draft is None

    def test_a_ticket_run_can_carry_a_draft_and_nothing_else_can(self) -> None:
        from src.domains.agents.api.run_origin import current_origin_carries_drafts

        assert current_origin_carries_drafts() is False
        token = out_of_turn_origin_ctx.set(_origin())
        try:
            assert current_origin_carries_drafts() is False
        finally:
            out_of_turn_origin_ctx.reset(token)
        token = out_of_turn_origin_ctx.set(self._carrying())
        try:
            assert current_origin_carries_drafts() is True
        finally:
            out_of_turn_origin_ctx.reset(token)
