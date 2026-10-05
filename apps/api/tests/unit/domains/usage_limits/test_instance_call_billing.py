"""Account-less structured calls retain every paid attempt on validation failure."""

import asyncio
from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.infrastructure.cache import pricing_cache
from src.infrastructure.llm.token_capture import TokenCaptureHandler

from .test_instance_spend import _fake_session

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "surface", ["diagnostician", "evaluation", "skill", "personality", "broadcast"]
)
@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_known_attempts_are_settled_once_for_success_failure_and_cancellation(
    surface: str,
    failure: type[BaseException] | None,
) -> None:
    from src.domains.diagnostics import diagnosis
    from src.domains.notifications.broadcast_service import BroadcastService
    from src.domains.personalities import translation_service
    from src.domains.skills.description_translation import _translate_description_all_langs
    from src.domains.usage_limits import instance_spend

    evaluation_pipeline = import_module("src.infrastructure.llm.evaluation_pipeline")

    starts = [datetime(2026, 10, 4, 23, 59, tzinfo=UTC), datetime(2026, 10, 5, 0, 1, tzinfo=UTC)]
    stamps = iter(stamp.timestamp() for stamp in starts)
    snapshot = pricing_cache.PricingCacheData(
        models={
            "first": pricing_cache.CachedModelPrice(1, 2, 0.1),
            "second": pricing_cache.CachedModelPrice(3, 4, 0.2),
        },
        usd_eur_rate=0.9,
        last_refresh_ts=starts[0].timestamp(),
    )

    def completed_attempts(capture):
        for model in ("first", "second"):
            run_id = uuid4()
            capture.on_chat_model_start({}, [], run_id=run_id, invocation_params={"model": model})
            capture.on_llm_end(
                LLMResult(
                    generations=[
                        [
                            ChatGeneration(
                                message=AIMessage(
                                    content="synthetic",
                                    response_metadata={"model_name": model},
                                    usage_metadata={
                                        "input_tokens": 1000,
                                        "output_tokens": 10,
                                        "total_tokens": 1010,
                                        "input_token_details": {"cache_read": 500},
                                    },
                                )
                            )
                        ]
                    ]
                ),
                run_id=run_id,
            )

    async def invoke(**kwargs):
        completed_attempts(kwargs["config"]["callbacks"][0])
        if failure is not None:
            raise failure()
        return kwargs["schema"].model_validate(
            {"diagnosis": "test", "probable_cause": "test", "recommended_actions": []}
            if surface == "diagnostician"
            else {"score": 1, "reasoning": "test"}
        )

    async def direct_invoke(*args, **kwargs):
        completed_attempts(
            next(
                handler
                for handler in kwargs["config"]["callbacks"]
                if isinstance(handler, TokenCaptureHandler)
            )
        )
        if failure is not None:
            raise failure()
        return AIMessage(
            content='{"title":"Test","description":"Synthetic", "en":"test", "fr":"test"}'
        )

    model = SimpleNamespace(model_name="first", ainvoke=direct_invoke)
    with (
        patch.object(pricing_cache, "_local_cache", snapshot),
        patch(
            "src.infrastructure.llm.token_capture.time",
            side_effect=lambda: next(stamps, starts[-1].timestamp()),
        ),
        patch.object(diagnosis, "get_structured_output_with_retry", side_effect=invoke),
        patch.object(evaluation_pipeline, "get_structured_output", side_effect=invoke),
        patch("src.infrastructure.llm.factory.get_llm", return_value=model),
        patch.object(translation_service, "get_llm", return_value=model),
        patch.object(instance_spend, "is_instance_spend_blocked", AsyncMock(return_value=False)),
        patch.object(
            translation_service, "is_instance_spend_blocked", AsyncMock(return_value=False)
        ),
        patch.object(diagnosis, "_record_spend", AsyncMock()) as private_budget,
        patch(
            "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
            AsyncMock(),
        ) as ledger,
        _fake_session(),
    ):

        async def run():
            if surface == "diagnostician":
                return await diagnosis._invoke_diagnostician(model, "synthetic", "synthetic")
            if surface == "skill":
                return await _translate_description_all_langs("synthetic", None)
            if surface == "personality":
                return (
                    await translation_service.PersonalityTranslationService.translate_personality(
                        source_title="test",
                        source_description="synthetic",
                        source_language="en",
                        target_language="fr",
                        personality_code=f"billing-{uuid4()}",
                    )
                )
            if surface == "broadcast":
                return await BroadcastService(AsyncMock())._translate_message(
                    model,
                    "synthetic",
                    "en",
                    "fr",
                    "synthetic",
                )
            return await evaluation_pipeline._scored_with_accounting(
                model,
                prompt="synthetic",
                schema=evaluation_pipeline.RelevanceScore,
                provider="synthetic",
                node_name="evaluation",
            )

        if failure is None:
            await run()
        else:
            with pytest.raises(failure):
                await run()
    assert ledger.await_count == 2
    assert [call.kwargs["now"] for call in ledger.await_args_list] == starts
    assert [float(call.kwargs["cost_eur"]) for call in ledger.await_args_list] == pytest.approx(
        [0.000513, 0.001476]
    )
    assert private_budget.await_count == (2 if surface == "diagnostician" else 0)


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_partial_error_usage_stays_instance_owned_and_is_billed_once(
    failure: type[BaseException],
) -> None:
    """The error callback's known stream usage survives without a final reply."""
    from src.domains.skills.description_translation import _translate_description_all_langs
    from src.domains.usage_limits import instance_spend

    started = datetime(2026, 10, 4, 23, 59, tzinfo=UTC)
    snapshot = pricing_cache.PricingCacheData(
        models={"provider-model": pricing_cache.CachedModelPrice(1, 2, 0.1)},
        usd_eur_rate=0.9,
        last_refresh_ts=started.timestamp(),
    )
    partial = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="partial",
                        response_metadata={"model_name": "provider-model"},
                        usage_metadata={
                            "input_tokens": 1000,
                            "output_tokens": 10,
                            "total_tokens": 1010,
                            "input_token_details": {"cache_read": 500},
                        },
                    )
                )
            ]
        ]
    )
    captures = []

    async def invoke(*args, **kwargs):
        capture = kwargs["config"]["callbacks"][0]
        captures.append(capture)
        run_id = uuid4()
        capture.on_chat_model_start(
            {}, [], run_id=run_id, invocation_params={"model": "requested-model"}
        )
        pricing_cache._local_cache = pricing_cache.PricingCacheData(
            models={"provider-model": pricing_cache.CachedModelPrice(100, 200, 10)},
            usd_eur_rate=0.5,
            last_refresh_ts=started.timestamp() + 600,
        )
        for _ in range(2):
            capture.on_llm_error(
                failure("synthetic stream failure"), run_id=run_id, response=partial
            )
        capture.on_llm_end(partial, run_id=run_id)
        raise failure("synthetic stream failure")

    model = SimpleNamespace(model_name="requested-model", ainvoke=invoke)
    with (
        patch.object(pricing_cache, "_local_cache", snapshot),
        patch("src.infrastructure.llm.token_capture.time", return_value=started.timestamp()),
        patch("src.infrastructure.llm.factory.get_llm", return_value=model),
        patch.object(instance_spend, "is_instance_spend_blocked", AsyncMock(return_value=False)),
        patch(
            "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
            AsyncMock(),
        ) as ledger,
        patch(
            "src.domains.chat.service.TrackingContext", side_effect=AssertionError("account owner")
        ),
        _fake_session(),
    ):
        with pytest.raises(failure):
            await _translate_description_all_langs("synthetic", None)

    ledger.assert_awaited_once()
    assert ledger.await_args.kwargs["now"] == started
    assert float(ledger.await_args.kwargs["cost_eur"]) == pytest.approx(0.000513)
    records = captures[0].get_billing_records("requested-model")
    assert len(records) == 1 and records[0].model_name == "provider-model"
    assert records[0].status == "error" and records[0].failure_kind is not None
    assert captures[0].claim_billing_records("requested-model") == ()
