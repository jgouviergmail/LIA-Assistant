"""Public compatibility exports and every importing tool survive cold loading."""

import importlib

import pytest

pytestmark = pytest.mark.unit


def test_connections_compatibility_export_is_the_common_native_preparer():
    from src.domains.agents.application.native_tool_preparation import prepare_native_tool
    from src.domains.agents.application.peer_tool_preparation import prepare_peer_tool

    assert prepare_peer_tool is prepare_native_tool


@pytest.mark.parametrize(
    "module",
    [
        "application_peer_tools",
        "workboard_tools",
        "application_space_tools",
    ],
)
def test_native_tool_module_imports_cold(module):
    importlib.import_module(f"src.domains.agents.tools.{module}")


def test_application_manifests_satisfy_the_actual_startup_policy_guard():
    from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
    from src.domains.agents.registry.catalogue import assert_mutation_policy_completeness

    assert APPLICATION_MANIFESTS
    assert_mutation_policy_completeness(APPLICATION_MANIFESTS)


def test_management_actions_cannot_be_added_without_private_safe_editor_dispatch():
    from src.domains.agents.application.management_editor_inputs import MANAGEMENT_EDITOR_MODELS
    from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    for operation in APPLICATION_OPERATIONS.all():
        if operation.kind == OperationKind.READ or not set(operation.sections).intersection(
            {"rag-spaces", "workboard"}
        ):
            continue
        assert operation.operation_id in MANAGEMENT_EDITORS, operation.operation_id
        assert operation.input_model in MANAGEMENT_EDITOR_MODELS, operation.operation_id
