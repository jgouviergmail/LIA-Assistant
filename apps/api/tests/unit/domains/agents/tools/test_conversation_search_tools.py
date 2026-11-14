"""The conversation search tool — what was SAID, word for word, in any discussion.

Long-term memory holds what LIA distilled; this lookup returns the real messages,
cut around the words, through the door the history search field asks too
(``conversations.discussion_search``, proven on PostgreSQL). Here: what the tool
hands the model, the run's own question left out, the person's clock, the bounds
the manifest publishes, and a refusal that never reads as « never said ».
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import CONVERSATION_SEARCH_MAX_LENGTH, CONVERSATION_SEARCH_MIN_LENGTH
from src.core.conversation_target import ConversationKind
from src.core.field_names import FIELD_RUN_ID
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.memory.catalogue_manifests import (
    MEMORY_AGENT_MANIFEST,
    search_conversations_catalogue_manifest,
)
from src.domains.agents.tools import conversation_search_tools
from src.domains.agents.tools.conversation_search_tools import passage_excerpt
from src.domains.conversations.discussion_search import DiscussionHit, DiscussionSearchPage

pytestmark = pytest.mark.unit

_RUN = "run-asking"


def _hit(content: str, **over: object) -> DiscussionHit:
    base: dict[str, object] = {
        "message_id": uuid4(),
        "role": "user",
        "content": content,
        "created_at": datetime(2026, 10, 3, 12, 15, tzinfo=UTC),
        "conversation_id": uuid4(),
        "conversation_kind": ConversationKind.MAIN,
        "conversation_title": None,
        "conversation_revision": 0,
    }
    return DiscussionHit(**{**base, **over})  # type: ignore[arg-type]


def _runtime(zone: str = "Europe/Paris") -> SimpleNamespace:
    context = LiaRuntimeContext(user_id=uuid4(), thread_id="t", conversation_id="t", timezone=zone)
    return SimpleNamespace(context=context, config={"metadata": {FIELD_RUN_ID: _RUN}})


async def _call(
    page: DiscussionSearchPage, query: str = "devis", **kwargs: object
) -> tuple[object, AsyncMock]:
    door = AsyncMock(return_value=page)
    config = SimpleNamespace(user_id=str(uuid4()))
    with (
        patch.object(conversation_search_tools, "validate_runtime_config", return_value=config),
        patch.object(conversation_search_tools, "search_discussions", door),
        patch.object(conversation_search_tools, "get_db_context", _no_session),
    ):
        output = await conversation_search_tools.search_conversations_tool.coroutine(
            query=query, runtime=_runtime(), **kwargs
        )
    return output, door


class _NoSession:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _no_session() -> _NoSession:
    return _NoSession()


class TestPassages:
    async def test_the_real_messages_reach_the_model_cut_around_the_words(self) -> None:
        annex = _hit(
            "Le devis de la toiture est arrivé",
            role="assistant",
            conversation_kind=ConversationKind.SECONDARY,
            conversation_title="Travaux",
        )
        output, _door = await _call(
            DiscussionSearchPage(hits=[annex, _hit("Mon devis")], has_more=False)
        )

        assert output.success is True
        assert output.structured_data["count"] == 2
        assert output.structured_data["more"] is False
        first, second = output.structured_data["passages"]
        assert first == {
            "discussion": "Travaux",
            "said_by": "assistant",
            # The person's clock: 12:15 UTC is 14:15 in Paris in October.
            "said_at": "2026-10-03T14:15+02:00",
            "excerpt": "Le devis de la toiture est arrivé",
        }
        assert (second["discussion"], second["said_by"]) == ("main", "person")

    async def test_the_question_of_this_run_is_never_its_own_answer(self) -> None:
        _output, door = await _call(DiscussionSearchPage(hits=[], has_more=False))

        assert door.await_args.kwargs["excluding_run"] == _RUN

    async def test_an_empty_result_is_a_success_that_says_nothing_was_said(self) -> None:
        output, _door = await _call(DiscussionSearchPage(hits=[], has_more=False))

        assert output.success is True
        assert output.structured_data == {"passages": [], "count": 0, "more": False}
        assert "no" in output.message.lower()

    async def test_more_matches_than_returned_are_said_never_hidden(self) -> None:
        output, _door = await _call(DiscussionSearchPage(hits=[_hit("devis")], has_more=True))

        assert output.structured_data["more"] is True
        assert "more" in output.message.lower()

    @pytest.mark.parametrize(
        "query",
        [
            "",
            " ",
            "d" * (CONVERSATION_SEARCH_MIN_LENGTH - 1),
            "d" * (CONVERSATION_SEARCH_MAX_LENGTH + 1),
        ],
    )
    async def test_words_out_of_the_published_bounds_are_refused(self, query: str) -> None:
        output, door = await _call(DiscussionSearchPage(hits=[], has_more=False), query=query)

        assert output.success is False
        assert output.error_code == "INVALID_INPUT"
        door.assert_not_awaited()


class TestBounds:
    async def test_max_results_is_clamped_to_the_published_ceiling(self) -> None:
        ceiling = settings.conversation_search_tool_max_results

        _output, door = await _call(
            DiscussionSearchPage(hits=[], has_more=False), max_results=ceiling + 50
        )

        assert door.await_args.kwargs["limit"] == ceiling

    def test_the_manifest_publishes_what_the_tool_enforces(self) -> None:
        params = {p.name: p for p in search_conversations_catalogue_manifest.parameters}
        query = {c.kind: c.value for c in params["query"].constraints}
        ceiling = {c.kind: c.value for c in params["max_results"].constraints}

        assert query == {
            "min_length": CONVERSATION_SEARCH_MIN_LENGTH,
            "max_length": CONVERSATION_SEARCH_MAX_LENGTH,
        }
        assert ceiling == {"minimum": 1, "maximum": settings.conversation_search_tool_max_results}

    def test_the_memory_agent_offers_it(self) -> None:
        assert "search_conversations_tool" in MEMORY_AGENT_MANIFEST.tools


class TestExcerpt:
    def test_a_short_message_is_whole(self) -> None:
        assert passage_excerpt("Le devis est arrivé.", "devis") == "Le devis est arrivé."

    def test_a_long_message_is_cut_around_the_words_found_without_accents(self) -> None:
        text = "début " * 80 + "la RÉUNION de lundi" + " fin" * 80

        excerpt = passage_excerpt(text, "reunion", width=60)

        assert "RÉUNION" in excerpt
        assert excerpt.startswith("…") and excerpt.endswith("…")
        assert len(excerpt) <= 62

    def test_markup_never_reaches_the_model(self) -> None:
        excerpt = passage_excerpt(
            '<div class="lia-card"><p>Le <b>devis</b> signé</p></div>', "devis"
        )

        assert "<" not in excerpt and "devis" in excerpt

    def test_words_that_cannot_be_located_give_the_beginning(self) -> None:
        excerpt = passage_excerpt("x" * 500, "devis", width=40)

        assert excerpt == "x" * 39 + "…"
