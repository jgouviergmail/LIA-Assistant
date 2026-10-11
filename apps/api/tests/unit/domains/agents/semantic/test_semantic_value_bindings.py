"""Independent proof oracles using actual native contracts and canonical payloads."""

import json
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from langchain_core.runnables import RunnableConfig

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.google_contacts.catalogue_manifests import get_contacts_catalogue_manifest
from src.domains.agents.places.catalogue_manifests import get_current_location_catalogue_manifest
from src.domains.agents.semantic.expansion_service import generate_jinja2_suggestions
from src.domains.agents.semantic.param_guard import (
    check_semantic_params,
    config_with_binding_evidence,
)
from src.domains.agents.semantic.reference_bindings import config_with_resolved_bindings
from src.domains.agents.semantic.registry_value_bindings import (
    bind_observed_arguments,
    config_with_registry_bindings,
    registry_source_observations,
)
from src.domains.agents.semantic.value_bindings import (
    SemanticValueBinding,
    binding_scope_from_config,
    parse_value_bindings,
    source_observation,
)
from src.domains.agents.weather.catalogue_manifests import get_current_weather_catalogue_manifest

ACCOUNT = "semantic-account"
CONFIG: RunnableConfig = {"metadata": {"user_id": ACCOUNT}}


@contextmanager
def _contracts() -> Iterator[None]:
    token = request_tool_manifests_ctx.set(
        [
            get_current_weather_catalogue_manifest,
            get_current_location_catalogue_manifest,
            get_contacts_catalogue_manifest,
        ]
    )
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(token)


def _registry(*, locality: str = "Nancy") -> dict[str, object]:
    return {
        "location_nancy": {
            "id": "location_nancy",
            "type": "LOCATION",
            "payload": {"locality": locality, "formatted_address": "Nancy, France"},
            "meta": {"tool_name": "get_current_location_tool", "source": "geocoding"},
        },
        "contact_nancy": {
            "id": "contact_nancy",
            "type": "CONTACT",
            "payload": {
                "names": [{"displayName": "Nancy"}],
                "addresses": [{"formattedValue": "12 rue de Metz, Nancy"}],
            },
            "meta": {"tool_name": "get_contacts_tool", "source": "google_contacts"},
        },
    }


def _selected_config() -> RunnableConfig:
    registry = _registry()
    steps = {"where": {"locations": [{"locality": "Nancy", "_registry_id": "location_nancy"}]}}
    return config_with_resolved_bindings(
        CONFIG,
        tool_name="get_current_weather_tool",
        original_arguments={"location": "$steps.where.locations[0].locality"},
        resolved_arguments={"location": "Nancy"},
        completed_steps=steps,
        context={},
        registry=registry,
    )


def _violation(config: RunnableConfig, value: str = "Nancy") -> object:
    bindings, account, sources = binding_scope_from_config(config)
    return check_semantic_params(
        "get_current_weather_tool",
        {"location": value},
        frozenset({"nancy"}),
        value_bindings=bindings,
        account_id=account,
        known_sources=sources,
    )


def test_selected_city_reference_exempts_homonym_using_real_native_payload() -> None:
    with _contracts():
        config = _selected_config()
        bindings, _, sources = binding_scope_from_config(config)
        assert bindings[0].entity_ref == "location_nancy"
        assert bindings[0].predicate == "locality"
        assert bindings[0].source_ref in sources
        assert _violation(config) is None


def test_weather_linking_hints_offer_the_declared_full_address_alternative_first() -> None:
    with _contracts():
        hints = generate_jinja2_suggestions(
            "get_current_weather_tool",
            "location",
            ["people"],
            step_tool_mapping={"people": "get_contacts_tool"},
        )
        assert hints[0] == "$steps.people.contacts[0].addresses[0].formattedValue"


def test_place_already_in_registry_does_not_bind_the_daughters_name_by_equality() -> None:
    with _contracts():
        config = config_with_registry_bindings(
            CONFIG,
            _registry(),
            "get_current_weather_tool",
            {"location": "Nancy"},
        )
        assert binding_scope_from_config(config)[0] == ()
        assert _violation(config) is not None


def test_actual_contact_address_can_feed_weather_without_retyping_contact_name() -> None:
    with _contracts():
        registry = _registry()
        sources = registry_source_observations(registry, ACCOUNT)
        ref = "$registry.contact_nancy.addresses[0].formattedValue"
        assert ref in sources
        assert not any(
            source.value == "Nancy" and source.entity_type == "Contact"
            for source in sources.values()
        )
        bindings = bind_observed_arguments(
            get_current_weather_catalogue_manifest,
            {"location": "12 rue de Metz, Nancy"},
            sources,
            account_id=ACCOUNT,
            selected_sources={"location": ref},
        )
        assert bindings[0].entity_ref == "contact_nancy"
        assert bindings[0].semantic_type == "physical_address"
        assert registry == _registry()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", "another-account"),
        ("status", "missing"),
        ("status", "declared"),
        ("status", "unusable"),
        ("source_ref", "$registry.unknown.locality"),
        ("path", "destination"),
        ("value", "Paris"),
        ("semantic_type", "person_name"),
        ("entity_type", "Contact"),
        ("entity_ref", "contact_nancy"),
        ("predicate", "name"),
        ("role", "recipient"),
    ],
)
def test_forged_or_incomplete_target_proof_never_exempts_collision(field: str, value: str) -> None:
    with _contracts():
        config = _selected_config()
        bindings, account, sources = binding_scope_from_config(config)
        forged = bindings[0].model_copy(update={field: value})
        assert (
            check_semantic_params(
                "get_current_weather_tool",
                {"location": "Nancy"},
                frozenset({"nancy"}),
                value_bindings=[forged],
                account_id=account,
                known_sources=sources,
            )
            is not None
        )


