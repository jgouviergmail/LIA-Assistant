"""Source, public package scope, native role and registry growth are deliberate contracts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.plugin_url_import_manifest import PLUGIN_URL_IMPORT_MANIFEST
from src.domains.agents.application.plugin_url_import_schemas import (
    PluginImportState,
    PluginUrlImportInput,
    PluginUrlImportSnapshot,
)
from src.domains.agents.application.plugin_url_import_spec import PLUGIN_URL_IMPORT_OPERATION
from src.domains.agents.application.state_changes import GROUP_RESOURCES
from src.domains.agents.tools.application_plugin_tools import import_lia_plugin_url_tool
from src.domains.plugins.schemas import PluginImportReport

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/plugin.zip",
        "https://me:private@example.com/package.zip",
        "https:///missing.zip",
    ],
)
def test_plugin_sources_reject_transport_and_embedded_credentials(url):
    with pytest.raises(ValidationError):
        PluginUrlImportInput(url=url)


def test_native_plugin_import_is_strict_nonadministrative_and_completely_registered():
    spec = PLUGIN_URL_IMPORT_OPERATION
    assert set(PluginUrlImportInput.model_fields) == {"url", "replace_plugin_id"}
    assert not spec.administrative
    assert spec.operation_id in MANAGEMENT_EDITORS and spec.operation_id in MANAGEMENT_CANONICAL
    assert spec in NATIVE_OPERATIONS
    assert spec.tool_name in APPLICATION_TOOL_NAMES
    assert PLUGIN_URL_IMPORT_MANIFEST.mutation_policy == "draft"
    assert PLUGIN_URL_IMPORT_MANIFEST.initiative_eligible is False
    assert GROUP_RESOURCES[spec.operation_id] == ("plugins", "skills", "user_mcp")
    assert set(import_lia_plugin_url_tool.tool_call_schema.model_fields) == {"request"}
    with pytest.raises(ValidationError):
        PluginUrlImportInput(url="https://example.com/package.zip", actor_id=uuid4())


def test_native_package_state_and_report_growth_require_explicit_review():
    assert set(PluginImportState.model_fields) == {
        "previous",
        "digest",
        "root_digest",
        "skills",
        "servers",
    }
    assert set(PluginUrlImportSnapshot.model_fields) == {
        "request",
        "filename",
        "size_bytes",
        "package",
        "state",
        "package_digest",
    }
    assert set(PluginImportReport.model_fields) == {
        "plugin_id",
        "name",
        "version",
        "description",
        "updated",
        "components",
        "warnings",
        "file_cleanup_pending",
    }
