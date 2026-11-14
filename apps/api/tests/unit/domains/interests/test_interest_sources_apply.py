"""An interest sweep asks a source only when it would ask its service (lot 18).

The sweep recorded a consultation for every source it ran — the Brave source of
a person with no Brave key too, which asked nothing and was filed as « Brave
consulted ». Each source now says first whether it would ask its service for this
person (``applies``); one that would not is skipped and files nothing.

The instance's SearXNG joins the sources on that rule: it answers for a person
with no Brave key of their own (their key wins, ADR-307), when the operator runs
one, and a failed search raises — filed failed by the generator, never « nothing
found ».
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from src.domains.agents.effects.treatments import treatment_collector
from src.domains.connectors.instance_search import WebLink
from src.domains.connectors.models import ConnectorType
from src.domains.interests.services.content_sources import (
    brave_source,
    perplexity_source,
    searxng_source,
)
from src.domains.interests.services.content_sources.searxng_source import (
    SearXNGContentSource,
)

pytestmark = pytest.mark.unit

PERSON = str(uuid.uuid4())


def _keys(monkeypatch: pytest.MonkeyPatch, *held: ConnectorType) -> None:
    async def key(_user: str, connector_type: ConnectorType) -> str | None:
        return "key-123456" if connector_type in held else None

    for module in (brave_source, perplexity_source, searxng_source):
        monkeypatch.setattr(module, "get_connector_api_key", key)


def _instance(monkeypatch: pytest.MonkeyPatch, *, available: bool, links: Any = ()) -> list[Any]:
    asked: list[Any] = []

    async def is_available() -> bool:
        return available

    async def search(query: str, **kwargs: Any) -> list[WebLink]:
        asked.append((query, kwargs))
        if isinstance(links, Exception):
            raise links
        return list(links)

    monkeypatch.setattr(searxng_source, "instance_search_available", is_available)
    monkeypatch.setattr(searxng_source, "search_instance", search)
    return asked


class TestWhoAsksWhat:
    async def test_brave_and_perplexity_apply_only_with_the_persons_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _keys(monkeypatch, ConnectorType.PERPLEXITY)

        assert not await brave_source.BraveSearchContentSource().applies(PERSON)
        assert await perplexity_source.PerplexityContentSource().applies(PERSON)
        assert not await perplexity_source.PerplexityContentSource().applies(None)

    async def test_the_instance_answers_only_who_has_no_brave_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _instance(monkeypatch, available=True)
        _keys(monkeypatch, ConnectorType.BRAVE_SEARCH)
        assert not await SearXNGContentSource().applies(PERSON)  # their key wins

        _keys(monkeypatch)
        assert await SearXNGContentSource().applies(PERSON)
        assert not await SearXNGContentSource().applies(None)

    async def test_no_instance_search_means_the_source_does_not_apply(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _keys(monkeypatch)
        _instance(monkeypatch, available=False)

        assert not await SearXNGContentSource().applies(PERSON)


class TestTheInstanceSource:
    async def test_it_searches_the_recent_web_in_the_persons_language(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _instance(
            monkeypatch,
            available=True,
            links=[
                WebLink(
                    title="Rugby: <b>finale</b>", url="https://r.example", snippet="Le XV.", note=""
                ),
                WebLink(
                    title="Mêlée",
                    url="https://m.example",
                    snippet="",
                    note="Il y a 3 heures | L'Équipe",
                ),
            ],
        )

        result = await SearXNGContentSource().generate(
            topic="rugby", user_language="fr", user_id=PERSON
        )

        assert result is not None and result.source == "searxng"
        assert result.citations == ["https://r.example", "https://m.example"]
        assert "1. Rugby: finale\n   Le XV." in result.content  # markup flattened
        assert "2. Mêlée\n   Il y a 3 heures | L'Équipe" in result.content
        ((query, kwargs),) = asked
        assert "rugby" in query and kwargs["language"] == "fr" and kwargs["recency"] == "week"

    async def test_nothing_found_is_no_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _instance(monkeypatch, available=True, links=[])

        assert await SearXNGContentSource().generate("rugby", "fr", user_id=PERSON) is None

    async def test_a_failed_search_raises_for_the_generator_to_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _instance(monkeypatch, available=True, links=RuntimeError("down"))

        with pytest.raises(RuntimeError):
            await SearXNGContentSource().generate("rugby", "fr", user_id=PERSON)


class _Declining:
    """A source that would ask nothing for this person."""

    source_name = "brave"

    async def applies(self, user_id: str | None) -> bool:
        return False

    async def generate(self, **_kwargs: Any) -> Any:
        raise AssertionError("a source that does not apply is never run")


class _Silent:
    """The fallback reflection, answering nothing."""

    source_name = "llm_reflection"

    async def applies(self, user_id: str | None) -> bool:
        return True

    async def generate(self, **_kwargs: Any) -> Any:
        return None


async def test_a_source_that_would_ask_nothing_is_skipped_and_files_nothing() -> None:
    from unittest.mock import AsyncMock

    from src.domains.interests.services.content_sources.content_generator import (
        ContentGenerationContext,
        InterestContentGenerator,
    )

    generator = InterestContentGenerator.__new__(InterestContentGenerator)
    generator._primary_sources = [_Declining()]
    generator._llm_source = _Silent()
    generator._generate_content_embedding = AsyncMock(return_value=None)  # type: ignore[method-assign]
    context = ContentGenerationContext(
        interest_id=uuid.uuid4(),
        topic="rugby",
        category="sport",
        user_id=PERSON,
        user_language="fr",
        recent_notification_embeddings=[],
    )
    tried: list[str] = []

    with treatment_collector(run_id="interest-skip") as rows:
        await generator._try_all_sources(context, tried)

    assert [row.tool_name for row in rows] == ["interest:llm_reflection"]
    assert tried == ["brave", "llm_reflection"]


def test_the_instance_source_is_declared_on_the_interest_surface() -> None:
    from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

    assert (
        CONSULTATION_SURFACES["interest"].domains[SearXNGContentSource.source_name] == "web_search"
    )
