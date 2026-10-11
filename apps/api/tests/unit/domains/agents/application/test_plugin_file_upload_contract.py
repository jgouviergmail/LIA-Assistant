"""New package fields require registry/schema review; browser transport is never model-controlled."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.plugin_file_upload_manifest import PLUGIN_FILE_UPLOAD_MANIFEST
from src.domains.agents.application.plugin_file_upload_schemas import (
    PluginFileUploadInput,
    PluginFileUploadSelection,
)
from src.domains.agents.application.plugin_file_upload_spec import PLUGIN_FILE_UPLOAD_OPERATION
from src.domains.agents.application.state_changes import GROUP_RESOURCES
from src.domains.agents.tools.application_plugin_tools import import_lia_plugin_file_tool

pytestmark = pytest.mark.unit


def test_plugin_file_requires_original_browser_and_complete_reviewed_registries():
    spec = PLUGIN_FILE_UPLOAD_OPERATION
    assert spec.interaction_kind == "device" and not spec.administrative
    assert spec in NATIVE_OPERATIONS and spec.tool_name in APPLICATION_TOOL_NAMES
    assert spec.operation_id in MANAGEMENT_CANONICAL and spec.operation_id in MANAGEMENT_EDITORS
    assert GROUP_RESOURCES[spec.operation_id] == ("plugins", "skills", "user_mcp")
    assert PLUGIN_FILE_UPLOAD_MANIFEST.mutation_policy == "draft"
    assert not PLUGIN_FILE_UPLOAD_MANIFEST.initiative_eligible
    assert set(import_lia_plugin_file_tool.tool_call_schema.model_fields) == {"request"}


def test_file_request_and_private_selection_growth_require_explicit_review():
    assert set(PluginFileUploadInput.model_fields) == {"replace_plugin_id"}
    assert set(PluginFileUploadSelection.model_fields) == {
        "request",
        "previous",
        "state",
        "max_file_size_bytes",
        "max_package_files",
        "max_decompressed_bytes",
        "max_personal_plugins",
    }
    for field, value in {
        "actor_id": uuid4(),
        "path": "private.zip",
        "bytes": "private",
        "origin": "browser",
    }.items():
        with pytest.raises(ValidationError):
            PluginFileUploadInput.model_validate({field: value})
