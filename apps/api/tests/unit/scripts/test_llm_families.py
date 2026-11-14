"""The model families a measurement asks, named one way for every bench."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from scripts.llm_families import family_llm, named_families, parse_families, price_response
from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent

pytestmark = pytest.mark.unit


def test_no_family_named_asks_the_instance_s_own_slot() -> None:
    assert parse_families(None) == [None]
    assert parse_families("") == [None]


def test_a_family_is_a_provider_a_model_and_a_reasoning_level() -> None:
    assert parse_families("deepseek:deepseek-flash@none, openai:gpt-4.1-mini") == [
        ("deepseek", "deepseek-flash", "none"),
        ("openai", "gpt-4.1-mini", "provider_default"),
    ]


def test_an_unknown_reasoning_level_is_refused() -> None:
    with pytest.raises(SystemExit):
        parse_families("deepseek:deepseek-flash@loud")


def test_a_bench_that_asks_no_configured_slot_wants_each_family_named() -> None:
    assert named_families("openai:gpt-4.1-mini@low") == [("openai", "gpt-4.1-mini", "low")]
    with pytest.raises(SystemExit):
        named_families("")


def test_another_family_keeps_every_setting_of_the_slot_but_its_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: dict[str, object] = {}

    def fake_get_llm(slot: str, config_override: object | None = None) -> str:
        built.update(slot=slot, config=config_override)
        return "llm"

    monkeypatch.setattr("scripts.llm_families.get_llm", fake_get_llm)

    name, llm, config = family_llm("query_analyzer", ("openai", "gpt-4.1-mini", "none"))

    slot = get_llm_config_for_agent(settings, "query_analyzer")
    assert (name, llm, built["slot"]) == ("gpt-4.1-mini", "llm", "query_analyzer")
    assert built["config"] is config
    assert (config.provider, config.model) == ("openai", "gpt-4.1-mini")
    assert config.reasoning_effort.level == "none"
    # Everything else is the slot's own.
    assert config.temperature == slot.temperature
    assert config.max_tokens == slot.max_tokens


def test_a_response_is_priced_from_its_own_usage_and_its_own_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[object, ...]] = []

    def tariff(*args: object, **kwargs: object) -> tuple[float, float]:
        asked.append((*args, kwargs))
        return 0.002, 0.0018

    monkeypatch.setattr("scripts.llm_families.get_cached_cost_usd_eur", tariff)
    response = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        response_metadata={"model_name": "served-model"},
    )

    priced = price_response(response, "asked-model")

    assert (priced.tokens_in, priced.tokens_out) == (120, 30)
    assert (priced.cost_usd, priced.cost_eur) == (0.002, 0.0018)
    # The model that ANSWERED is priced, the one asked only when it says nothing.
    assert asked[0][0] == "served-model"
