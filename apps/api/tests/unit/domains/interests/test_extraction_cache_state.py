"""The analysis cache may replay only the same effective extractor input."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.services.jev_extraction_observer import ExtractionObservation
from src.domains.feature_switches import registry as capabilities
from src.domains.interests.services import extraction_service as module

pytestmark = pytest.mark.unit


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 4, 14, 0, tzinfo=UTC)


@pytest.fixture
def extraction(monkeypatch):
    """Exercise the real core/cache/render seam without external I/O or writes."""
    owner = str(uuid4())
    interest = SimpleNamespace(id=uuid4(), topic="escalade", category="sports")
    active = [interest]
    cache = {}

    @asynccontextmanager
    async def database():
        yield object()

    async def get_cached(key):
        value = cache.get(key)
        return module.InterestAnalysisResult.from_cache_dict(value) if value else None

    async def set_cached(key, result):
        cache[key] = result.to_cache_dict()

    repository = SimpleNamespace(get_active_for_user=AsyncMock(side_effect=lambda *a, **k: active))
    invoke = AsyncMock(
        side_effect=[
            AIMessage(
                content=json.dumps(
                    [{"action": "create", "topic": topic, "category": "sports", "confidence": 0.99}]
                )
            )
            for topic in ("escalade", "musique")
        ]
    )
    observer = MagicMock(side_effect=lambda prompt: ExtractionObservation())
    monkeypatch.setattr(capabilities, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(module, "datetime", _FixedDatetime)
    monkeypatch.setattr(module, "get_db_context", database)
    monkeypatch.setattr(module, "InterestRepository", lambda db: repository)
    monkeypatch.setattr(module, "_get_cached_analysis", get_cached)
    monkeypatch.setattr(module, "_set_cached_analysis", set_cached)
    monkeypatch.setattr(module, "get_llm", MagicMock())
    monkeypatch.setattr(module, "invoke_with_instrumentation", invoke)
    monkeypatch.setattr(module, "start_extraction_observation", observer)
    monkeypatch.setattr(
        module,
        "get_llm_config_for_agent",
        lambda *a: SimpleNamespace(model="test-model", temperature=0.0),
    )
    return SimpleNamespace(
        owner=owner,
        active=active,
        cache=cache,
        invoke=invoke,
        observer=observer,
        repository=repository,
    )


def _messages(context="Tu parles de l'escalade ?"):
    return [AIMessage(content=context), HumanMessage(content="Oui, c'est ma passion.")]


async def _analyze(extraction, messages=None, language="fr", owner=None):
    return await module._analyze_interests_core(
        user_id=owner or extraction.owner,
        messages=messages or _messages(),
        session_id="test-session",
        user_language=language,
    )


@pytest.mark.asyncio
async def test_identical_effective_state_reuses_the_analysis_without_a_second_observer(extraction):
    first = await _analyze(extraction)
    second = await _analyze(extraction)

    assert first.analyzed and second.analyzed
    assert second.to_cache_dict() == first.to_cache_dict()
    assert extraction.invoke.await_count == 1
    assert extraction.observer.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["conversation", "interest_topic", "interest_id", "language"])
async def test_changed_effective_state_cannot_replay_previous_proposals(extraction, changed):
    first = await _analyze(extraction)
    messages = _messages()
    language = "fr"
    if changed == "conversation":
        messages = _messages("Tu parles de la musique ?")
    elif changed == "interest_topic":
        extraction.active[0].topic = "musique"
    elif changed == "interest_id":
        extraction.active[0].id = uuid4()
    else:
        language = "en"

    second = await _analyze(extraction, messages, language)

    assert extraction.invoke.await_count == 2
    assert extraction.observer.call_count == 2
    assert extraction.observer.call_args_list[0].args != extraction.observer.call_args_list[1].args
    assert len(extraction.cache) == 2
    assert [interest.topic for interest in first.extracted_interests] == ["escalade"]
    assert [interest.topic for interest in second.extracted_interests] == ["musique"]


@pytest.mark.asyncio
async def test_other_account_cannot_reuse_the_same_state(extraction):
    await _analyze(extraction)
    await _analyze(extraction, owner=str(uuid4()))

    assert extraction.invoke.await_count == 2
    assert len(extraction.cache) == 2


@pytest.mark.asyncio
async def test_changed_shipped_policy_cannot_replay_the_old_analysis(extraction, monkeypatch):
    await _analyze(extraction)
    original = module._get_extraction_prompt()
    monkeypatch.setattr(module, "_get_extraction_prompt", lambda: original + "\nUpdated policy.")

    await _analyze(extraction)

    assert extraction.invoke.await_count == 2
    assert len(extraction.cache) == 2
