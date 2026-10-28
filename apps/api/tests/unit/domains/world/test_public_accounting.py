"""The public batch enters the same single-attempt, quota and native-accounting door."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.world import translation as native
from src.domains.world.public_translation import translate_public_message

pytestmark = pytest.mark.unit


async def test_quota_denial_never_constructs_or_calls_a_provider(monkeypatch) -> None:
    guard = AsyncMock(side_effect=ValueError("quota"))
    factory = MagicMock()
    monkeypatch.setattr(native, "enforce_usage_limit", guard)
    monkeypatch.setattr(native, "get_llm", factory)
    owner = uuid4()
    with pytest.raises(ValueError, match="quota"):
        await translate_public_message(
            "Bonjour", source="fr", targets=("en",), user_id=owner, request_id=uuid4()
        )
    guard.assert_awaited_once_with(owner, layer="world_translation")
    factory.assert_not_called()


@pytest.mark.parametrize(
    "raw,accepted",
    [
        ('{"translations":[{"language":"en","text":"Hello"}]}', True),
        ('{"translations":[{"language":"de","text":"Hallo"}]}', False),
    ],
)
async def test_public_batch_accounts_once_and_never_repairs_bad_output(
    monkeypatch, raw: str, accepted: bool
) -> None:
    usage = TokenSummaryDTO(17, 8, 0, 0.001, 0)

    class Tracker:
        cleanup_run_records = MagicMock()

        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def get_summary_dto(self):
            return usage

    config = SimpleNamespace(max_tokens=2048, timeout_seconds=8)
    config.model_copy = lambda **kwargs: config
    provider = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content=raw)))
    filing = AsyncMock()
    monkeypatch.setattr(native, "enforce_usage_limit", AsyncMock())
    monkeypatch.setattr(native, "get_llm_config_for_agent", lambda *args: config)
    monkeypatch.setattr(native, "get_effective_context_window_for_slot", lambda *args: 65536)
    monkeypatch.setattr(native, "get_llm", lambda *args, **kwargs: provider)
    monkeypatch.setattr(native, "single_async_attempt", nullcontext)
    monkeypatch.setattr(native, "TrackingContext", Tracker)
    monkeypatch.setattr(native, "TokenTrackingCallback", lambda *args: object())
    monkeypatch.setattr(native, "file_translation", filing)
    kwargs = {"source": "fr", "targets": ("en",), "user_id": uuid4(), "request_id": uuid4()}
    if accepted:
        result = await translate_public_message("Bonjour", **kwargs)
        assert result.translations == {"en": "Hello"} and result.usage == usage
    else:
        with pytest.raises(ValueError):
            await translate_public_message("Bonjour", **kwargs)
    provider.ainvoke.assert_awaited_once()
    filing.assert_awaited_once()
    Tracker.cleanup_run_records.assert_called_once()
