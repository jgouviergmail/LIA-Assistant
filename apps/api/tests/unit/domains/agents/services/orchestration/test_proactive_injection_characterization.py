"""What a proactive notification becomes when the person answers it.

The whole anticipated-moments programme rests on one mechanism that nothing
tested: ``OrchestrationService._inject_proactive_messages``. A notification is
archived in ``conversation_messages`` and never written to the LangGraph
checkpoint, so without this bridge the router, the planner, the response node
and the six post-response extractions would all read « oui, très bien » with no
idea what question it answers.

Measured 2026-09-11: the mechanism is complete and correct, and it had zero
tests. These pin it BEFORE anything is built on top of it — a load-bearing
mechanism nobody holds is one that can disappear without a sound.

Four properties, and each one is load-bearing for a different reason:

- **the notification lands in the state**, carrying a marker the prompt layers
  can read;
- **it lands BEFORE the person's message**, because a question that follows its
  answer is not a conversation (pinned structurally, on the source, since the
  ordering belongs to ``load_or_create_state`` and not to the injection);
- **a hidden row never lands** — since ADR-276 a conversation holds rows a
  person must never be shown, and re-injecting a ticket run's synthetic question
  as if LIA had said it to them is the exact failure mode ``visible_only``
  exists to prevent;
- **the bounds come from the settings**, never from a literal.
"""

from __future__ import annotations

import ast
import inspect
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.core.config import settings
from src.domains.agents.services.orchestration.service import OrchestrationService

pytestmark = pytest.mark.unit

_DB_CONTEXT = "src.infrastructure.database.get_db_context"
_REPOSITORY = "src.domains.conversations.repository.ConversationRepository"


def _db_ctx():
    """An async context manager yielding a throwaway session."""

    @asynccontextmanager
    async def _ctx():
        yield MagicMock()

    return _ctx


def _row(content: str, *, metadata: dict | None, created_at: datetime | None = None):
    """One archived assistant row as the repository hands it back."""
    return SimpleNamespace(
        content=content,
        message_metadata=metadata,
        created_at=created_at or datetime(2026, 9, 11, 8, 0, tzinfo=UTC),
    )


def _repo(rows: list) -> MagicMock:
    repo = MagicMock()
    repo.get_proactive_messages_after = AsyncMock(return_value=rows)
    return repo


async def _inject(state: dict, rows: list, *, checkpoint: str | None) -> tuple[int, MagicMock]:
    """Run the injection against a mocked repository, return (count, repo)."""
    repo = _repo(rows)
    with (
        patch(_DB_CONTEXT, new=_db_ctx()),
        patch(_REPOSITORY, return_value=repo),
    ):
        injected = await OrchestrationService()._inject_proactive_messages(
            state=state,
            conversation_id=uuid4(),
            checkpoint_created_at=checkpoint,
            run_id="run-characterization",
        )
    return injected, repo


class TestTheNotificationReachesTheGraph:
    """A question LIA asked out of turn must be readable when the answer comes."""

    async def test_an_archived_notification_becomes_an_ai_message(self) -> None:
        state: dict = {"messages": []}

        injected, _ = await _inject(
            state,
            [
                _row(
                    "Ta réunion budget s'est bien passée ?",
                    metadata={"type": "proactive_heartbeat"},
                )
            ],
            checkpoint="2026-09-11T07:00:00+00:00",
        )

        assert injected == 1
        assert len(state["messages"]) == 1
        message = state["messages"][0]
        assert isinstance(message, AIMessage)
        assert message.content == "Ta réunion budget s'est bien passée ?"

    async def test_the_message_carries_its_provenance(self) -> None:
        """The marker is what lets a later layer tell LIA's own words apart."""
        state: dict = {"messages": []}

        await _inject(
            state,
            [_row("…", metadata={"type": "proactive_workboard"})],
            checkpoint="2026-09-11T07:00:00+00:00",
        )

        kwargs = state["messages"][0].additional_kwargs
        assert kwargs["proactive_notification"] is True
        assert kwargs["proactive_type"] == "proactive_workboard"
        assert kwargs["original_created_at"] is not None

    async def test_metadata_absent_degrades_rather_than_raising(self) -> None:
        state: dict = {"messages": []}

        injected, _ = await _inject(
            state, [_row("…", metadata=None)], checkpoint="2026-09-11T07:00:00+00:00"
        )

        assert injected == 1
        assert state["messages"][0].additional_kwargs["proactive_type"] == ""

    async def test_history_already_in_the_state_is_preserved(self) -> None:
        """The injection appends; it never replaces what the checkpoint held."""
        earlier = HumanMessage(content="salut")
        state: dict = {"messages": [earlier]}

        await _inject(
            state,
            [_row("…", metadata={"type": "proactive_heartbeat"})],
            checkpoint="2026-09-11T07:00:00+00:00",
        )

        assert state["messages"][0] is earlier
        assert isinstance(state["messages"][1], AIMessage)


