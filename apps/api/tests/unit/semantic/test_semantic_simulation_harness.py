"""Offline probes of the measurement harness, not evidence about any model."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from scripts.semantic_simulation import execution, prompts, runtime
from scripts.semantic_simulation.corpus import SCENARIOS, assess, read_result
from src.core.context import request_tool_manifests_ctx
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.infrastructure.cache.pricing_cache import CachedModelPrice, PricingCacheData

pytestmark = pytest.mark.unit


def test_no_retry_probe_also_disables_the_existing_sdk_transport() -> None:
    client = ChatOpenAI(model="fictional", api_key="unused-test-key", max_retries=4)
    bounded = runtime._without_retries(client)
    assert isinstance(bounded, ChatOpenAI)
    assert bounded.max_retries == 0
    assert bounded.root_async_client.max_retries == 0
    assert bounded.async_client is bounded.root_async_client.chat.completions
    assert client.max_retries == 4


@pytest.fixture(scope="module")
def registry() -> AgentRegistry:
    return prompts.registry_for_probe()


def _timing() -> dict[str, object]:
    return {
        "summary": "Revue",
        "start_datetime": "2026-10-08T10:00:00",
        "end_datetime": "2026-10-08T11:00:00",
    }


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda case: case.name)
def test_each_prompt_is_built_offline_with_its_exact_native_contracts(
    scenario: prompts.Scenario, registry: AgentRegistry
) -> None:
    selected = prompts.manifests_for_case(registry, scenario)
    token = request_tool_manifests_ctx.set([])
    try:
        planner = prompts.planner_messages(scenario, selected, registry)
        react = prompts.react_messages(scenario, selected)
        assert len(planner) == len(react) == 2
        assert scenario.query in str(planner[1].content)
        assert react[1].content == scenario.query
        assert request_tool_manifests_ctx.get() == []
        if scenario.name == "mail_sender_to_attendees":
            assert "from_email" in str(planner[0].content)
            assert "email_address" in str(react[0].content)
    finally:
        request_tool_manifests_ctx.reset(token)


@pytest.mark.parametrize(
    ("scenario_index", "read_name", "arguments"),
    [
        (
            0,
            "get_contacts_tool",
            {**_timing(), "attendees": ["$steps.read.contacts[0].emailAddresses[0].value"]},
        ),
        (1, None, {**_timing(), "attendees": ["ada@example.test"]}),
        (2, "get_emails_tool", {**_timing(), "attendees": ["$steps.read.emails[0].from_email"]}),
        (
            3,
            "get_emails_tool",
            {"title": "$steps.read.emails[0].subject", "notes": "$steps.read.emails[0].body"},
        ),
    ],
)
def test_documented_plan_examples_resolve_but_never_execute_native_tools(
    registry: AgentRegistry,
    monkeypatch: pytest.MonkeyPatch,
    scenario_index: int,
    read_name: str | None,
    arguments: dict[str, object],
) -> None:
    forbidden = MagicMock(side_effect=AssertionError("Native tools are an unexecuted boundary"))
    monkeypatch.setattr(BaseTool, "invoke", forbidden)
    monkeypatch.setattr(BaseTool, "ainvoke", forbidden)
    steps: list[dict[str, object]] = []
    if read_name is not None:
        steps.append({"id": "read", "tool_name": read_name, "parameters": {"query": "Ada"}})
    scenario = SCENARIOS[scenario_index]
    steps.append(
        {
            "id": "action",
            "tool_name": scenario.action,
            "parameters": arguments,
            "depends_on": ["read"] if read_name else [],
        }
    )
    result = execution.simulate_plan(
        scenario, "```json\n" + json.dumps({"steps": steps}) + "\n```", registry
    )
    assert result["failures"] == []
    calls = result["calls"]
    assert isinstance(calls, list)
    observed = calls[-1]["arguments"]
    if scenario_index == 3:
        assert observed["title"] == "Revue Ada"
        assert observed["notes"] == "N/A\nVérifier le dossier 123, sans modification."
    else:
        assert observed["attendees"] == ["ada@example.test"]
    forbidden.assert_not_called()


def test_oracle_rejects_wrong_mailbox_and_unnecessary_reads() -> None:
    actions: list[dict[str, object]] = [
        {"name": "get_contacts_tool", "arguments": {"query": "Ada"}},
        {
            "name": "create_event_tool",
            "arguments": {**_timing(), "attendees": ["other@example.test"]},
        },
    ]
    failures = assess(SCENARIOS[1], actions)
    assert any("attendees" in failure for failure in failures)
    assert any("Reads" in failure for failure in failures)


def test_incomplete_plan_is_refused_before_read_boundaries(
    registry: AgentRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = MagicMock(side_effect=AssertionError("Invalid plans cannot be simulated"))
    monkeypatch.setattr(execution, "read_result", boundary)
    result = execution.simulate_plan(
        SCENARIOS[0],
        json.dumps(
            {"steps": [{"id": "action", "tool_name": "create_event_tool", "parameters": {}}]}
        ),
        registry,
    )
    assert result["validation"] and result["calls"] == []
    boundary.assert_not_called()
    with pytest.raises(ValidationError):
        execution.parse_plan(json.dumps({"steps": [{"tool_name": "get_contacts_tool"}]}), registry)


def test_corpus_returns_provider_paths_and_keeps_header_separate_from_mailbox() -> None:
    contacts = read_result("get_contacts_tool")["contacts"]
    emails = read_result("get_emails_tool")["emails"]
    assert isinstance(contacts, list) and isinstance(emails, list)
    assert contacts[0]["emailAddresses"][0]["value"] == "ada@example.test"
    assert emails[0]["from"] == '"Lovelace, Ada" <ada@example.test>'
    assert emails[0]["from_email"] == "ada@example.test"


def _budget_runtime(price: CachedModelPrice, *, budget: float = 2.0) -> runtime.ProbeRuntime:
    return runtime.ProbeRuntime(
        clients={},
        configuration={
            "planner": {
                "effective": {"max_tokens": 50_000},
                "model": "fictional",
                "provider": "test",
            }
        },
        prices={"planner": price},
        snapshot=PricingCacheData({"fictional": price}, usd_eur_rate=0.9, last_refresh_ts=0),
        budget_eur=budget,
    )


def test_upper_cost_covers_peak_cached_window_and_cache_write_costs() -> None:
    price = CachedModelPrice(
        input_unit_price=1,
        output_unit_price=1,
        cached_input_unit_price=2,
        cache_write_multiplier=1.25,
        time_slots=[
            {
                "start_utc": "00:00",
                "end_utc": "12:00",
                "input_unit_price": 2,
                "cached_input_unit_price": 100,
                "output_unit_price": 3,
            }
        ],
    )
    estimate = runtime.upper_cost_eur(_budget_runtime(price), "planner", input_bytes=100)
    # 10,100 input tokens at the highest selectable rate, 50,000 output tokens,
    # and the published 0.9 EUR/USD exchange rate. This is an independent bound.
    assert estimate >= 1.27125


@pytest.mark.asyncio
async def test_euro_ceiling_prevents_even_a_fake_provider_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _budget_runtime(CachedModelPrice(100, 100, 100), budget=2.0)
    provider = MagicMock()
    provider.ainvoke = AsyncMock(side_effect=AssertionError("No invocation above the ceiling"))
    probe.clients["planner"] = provider
    monkeypatch.setattr(runtime, "_check_database_identity", AsyncMock())
    monkeypatch.setattr(runtime, "enforce_usage_limit", AsyncMock())
    settle = AsyncMock()
    monkeypatch.setattr(runtime, "_settle", settle)
    with pytest.raises(ValueError, match="euro ceiling"):
        await runtime.invoke(
            probe, "planner", [HumanMessage(content="Fictional test")], case="guard"
        )
    provider.ainvoke.assert_not_awaited()
    settle.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_database_model_is_not_replaced_with_a_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    database.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def empty_database() -> AsyncIterator[MagicMock]:
        yield database

    factory = MagicMock(side_effect=AssertionError("No inherited provider may be created"))
    monkeypatch.setattr(runtime, "get_db_context", empty_database)
    monkeypatch.setattr(runtime, "get_llm", factory)
    with pytest.raises(ValueError, match="explicit model AND provider"):
        await runtime.prepare(2.0)
    factory.assert_not_called()
