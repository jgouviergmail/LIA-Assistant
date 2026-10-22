"""Native LLM entry uses the dedicated slot and refuses before paid work when a prompt cannot fit."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.proactive_discussions.llm_contracts import PromptBudgetExceeded
from src.infrastructure.proactive.discussion_llm import DiscussionLLM, prepare_call

pytestmark = pytest.mark.unit


class Permit:
    def __init__(self):
        self.calls = []
        self.receipts = []

    async def admit(self, phase, config, tokens):
        self.calls.append((phase, config, tokens))

    def record(self, records, *, uncertain):
        self.receipts.append((records, uncertain))


async def test_oversized_complete_rules_never_create_or_call_a_model(monkeypatch):
    created = []
    monkeypatch.setattr(
        "src.infrastructure.proactive.discussion_llm.get_llm",
        lambda *args, **kwargs: created.append(args),
    )
    # The configured slot's window is the only room a prompt has.
    monkeypatch.setattr(
        "src.infrastructure.proactive.discussion_llm.get_effective_context_window_for_slot",
        lambda slot: 8000,
    )
    permit = Permit()
    model = DiscussionLLM(
        UUID(int=1), UUID(int=2), permit, authorize=AsyncMock(), source="proactive"
    )
    with pytest.raises(PromptBudgetExceeded):
        await model.decide("Binding rule " * 10000)
    assert created == [] and permit.calls == []


@pytest.mark.parametrize("phase", ["context", "decision", "message"])
def test_a_call_keeps_its_configured_slot_budget_and_timeout(monkeypatch, phase):
    slot = f"discussion_{phase}"
    cfg = LLM_DEFAULTS[slot].model_copy(
        update={"provider": "openai", "max_tokens": 100_000, "timeout_seconds": 95}
    )
    monkeypatch.setattr(
        "src.infrastructure.proactive.discussion_llm.get_llm_config_for_agent", lambda *args: cfg
    )
    monkeypatch.setattr(
        "src.infrastructure.proactive.discussion_llm.get_effective_context_window_for_slot",
        lambda slot: 1_000_000,
    )
    # Far past the former fixed envelopes, the prompt fits the configured slot.
    call = prepare_call(phase, "Fictional fact. " * 4000, None)
    assert call.slot == slot and call.input_tokens > 8000
    assert call.config.max_tokens == 100_000 and call.config.timeout_seconds == 95
    assert '"max_retries": 0' in call.config.provider_config


@pytest.mark.parametrize("source", ["proactive", "user"])
async def test_native_structured_decision_uses_dedicated_slot_and_bills_even_skip(
    monkeypatch, source
):
    cfg = LLM_DEFAULTS["discussion_decision"].model_copy(update={"provider": "perplexity"})
    monkeypatch.setattr(
        "src.infrastructure.proactive.discussion_llm.get_llm_config_for_agent", lambda *args: cfg
    )
    monkeypatch.setattr(
        "src.infrastructure.proactive.discussion_llm.get_effective_context_window_for_slot",
        lambda slot: 32000,
    )
    captured = []

    def factory(slot, config_override):
        captured.append((slot, config_override))
        return FakeListChatModel(
            responses=['{"decision":{"action":"skip","reason":"No natural opening"}}']
        )

    monkeypatch.setattr("src.infrastructure.proactive.discussion_llm.get_llm", factory)
    billed = AsyncMock(return_value=None)
    monkeypatch.setattr("src.infrastructure.proactive.discussion_llm.bill_captured_usage", billed)
    permit = Permit()
    authorize = AsyncMock()
    result = await DiscussionLLM(
        UUID(int=1), UUID(int=2), permit, authorize=authorize, source=source
    ).decide("Only a fictional unchanged fact.")
    assert result.action == "skip" and captured[0][0] == "discussion_decision"
    assert '"max_retries": 0' in captured[0][1].provider_config
    assert len(permit.calls) == 1 and len(permit.receipts) == 1
    assert billed.await_count == 1 and authorize.await_count >= 2
    # The register's authorship is the call site's declaration, never a default.
    assert billed.await_args.kwargs["source"] == source
