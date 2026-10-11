"""Every input bound must reach both planner and native ReAct schemas."""

import pytest
from jsonschema import Draft202012Validator

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.domains.agents.application.catalogue_registration import (
    APPLICATION_MANIFESTS,
    PREFERENCES_READ_MANIFEST,
)
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.schemas import PreferencePatch, PreferenceRead
from src.domains.agents.registry.catalogue import assert_mutation_policy_completeness
from src.domains.agents.tools.application_read_tools import get_lia_preferences_tool

pytestmark = pytest.mark.unit


def test_application_registry_capability_and_manifest_share_tool_identity() -> None:
    assert {spec.tool_name for spec in APPLICATION_OPERATIONS.all()} == set(APPLICATION_TOOL_NAMES)
    assert PREFERENCES_READ_MANIFEST.name in APPLICATION_TOOL_NAMES


def test_all_application_manifests_satisfy_the_boot_mutation_policy_guard() -> None:
    assert {manifest.name for manifest in APPLICATION_MANIFESTS} == set(APPLICATION_TOOL_NAMES)
    assert_mutation_policy_completeness(APPLICATION_MANIFESTS)


def test_native_read_schema_publishes_the_same_field_bounds_as_the_ui_contract() -> None:
    expected = PreferenceRead.model_json_schema()["properties"]["fields"]
    actual = get_lia_preferences_tool.args["fields"]
    assert actual == expected
    declared = PREFERENCES_READ_MANIFEST.parameters[0].schema
    assert declared is not None
    assert {key: value for key, value in declared.items() if key != "$defs"} == expected
    assert "runtime" not in get_lia_preferences_tool.tool_call_schema.model_fields


def test_planner_parameter_schema_resolves_its_field_vocabulary_without_external_definitions() -> (
    None
):
    declared = PREFERENCES_READ_MANIFEST.parameters[0].schema
    assert declared is not None
    validator = Draft202012Validator(declared)
    validator.validate(["font_size"])
    assert not validator.is_valid(["hashed_password"])


@pytest.mark.parametrize("payload", [{}, {"font_size": None}, {"theme": None}])
def test_patch_schema_never_offers_a_shape_its_shared_validator_refuses(
    payload: dict[str, object],
) -> None:
    assert not Draft202012Validator(PreferencePatch.model_json_schema()).is_valid(payload)