class TestTheBoundsComeFromTheSettings:
    """A number a test re-declares is a number that silently drifts."""

    async def test_the_repository_is_asked_for_the_configured_page(self) -> None:
        state: dict = {"messages": []}

        _, repo = await _inject(state, [], checkpoint="2026-09-11T07:00:00+00:00")

        kwargs = repo.get_proactive_messages_after.await_args.kwargs
        assert kwargs["limit"] == settings.proactive_inject_max_messages

    async def test_the_cutoff_is_the_checkpoint_when_there_is_one(self) -> None:
        state: dict = {"messages": []}

        _, repo = await _inject(state, [], checkpoint="2026-09-11T07:00:00+00:00")

        cutoff = repo.get_proactive_messages_after.await_args.kwargs["after_timestamp"]
        assert cutoff == datetime(2026, 9, 11, 7, 0, tzinfo=UTC)

    async def test_a_naive_checkpoint_is_read_as_utc(self) -> None:
        """A naive timestamp compared against timezone-aware rows would raise."""
        state: dict = {"messages": []}

        _, repo = await _inject(state, [], checkpoint="2026-09-11T07:00:00")

        cutoff = repo.get_proactive_messages_after.await_args.kwargs["after_timestamp"]
        assert cutoff.tzinfo is not None
        assert cutoff == datetime(2026, 9, 11, 7, 0, tzinfo=UTC)

    async def test_without_a_checkpoint_the_lookback_window_applies(self) -> None:
        state: dict = {"messages": []}
        before = datetime.now(UTC)

        _, repo = await _inject(state, [], checkpoint=None)

        cutoff = repo.get_proactive_messages_after.await_args.kwargs["after_timestamp"]
        expected = before - timedelta(hours=settings.proactive_inject_lookback_hours)
        # One second of slack: the implementation reads its own clock.
        assert abs((cutoff - expected).total_seconds()) < 1.0


class TestNothingBreaksTheTurn:
    """The bridge is a bonus; it may never cost the person their answer."""

    async def test_a_repository_failure_returns_zero_and_leaves_the_state_usable(
        self,
    ) -> None:
        state: dict = {"messages": []}
        repo = MagicMock()
        repo.get_proactive_messages_after = AsyncMock(side_effect=RuntimeError("db down"))

        with (
            patch(_DB_CONTEXT, new=_db_ctx()),
            patch(_REPOSITORY, return_value=repo),
        ):
            injected = await OrchestrationService()._inject_proactive_messages(
                state=state,
                conversation_id=uuid4(),
                checkpoint_created_at=None,
                run_id="run-characterization",
            )

        assert injected == 0
        assert state["messages"] == []

    async def test_nothing_to_inject_is_not_an_error(self) -> None:
        state: dict = {"messages": []}

        injected, _ = await _inject(state, [], checkpoint="2026-09-11T07:00:00+00:00")

        assert injected == 0
        assert state["messages"] == []


class TestTheQuestionComesBeforeItsAnswer:
    """Ordering belongs to ``load_or_create_state``, so it is pinned there.

    Reading it off the source rather than off a run is deliberate: the append of
    the person's ``HumanMessage`` and the injection are two statements in one
    method, and only their ORDER makes the exchange readable. A behavioural test
    would need the whole turn; an AST test states the invariant exactly.
    """

    @staticmethod
    def _load_or_create_state_body() -> ast.FunctionDef:
        source = Path(inspect.getfile(OrchestrationService)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "load_or_create_state":
                return node  # type: ignore[return-value]
        raise AssertionError("load_or_create_state not found — was it renamed?")

    def test_the_injection_precedes_the_user_message_append(self) -> None:
        body = self._load_or_create_state_body()

        injection_lines = [
            node.lineno
            for node in ast.walk(body)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_inject_proactive_messages"
        ]
        append_lines = [
            node.lineno
            for node in ast.walk(body)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and any(
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "HumanMessage"
                for arg in node.args
            )
        ]

        assert injection_lines, "load_or_create_state no longer injects proactive messages"
        assert append_lines, "load_or_create_state no longer appends the user message"
        assert max(injection_lines) < min(append_lines), (
            "the proactive notification must be injected BEFORE the person's message, "
            "or LIA reads the answer before its own question"
        )


class TestAHiddenRowIsNeverReInjected:
    """ADR-276 rows exist to stay unseen; re-injecting one would undo that."""

    def test_the_statement_excludes_hidden_rows(self) -> None:
        """The narrowing is in the WHERE clause, not in a docstring.

        Asserted on ``whereclause`` rather than on the compiled string:
        ``select(ConversationMessage)`` names every column, so the word
        « hidden » appears in the SELECT list whether or not anything filters on
        it — a substring assertion would pass on a statement that filters
        nothing.
        """
        from sqlalchemy import select

        from src.domains.conversations.message_reads import visible_only
        from src.domains.conversations.models import ConversationMessage

        narrowed = visible_only(select(ConversationMessage), include_hidden=False)
        widened = visible_only(select(ConversationMessage), include_hidden=True)

        assert widened.whereclause is None
        assert narrowed.whereclause is not None
        assert "hidden" in str(narrowed.whereclause)

    def test_the_repository_narrows_by_default(self) -> None:
        """The default matters: every caller but the export relies on it."""
        from src.domains.conversations.repository import ConversationRepository

        signature = inspect.signature(ConversationRepository.get_proactive_messages_after)
        assert signature.parameters["include_hidden"].default is False
