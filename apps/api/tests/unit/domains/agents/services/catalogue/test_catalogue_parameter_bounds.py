"""The catalogue must publish the bounds the validator will enforce.

The planner writes ``max_results`` from two inputs: the prompt, and the tool
entry it is handed. Until 2026-07-31 the entry carried neither the bound nor
even the description that mentions it — ``_manifest_to_dict`` only kept a
description for parameters that are required, semantic, patterned or ID-like,
and ``max_results`` is none of those. What the planner actually received was::

    {"name": "max_results", "type": "integer", "required": false}

while the manifest declared ``maximum=10``. The prompt then told it to fetch a
broad batch, the validator rejected the plan for obeying, and the response
layer reported the stale verdict as a failure to the user (production requests
2f6c6366 / 52e54297 / 83c98053).

A bound the validator enforces and the planner cannot see is not a contract —
it is a trap. These tests pin the bound into the entry, in the compact form the
catalogue uses for ``pattern``.
"""

from __future__ import annotations

from src.domains.agents.registry.catalogue import (
    CostProfile,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.services.smart_catalogue_service import get_smart_catalogue_service


def _manifest(*parameters: ParameterSchema) -> ToolManifest:
    return ToolManifest(
        name="get_emails_tool",
        agent="emails_agent",
        description="Read emails.",
        parameters=list(parameters),
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
    )


def _entry(*parameters: ParameterSchema) -> dict[str, dict]:
    """Serialize a manifest the way the planner prompt receives it."""
    serialized = get_smart_catalogue_service()._manifest_to_dict(_manifest(*parameters))
    return {p["name"]: p for p in serialized["parameters"]}


def _bounded(**constraints: int) -> ParameterSchema:
    return ParameterSchema(
        name="max_results",
        type="integer",
        required=False,
        description="Max results for query mode (def: 10, max: 10)",
        constraints=[ParameterConstraint(kind=k, value=v) for k, v in constraints.items()],
    )


def test_maximum_reaches_the_planner():
    """The verbatim gap behind request 83c98053."""
    assert _entry(_bounded(maximum=10))["max_results"]["max"] == 10


def test_minimum_reaches_the_planner():
    assert _entry(_bounded(minimum=1))["max_results"]["min"] == 1


def test_both_bounds_are_published_together():
    entry = _entry(_bounded(minimum=1, maximum=25))["max_results"]

    assert (entry["min"], entry["max"]) == (1, 25)


def test_an_unbounded_parameter_stays_compact():
    """Token budget: no key is added when the manifest declares no bound."""
    entry = _entry(
        ParameterSchema(name="query", type="string", required=False, description="Gmail query")
    )["query"]

    assert "min" not in entry
    assert "max" not in entry


def test_publishing_a_bound_does_not_drop_the_existing_fields():
    entry = _entry(_bounded(maximum=10))["max_results"]

    assert entry["name"] == "max_results"
    assert entry["type"] == "integer"
    assert entry["required"] is False


def test_pattern_and_bounds_coexist_on_the_same_parameter():
    """`pattern` was the only constraint published before — it must survive."""
    parameter = ParameterSchema(
        name="max_results",
        type="integer",
        required=False,
        description="",
        constraints=[
            ParameterConstraint(kind="pattern", value="^[0-9]+$"),
            ParameterConstraint(kind="maximum", value=10),
        ],
    )

    entry = _entry(parameter)["max_results"]

    assert entry["pattern"] == "^[0-9]+$"
    assert entry["max"] == 10


def test_non_numeric_bound_values_are_not_published():
    """A mis-seeded constraint must not put a string where a number is read."""
    parameter = ParameterSchema(
        name="max_results",
        type="integer",
        required=False,
        description="",
        constraints=[ParameterConstraint(kind="maximum", value="ten")],
    )

    assert "max" not in _entry(parameter)["max_results"]


def test_the_real_email_manifest_publishes_its_configured_cap():
    """End to end on the tool that failed: settings → manifest → planner."""
    from src.core.config import settings
    from src.domains.agents.emails.catalogue_manifests import get_emails_catalogue_manifest

    serialized = get_smart_catalogue_service()._manifest_to_dict(get_emails_catalogue_manifest)
    by_name = {p["name"]: p for p in serialized["parameters"]}

    assert by_name["max_results"]["max"] == settings.emails_tool_default_max_results


def test_enum_reaches_the_planner():
    """ADR-226: an enum the validator enforces must be visible too — same
    doctrine as min/max (a closed set the planner cannot see is a trap)."""
    parameter = ParameterSchema(
        name="doc_type",
        type="string",
        required=True,
        description="Target format.",
        constraints=[ParameterConstraint(kind="enum", value=["csv", "pdf"])],
    )

    assert _entry(parameter)["doc_type"]["enum"] == ["csv", "pdf"]


def test_non_list_enum_value_is_not_published():
    """A mis-seeded enum must not put garbage where a list is read."""
    parameter = ParameterSchema(
        name="doc_type",
        type="string",
        required=True,
        description="",
        constraints=[ParameterConstraint(kind="enum", value="csv")],
    )

    assert "enum" not in _entry(parameter)["doc_type"]


def test_the_real_document_manifest_publishes_its_enum():
    """End to end: the generate_document entry carries the exact closed set."""
    from src.domains.agents.document_generation.catalogue_manifests import (
        generate_document_catalogue_manifest,
    )
    from src.domains.document_generation.schemas import DocumentType

    serialized = get_smart_catalogue_service()._manifest_to_dict(
        generate_document_catalogue_manifest
    )
    by_name = {p["name"]: p for p in serialized["parameters"]}

    assert set(by_name["doc_type"]["enum"]) == {t.value for t in DocumentType}
