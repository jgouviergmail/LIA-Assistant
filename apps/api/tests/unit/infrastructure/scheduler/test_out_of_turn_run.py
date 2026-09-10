"""One engine for « LIA runs an instruction out of turn » (ADR-276).

Three pieces were identical in the routine executor and would have been
identical again in the workboard runner: resolving the person's context,
asking whether their thread already holds an unanswered question, and driving
``stream_chat_response`` with a timeout and a retry policy. They are extracted
here, and this file is what says what each of them promises.

The retry loop is where the subtlety lives, and every assertion below is a
defect the routine path already paid for:

- a **``content_replacement`` chunk REPLACES** the accumulated tokens rather
  than appending to them — the post-processed content (HTML cards, photo
  injection, psyche-tag cleanup) arrives after the deltas, and accumulating
  only tokens built the notification from the pre-post-processing text;
- a **HITL interrupt is not retryable** — attempting it again asks a question
  nobody answered the first time;
- **a fresh session id per attempt**, because attempt 1 may have half-run the
  graph and attempt 2 must not resume a broken checkpoint.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.api.run_origin import RunOrigin, current_origin
from src.infrastructure.scheduler.out_of_turn_run import (
    RunOutcome,
    StreamRequest,
    conversation_has_pending_hitl,
    resolve_run_context,
    stream_instruction,
)

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


def _chunk(
    chunk_type: str, content: Any = None, metadata: dict[str, Any] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(type=chunk_type, content=content, metadata=metadata)


def _asked(*, kind: str = "draft_critique", **request: Any) -> list[SimpleNamespace]:
    """The three chunks the stream emits when the turn stops on a question."""
    return [
        _chunk(
            "hitl_interrupt_metadata",
            "",
            {"message_id": "m-1", "action_requests": [{"type": kind, **request}]},
        ),
        _chunk("hitl_question_token", "Je "),
        _chunk("hitl_question_token", "supprime ?"),
        _chunk(
            "hitl_interrupt_complete",
            "",
            {"message_id": "m-1", "generated_question": "Je supprime « the archive » ?"},
        ),
    ]


def _request(**overrides: Any) -> StreamRequest:
    base: dict[str, Any] = {
        "user_id": USER,
        "prompt": "Do the thing",
        "session_id": "wb_ticket_1",
        "language": "fr",
        "timezone": "Europe/Paris",
        "display_name": "Alice",
        "display_mode": "cards",
        "timeout_seconds": 30,
        "max_attempts": 2,
        "retry_delay_seconds": 0,
    }
    base.update(overrides)
    return StreamRequest(**base)


def _service_yielding(*chunk_batches: list[SimpleNamespace]) -> MagicMock:
    """An AgentService whose successive calls yield the given chunk batches."""
    calls: list[dict[str, Any]] = []

    def stream(**kwargs: Any) -> Any:
        calls.append(kwargs)
        batch = chunk_batches[min(len(calls) - 1, len(chunk_batches) - 1)]

        async def generator() -> Any:
            for chunk in batch:
                yield chunk

        return generator()

    service = MagicMock()
    service.stream_chat_response = MagicMock(side_effect=stream)
    service.calls = calls
    return service


class TestResolvingWhoTheRunBelongsTo:
    async def test_an_unknown_account_has_no_context(self) -> None:
        service = MagicMock()
        service.get_user_by_id = AsyncMock(return_value=None)
        with patch("src.domains.users.service.UserService", return_value=service):
            assert await resolve_run_context(MagicMock(), USER) is None

    async def test_an_inactive_account_has_no_context(self) -> None:
        """A deleted account is inactive too — this is the same guard."""
        service = MagicMock()
        service.get_user_by_id = AsyncMock(
            return_value=SimpleNamespace(is_active=False, language="fr")
        )
        with patch("src.domains.users.service.UserService", return_value=service):
            assert await resolve_run_context(MagicMock(), USER) is None

    async def test_it_resolves_the_preferences_the_run_will_answer_in(self) -> None:
        user = SimpleNamespace(
            is_active=True,
            language="de",
            timezone="Europe/Berlin",
            full_name="Alice Martin",
            email="alice@example.test",
            response_display_mode="html",
        )
        service = MagicMock()
        service.get_user_by_id = AsyncMock(return_value=user)
        with patch("src.domains.users.service.UserService", return_value=service):
            context = await resolve_run_context(MagicMock(), USER)
        assert context is not None
        assert context.language == "de"
        assert context.timezone == "Europe/Berlin"
        assert context.display_mode == "html"
        assert context.user is user

    async def test_missing_preferences_fall_back_to_the_deployment_defaults(self) -> None:
        user = SimpleNamespace(
            is_active=True,
            language=None,
            timezone=None,
            full_name=None,
            email="alice@example.test",
            response_display_mode=None,
        )
        service = MagicMock()
        service.get_user_by_id = AsyncMock(return_value=user)
        with patch("src.domains.users.service.UserService", return_value=service):
            context = await resolve_run_context(MagicMock(), USER)
        assert context is not None
        assert context.language
        assert context.timezone
        assert context.display_mode == "cards"


class TestTheThreadAlreadyHoldsAQuestion:
    """The probe reads the SAME record the chat routes an answer on: the
    pending-HITL entry in Redis. A run that moved its question to the ticket
    deletes that record, and the next ticket of the account must not step
    aside for a question nobody can see any more (lot 7)."""

    async def _ask(self, record: dict[str, Any] | None) -> tuple[bool, Any]:
        conversation = SimpleNamespace(id=uuid.uuid4())
        conv_service = MagicMock()
        conv_service.get_or_create_conversation = AsyncMock(return_value=conversation)
        probe = AsyncMock(return_value=record)
        with (
            patch(
                "src.domains.conversations.service.ConversationService",
                return_value=conv_service,
            ),
            patch("src.domains.agents.api.hitl_pending.check_pending_hitl_uncached", probe),
        ):
            pending, conversation_id = await conversation_has_pending_hitl(MagicMock(), USER, "fr")
        probe.assert_awaited_once_with(str(conversation.id))
        return pending, conversation_id

    async def test_an_unanswered_question_stops_the_run(self) -> None:
        pending, _ = await self._ask({"action_requests": [{"type": "clarification"}]})
        assert pending is True

    async def test_a_quiet_thread_lets_it_proceed(self) -> None:
        pending, conversation_id = await self._ask(None)
        assert pending is False
        assert conversation_id is not None

    async def test_the_checkpoint_is_not_consulted(self) -> None:
        """After a run moved its question to the ticket the checkpoint still
        says « interrupted » until the next input; reading it would make the
        board stall on its own question."""
        conv_service = MagicMock()
        conv_service.get_or_create_conversation = AsyncMock(
            return_value=SimpleNamespace(id=uuid.uuid4())
        )
        agent_service = MagicMock()
        with (
            patch(
                "src.domains.conversations.service.ConversationService",
                return_value=conv_service,
            ),
            patch("src.domains.agents.api.service.AgentService", return_value=agent_service),
            patch(
                "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
                AsyncMock(return_value=None),
            ),
        ):
            pending, _ = await conversation_has_pending_hitl(MagicMock(), USER, "fr")
        assert pending is False
        agent_service._ensure_graph_built.assert_not_called()

    async def test_a_probe_that_fails_never_blocks_the_run(self) -> None:
        """The guard exists to avoid stepping on a pending question; failing to
        ASK must not become a reason to do nothing at all."""
        conv_service = MagicMock()
        conv_service.get_or_create_conversation = AsyncMock(side_effect=RuntimeError("db down"))
        with patch(
            "src.domains.conversations.service.ConversationService",
            return_value=conv_service,
        ):
            pending, conversation_id = await conversation_has_pending_hitl(MagicMock(), USER, "fr")
        assert pending is False
        assert conversation_id is None


class TestDrivingTheTurn:
    async def test_it_returns_the_streamed_answer(self) -> None:
        service = _service_yielding([_chunk("token", "Bon"), _chunk("token", "jour")])
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.SUCCESS
        assert result.text == "Bonjour"
        assert result.attempts == 1

    async def test_a_content_replacement_replaces_the_tokens(self) -> None:
        """The post-processed content arrives AFTER the deltas and supersedes
        them; appending would ship the pre-post-processing text."""
        service = _service_yielding(
            [
                _chunk("token", "raw"),
                _chunk("content_replacement", "<div class='lia-response'>final</div>"),
            ]
        )
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.text == "<div class='lia-response'>final</div>"

    async def test_the_run_is_automated_and_its_plan_pre_approved(self) -> None:
        """Nobody is there to approve a plan; the pipeline must not wait."""
        service = _service_yielding([_chunk("token", "ok")])
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request())
        kwargs = service.calls[0]
        assert kwargs["is_automated_source"] is True
        assert kwargs["auto_approve_plan"] is True

    async def test_the_turn_runs_in_pipeline_mode(self) -> None:
        """ReAct interrupts BEFORE its own gate on every mutation, so a run
        nobody is watching would die on a question instead of being refused one
        (ADR-276 D5). The engine passes no execution mode at all — the service's
        default IS pipeline — and this pins that: the day a caller starts
        forwarding the person's preference, an unattended run would inherit it.
        """
        service = _service_yielding([_chunk("token", "ok")])
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request())
        assert service.calls[0].get("user_execution_mode", "pipeline") == "pipeline"

    async def test_the_run_id_travels_when_the_caller_owns_a_row(self) -> None:
        """A caller with a row to settle files everything under ONE id: the
        three registers, the token logs, the hidden rows and the ticket."""
        service = _service_yielding([_chunk("token", "ok")])
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request(run_id="run-42"))
        assert service.calls[0]["run_id"] == "run-42"

    async def test_every_attempt_of_one_run_shares_its_id(self) -> None:
        """The ticket paid for both attempts; the cost aggregate must find
        them both."""
        service = MagicMock()
        attempts: list[dict[str, Any]] = []

        def stream(**kwargs: Any) -> Any:
            attempts.append(kwargs)

            async def generator() -> Any:
                if len(attempts) == 1:
                    raise ConnectionError("provider blinked")
                yield _chunk("token", "ok")

            return generator()

        service.stream_chat_response = MagicMock(side_effect=stream)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request(run_id="run-42"))
        assert [call["run_id"] for call in attempts] == ["run-42", "run-42"]

    async def test_a_caller_with_no_row_lets_the_graph_mint_its_own_id(self) -> None:
        """What the routine path has always done — and must keep doing."""
        service = _service_yielding([_chunk("token", "ok")])
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request())
        assert service.calls[0]["run_id"] is None

    async def test_a_hitl_interrupt_settles_as_waiting_without_retrying(self) -> None:
        """Asking again a question nobody answered is not a retry."""
        service = _service_yielding(_asked(kind="clarification"))
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.WAITING
        assert result.attempts == 1
        assert len(service.calls) == 1


class TestAQuestionIsReadFromTheStream:
    """The stream never carries a bare ``hitl_interrupt`` chunk. Measured
    2026-09-09: the reader waited for one, so a turn that stopped on a
    clarification settled as a SUCCESS with the tokens streamed before it."""

    async def _run(self, chunks: list[SimpleNamespace]) -> Any:
        service = _service_yielding(chunks)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            return await stream_instruction(_request())

    async def test_a_draft_critique_is_captured_whole(self) -> None:
        content = {"tool_name": "mcp_x_delete", "tool_args": {"target": "the archive"}}
        result = await self._run(
            _asked(
                draft_id="draft_1",
                draft_type="tool_call",
                draft_content=content,
                tool_name="mcp_x_delete",
                registry_ids=["draft_1"],
                step_id=None,
            )
        )

        assert result.outcome is RunOutcome.WAITING
        assert result.interrupt is not None
        assert result.interrupt.kind == "draft_critique"
        assert result.interrupt.question == "Je supprime « the archive » ?"
        assert result.interrupt.draft == {
            "draft_id": "draft_1",
            "draft_type": "tool_call",
            "draft_content": content,
            "tool_name": "mcp_x_delete",
        }

    async def test_a_batch_is_captured_whole(self) -> None:
        """Approving the first of three must never run the other two unseen:
        every draft of the batch travels with the interrupt."""
        first = {"to": "a@example.org", "body": "one"}
        second = {"to": "b@example.org", "body": "two"}
        result = await self._run(
            _asked(
                draft_id="draft_1",
                draft_type="email",
                draft_content=first,
                tool_name="send_email_tool",
                batch_total=2,
                batch_drafts=[
                    {"draft_id": "draft_1", "draft_type": "email", "draft_content": first},
                    {"draft_id": "draft_2", "draft_type": "email", "draft_content": second},
                ],
            )
        )
        assert result.interrupt is not None
        assert result.interrupt.draft is not None
        assert result.interrupt.draft["batch"] == [
            {"draft_id": "draft_1", "draft_type": "email", "draft_content": first},
            {"draft_id": "draft_2", "draft_type": "email", "draft_content": second},
        ]

    async def test_a_lone_draft_carries_no_batch(self) -> None:
        result = await self._run(
            _asked(draft_id="d", draft_type="email", draft_content={}, tool_name="t")
        )
        assert result.interrupt is not None
        assert result.interrupt.draft is not None
        assert "batch" not in result.interrupt.draft

    async def test_the_generated_question_wins_over_its_tokens(self) -> None:
        """The completion chunk carries the question the chat archives; the
        tokens are its streaming, possibly of a word-split fallback."""
        result = await self._run(_asked(kind="clarification"))
        assert result.interrupt is not None
        assert result.interrupt.question == "Je supprime « the archive » ?"

    async def test_the_tokens_are_the_question_when_nothing_else_names_it(self) -> None:
        chunks = _asked(kind="clarification")
        chunks[-1] = _chunk("hitl_interrupt_complete", "", {"message_id": "m-1"})
        result = await self._run(chunks)
        assert result.interrupt is not None
        assert result.interrupt.question == "Je supprime ?"

    async def test_any_other_question_carries_no_draft(self) -> None:
        result = await self._run(_asked(kind="clarification", question="Quel jour ?"))
        assert result.interrupt is not None
        assert result.interrupt.kind == "clarification"
        assert result.interrupt.draft is None

    async def test_the_metadata_alone_is_already_a_stop(self) -> None:
        """A stream that broke while generating the question still left the
        graph paused on it: the turn did not finish."""
        result = await self._run(_asked(kind="clarification")[:1])
        assert result.outcome is RunOutcome.WAITING
        assert result.interrupt is not None
        assert result.interrupt.question == ""

    async def test_what_was_streamed_before_the_question_is_kept(self) -> None:
        result = await self._run([_chunk("token", "Trouvé. "), *_asked(kind="clarification")])
        assert result.text == "Trouvé. "

    async def test_a_turn_that_never_asked_is_not_a_stop(self) -> None:
        result = await self._run([_chunk("token", "Done.")])
        assert result.outcome is RunOutcome.SUCCESS
        assert result.interrupt is None

    async def test_the_generator_is_consumed_to_its_end(self) -> None:
        """Its tail commits the token accounting; breaking out would skip it."""
        tail_reached = False

        async def stream(**_: Any) -> Any:
            nonlocal tail_reached
            for chunk in _asked(kind="clarification"):
                yield chunk
            tail_reached = True

        service = MagicMock()
        service.stream_chat_response = MagicMock(side_effect=stream)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request())
        assert tail_reached is True

    async def test_a_transient_failure_is_retried_with_a_fresh_session(self) -> None:
        """Attempt 1 may have half-run the graph; attempt 2 must not resume a
        broken checkpoint."""
        service = MagicMock()
        attempts: list[dict[str, Any]] = []

        def stream(**kwargs: Any) -> Any:
            attempts.append(kwargs)

            async def generator() -> Any:
                if len(attempts) == 1:
                    raise ConnectionError("provider blinked")
                yield _chunk("token", "second time lucky")

            return generator()

        service.stream_chat_response = MagicMock(side_effect=stream)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.SUCCESS
        assert result.attempts == 2
        assert attempts[0]["session_id"] != attempts[1]["session_id"]

    async def test_only_the_first_attempt_archives_the_question(self) -> None:
        """Archive-first persisted it once; a retry must not duplicate the row."""
        service = MagicMock()
        attempts: list[dict[str, Any]] = []

        def stream(**kwargs: Any) -> Any:
            attempts.append(kwargs)

            async def generator() -> Any:
                if len(attempts) == 1:
                    raise ConnectionError("provider blinked")
                yield _chunk("token", "ok")

            return generator()

        service.stream_chat_response = MagicMock(side_effect=stream)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request())
        assert attempts[0]["archive_user_message"] is True
        assert attempts[1]["archive_user_message"] is False

    async def test_exhausting_the_attempts_settles_as_failed(self) -> None:
        service = MagicMock()

        def stream(**_kwargs: Any) -> Any:
            async def generator() -> Any:
                raise ConnectionError("provider down")
                yield  # pragma: no cover - unreachable, makes it a generator

            return generator()

        service.stream_chat_response = MagicMock(side_effect=stream)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request(max_attempts=2))
        assert result.outcome is RunOutcome.FAILED
        assert result.attempts == 2
        assert result.error and "ConnectionError" in result.error

    async def test_a_non_transient_failure_is_not_retried(self) -> None:
        service = MagicMock()
        calls: list[int] = []

        def stream(**_kwargs: Any) -> Any:
            calls.append(1)

            async def generator() -> Any:
                raise ValueError("a bug, not a blip")
                yield  # pragma: no cover

            return generator()

        service.stream_chat_response = MagicMock(side_effect=stream)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request(max_attempts=3))
        assert result.outcome is RunOutcome.FAILED
        assert len(calls) == 1

    async def test_a_timeout_settles_as_failed_and_names_the_bound(self) -> None:
        service = MagicMock()

        def stream(**_kwargs: Any) -> Any:
            async def generator() -> Any:
                await asyncio.sleep(5)
                yield _chunk("token", "too late")

            return generator()

        service.stream_chat_response = MagicMock(side_effect=stream)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request(timeout_seconds=0, max_attempts=1))
        assert result.outcome is RunOutcome.FAILED
        assert result.error and "timed out" in result.error


class TestTheOriginTravelsWithTheTurn:
    async def test_the_run_publishes_its_origin_to_the_turn(self) -> None:
        """The archive enrichers and the gate both read it from there."""
        seen: list[str | None] = []

        def stream(**_kwargs: Any) -> Any:
            async def generator() -> Any:
                origin = current_origin()
                seen.append(origin.ticket_id if origin else None)
                yield _chunk("token", "ok")

            return generator()

        service = MagicMock()
        service.stream_chat_response = MagicMock(side_effect=stream)
        origin = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request(origin=origin))
        assert seen == ["t-1"]
        assert result.refusals == []

    async def test_the_origin_is_cleared_afterwards(self) -> None:
        """A leaked ContextVar would hide the NEXT chat turn from its reader."""
        service = _service_yielding([_chunk("token", "ok")])
        origin = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request(origin=origin))
        assert current_origin() is None

    async def test_a_refusal_collected_during_the_turn_reaches_the_result(self) -> None:
        """This is what lets the settle read a CODE instead of the prose."""
        from src.domains.agents.api.run_origin import record_refusal

        def stream(**_kwargs: Any) -> Any:
            async def generator() -> Any:
                record_refusal("send_email_tool", "confirmation_impossible_unattended")
                yield _chunk("token", "I could not send it.")

            return generator()

        service = MagicMock()
        service.stream_chat_response = MagicMock(side_effect=stream)
        origin = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request(origin=origin))
        assert result.refusals == [("send_email_tool", "confirmation_impossible_unattended")]
        assert result.outcome is RunOutcome.WAITING, "a refusal means it needs the person"

    async def test_without_an_origin_nothing_is_published(self) -> None:
        """The routine path keeps its behaviour: no origin, no stamp."""
        seen: list[Any] = []

        def stream(**_kwargs: Any) -> Any:
            async def generator() -> Any:
                seen.append(current_origin())
                yield _chunk("token", "ok")

            return generator()

        service = MagicMock()
        service.stream_chat_response = MagicMock(side_effect=stream)
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            await stream_instruction(_request())
        assert seen == [None]


class TestTheStreamsOwnRefusalIsRead:
    """An error chunk is a VERDICT, not silence.

    Measured 2026-09-10: the reader knew four chunk types and dropped every
    other, so a stream that refused — a spend ceiling, a provider failure, a
    question already pending on the conversation — left it with no token and
    no interrupt. The run then settled SUCCESS with an empty answer, which
    `plan_settle` reads as `workboard_empty_answer`: the ticket told the
    person LIA had nothing to say, burnt one of its ten runs, and scheduled
    no retry. An invented diagnosis (ADR-182) on the one line they read.

    The code is read from the chunk's METADATA, never from its sentence: that
    sentence is localized by the frontend and would change under us.
    """

    async def test_a_spend_ceiling_settles_as_quota_blocked(self) -> None:
        service = _service_yielding(
            [
                _chunk(
                    "error",
                    "Daily budget exhausted",
                    {"error_code": "instance_budget_exhausted", "limit": "instance_daily_budget"},
                )
            ]
        )
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.QUOTA_BLOCKED
        assert result.outcome is not RunOutcome.SUCCESS

    async def test_a_per_account_ceiling_is_the_same_verdict(self) -> None:
        service = _service_yielding(
            [_chunk("error", "Limit reached", {"error_code": "usage_limit_exceeded"})]
        )
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.QUOTA_BLOCKED

    async def test_a_refusal_is_never_retried(self) -> None:
        """A ceiling that refused this call refuses the next one too."""
        service = _service_yielding(
            [_chunk("error", "Limit reached", {"error_code": "usage_limit_exceeded"})]
        )
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.attempts == 1
        assert len(service.calls) == 1

    async def test_any_other_error_settles_as_a_failure_carrying_its_message(self) -> None:
        service = _service_yielding([_chunk("error", "provider unavailable", {})])
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.FAILED
        assert result.error is not None
        assert "provider unavailable" in result.error

    async def test_an_error_with_no_metadata_is_still_a_failure(self) -> None:
        """A chunk that carries no mapping must not crash the reader."""
        service = _service_yielding([_chunk("error", "boom")])
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.FAILED

    async def test_a_refusal_no_longer_reads_as_an_empty_answer(self) -> None:
        """The defect itself, stated as the property that closes it."""
        service = _service_yielding(
            [_chunk("error", "Limit reached", {"error_code": "usage_limit_exceeded"})]
        )
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert not (result.outcome is RunOutcome.SUCCESS and result.text == "")

    async def test_tokens_streamed_before_the_refusal_are_kept(self) -> None:
        """Whatever was said still travels — the verdict decides, not the text."""
        service = _service_yielding(
            [
                _chunk("token", "Je regarde"),
                _chunk("error", "Limit reached", {"error_code": "usage_limit_exceeded"}),
            ]
        )
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.QUOTA_BLOCKED
        assert result.text == "Je regarde"

    async def test_a_question_already_asked_still_wins(self) -> None:
        """A turn that delivered its question stopped ON the question."""
        service = _service_yielding(
            [*_asked(kind="clarification"), _chunk("error", "late", {"error_code": "whatever"})]
        )
        with patch("src.domains.agents.api.service.AgentService", return_value=service):
            result = await stream_instruction(_request())
        assert result.outcome is RunOutcome.WAITING
