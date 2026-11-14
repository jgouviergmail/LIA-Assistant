"""The instance's web search, one door (lot 18): who it serves, what it hands back, how it fails.

Every surface that searches the web for a person with no search key of their own
goes through ``connectors/instance_search``: the keyless predicate decides whether
the instance runs one (ADR-307), a search hands back plain links, and a failure
RAISES — counted on the connector metrics every client shares, never read as an
empty result.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import ExternalServiceError
from src.domains.connectors import instance_search
from src.domains.connectors.clients.searxng_client import SearXNGAnswer
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit


class _Client:
    """A SearXNG client double that records what it was asked and whether it closed."""

    def __init__(self, answer: SearXNGAnswer | None = None, error: Exception | None = None):
        self.answer = answer
        self.error = error
        self.asked: dict[str, object] = {}
        self.closed = False

    async def search(self, query: str, **kwargs: object) -> SearXNGAnswer:
        self.asked = {"query": query, **kwargs}
        if self.error is not None:
            raise self.error
        assert self.answer is not None
        return self.answer

    async def close(self) -> None:
        self.closed = True


def _answer(count: int, *, engines_down: int = 0) -> SearXNGAnswer:
    return SearXNGAnswer.model_validate(
        {
            "results": [
                {
                    "url": f"https://site{n}.example/page",
                    "title": f"Title {n}",
                    "content": f"Excerpt {n}",
                    "metadata": "Il y a 2 heures | Outlet" if n == 0 else None,
                }
                for n in range(count)
            ],
            "unresponsive_engines": [[f"engine{n}", "CAPTCHA"] for n in range(engines_down)],
        }
    )


@pytest.fixture
def metrics(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    counters = SimpleNamespace(requests=MagicMock(), errors=MagicMock(), duration=MagicMock())
    monkeypatch.setattr(instance_search, "connector_api_requests_total", counters.requests)
    monkeypatch.setattr(instance_search, "connector_api_errors_total", counters.errors)
    monkeypatch.setattr(instance_search, "connector_api_duration_seconds", counters.duration)
    return counters


def _install(monkeypatch: pytest.MonkeyPatch, client: _Client) -> None:
    monkeypatch.setattr(instance_search, "SearXNGClient", lambda **_kwargs: client)


async def test_a_search_hands_back_plain_links_within_the_count(
    monkeypatch: pytest.MonkeyPatch, metrics: SimpleNamespace
) -> None:
    client = _Client(_answer(6))
    _install(monkeypatch, client)

    links = await instance_search.search_instance(
        "grève SNCF", user_id=uuid4(), language="fr", recency="week", news=True, count=4
    )

    assert [link.url for link in links] == [f"https://site{n}.example/page" for n in range(4)]
    assert links[0].note == "Il y a 2 heures | Outlet" and links[1].note == ""
    assert links[0].title == "Title 0" and links[0].snippet == "Excerpt 0"
    assert client.asked == {
        "query": "grève SNCF",
        "language": "fr",
        "recency": "week",
        "news": True,
    }
    assert client.closed
    metrics.requests.labels.assert_called_once_with(
        connector_type=ConnectorType.SEARXNG.value, operation="search", status="success"
    )


async def test_engines_that_could_not_answer_are_counted_for_the_operator(
    monkeypatch: pytest.MonkeyPatch, metrics: SimpleNamespace
) -> None:
    _install(monkeypatch, _Client(_answer(3, engines_down=2)))

    await instance_search.search_instance("x", user_id=None, language="en", count=5)

    metrics.errors.labels.assert_called_once_with(
        connector_type=ConnectorType.SEARXNG.value, error_type="engine_unresponsive"
    )
    metrics.errors.labels.return_value.inc.assert_called_once_with(2)


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (httpx.ConnectError("refused connection"), "unreachable"),
        (ExternalServiceError(service_name="searxng", error_type="circuit_open"), "circuit_open"),
        (
            httpx.HTTPStatusError(
                "refused",
                request=httpx.Request("GET", "http://searxng:8080/search"),
                response=httpx.Response(400),
            ),
            "refused",
        ),
        # An answer that is not its JSON reached the service: neither unreachable nor refused.
        (ValueError("not json"), "malformed"),
    ],
)
async def test_a_failure_raises_and_is_counted_by_its_kind(
    monkeypatch: pytest.MonkeyPatch,
    metrics: SimpleNamespace,
    error: Exception,
    error_type: str,
) -> None:
    client = _Client(error=error)
    _install(monkeypatch, client)

    with pytest.raises(type(error)):
        await instance_search.search_instance("x", user_id=uuid4(), language="en", count=5)

    assert client.closed
    metrics.requests.labels.assert_called_once_with(
        connector_type=ConnectorType.SEARXNG.value, operation="search", status="error"
    )
    metrics.errors.labels.assert_called_once_with(
        connector_type=ConnectorType.SEARXNG.value, error_type=error_type
    )


async def test_a_timeout_is_told_apart_from_an_unreachable_service(
    monkeypatch: pytest.MonkeyPatch, metrics: SimpleNamespace
) -> None:
    _install(monkeypatch, _Client(error=httpx.ReadTimeout("slow")))

    with pytest.raises(httpx.ReadTimeout):
        await instance_search.search_instance("x", user_id=uuid4(), language="en", count=5)

    metrics.requests.labels.assert_called_once_with(
        connector_type=ConnectorType.SEARXNG.value, operation="search", status="timeout"
    )


async def test_availability_is_the_keyless_predicates_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[ConnectorType] = []

    async def available(_repository: object, connector_type: ConnectorType) -> bool:
        asked.append(connector_type)
        return True

    class _Db:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *exc: object) -> bool:
            return False

    monkeypatch.setattr(instance_search, "is_keyless_available", available)
    monkeypatch.setattr(instance_search, "get_db_context", lambda: _Db())
    monkeypatch.setattr(instance_search, "ConnectorRepository", lambda _db: object())

    assert await instance_search.instance_search_available()
    assert asked == [ConnectorType.SEARXNG]


def test_the_source_name_is_one_constant() -> None:
    assert instance_search.INSTANCE_SEARCH_SOURCE == ConnectorType.SEARXNG.value
