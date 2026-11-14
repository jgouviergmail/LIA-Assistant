"""The Tools' Internet research through the instance's search (lot 18).

A person with neither a Brave nor a Perplexity key was researched on Wikipedia
alone. The instance's SearXNG now stands between the person's own keys and
Wikipedia: their keys still come first, it asks for no key, its links are shown
as the service it is, and a failure raises — the door files it failed.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from src.core.constants import TOOL_ASSIST_SEARCH_RESULTS_MAX
from src.domains.connectors.instance_search import WebLink
from src.domains.connectors.models import ConnectorType
from src.domains.feature_switches import guard
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.tool_assists import selection_research as research
from src.domains.tool_assists.catalogue import ASSISTS, ToolAssist
from src.domains.tool_assists.door import AssistRun

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def capability(monkeypatch: pytest.MonkeyPatch) -> None:
    async def enabled(capability: PlatformCapability) -> bool:
        return True

    monkeypatch.setattr(guard, "is_capability_enabled", enabled)


@pytest.fixture
def run() -> AssistRun:
    return AssistRun(uuid4(), "fr", {}, sections=ASSISTS[ToolAssist.SELECTION_INTERNET].sections)


def test_the_persons_keys_come_first_then_the_instance_then_wikipedia() -> None:
    assert list(research.SEARCH_CONNECTORS) == ["brave", "perplexity", "searxng", "wikipedia"]
    assert research.SEARCH_CONNECTORS["searxng"] is ConnectorType.SEARXNG
    research.assert_research_providers_complete()


def test_the_assist_may_read_every_provider_it_can_choose() -> None:
    assert set(ASSISTS[ToolAssist.SELECTION_INTERNET].sections) == set(research.SEARCH_CONNECTORS)


async def test_the_instance_search_reads_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    reads: list[ConnectorType] = []

    class Service:
        def __init__(self, _session: object) -> None:
            pass

        async def is_connector_active(self, user_id: UUID, connector_type: ConnectorType) -> bool:
            return True

        async def get_api_key_credentials(
            self, user_id: UUID, connector_type: ConnectorType
        ) -> Any:
            reads.append(connector_type)
            return None

    class _Db:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *exc: object) -> bool:
            return False

    monkeypatch.setattr(research, "get_db_context", lambda: _Db())
    monkeypatch.setattr(research, "ConnectorService", Service)

    assert await research._credentials(uuid4(), "searxng") is None
    assert reads == []


def _wire(monkeypatch: pytest.MonkeyPatch, links: list[WebLink] | Exception) -> list[Any]:
    asked: list[Any] = []

    async def preferred(user_id: UUID) -> research.ResearchProvider:
        return "searxng"

    async def credentials(user_id: UUID, provider: research.ResearchProvider) -> None:
        return None

    async def ask[T: BaseModel](run: AssistRun, prompt: str, schema: type[T]) -> T:
        return schema.model_validate({"query": "selected topic"})

    async def search(query: str, **kwargs: Any) -> list[WebLink]:
        asked.append((query, kwargs))
        if isinstance(links, Exception):
            raise links
        return links

    monkeypatch.setattr(research, "preferred_provider", preferred)
    monkeypatch.setattr(research, "_credentials", credentials)
    monkeypatch.setattr(research, "ask_slot", ask)
    monkeypatch.setattr(research, "search_instance", search)
    return asked


async def test_a_research_through_the_instance_shows_its_links_as_its_own(
    monkeypatch: pytest.MonkeyPatch, run: AssistRun
) -> None:
    asked = _wire(
        monkeypatch,
        [
            WebLink(
                title="Topic <b>page</b>", url="https://t.example/a", snippet="About.", note=""
            ),
            WebLink(title="  ", url="https://blank.example", snippet="No title.", note=""),
            WebLink(title="News", url="https://n.example", snippet="Seen.", note="2 h | Outlet"),
        ],
    )

    proposal = await research.research_selection(run, "a selected passage")

    assert proposal.provider == "searxng" and proposal.query == "selected topic"
    assert [str(source.url) for source in proposal.sources] == [
        "https://t.example/a",
        "https://n.example/",
    ]
    assert proposal.sources[0].title == "Topic page"  # markup flattened, never active
    assert proposal.sources[1].excerpt == "[2 h | Outlet] Seen."
    ((query, kwargs),) = asked
    assert query == "selected topic" and kwargs["language"] == "fr"
    assert kwargs["count"] == TOOL_ASSIST_SEARCH_RESULTS_MAX and kwargs["user_id"] == run.user_id
    assert run.served


async def test_a_failed_instance_search_raises_for_the_door_to_file(
    monkeypatch: pytest.MonkeyPatch, run: AssistRun
) -> None:
    _wire(monkeypatch, RuntimeError("down"))

    with pytest.raises(RuntimeError):
        await research.research_selection(run, "a selected passage")
    assert not run.served
