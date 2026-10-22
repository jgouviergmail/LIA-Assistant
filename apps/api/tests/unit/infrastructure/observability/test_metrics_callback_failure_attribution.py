"""Failed model calls retain their own provider/model without storing inputs."""

from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from structlog.testing import capture_logs

from src.core.field_names import FIELD_LLM_PROVIDER
from src.infrastructure.observability.callbacks import MetricsCallbackHandler
from src.infrastructure.observability.metrics_agents import llm_api_calls_total

pytestmark = pytest.mark.unit


class _NamedModel(GenericFakeChatModel):
    """Expose the public ``model`` spelling used by native chat adapters."""

    model: str = "gemini-synthetic"


async def test_a_native_adapter_model_attribute_attributes_a_failure() -> None:
    callback = MetricsCallbackHandler(llm=_NamedModel(messages=iter([])))
    with capture_logs() as logs:
        await callback.on_llm_error(RuntimeError("synthetic refusal"), run_id=uuid4())

    (event,) = [entry for entry in logs if entry["event"] == "llm_api_call_failed"]
    assert (event["model"], event["provider"]) == ("gemini-synthetic", "google")


async def test_parallel_runs_keep_their_invocation_and_declared_provider() -> None:
    callback = MetricsCallbackHandler(node_name="synthetic_attribution")
    run_a, run_b = uuid4(), uuid4()
    await callback.on_chat_model_start(
        {},
        [],
        run_id=run_a,
        metadata={FIELD_LLM_PROVIDER: "qwen"},
        invocation_params={"model": "qwen-synthetic", "_type": "openai-chat", "api_key": "secret"},
    )
    await callback.on_llm_start(
        {},
        ["private synthetic prompt"],
        run_id=run_b,
        invocation_params={"model_name": "native-synthetic", "_type": "chat-ollama"},
    )
    label_a = llm_api_calls_total.labels(
        model="qwen-synthetic", node_name="synthetic_attribution", status="error"
    )
    before = label_a._value.get()
    with capture_logs() as logs:
        await callback.on_llm_error(RuntimeError("synthetic refusal"), run_id=run_b)
        await callback.on_llm_error(RuntimeError("synthetic refusal"), run_id=run_a)
        await callback.on_llm_error(RuntimeError("duplicate"), run_id=run_a)

    events = [entry for entry in logs if entry["event"] == "llm_api_call_failed"]
    assert [(event["model"], event["provider"]) for event in events] == [
        ("native-synthetic", "ollama"),
        ("qwen-synthetic", "qwen"),
    ]
    assert label_a._value.get() - before == 1
    assert "secret" not in str(vars(callback))
    assert "private synthetic prompt" not in str(vars(callback))
    assert not callback.start_times
    assert not callback.pricing_snapshots


@pytest.mark.parametrize(
    ("served", "expected"),
    [("qwen-served-synthetic", "qwen-served-synthetic"), (None, "qwen-synthetic:local")],
)
async def test_partial_usage_keeps_the_served_model_and_configured_provider(
    served: str | None, expected: str
) -> None:
    callback = MetricsCallbackHandler()
    run_id = uuid4()
    await callback.on_chat_model_start(
        {},
        [],
        run_id=run_id,
        metadata={FIELD_LLM_PROVIDER: "ollama"},
        invocation_params={"model": "qwen-synthetic:local", "_type": "chat-ollama"},
    )
    partial = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                        response_metadata={"model_name": served} if served else {},
                    )
                )
            ]
        ]
    )
    calls = llm_api_calls_total.labels(model=expected, node_name="unknown", status="error")
    before = calls._value.get()
    with capture_logs() as logs:
        await callback.on_llm_error(
            RuntimeError("synthetic refusal"), run_id=run_id, response=partial
        )

    (event,) = [entry for entry in logs if entry["event"] == "llm_api_call_failed"]
    assert (event["model"], event["provider"]) == (expected, "ollama")
    assert calls._value.get() - before == 1


async def test_success_releases_the_identity_of_its_run() -> None:
    callback = MetricsCallbackHandler()
    run_id = uuid4()
    await callback.on_chat_model_start(
        {}, [], run_id=run_id, invocation_params={"model": "synthetic-success"}
    )
    await callback.on_llm_end(LLMResult(generations=[]), run_id=run_id)

    assert "synthetic-success" not in str(vars(callback))
