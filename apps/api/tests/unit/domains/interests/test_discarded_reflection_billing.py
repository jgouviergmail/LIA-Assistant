"""Rejected reflections remain paid once; accepted content keeps the runner's bill."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.domains.interests.services.content_sources import llm_reflection_source as source_module
from src.domains.interests.services.content_sources.base import (
    ContentGenerationContext,
    bill_discarded_content,
)
from src.domains.interests.services.content_sources.content_generator import (
    InterestContentGenerator,
)
from src.infrastructure.llm import token_capture
from src.infrastructure.proactive import tracking

pytestmark = pytest.mark.unit


@pytest.fixture
def ledger(monkeypatch):
    writer = SimpleNamespace(record_node_tokens=AsyncMock(), commit=AsyncMock(), runs=[])

    @asynccontextmanager
    async def context(*args, **kwargs):
        writer.runs.append((args, kwargs))
        yield writer

    monkeypatch.setattr("src.domains.chat.service.TrackingContext", context)
    monkeypatch.setattr(tracking, "_record_out_of_turn", AsyncMock())
    monkeypatch.setattr(tracking, "ambient_run_id", lambda: "sweep-run")
    monkeypatch.setattr(token_capture, "get_cached_cost_usd_eur", lambda **kwargs: (0.02, 0.018))
    monkeypatch.setattr(token_capture, "get_cached_usd_eur_rate", lambda snapshot=None: 0.9)
    monkeypatch.setattr(source_module, "time", lambda: 100.0)
    monkeypatch.setattr(token_capture, "time", lambda: 100.0)
    monkeypatch.setattr(
        source_module, "get_llm", lambda _slot: SimpleNamespace(model="requested-model")
    )
    return writer


def install_reply(monkeypatch, text, *, callbacks=False, with_usage=True):
    async def invoke(**kwargs):
        reply = SimpleNamespace(
            text=text,
            response_metadata={"model_name": "returned-model"},
            usage_metadata=(
                {
                    "input_tokens": 28,
                    "output_tokens": 2,
                    "total_tokens": 30,
                    "input_token_details": {"cache_read": 20},
                }
                if with_usage
                else None
            ),
        )
        if callbacks and with_usage:
            capture = kwargs["config"]["callbacks"][0]
            run = uuid4()
            capture.on_chat_model_start({}, [], run_id=run)
            capture.on_llm_end(
                LLMResult(
                    generations=[
                        [
                            ChatGeneration(
                                message=AIMessage(
                                    content=text or "",
                                    usage_metadata=reply.usage_metadata,
                                    response_metadata=reply.response_metadata,
                                )
                            )
                        ]
                    ]
                ),
                run_id=run,
            )
        return reply

    monkeypatch.setattr(source_module, "invoke_with_instrumentation", invoke)


def assert_one_frozen_attempt(ledger):
    assert ledger.record_node_tokens.await_count == 1
    assert ledger.commit.await_count == 1
    assert ledger.runs[0][1]["run_id"] == "sweep-run"
    row = ledger.record_node_tokens.await_args.kwargs
    assert row["model_name"] == "returned-model"
    assert row["started_at"] == 100.0
    assert (row["prompt_tokens"], row["completion_tokens"], row["cached_tokens"]) == (8, 2, 20)
    assert (row["cost_usd"], row["cost_eur"]) == (0.02, 0.018)


@pytest.mark.parametrize("text", [None, "", "short"])
@pytest.mark.parametrize("callbacks", [False, True])
async def test_empty_or_short_paid_content_bills_once_before_returning_none(
    monkeypatch, ledger, text, callbacks
):
    install_reply(monkeypatch, text, callbacks=callbacks)
    result = await source_module.LLMReflectionContentSource().generate(
        "Topic", "fr", user_id=str(uuid4())
    )
    assert result is None
    assert_one_frozen_attempt(ledger)


async def test_no_reported_usage_never_invents_a_bill(monkeypatch, ledger):
    install_reply(monkeypatch, "", with_usage=False)
    assert (
        await source_module.LLMReflectionContentSource().generate(
            "Topic", "fr", user_id=str(uuid4())
        )
        is None
    )
    assert ledger.record_node_tokens.await_count == 0


async def test_duplicate_reuses_claim_and_never_bills_the_same_attempt_twice(monkeypatch, ledger):
    install_reply(monkeypatch, "A useful reflection long enough to be retained initially.")
    owner = uuid4()
    paid = await source_module.LLMReflectionContentSource().generate(
        "Topic", "fr", user_id=str(owner)
    )
    assert paid is not None
    assert ledger.record_node_tokens.await_count == 0

    generator = InterestContentGenerator.__new__(InterestContentGenerator)
    generator._get_shuffled_primary_sources = lambda _user: []
    generator._generate_content_embedding = AsyncMock(return_value=[0.1])
    generator._is_duplicate = lambda _content, _embeddings: True
    generator._llm_source = SimpleNamespace(
        source_name="llm_reflection", generate=AsyncMock(return_value=paid)
    )
    context = ContentGenerationContext(
        interest_id="interest",
        topic="Topic",
        category="general",
        user_id=str(owner),
        user_language="fr",
    )

    assert await generator._try_all_sources(context, []) is None
    assert await generator._try_all_sources(context, []) is None
    await bill_discarded_content(paid, owner, "interest")
    assert_one_frozen_attempt(ledger)
    assert paid.billing_capture.accounting_handled is True


async def test_kept_reflection_is_only_billed_by_its_runner(monkeypatch, ledger):
    install_reply(
        monkeypatch, "A useful reflection long enough to be retained initially.", callbacks=True
    )
    owner = uuid4()
    paid = await source_module.LLMReflectionContentSource().generate(
        "Topic", "fr", user_id=str(owner)
    )
    assert paid is not None
    assert ledger.record_node_tokens.await_count == 0
    assert len(paid.billing_records) == 1
    assert paid.billing_capture.accounting_handled is False
    await tracking.track_proactive_tokens(
        user_id=owner,
        task_type="interest",
        target_id="interest",
        conversation_id=None,
        tokens_in=paid.tokens_in,
        tokens_out=paid.tokens_out,
        tokens_cache=paid.tokens_cache,
        model_name="later-model",
        billing_records=paid.billing_records,
        run_id="sweep-run",
        source="proactive",
    )
    assert_one_frozen_attempt(ledger)
