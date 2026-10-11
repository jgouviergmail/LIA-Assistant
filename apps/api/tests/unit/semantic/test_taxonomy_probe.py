"""Offline qualification of probe policy, budget boundaries and failure persistence."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage

from scripts.semantic_simulation import taxonomy_run
from scripts.semantic_simulation.runtime import ProbeRuntime, Slot
from scripts.semantic_simulation.taxonomy_corpus import TAXONOMY_CASES, TaxonomyRoutingCase
from scripts.semantic_simulation.taxonomy_fixtures import full_domain_menu
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.infrastructure.cache.pricing_cache import CachedModelPrice, PricingCacheData

pytestmark = pytest.mark.unit


@pytest.fixture
def probe() -> ProbeRuntime:
    price = CachedModelPrice(1, 1, 0)
    return ProbeRuntime(
        clients={},
        configuration={
            "query_analyzer": {
                "model": "fictional-local-probe",
                "provider": "test",
                "effective": {"max_tokens": 512},
            }
        },
        prices={"query_analyzer": price},
        snapshot=PricingCacheData(
            {"fictional-local-probe": price}, usd_eur_rate=1.0, last_refresh_ts=0
        ),
        budget_eur=0.5,
    )


def _case() -> TaxonomyRoutingCase:
    return TaxonomyRoutingCase(
        "read_contact",
        "Lis les coordonnées de Clara dans mes contacts.",
        ("contact",),
        expected_primary="contact",
    )


def _payload(primary: str = "contact") -> dict[str, object]:
    return {
        "intent": "action",
        "primary_domain": primary,
        "secondary_domains": [],
        "confidence": 0.9,
        "english_query": "Read Clara's contact details.",
        "reasoning": "Contact details explicitly requested",
        "is_mutation_intent": False,
    }


def _response(payload: dict[str, object]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "QueryAnalysisOutput", "args": payload, "id": "offline-call"}],
    )


def _assert_menu_in_prompt(prompt: str, menu: list[dict[str, str]]) -> None:
    for item in menu:
        assert f"- **{item['name']}**: {item['description']}" in prompt


def test_prompt_contains_every_current_native_domain() -> None:
    expected = {
        name
        for name, config in DOMAIN_REGISTRY.items()
        if config.is_routable and not config.metadata.get("dynamic")
    }
    with full_domain_menu("native") as menu:
        assert {item["name"] for item in menu} == expected
        _assert_menu_in_prompt(taxonomy_run._prompt(_case(), menu), menu)


@pytest.mark.asyncio
async def test_decision_records_raw_invention_but_policy_and_oracle_reject_it(
    probe: ProbeRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    invocation = AsyncMock(return_value=_response(_payload("mcp_nonexistent")))
    monkeypatch.setattr(taxonomy_run, "invoke", invocation)
    with full_domain_menu("native") as menu:
        result = await taxonomy_run._decision(probe, _case(), menu)
    assert result["raw_primary"] == "mcp_nonexistent"
    assert result["primary"] is None
    assert result["secondary"] == []
    assert "missing_domains:contact" in result["failures"]
    assert "missing_primary_domain" in result["failures"]
    assert result["unavailable_domains"] == ["mcp_nonexistent"]
    invocation.assert_awaited_once()


@pytest.mark.asyncio
async def test_policy_success_preserves_the_models_raw_scope_failure(
    probe: ProbeRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {**_payload(), "secondary_domains": ["mcp_nonexistent"]}
    monkeypatch.setattr(taxonomy_run, "invoke", AsyncMock(return_value=_response(payload)))
    with full_domain_menu("native") as menu:
        result = await taxonomy_run._decision(probe, _case(), menu)
    assert result["primary"] == "contact"
    assert result["secondary"] == []
    assert result["failures"] == []
    assert result["raw_secondary"] == ["mcp_nonexistent"]
    assert result["raw_failures"] == ["unwanted_domains:mcp_nonexistent"]
    assert result["unavailable_domains"] == ["mcp_nonexistent"]
    assert taxonomy_run._summary([result]) == {
        "cases_recorded": 1,
        "cases_evaluated": 1,
        "passed": 1,
        "failed": 0,
        "raw_failed": 1,
        "unavailable_selections": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _response({"primary_domain": "contact"}),
        _response({**_payload(), "confidence": 1.1}),
    ],
)
async def test_invalid_payload_is_not_scored_as_a_routing_success(
    probe: ProbeRuntime, monkeypatch: pytest.MonkeyPatch, response: AIMessage
) -> None:
    invocation = AsyncMock(return_value=response)
    monkeypatch.setattr(taxonomy_run, "invoke", invocation)
    with full_domain_menu("native") as menu:
        result = await taxonomy_run._decision(probe, _case(), menu)
    assert result == {"failures": ["schema_validation_failed"]}
    invocation.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_json_is_explicitly_rejected(
    probe: ProbeRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(taxonomy_run, "invoke", AsyncMock(return_value=AIMessage(content="broken")))
    with full_domain_menu("native") as menu:
        result = await taxonomy_run._decision(probe, _case(), menu)
    assert result == {"failures": ["invalid_structured_result"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "calls",
    [
        [{"name": "UnexpectedFunction", "args": _payload(), "id": "wrong-name"}],
        [
            {"name": "QueryAnalysisOutput", "args": _payload(), "id": "first"},
            {"name": "QueryAnalysisOutput", "args": _payload("email"), "id": "second"},
        ],
    ],
)
async def test_only_one_call_to_the_requested_output_contract_is_accepted(
    probe: ProbeRuntime, monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]]
) -> None:
    response = AIMessage(content="", tool_calls=calls)
    monkeypatch.setattr(taxonomy_run, "invoke", AsyncMock(return_value=response))
    with full_domain_menu("native") as menu:
        result = await taxonomy_run._decision(probe, _case(), menu)
    assert result in (
        {"failures": ["call_contract_failed"]},
        {"failures": ["invalid_structured_result"]},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("structured_call", [True, False])
async def test_provider_output_cut_cannot_pass_even_with_parseable_fields(
    probe: ProbeRuntime, monkeypatch: pytest.MonkeyPatch, structured_call: bool
) -> None:
    response = (
        _response(_payload()) if structured_call else AIMessage(content=json.dumps(_payload()))
    )
    response.response_metadata["finish_reason"] = "length"
    monkeypatch.setattr(taxonomy_run, "invoke", AsyncMock(return_value=response))
    with full_domain_menu("native") as menu:
        result = await taxonomy_run._decision(probe, _case(), menu)
    assert result == {"failures": ["output_truncated"]}


@pytest.mark.asyncio
async def test_decision_sends_the_complete_menu_and_production_output_schema(
    probe: ProbeRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    invocation = AsyncMock(return_value=_response(_payload()))
    monkeypatch.setattr(taxonomy_run, "invoke", invocation)
    with full_domain_menu("native") as menu:
        await taxonomy_run._decision(probe, _case(), menu)
        call = invocation.await_args
        assert call is not None
        assert call.args[0] is probe and call.args[1] == "query_analyzer"
        prompt = "\n".join(str(message.content) for message in call.args[2])
        _assert_menu_in_prompt(prompt, menu)
    assert _case().query in prompt
    assert call.kwargs["tool_choice"] == "QueryAnalysisOutput"
    schema = call.kwargs["tools"][0]["function"]
    assert schema["name"] == "QueryAnalysisOutput"
    assert {"intent", "english_query", "reasoning"} <= set(schema["parameters"]["required"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("budget", "prior"),
    [
        (float("nan"), 0.0),
        (float("inf"), 0.0),
        (float("-inf"), 0.0),
        (0.5, float("nan")),
        (0.5, float("inf")),
        (0.5, float("-inf")),
        (0.0, 0.0),
        (-0.1, 0.0),
        (2.01, 0.0),
        (0.5, -0.1),
        (0.51, 1.5),
    ],
)
@pytest.mark.parametrize("real_models", [True, False])
async def test_direct_run_rejects_invalid_cumulative_budget_before_preparation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    budget: float,
    prior: float,
    real_models: bool,
) -> None:
    prepare = AsyncMock(side_effect=AssertionError("Preparation must remain unreachable"))
    invoke = AsyncMock(side_effect=AssertionError("Provider must remain unreachable"))
    monkeypatch.setattr(taxonomy_run, "prepare", prepare)
    monkeypatch.setattr(taxonomy_run, "invoke", invoke)
    output = tmp_path / "report.json"
    with pytest.raises(ValueError, match="cumulative authorized 2 EUR"):
        await taxonomy_run.run(
            output,
            real_models=real_models,
            budget_eur=budget,
            prior_spend=prior,
            cases=(_case(),),
        )
    prepare.assert_not_awaited()
    invoke.assert_not_awaited()
    assert not output.exists()


@pytest.mark.asyncio
async def test_paid_failure_is_saved_before_exit_and_stops_every_later_case(
    probe: ProbeRuntime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prepare = AsyncMock(return_value=probe)
    monkeypatch.setattr(taxonomy_run, "prepare", prepare)
    paid_cost = 0.000003
    attempted: list[str] = []

    async def paid_failure(
        observed: ProbeRuntime,
        slot: Slot,
        messages: list[BaseMessage],
        *,
        case: str,
        tools: list[dict[str, object]] | None = None,
        tool_choice: str | None = None,
    ) -> AIMessage:
        attempted.append(case)
        observed.spent_eur += paid_cost
        observed.calls.append(
            {"case": case, "slot": slot, "cost_eur": paid_cost, "error_type": "TimeoutError"}
        )
        raise TimeoutError("Offline failure after metered usage")

    monkeypatch.setattr(taxonomy_run, "invoke", paid_failure)
    output = tmp_path / "failure.json"
    with pytest.raises(TimeoutError, match="metered usage"):
        await taxonomy_run.run(
            output,
            real_models=True,
            budget_eur=0.5,
            prior_spend=0.02,
            cases=TAXONOMY_CASES[:2],
        )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert attempted == [TAXONOMY_CASES[0].name]
    assert report["cost_eur"] == paid_cost
    assert report["cumulative_cost_eur"] == pytest.approx(0.02 + paid_cost)
    assert report["calls"] == probe.calls
    assert report["results"][0]["failures"] == ["probe_stopped:TimeoutError"]
    assert report["summary"] == {
        "cases_recorded": 1,
        "cases_evaluated": 1,
        "passed": 0,
        "failed": 1,
        "raw_failed": 0,
        "unavailable_selections": 0,
    }
    assert "finished_at" not in report
    prepare.assert_awaited_once_with(0.5)
