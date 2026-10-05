"""A completed journal call keeps its own start and model across hot switches."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.core.llm_usage import LLMBillingRecord
from src.domains.journals import consolidation_service, extraction_service
from src.infrastructure.llm.token_capture import TokenCaptureHandler

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

USER = UUID("00000000-0000-0000-0000-000000000017")
START = datetime(2026, 10, 2, 23, 59, 59, tzinfo=UTC).timestamp()


def _response(model: str | None = None) -> AIMessage:
    return AIMessage(
        content="[]",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 0,
            "total_tokens": 100,
            "input_token_details": {"cache_read": 100},
        },
        response_metadata={"model_name": model} if model else {},
    )


@pytest.fixture
def fake_journal_dependencies(monkeypatch):
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    db.commit = AsyncMock()

    @asynccontextmanager
    async def database():
        yield db

    monkeypatch.setattr("src.infrastructure.database.get_db_context", database)
    service = SimpleNamespace(
        repo=SimpleNamespace(
            get_recent_for_user=AsyncMock(return_value=[]),
            get_total_chars=AsyncMock(return_value=0),
        ),
        get_all_active=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr("src.domains.journals.service.JournalService", lambda _: service)
    return db


async def test_cached_only_call_keeps_start_and_requested_model(monkeypatch):
    tracker = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=tracker)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("src.domains.chat.service.TrackingContext", lambda **_: context)

    await extraction_service._persist_journal_tokens(
        str(USER),
        "synthetic-session",
        None,
        _response("reported-snapshot"),
        "reported-snapshot",
        started_at=START,
        requested_model="requested-snapshot",
    )

    tracker.record_node_tokens.assert_awaited_once()
    call = tracker.record_node_tokens.await_args.kwargs
    assert call["prompt_tokens"] == call["completion_tokens"] == 0
    assert call["cached_tokens"] == 100
    assert call["started_at"] == START
    assert call["model_name"] == "reported-snapshot"
    assert call["requested_model"] == "requested-snapshot"


async def test_settings_cost_uses_call_start_across_weekend(monkeypatch, fake_journal_dependencies):
    user = SimpleNamespace()
    fake_journal_dependencies.execute.return_value.scalar_one_or_none = lambda: user
    price = MagicMock(return_value=(0.5, 0.4))
    monkeypatch.setattr("src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur", price)

    await extraction_service._update_user_last_cost(
        str(USER), _response(), "snapshot-model", started_at=START
    )

    assert price.call_args.kwargs["at"] == datetime.fromtimestamp(START, UTC)
    assert price.call_args.kwargs["prompt_tokens"] == 0
    assert price.call_args.kwargs["cached_tokens"] == 100
    assert user.journal_last_cost_at == datetime.fromtimestamp(START, UTC)
    assert float(user.journal_last_cost_eur) == 0.4


@pytest.mark.parametrize("reported_model", [None, "provider-returned-model"])
@pytest.mark.parametrize("kind", ["extraction", "consolidation"])
@pytest.mark.parametrize(
    "failure", [None, "before_response", "paid_error", "paid_cancel", "post_processing"]
)
async def test_completed_call_ignores_later_hot_switch(
    monkeypatch, fake_journal_dependencies, reported_model, kind, failure
):
    module = extraction_service if kind == "extraction" else consolidation_service
    clock = {"now": START}
    monkeypatch.setattr("time.time", lambda: clock["now"])
    if kind == "consolidation":
        monkeypatch.setattr(module, "time", lambda: clock["now"])
    active_model = {"name": "requested-before-call"}
    monkeypatch.setattr(
        module,
        "get_llm_config_for_agent",
        lambda *_: SimpleNamespace(model=active_model["name"]),
    )
    monkeypatch.setattr(
        module, "get_llm", lambda *_: SimpleNamespace(model_name="requested-before-call")
    )

    async def answer(**kwargs):
        if failure == "before_response":
            raise RuntimeError("provider returned no known usage")
        active_model["name"] = "changed-after-call-start"
        clock["now"] = START + 2  # completion crossed the UTC weekend boundary
        response = _response(reported_model)
        if kind == "consolidation":
            response.content = '{"actions": []}'
        if failure in {"paid_error", "paid_cancel"}:
            capture = kwargs["config"]["callbacks"][0]
            call_id = uuid4()
            capture.on_chat_model_start({}, [], run_id=call_id)
            capture.on_llm_end(
                LLMResult(generations=[[ChatGeneration(message=response)]]), run_id=call_id
            )
            if failure == "paid_cancel":
                raise asyncio.CancelledError("after known paid response")
            raise RuntimeError("after known paid response")
        return response

    monkeypatch.setattr(module, "invoke_with_instrumentation", answer)
    persist = AsyncMock()
    update = AsyncMock()
    monkeypatch.setattr(module, "_persist_journal_tokens", persist)
    monkeypatch.setattr(module, "_update_user_last_cost", update)
    if failure == "post_processing":
        if kind == "extraction":
            monkeypatch.setattr(
                module,
                "_parse_journal_extraction_result",
                MagicMock(side_effect=RuntimeError("processing")),
            )
        else:
            monkeypatch.setattr(
                module,
                "_parse_consolidation_result",
                MagicMock(side_effect=RuntimeError("processing")),
            )

    if kind == "extraction":
        monkeypatch.setattr(
            module,
            "settings",
            SimpleNamespace(
                journals_enabled=True,
                journal_extraction_enabled=True,
                journal_extraction_min_messages=1,
                journal_default_max_total_chars=40000,
            ),
        )
        monkeypatch.setattr(module, "_maybe_build_health_context", AsyncMock(return_value=""))
        monkeypatch.setattr(module, "_maybe_build_inner_state_section", AsyncMock(return_value=""))
        monkeypatch.setattr(
            module, "_build_previous_turn_directives_section", AsyncMock(return_value=("", set()))
        )
        monkeypatch.setattr(module, "build_introspection_prompt", lambda **_: "synthetic prompt")
        monkeypatch.setattr(module, "start_extraction_observation", MagicMock())
        operation = module.extract_journal_entry_background.__wrapped__(
            str(USER), [HumanMessage(content="A synthetic message")], "synthetic-session"
        )
    else:
        monkeypatch.setattr(module, "_build_usage_patterns_section", AsyncMock(return_value=""))
        monkeypatch.setattr(
            module, "_maybe_build_health_signals_section", AsyncMock(return_value="")
        )
        monkeypatch.setattr(
            module,
            "build_portrait_source_sections",
            AsyncMock(
                return_value=SimpleNamespace(
                    sections=dict.fromkeys(
                        ("memories", "interests", "habits", "relation_debriefs"), ""
                    ),
                    provenance={},
                )
            ),
        )
        monkeypatch.setattr(module, "build_consolidation_prompt", lambda **_: "synthetic prompt")
        monkeypatch.setattr(module, "_stamp_last_consolidated", AsyncMock())
        monkeypatch.setattr(module, "_file_consolidation", AsyncMock())
        operation = module.consolidate_journals_for_user(USER, None, None, "en")

    if failure == "paid_cancel":
        with pytest.raises(asyncio.CancelledError):
            await operation
    else:
        assert await operation == 0

    assert persist.await_count == 1
    captured = persist.await_args.kwargs["capture"]
    records = captured.get_billing_records("requested-before-call")
    assert len(records) == (0 if failure == "before_response" else 1)
    assert persist.await_args.kwargs["failed"] == (
        failure in {"before_response", "paid_error", "paid_cancel"}
    )
    assert persist.await_args.kwargs["requested_model"] == "requested-before-call"
    assert persist.await_args.kwargs["started_at"] == START
    if failure in {None, "post_processing"}:
        assert update.await_count == 1
        assert persist.await_args.kwargs["model_name"] == (
            reported_model or "requested-before-call"
        )
        assert update.await_args.kwargs["started_at"] == START
        assert update.await_args.args[2] == (reported_model or "requested-before-call")
    else:
        update.assert_not_awaited()


@pytest.mark.parametrize("failed", [False, True])
async def test_capture_persists_frozen_price_and_fx_once_even_with_no_final_reply(
    monkeypatch, failed
):
    tracker = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=tracker)
    context.__aexit__ = AsyncMock(return_value=False)
    owner = MagicMock(return_value=context)
    monkeypatch.setattr("src.domains.chat.service.TrackingContext", owner)
    record = LLMBillingRecord(
        model_name="provider-snapshot",
        started_at=START,
        tokens_in=0,
        tokens_out=0,
        tokens_cache=100,
        cost_usd=0.2,
        cost_eur=0.16,
        usd_to_eur_rate=0.8,
    )
    monkeypatch.setattr(
        "src.infrastructure.llm.token_capture.priced_call", lambda *_args, **_kwargs: record
    )
    capture = TokenCaptureHandler()
    capture.on_llm_error(
        RuntimeError("synthetic stream failure"),
        run_id=uuid4(),
        response=LLMResult(generations=[[ChatGeneration(message=_response())]]),
    )
    for _ in range(2):
        await extraction_service._persist_journal_tokens(
            str(USER),
            "synthetic-session",
            str(USER),
            None,
            "requested-model",
            parent_run_id="synthetic-parent",
            capture=capture,
            failed=failed,
        )
    owner.assert_called_once()
    assert owner.call_args.kwargs["run_id"] == "synthetic-parent"
    assert owner.call_args.kwargs["conversation_id"] == USER
    tracker.record_node_tokens.assert_awaited_once()
    bill = tracker.record_node_tokens.await_args.kwargs
    assert bill["model_name"] == "provider-snapshot"
    assert bill["started_at"] == START
    assert bill["status"] == "error"
    assert bill["failure_kind"] == "unknown"
    assert bill["prompt_tokens"] == bill["completion_tokens"] == 0
    assert bill["cached_tokens"] == 100
    assert bill["cost_usd"] == 0.2 and bill["cost_eur"] == 0.16
    assert float(bill["usd_to_eur_rate"]) == 0.8


async def test_settings_cost_keeps_callback_bill_when_final_message_has_no_usage(
    monkeypatch, fake_journal_dependencies
):
    user = SimpleNamespace()
    fake_journal_dependencies.execute.return_value.scalar_one_or_none = lambda: user
    record = LLMBillingRecord(
        model_name="provider-snapshot",
        started_at=START,
        tokens_in=0,
        tokens_out=0,
        tokens_cache=100,
        cost_usd=0.2,
        cost_eur=0.16,
        usd_to_eur_rate=0.8,
    )
    monkeypatch.setattr(
        "src.infrastructure.llm.token_capture.priced_call", lambda *_args, **_kwargs: record
    )
    capture = TokenCaptureHandler()
    capture.ensure_response_record(
        _response(), model_name="requested-model", started_at=START, snapshot=MagicMock()
    )
    pricing = MagicMock(side_effect=AssertionError("must not reprice the completed bill"))
    monkeypatch.setattr("src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur", pricing)
    await extraction_service._update_user_last_cost(
        str(USER), AIMessage(content="[]"), "requested-model", capture=capture
    )
    assert user.journal_last_cost_tokens_in == 100
    assert user.journal_last_cost_tokens_out == 0
    assert float(user.journal_last_cost_eur) == 0.16
    assert user.journal_last_cost_at == datetime.fromtimestamp(START, UTC)
    pricing.assert_not_called()
