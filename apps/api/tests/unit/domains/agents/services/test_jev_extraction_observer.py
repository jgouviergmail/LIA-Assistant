"""Observation never controls baseline extraction or leaves an orphan native task."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("choice", ["empty", "useful", "uncertain"])
async def test_every_native_judgment_keeps_baseline_and_records_actual_output(choice):
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    answer = ChoiceAnswer(
        type="choice", choice=choice, confidence=0.99, probabilities={choice: 0.99, "other": 0.01}
    )
    with (
        patch.object(
            module,
            "choose_with_jev",
            AsyncMock(return_value=DecisionAttempt(outcome="success", answer=answer)),
        ) as native,
        patch.object(module, "record_action", AsyncMock()) as record,
    ):
        baseline = AsyncMock(return_value='[{"action":"update","content":"new fact"}]')
        async with module.observe_extraction(
            JevUsage.OBSERVE_MEMORY,
            str(uuid4()),
            "run",
            "Complete policy and full rendered context",
        ) as observed:
            result = await baseline()
            observed.set_output(result)
    baseline.assert_awaited_once()
    assert result.startswith('[{"action"')
    assert (
        native.call_args.kwargs["state"]["extractor_prompt"]
        == "Complete policy and full rendered context"
    )
    assert record.call_args.kwargs["action"] == "observed"
    assert "new fact" in record.call_args.kwargs["observed_result"].text


@pytest.mark.parametrize("error", [RuntimeError("provider"), TimeoutError(), ValueError("quota")])
async def test_native_failure_cannot_break_baseline(error):
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    with patch.object(module, "choose_with_jev", AsyncMock(side_effect=error)):
        async with module.observe_extraction(
            JevUsage.OBSERVE_MEMORY, str(uuid4()), "r", "p"
        ) as observation:
            observation.set_output("baseline result")


async def test_baseline_error_cancels_and_joins_observer():
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    entered, closed = asyncio.Event(), asyncio.Event()

    async def native(**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    with patch.object(module, "choose_with_jev", native):
        with pytest.raises(RuntimeError, match="baseline"):
            async with module.observe_extraction(JevUsage.OBSERVE_JOURNAL, str(uuid4()), "r", "p"):
                await entered.wait()
                raise RuntimeError("baseline")
    assert closed.is_set()


async def test_baseline_cancellation_propagates_after_observer_cleanup():
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    closed = asyncio.Event()

    async def native(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    with patch.object(module, "choose_with_jev", native):
        with pytest.raises(asyncio.CancelledError):
            async with module.observe_extraction(
                JevUsage.OBSERVE_OPEN_LOOPS, str(uuid4()), "r", "p"
            ):
                await asyncio.sleep(0)
                raise asyncio.CancelledError()
    assert closed.is_set()


async def test_debug_storage_failure_is_nonfatal_and_output_is_bounded():
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    with (
        patch.object(
            module, "choose_with_jev", AsyncMock(return_value=DecisionAttempt(outcome="disabled"))
        ),
        patch.object(module, "record_action", AsyncMock(side_effect=OSError())) as record,
    ):
        async with module.observe_extraction(
            JevUsage.OBSERVE_INTERESTS, str(uuid4()), "r", "p"
        ) as observed:
            observed.set_output("x" * 20000)
    value = record.call_args.kwargs["observed_result"]
    assert len(value.text) <= 6000 and value.omitted_characters > 0


@pytest.mark.parametrize("text", ["[" * 1500 + "0" + "]" * 1500, '{"value": NaN}', "not JSON"])
def test_unusual_baseline_output_remains_inspectable_and_never_breaks_extraction(text):
    from src.domains.agents.services.jev_extraction_observer import ExtractionObservation

    observation = ExtractionObservation()
    observation.set_output(text)
    assert observation.result is not None


async def test_missing_owner_does_not_spend_or_prevent_baseline():
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    with patch.object(module, "choose_with_jev", AsyncMock()) as native:
        async with module.observe_extraction(
            JevUsage.OBSERVE_MEMORY, "unknown", None, "policy"
        ) as observation:
            observation.set_output("[]")
    native.assert_not_awaited()


async def test_wait_is_after_baseline_writes_and_accounting_even_when_cancelled():
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    entered, written, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    completed = []

    async def native(**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    @module.observe_extractor(JevUsage.OBSERVE_MEMORY)
    async def baseline(user_id: str, parent_run_id: str) -> str:
        observation = module.start_extraction_observation("full prompt")
        await entered.wait()
        completed.extend(["paid", "written"])
        observation.set_output("[]")
        written.set()
        return "original result"

    with patch.object(module, "choose_with_jev", native):
        task = asyncio.create_task(baseline(str(uuid4()), "run"))
        await written.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert closed.is_set() and completed == ["paid", "written"]


async def test_background_observer_never_joins_an_inherited_tracker():
    from src.core.context import current_tracker
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    inherited = object()
    token = current_tracker.set(inherited)

    async def native(**kwargs):
        assert current_tracker.get() is None
        assert kwargs["run_id"] == "parent-run"
        return DecisionAttempt(outcome="disabled")

    try:
        with patch.object(module, "choose_with_jev", native):
            async with module.observe_extraction(
                JevUsage.OBSERVE_MEMORY, str(uuid4()), "parent-run", "full"
            ):
                assert current_tracker.get() is inherited
        assert current_tracker.get() is inherited
    finally:
        current_tracker.reset(token)


async def test_guarded_extractor_without_model_call_never_starts_observer():
    from src.domains.agents.services import jev_extraction_observer as module
    from src.domains.llm_config.jev_registry import JevUsage

    @module.observe_extractor(JevUsage.OBSERVE_INTERESTS)
    async def baseline(user_id: str) -> int:
        return 0

    with patch.object(module, "choose_with_jev", AsyncMock()) as native:
        assert await baseline(user_id=str(uuid4())) == 0
    native.assert_not_awaited()
