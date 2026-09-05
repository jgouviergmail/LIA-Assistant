"""The traced Ollama client publishes what it sends, so the register can read it."""

from __future__ import annotations

import pytest

from src.infrastructure.llm.inference_params import capture_inference_params
from src.infrastructure.llm.providers.ollama_chat import ChatOllamaTraced

pytestmark = pytest.mark.unit


def _client(**overrides: object) -> ChatOllamaTraced:
    params: dict[str, object] = {
        "model": "qwen3.8:27b",
        "base_url": "http://ollama.local:11434",
        "temperature": 0.2,
        "top_p": 0.9,
        "num_predict": 1000,
        "num_ctx": 32768,
        "reasoning": "low",
    }
    params.update(overrides)
    return ChatOllamaTraced(**params)  # type: ignore[arg-type]


def test_the_client_stays_a_chat_ollama() -> None:
    assert _client()._llm_type == "chat-ollama"


def test_the_sent_parameters_are_published() -> None:
    params = _client()._get_invocation_params()
    assert params["_type"] == "chat-ollama"
    assert params["model"] == "qwen3.8:27b"
    assert params["temperature"] == 0.2
    assert params["top_p"] == 0.9
    assert params["num_predict"] == 1000
    assert params["num_ctx"] == 32768
    assert params["reasoning"] == "low"


def test_a_parameter_that_was_not_set_is_not_invented() -> None:
    params = _client(top_p=None, num_ctx=None, reasoning=None)._get_invocation_params()
    assert "top_p" not in params
    assert "num_ctx" not in params
    assert "reasoning" not in params


def test_a_per_call_reasoning_override_wins() -> None:
    params = _client()._get_invocation_params(reasoning=False)
    assert params["reasoning"] is False


def test_the_register_reads_the_ollama_call_in_its_own_vocabulary() -> None:
    """End to end into ADR-263's reader: provider, cap and level, no provider spelling."""
    captured = capture_inference_params(_client()._get_invocation_params())
    assert captured.provider == "ollama"
    assert captured.temperature == 0.2
    assert captured.top_p == 0.9
    assert captured.max_output_tokens == 1000
    assert captured.reasoning_level == "low"
    assert captured.reasoning_budget_tokens is None


def test_thinking_switched_off_reads_as_none() -> None:
    captured = capture_inference_params(_client(reasoning=False)._get_invocation_params())
    assert captured.reasoning_level == "none"


def test_the_explicit_server_default_reads_as_no_stated_depth() -> None:
    """``True`` asks the server to think at ITS default depth: honest is « unknown »."""
    captured = capture_inference_params(_client(reasoning=True)._get_invocation_params())
    assert captured.reasoning_level is None
