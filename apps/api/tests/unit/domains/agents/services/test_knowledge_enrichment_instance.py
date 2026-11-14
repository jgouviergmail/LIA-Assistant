"""The answer's web enrichment for a person with no Brave key (lot 18).

The enrichment searched Brave with the person's own key, and nothing else: a person
with no key had no enrichment. Now their choice still wins — a Brave key is searched
first — and without one the instance's SearXNG enriches the answer, recorded as its
own capability, cached apart (a link SearXNG found is never served as Brave's), and
named for what it is in the prompt.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.services import knowledge_enrichment_service as module
from src.domains.agents.services.knowledge_enrichment_service import (
    KnowledgeContext,
    KnowledgeEnrichmentService,
)
from src.domains.connectors.instance_search import WebLink

pytestmark = pytest.mark.unit

_RECORD = "src.domains.agents.effects.treatments.record_treatment"


def _deps(*, key: str | None, brave_enabled: bool = True) -> MagicMock:
    connectors = MagicMock()
    connectors.get_api_key_credentials = AsyncMock(
        return_value=SimpleNamespace(api_key=key) if key else None
    )
    connectors.get_global_config = AsyncMock(
        return_value=None if brave_enabled else SimpleNamespace(is_enabled=False)
    )
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=connectors)
    return deps


class _Redis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"instance": True, "links": [], "asked": [], "records": []}
    monkeypatch.setattr(settings, "knowledge_enrichment_enabled", True)

    async def available() -> bool:
        return state["instance"]

    async def search(query: str, **kwargs: Any) -> list[WebLink]:
        state["asked"].append((query, kwargs))
        if isinstance(state["links"], Exception):
            raise state["links"]
        return state["links"]

    def record(capability: str, _target: object, **kwargs: Any) -> None:
        state["records"].append((capability, kwargs["succeeded"]))

    monkeypatch.setattr(module, "instance_search_available", available)
    monkeypatch.setattr(module, "search_instance", search)
    monkeypatch.setattr(_RECORD, record)
    return state


def _service(redis: _Redis | None = None) -> KnowledgeEnrichmentService:
    async def provider() -> _Redis | None:
        return redis

    return KnowledgeEnrichmentService(redis_provider=provider)


async def test_without_a_key_the_instance_enriches_the_answer(wired: dict[str, Any]) -> None:
    wired["links"] = [
        WebLink(title="Eclipse 2026", url="https://e.example", snippet="Total eclipse.", note=""),
        WebLink(
            title="News", url="https://n.example", snippet="Seen.", note="2 hours ago | Outlet"
        ),
    ]
    redis = _Redis()

    context = await _service(redis).enrich(
        ["solar", "eclipse"],
        is_news_query=True,
        user_id=uuid4(),
        language="en",
        tool_deps=_deps(key=None),
    )

    assert isinstance(context, KnowledgeContext) and context.source == "searxng"
    assert [result["url"] for result in context.results] == [
        "https://e.example",
        "https://n.example",
    ]
    assert context.results[1]["description"] == "[2 hours ago | Outlet] Seen."
    assert context.to_prompt_context().startswith("[Source: SearXNG News Search - solar eclipse]")
    ((query, kwargs),) = wired["asked"]
    assert query == "solar eclipse" and kwargs["news"] is True and kwargs["recency"] == "week"
    assert wired["records"] == [("enrichment:searxng", True)]
    assert [key.split(":", 1)[0] for key in redis.store] == ["searxng_search"]


async def test_a_cached_instance_search_is_never_served_as_brave(wired: dict[str, Any]) -> None:
    wired["links"] = [WebLink(title="T", url="https://t.example", snippet="S", note="")]
    redis = _Redis()
    service = _service(redis)
    await service.enrich(["topic"], user_id=uuid4(), language="en", tool_deps=_deps(key=None))

    again = await service.enrich(
        ["topic"], user_id=uuid4(), language="en", tool_deps=_deps(key=None)
    )

    assert again is not None and again.from_cache and again.source == "searxng"
    assert len(wired["asked"]) == 1  # the second read came from the cache


async def test_the_persons_own_key_wins(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    async def brave(self: KnowledgeEnrichmentService, **kwargs: Any) -> KnowledgeContext:
        called.append(kwargs["credentials"].api_key)
        return KnowledgeContext(keyword="k", endpoint="web", results=(), from_cache=False)

    monkeypatch.setattr(KnowledgeEnrichmentService, "_call_api", brave)

    await _service().enrich(["topic"], user_id=uuid4(), language="en", tool_deps=_deps(key="BSA-k"))

    assert called == ["BSA-k"] and wired["asked"] == []


async def test_a_brave_switched_off_by_the_administrator_leaves_the_instance(
    wired: dict[str, Any],
) -> None:
    wired["links"] = [WebLink(title="T", url="https://t.example", snippet="S", note="")]

    context = await _service().enrich(
        ["topic"], user_id=uuid4(), language="en", tool_deps=_deps(key="BSA-k", brave_enabled=False)
    )

    assert context is not None and context.source == "searxng"


async def test_no_key_and_no_instance_search_is_no_enrichment(wired: dict[str, Any]) -> None:
    wired["instance"] = False

    context = await _service().enrich(
        ["topic"], user_id=uuid4(), language="en", tool_deps=_deps(key=None)
    )

    assert context is None and wired["asked"] == [] and wired["records"] == []


async def test_a_failed_instance_search_is_recorded_failed(wired: dict[str, Any]) -> None:
    wired["links"] = RuntimeError("down")

    context = await _service().enrich(
        ["topic"], user_id=uuid4(), language="en", tool_deps=_deps(key=None)
    )

    assert context is None
    assert wired["records"] == [("enrichment:searxng", False)]
