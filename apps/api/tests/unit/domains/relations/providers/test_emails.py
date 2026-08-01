"""Mail exchanged with one person — and the provider asymmetries it must survive.

The shape of this fetcher is dictated by one finding: a single Gmail-style
query cannot express "from OR to OR cc" across the three providers.

- Apple: ``convert_imap_query`` builds an **AND** of criteria, so ``from:x
  to:x`` matches nothing;
- Microsoft: ``build_search_filter`` defaults to the **inbox** folder, so sent
  mail is invisible unless ``in:sent`` is asked for explicitly;
- Gmail: space-separated operators are ANDed too.

So the exchange is THREE searches per address — received, sent-to, sent-cc —
each carrying its own direction. Being in copy is being written to: dropping
``cc`` would hide every thread where the person was not the first recipient.

The window bounds RELEVANCE (and what the provider scans), never quota: a
search costs one call whatever it spans.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.relations.providers.client import CategoryClient
from src.domains.relations.providers.emails import fetch_exchanged_emails

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NOW = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
BASE_MS = int(NOW.timestamp() * 1000)


def _message(msg_id: str, *, subject: str = "Sujet", offset_minutes: int = 0) -> dict:
    return {
        "id": msg_id,
        "subject": subject,
        "internalDate": str(BASE_MS + offset_minutes * 60_000),
    }


def _patched(by_query: dict[str, list[dict]] | None = None):
    """Patch the mail client; each query answers with its own message list."""
    import contextlib

    async def _search(query: str, **kwargs):
        return {"messages": (by_query or {}).get(query, [])}

    client = SimpleNamespace(search_emails=AsyncMock(side_effect=_search))

    @contextlib.asynccontextmanager
    async def _open(category, user_id):
        yield CategoryClient(client=client, connector_type=None, session=None)

    return patch("src.domains.relations.providers.emails.open_category_client", _open), client


async def _fetch(by_query=None, addresses=("gerard@x.com",), limit=10, window_days=365):
    patcher, client = _patched(by_query)
    with patcher:
        found = await fetch_exchanged_emails(
            USER_ID,
            addresses=list(addresses),
            limit=limit,
            window_days=window_days,
            now=NOW,
        )
    return found, client


def _queries(client) -> list[str]:
    return [call.args[0] for call in client.search_emails.await_args_list]


class TestThreeSearchesPerAddress:
    """Received, sent-to and sent-cc — anything less loses part of the exchange."""

    async def test_asks_each_direction_on_its_own_terms(self) -> None:
        _, client = await _fetch()
        assert _queries(client) == [
            "from:gerard@x.com after:2025/07/30",
            "in:sent to:gerard@x.com after:2025/07/30",
            "in:sent cc:gerard@x.com after:2025/07/30",
        ]

    async def test_being_in_copy_counts_as_written_to(self) -> None:
        """A thread where the person was only in copy is still an exchange."""
        found, _ = await _fetch({"in:sent cc:gerard@x.com after:2025/07/30": [_message("copied")]})
        assert [(email.id, email.direction) for email in found] == [("copied", "sent")]

    async def test_labels_each_result_with_the_direction_that_produced_it(self) -> None:
        found, _ = await _fetch(
            {
                "from:gerard@x.com after:2025/07/30": [_message("r1", offset_minutes=10)],
                "in:sent to:gerard@x.com after:2025/07/30": [_message("s1", offset_minutes=20)],
            }
        )
        assert [(email.id, email.direction) for email in found] == [
            ("s1", "sent"),  # newest first
            ("r1", "received"),
        ]

    async def test_every_address_of_the_card_is_asked(self) -> None:
        _, client = await _fetch(addresses=("home@x.com", "work@acme.com"))
        assert len(_queries(client)) == 6  # 3 per address
        assert _queries(client)[3].startswith("from:work@acme.com")


class TestWindow:
    async def test_the_window_is_expressed_as_a_portable_after_operator(self) -> None:
        """`after:` is one of the operators ALL THREE converters understand —
        Apple maps it to date_gte, Microsoft to a receivedDateTime filter."""
        _, client = await _fetch(window_days=30)
        assert all(query.endswith("after:2026/06/30") for query in _queries(client))


class TestMerging:
    async def test_newest_first_across_addresses_and_directions(self) -> None:
        found, _ = await _fetch(
            {
                "from:a@x.com after:2025/07/30": [_message("old", offset_minutes=0)],
                "in:sent to:b@x.com after:2025/07/30": [_message("new", offset_minutes=60)],
            },
            addresses=("a@x.com", "b@x.com"),
        )
        assert [email.id for email in found] == ["new", "old"]

    async def test_one_message_reached_twice_is_listed_once(self) -> None:
        """A thread can answer both `to:` and `cc:`, or two addresses at once."""
        found, _ = await _fetch(
            {
                "in:sent to:a@x.com after:2025/07/30": [_message("dup")],
                "in:sent cc:a@x.com after:2025/07/30": [_message("dup")],
            },
            addresses=("a@x.com",),
        )
        assert [email.id for email in found] == ["dup"]

    async def test_the_cap_keeps_the_newest(self) -> None:
        found, _ = await _fetch(
            {
                "from:a@x.com after:2025/07/30": [
                    _message("old", offset_minutes=0),
                    _message("mid", offset_minutes=30),
                    _message("new", offset_minutes=60),
                ]
            },
            addresses=("a@x.com",),
            limit=2,
        )
        assert [email.id for email in found] == ["new", "mid"]

    async def test_a_message_without_a_usable_date_still_appears_last(self) -> None:
        """Dropping it would hide real correspondence over a header quirk."""
        found, _ = await _fetch(
            {
                "from:a@x.com after:2025/07/30": [
                    {"id": "nodate", "subject": "Sans date"},
                    _message("dated"),
                ]
            },
            addresses=("a@x.com",),
        )
        assert [email.id for email in found] == ["dated", "nodate"]
        assert found[1].occurred_at is None


class TestBoundaries:
    async def test_no_address_asks_nothing(self) -> None:
        patcher, client = _patched()
        with patcher:
            assert (
                await fetch_exchanged_emails(
                    USER_ID, addresses=[], limit=10, window_days=365, now=NOW
                )
                == []
            )
        client.search_emails.assert_not_awaited()

    async def test_an_exhausted_retry_never_loses_the_others(self) -> None:
        """`MaxRetriesExceededError` is THE shape a tired provider takes here.

        The briefing catches it next to TimeoutError and httpx.HTTPError for
        the same reason; missing it would let one exhausted search blank an
        exchange whose other halves answered perfectly.
        """
        import contextlib

        from src.core.exceptions import MaxRetriesExceededError

        async def _search(query: str, **kwargs):
            if "cc:" in query:
                raise MaxRetriesExceededError("search_emails", 3)
            return {"messages": [_message("r1")] if query.startswith("from:") else []}

        client = SimpleNamespace(search_emails=AsyncMock(side_effect=_search))

        @contextlib.asynccontextmanager
        async def _open(category, user_id):
            yield CategoryClient(client=client, connector_type=None, session=None)

        with patch("src.domains.relations.providers.emails.open_category_client", _open):
            found = await fetch_exchanged_emails(
                USER_ID, addresses=["a@x.com"], limit=10, window_days=365, now=NOW
            )

        assert [email.id for email in found] == ["r1"]

    async def test_one_failing_search_never_loses_the_others(self) -> None:
        """A provider that refuses `cc:` must not blank a readable exchange."""
        import contextlib

        async def _search(query: str, **kwargs):
            if "cc:" in query:
                raise TimeoutError("provider said no")
            return {"messages": [_message("r1")] if query.startswith("from:") else []}

        client = SimpleNamespace(search_emails=AsyncMock(side_effect=_search))

        @contextlib.asynccontextmanager
        async def _open(category, user_id):
            yield CategoryClient(client=client, connector_type=None, session=None)

        with patch("src.domains.relations.providers.emails.open_category_client", _open):
            found = await fetch_exchanged_emails(
                USER_ID, addresses=["a@x.com"], limit=10, window_days=365, now=NOW
            )

        assert [email.id for email in found] == ["r1"]

    async def test_a_subject_less_message_says_so_rather_than_rendering_blank(self) -> None:
        found, _ = await _fetch(
            {"from:a@x.com after:2025/07/30": [{"id": "m", "subject": "  "}]},
            addresses=("a@x.com",),
        )
        assert found[0].subject == "(no subject)"
