"""Runnable source-path oracles, independent of model-generated plans."""

from typing import Literal

from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.registry.value_contracts import SemanticFieldRole
from src.domains.agents.services.catalogue.closure import (
    catalogue_source_gaps,
    resolve_closure_additions,
)


def contract(
    name: str,
    required: str | None,
    produced: str | None,
    *,
    mutation: Literal["read", "confirm"] = "read",
) -> ToolManifest:
    return ToolManifest(
        name=name,
        agent="contact_agent",
        description="Structural source-path oracle",
        parameters=(
            [ParameterSchema("id", "string", True, "Required handle", semantic_type=required)]
            if required
            else []
        ),
        outputs=(
            [OutputFieldSchema("id", "string", "Produced handle", semantic_type=produced)]
            if produced
            else []
        ),
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mutation_policy=mutation,
        tool_category="readonly" if mutation == "read" else "update",
    )


def cycle() -> tuple[ToolManifest, ToolManifest, ToolManifest]:
    left = contract("left", "event_id", "contact_id")
    right = contract("right", "contact_id", "event_id")
    consumer = contract("consumer", "contact_id", None, mutation="confirm")
    return left, right, consumer


def test_mutual_cycle_never_advertises_a_source_without_a_starting_value() -> None:
    left, right, consumer = cycle()
    result = resolve_closure_additions([consumer], [left, right, consumer])
    assert result.additions == []
    assert result.consumers == {"consumer"}
    assert result.unresolved == {"consumer": {"contact_id"}}
    assert result.blocked_providers == {"left", "right"}


def test_exact_seed_breaks_cycle_and_retains_only_the_needed_runnable_provider() -> None:
    left, right, consumer = cycle()
    result = resolve_closure_additions(
        [consumer],
        [left, right, consumer],
        seeded_parameters={"left": {"id"}},
    )
    assert result.additions == ["left"]
    assert result.unresolved == {}


def test_seed_for_another_parameter_or_tool_never_bootstraps_cycle() -> None:
    left, right, consumer = cycle()
    for seeds in ({"left": {"other_id"}}, {"unavailable": {"id"}}, {"consumer": {"other_id"}}):
        result = resolve_closure_additions(
            [consumer], [left, right, consumer], seeded_parameters=seeds
        )
        assert result.additions == []
        assert result.unresolved == {"consumer": {"contact_id"}}


def test_runnable_alternative_beats_high_scored_provider_with_no_starting_source() -> None:
    left, right, consumer = cycle()
    fallback = contract("fallback", None, "contact_id")
    result = resolve_closure_additions(
        [consumer],
        [left, right, fallback, consumer],
        {"left": 0.99, "fallback": 0.01},
    )
    assert result.additions == ["fallback"]
    assert result.unresolved == {}


def test_every_ancestor_of_a_chain_longer_than_three_hops_is_kept_in_execution_order() -> None:
    types = ["contact_id", "event_id", "message_id", "file_id", "ticket_id"]
    chain = [contract("seed", None, types[0])]
    chain += [
        contract(f"hop_{index}", types[index - 1], type_name)
        for index, type_name in enumerate(types[1:], 1)
    ]
    consumer = contract("consumer", types[-1], None, mutation="confirm")
    result = resolve_closure_additions([consumer], [consumer, *reversed(chain)])
    assert result.additions == ["seed", "hop_1", "hop_2", "hop_3", "hop_4"]
    assert result.unresolved == {}
    assert catalogue_source_gaps([consumer, *chain], chain) == {}
    assert catalogue_source_gaps([consumer, *chain[1:]], chain) == {
        "consumer": {"ticket_id"},
        "hop_1": {"contact_id"},
        "hop_2": {"event_id"},
        "hop_3": {"message_id"},
        "hop_4": {"file_id"},
    }


def test_missing_source_is_explicit_and_mutation_cannot_discover_it() -> None:
    consumer = contract("consumer", "contact_id", None, mutation="confirm")
    mutation = contract("create", None, "contact_id", mutation="confirm")
    result = resolve_closure_additions([consumer], [consumer, mutation])
    assert result.additions == []
    assert result.unresolved == {"consumer": {"contact_id"}}


def test_preseeded_consumer_does_not_request_a_lookup_for_another_entity() -> None:
    _, _, consumer = cycle()
    result = resolve_closure_additions(
        [consumer], [consumer], seeded_parameters={"consumer": {"id"}}
    )
    assert result.additions == []
    assert result.consumers == set()
    assert result.unresolved == {}


def test_declared_location_alternatives_require_one_source_not_every_type() -> None:
    consumer = ToolManifest(
        name="weather",
        agent="weather_agent",
        description="City or address contract",
        parameters=[
            ParameterSchema(
                "location",
                "string",
                True,
                "Location",
                semantic_type="locality",
                semantic_role=SemanticFieldRole("location", accepted_types=("physical_address",)),
            )
        ],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
    )
    source = contract("contact_address", None, "physical_address")
    result = resolve_closure_additions([consumer], [consumer, source])
    assert result.additions == ["contact_address"]
    assert result.unresolved == {}


def test_generic_roots_and_related_id_types_never_close_an_incompatible_requirement() -> None:
    consumer = contract("consumer", "event_id", None, mutation="confirm")
    sources = [
        contract("text", None, "Text"),
        contract("number", None, "QuantitativeValue"),
        contract("person", None, "contact_id"),
    ]
    result = resolve_closure_additions([consumer], [consumer, *sources])
    assert result.additions == []
    assert result.unresolved == {"consumer": {"event_id"}}
