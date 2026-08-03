"""The suggestions endpoint, at its HTTP boundary.

Returning nothing is a normal answer here, not an error: the empty chat must
never wait on a connector, and a suggestion nobody can act on is worse than the
generic example it would replace.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.chat.router import get_chat_suggestions
from src.domains.chat.suggestions import ChatSuggestion

pytestmark = pytest.mark.unit


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


class TestSuggestionsRoute:
    async def test_projects_id_and_params_verbatim(self) -> None:
        built = [ChatSuggestion(id="next_event", params={"subject": "Revue produit"})]
        with patch(
            "src.domains.chat.router.build_chat_suggestions", new=AsyncMock(return_value=built)
        ):
            response = await get_chat_suggestions(current_user=_user())

        assert [(s.id, s.params) for s in response.suggestions] == [
            ("next_event", {"subject": "Revue produit"})
        ]

    async def test_an_empty_answer_is_a_success_not_an_error(self) -> None:
        """A cold cache is the ordinary case; the client falls back to starters."""
        with patch(
            "src.domains.chat.router.build_chat_suggestions", new=AsyncMock(return_value=[])
        ):
            response = await get_chat_suggestions(current_user=_user())

        assert response.suggestions == []

    async def test_the_caller_is_the_only_subject(self) -> None:
        user = _user()
        with patch(
            "src.domains.chat.router.build_chat_suggestions", new=AsyncMock(return_value=[])
        ) as build:
            await get_chat_suggestions(current_user=user)

        assert build.await_args.args[0] is user

    async def test_a_suggestion_carrying_no_params_serialises_as_empty(self) -> None:
        with patch(
            "src.domains.chat.router.build_chat_suggestions",
            new=AsyncMock(return_value=[ChatSuggestion(id="important_mails")]),
        ):
            response = await get_chat_suggestions(current_user=_user())

        assert response.suggestions[0].params == {}
