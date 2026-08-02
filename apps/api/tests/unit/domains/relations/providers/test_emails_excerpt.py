"""An exchanged message shows a short EXCERPT, not just a subject line.

The subject alone rarely says what an exchange was about ("Re: Re: point"),
so the relationship card and the 360° now carry the provider's own preview.

Two invariants shape it:

- it is FREE. All three providers already return a preview with the search
  (Gmail ``snippet``, Graph ``bodyPreview``, Apple through its normalizer);
  fetching the full body would cost one extra call PER MESSAGE, which the
  window and the cap exist to avoid;
- it is BOUNDED, and the bound is published (ADR-184): whatever the provider
  returns, the excerpt is cut to ``relations_provider_email_excerpt_max_chars``.

A message with no preview carries NO excerpt at all — never an empty string,
which would render as a blank line pretending the message was empty.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.relations.providers.client import CategoryClient
from src.domains.relations.providers.emails import fetch_exchanged_emails

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NOW = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
BASE_MS = int(NOW.timestamp() * 1000)


def _message(msg_id: str, **fields: object) -> dict:
    return {"id": msg_id, "subject": "Sujet", "internalDate": str(BASE_MS), **fields}


async def _fetch(messages: list[dict]) -> list:
    import contextlib

    async def _search(query: str, **kwargs: object) -> dict:
        return {"messages": messages if query.startswith("from:") else []}

    client = SimpleNamespace(search_emails=AsyncMock(side_effect=_search))

    @contextlib.asynccontextmanager
    async def _open(category: str, user_id: object):
        yield CategoryClient(client=client, connector_type=None, session=None)

    with patch("src.domains.relations.providers.emails.open_category_client", _open):
        return await fetch_exchanged_emails(
            USER_ID, addresses=["gerard@x.com"], limit=10, window_days=365, now=NOW
        )


class TestTheExcerptIsCarried:
    async def test_snippet_becomes_the_excerpt(self) -> None:
        found = await _fetch([_message("m1", snippet="On se voit jeudi 14h ?")])

        assert found[0].excerpt == "On se voit jeudi 14h ?"

    async def test_whitespace_is_collapsed(self) -> None:
        """Providers pad previews with newlines and non-breaking spaces; a card
        line must not inherit them."""
        found = await _fetch([_message("m1", snippet="On se voit\n\n  jeudi 14h ?")])

        assert found[0].excerpt == "On se voit jeudi 14h ?"


class TestTheBoundIsApplied:
    async def test_excerpt_is_cut_to_the_published_bound(self) -> None:
        cap = settings.relations_provider_email_excerpt_max_chars
        found = await _fetch([_message("m1", snippet="x" * (cap + 200))])

        assert found[0].excerpt is not None
        assert len(found[0].excerpt) <= cap

    async def test_a_short_excerpt_is_untouched(self) -> None:
        found = await _fetch([_message("m1", snippet="court")])

        assert found[0].excerpt == "court"


class TestNothingIsFabricated:
    @pytest.mark.parametrize("snippet", [None, "", "   ", "\n\n"])
    async def test_no_preview_means_no_excerpt(self, snippet: str | None) -> None:
        """Absent, never an empty line: a blank excerpt would read as
        'this message had no content', which the provider never said."""
        found = await _fetch([_message("m1", snippet=snippet)])

        assert found[0].excerpt is None

    async def test_the_message_is_still_listed_without_a_preview(self) -> None:
        found = await _fetch([_message("m1", snippet=None)])

        assert len(found) == 1
        assert found[0].subject == "Sujet"
