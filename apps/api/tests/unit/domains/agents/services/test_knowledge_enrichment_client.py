"""The enrichment's Brave client lives for ONE search.

The service is a process singleton. Its clients used to be cached by person and
language for the life of the process: a rotated Brave key kept being used until
a restart, no client was ever closed, and the cache grew without bound.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.domains.agents.services.knowledge_enrichment_service import (
    KnowledgeContext,
    KnowledgeEnrichmentService,
)

pytestmark = pytest.mark.unit

_CLIENT = "src.domains.connectors.clients.brave_search_client.BraveSearchClient"
_RECORD = "src.domains.agents.effects.treatments.record_treatment"


def _deps(*api_keys: str) -> MagicMock:
    """Tool dependencies whose connector returns these keys, one per call."""
    connectors = MagicMock()
    connectors.get_api_key_credentials = AsyncMock(
        side_effect=[SimpleNamespace(api_key=key) for key in api_keys]
    )
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=connectors)
    return deps


def _clients(search: AsyncMock) -> tuple[MagicMock, list[MagicMock]]:
    made: list[MagicMock] = []

    def _make(**kwargs: object) -> MagicMock:
        client = MagicMock()
        client.api_key = kwargs["api_key"]
        client.search = search
        client.close = AsyncMock()
        made.append(client)
        return client

    return MagicMock(side_effect=_make), made


async def _search(
    service: KnowledgeEnrichmentService, deps: MagicMock, person: UUID
) -> KnowledgeContext | None:
    return await service._call_api(
        keyword="solar eclipse",
        endpoint="web",
        is_news_query=False,
        user_id=person,
        language="it",
        tool_deps=deps,
        redis=None,
    )


def _succeeded(record: MagicMock) -> list[bool]:
    return [call.kwargs["succeeded"] for call in record.call_args_list]


async def test_each_search_opens_its_own_client_and_closes_it() -> None:
    """The SAME person, in the same language, twice: the old per-person cache
    would have served the first client — and the first key — again."""
    service = KnowledgeEnrichmentService()
    factory, made = _clients(AsyncMock(return_value={"web": {"results": []}}))
    person = uuid4()

    with patch(_CLIENT, factory), patch(_RECORD) as record:
        await _search(service, _deps("old-key"), person)
        await _search(service, _deps("new-key"), person)

    assert [client.api_key for client in made] == ["old-key", "new-key"]
    for client in made:
        client.close.assert_awaited_once()
    assert _succeeded(record) == [True, True]


async def test_a_refusal_the_client_swallowed_is_recorded_failed() -> None:
    """The client answers None for a 403, a 429, a 5xx or a network error —
    its None-on-error contract: a return is not an answer."""
    service = KnowledgeEnrichmentService()
    factory, made = _clients(AsyncMock(return_value=None))

    with patch(_CLIENT, factory), patch(_RECORD) as record:
        result = await _search(service, _deps("key"), uuid4())

    assert result is None
    made[0].close.assert_awaited_once()
    assert _succeeded(record) == [False]


async def test_the_search_is_recorded_before_its_client_closes() -> None:
    """A close that fails, or a second cancellation during it, never loses the row."""
    order: list[str] = []
    service = KnowledgeEnrichmentService()
    factory, made = _clients(AsyncMock(return_value={"web": {"results": []}}))

    with patch(_CLIENT, factory), patch(_RECORD) as record:
        record.side_effect = lambda *_a, **_k: order.append("record")
        original = factory.side_effect

        def _tracked(**kwargs: object) -> MagicMock:
            client = original(**kwargs)
            client.close = AsyncMock(side_effect=lambda: order.append("close"))
            return client

        factory.side_effect = _tracked
        await _search(service, _deps("key"), uuid4())

    assert order == ["record", "close"]


async def test_a_close_that_fails_keeps_the_answer() -> None:
    service = KnowledgeEnrichmentService()
    answer = {
        "web": {"results": [{"title": "Eclipse", "url": "https://example.org", "description": "d"}]}
    }
    factory, made = _clients(AsyncMock(return_value=answer))

    with patch(_CLIENT, factory), patch(_RECORD) as record:
        original = factory.side_effect

        def _failing_close(**kwargs: object) -> MagicMock:
            client = original(**kwargs)
            client.close = AsyncMock(side_effect=RuntimeError("pool gone"))
            return client

        factory.side_effect = _failing_close
        result = await _search(service, _deps("key"), uuid4())

    assert result is not None
    assert _succeeded(record) == [True]


async def test_a_failed_search_still_closes_its_client() -> None:
    service = KnowledgeEnrichmentService()
    factory, made = _clients(AsyncMock(side_effect=RuntimeError("provider down")))

    with patch(_CLIENT, factory), patch(_RECORD) as record:
        result = await _search(service, _deps("key"), uuid4())

    assert result is None
    made[0].close.assert_awaited_once()
    assert _succeeded(record) == [False]


async def _never_answers(**_kwargs: object) -> dict[str, object]:
    await asyncio.Event().wait()
    raise AssertionError("unreachable: nothing sets the event")


async def test_a_search_past_its_timeout_is_closed_and_recorded_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "brave_search_enrichment_timeout_seconds", 0.01)
    service = KnowledgeEnrichmentService()
    factory, made = _clients(AsyncMock(side_effect=_never_answers))

    with patch(_CLIENT, factory), patch(_RECORD) as record:
        result = await _search(service, _deps("key"), uuid4())

    assert result is None
    made[0].close.assert_awaited_once()
    assert _succeeded(record) == [False]


async def test_a_cancelled_search_is_closed_and_recorded_failed() -> None:
    """``CancelledError`` is no ``Exception``: it used to be recorded as a success."""
    started = asyncio.Event()

    async def _starts_then_hangs(**_kwargs: object) -> dict[str, object]:
        started.set()
        return await _never_answers()

    service = KnowledgeEnrichmentService()
    factory, made = _clients(AsyncMock(side_effect=_starts_then_hangs))

    with patch(_CLIENT, factory), patch(_RECORD) as record:
        search = asyncio.create_task(_search(service, _deps("key"), uuid4()))
        await started.wait()
        search.cancel()
        with pytest.raises(asyncio.CancelledError):
            await search

    made[0].close.assert_awaited_once()
    assert _succeeded(record) == [False]