def test_json_checkpoint_roundtrip_carries_canonical_proof_and_keeps_value_unchanged() -> None:
    with _contracts():
        config = _selected_config()
        state = json.loads(json.dumps(config["configurable"]))
        reconstructed = config_with_binding_evidence(CONFIG, state)
        assert reconstructed["configurable"] == state
        assert _violation(reconstructed) is None
        assert binding_scope_from_config(reconstructed)[0][0].value == "Nancy"


def test_stale_config_sidecar_does_not_survive_a_new_state_without_proof() -> None:
    with _contracts():
        cleared = config_with_binding_evidence(_selected_config(), {})
        assert binding_scope_from_config(cleared)[0] == ()
        assert _violation(cleared) is not None


@pytest.mark.parametrize(
    ("invalid", "complete", "status"),
    [
        ("result.people[0].email", True, "present"),
        ("result.people[1].email", True, "unusable"),
        ("result.people[].email", True, "unusable"),
        ("unrelated", False, "declared"),
    ],
)
def test_concrete_mcp_bad_item_never_poisons_siblings_and_truncation_never_proves_presence(
    invalid: str,
    complete: bool,
    status: str,
) -> None:
    observed = source_observation(
        source_ref="$steps.lookup.result.people[1].email",
        source_path="result.people[1].email",
        value="nancy@example.com",
        present=True,
        semantic_type="email_address",
        account_id=ACCOUNT,
        entity_type="Contact",
        entity_ref="contact_nancy",
        predicate="email",
        role="recipient",
        unusable_paths=[invalid],
        observations_complete=complete,
    )
    assert observed.status == status
    assert observed.value == "nancy@example.com"


def test_missing_expired_or_disabled_source_never_becomes_present_evidence() -> None:
    with _contracts():
        registry = _registry()
        item = registry["location_nancy"]
        assert isinstance(item, dict)
        item["payload"] = {"formatted_address": "Nancy, France"}
        sources = registry_source_observations(registry, ACCOUNT)
        assert "$registry.location_nancy.locality" not in sources
        item["payload"] = {"locality": "Nancy"}
        item["meta"] = {
            "tool_name": "get_current_location_tool",
            "ttl_seconds": 1,
            "timestamp": "2020-01-01T00:00:00Z",
        }
        assert (
            registry_source_observations(registry, ACCOUNT)[
                "$registry.location_nancy.locality"
            ].status
            == "declared"
        )
    token = request_tool_manifests_ctx.set([get_current_weather_catalogue_manifest])
    try:
        assert registry_source_observations(_registry(), ACCOUNT) == {}
    finally:
        request_tool_manifests_ctx.reset(token)


def test_canonical_observation_cannot_change_identity_to_contact_name() -> None:
    with _contracts():
        config = _selected_config()
        bindings, account, sources = binding_scope_from_config(config)
        fake = bindings[0].model_copy(update={"entity_type": "Contact", "predicate": "name"})
        assert (
            check_semantic_params(
                "get_current_weather_tool",
                {"location": "Nancy"},
                frozenset({"nancy"}),
                value_bindings=[fake],
                account_id=account,
                known_sources={fake.source_ref: fake},
            )
            is not None
        )


def test_numeric_bool_values_never_compare_as_the_same_evidence() -> None:
    one = SemanticValueBinding(
        path="x",
        value=1,
        semantic_type="latitude",
        source_ref="s",
        account_id=ACCOUNT,
        status="present",
    )
    assert type(parse_value_bindings([one.model_dump()])[0].value) is int
    assert parse_value_bindings([{"unexpected": True}]) == ()


def test_mutation_cutoff_prevents_historical_registry_from_resurrecting_proof() -> None:
    with _contracts():
        config = _selected_config()
        configurable = dict(config.get("configurable") or {})
        cutoff = "2026-10-06T18:00:00+00:00"
        configurable["semantic_source_valid_after"] = cutoff
        registry = _registry()
        item = registry["location_nancy"]
        assert isinstance(item, dict)
        item["meta"] = {
            "tool_name": "get_current_location_tool",
            "timestamp": "2026-10-06T17:59:59+00:00",
        }
        historical = config_with_registry_bindings(
            {**config, "configurable": configurable},
            registry,
            "get_current_weather_tool",
            {"location": "Nancy"},
            selected_sources={"location": "$registry.location_nancy.locality"},
        )
        assert _violation(historical) is not None
        assert (
            binding_scope_from_config(historical)[2]["$registry.location_nancy.locality"].status
            == "declared"
        )
        item["meta"] = {
            "tool_name": "get_current_location_tool",
            "timestamp": "2026-10-06T18:00:01+00:00",
        }
        refreshed = config_with_registry_bindings(
            {**config, "configurable": configurable},
            registry,
            "get_current_weather_tool",
            {"location": "Nancy"},
            selected_sources={"location": "$registry.location_nancy.locality"},
        )
        assert _violation(refreshed) is None
        checkpointed = config_with_binding_evidence(CONFIG, refreshed["configurable"])
        assert checkpointed["configurable"]["semantic_source_valid_after"] == cutoff
