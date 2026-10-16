"""Native taxonomy claims must agree with the complete, independently imported catalogue."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.domain_exemptions import is_platform_domain
from src.domains.agents.registry.domain_taxonomy import (
    DOMAIN_REGISTRY,
    DomainConfig,
    validate_domain_registry,
)
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.services.analysis.domain_availability import build_available_domains

API_ROOT = Path(__file__).resolve().parents[5]

#: Stops a cold import that deadlocks — a hang guard, never a speed oracle. The
#: inventory's import takes about 10 s alone and 93 s with every core saturated
#: (the briefing's 36 s; measured 2026-10-16): under the parallel unit suite the
#: former 30 s failed a green import. Sized like the sibling cold-import guards
#: (the tool families' import order: 180 s).
COLD_IMPORT_HANG_GUARD_SECONDS = 180


@pytest.fixture(scope="module")
def native_manifests() -> list[ToolManifest]:
    return collect_static_manifests()


def _domain(agent_name: str) -> str:
    return AgentRegistry._extract_domain_from_agent_name(
        AgentRegistry.__new__(AgentRegistry), agent_name
    )


def test_every_static_taxonomy_domain_has_a_declared_native_tool(
    native_manifests: list[ToolManifest],
) -> None:
    observed = {_domain(manifest.agent) for manifest in native_manifests}
    data_domains = {domain for domain in observed if not is_platform_domain(domain)}
    dynamic = {name for name, config in DOMAIN_REGISTRY.items() if config.metadata.get("dynamic")}
    assert data_domains == set(DOMAIN_REGISTRY) - dynamic


def test_native_agent_bindings_and_explicit_exceptions_are_truthful(
    native_manifests: list[ToolManifest],
) -> None:
    agents = {manifest.agent for manifest in native_manifests}
    declared = {agent for config in DOMAIN_REGISTRY.values() for agent in config.agent_names}
    assert agents - declared == {"devops_diagnostics_agent", "python_sandbox_agent"}
    assert _domain("devops_diagnostics_agent") == "devops"
    assert is_platform_domain(_domain("python_sandbox_agent"))
    missing = declared - agents
    assert missing == {"mcp_agent"}
    assert DOMAIN_REGISTRY["mcp"].metadata["dynamic"] is True
    assert all(
        domain in DOMAIN_REGISTRY
        for manifest in native_manifests
        for domain in manifest.serves_domains
    )


def test_result_storage_keys_follow_taxonomy_or_the_declared_auxiliary_alias(
    native_manifests: list[ToolManifest],
) -> None:
    aliases: dict[str, str] = {}
    for manifest in native_manifests:
        if not manifest.context_key:
            continue
        # Storage keys need not prefix a flat action payload (e.g. Hue returns
        # name/on/brightness). Existing builder/reference oracles verify payloads.
        result_key = DOMAIN_REGISTRY[_domain(manifest.agent)].result_key
        if manifest.context_key != result_key:
            aliases[manifest.name] = manifest.context_key
    assert aliases == {"get_current_location_tool": "locations"}


def test_production_domain_menu_advertises_image_creation_and_editing(
    native_manifests: list[ToolManifest],
) -> None:
    image_tools = {
        manifest.name for manifest in native_manifests if manifest.agent == "image_generation_agent"
    }
    assert image_tools == {"generate_image", "edit_image"}
    with patch("src.infrastructure.mcp.registration.get_admin_mcp_domains", return_value={}):
        offered = {item["name"]: item["description"] for item in build_available_domains()}
    description = offered["image_generation"]
    assert "Generate" in description
    assert "Edit existing images" in description
    assert "NOT for editing" not in description


def test_inventory_imports_without_application_preloading() -> None:
    source = """
import io
import sys
from contextlib import redirect_stdout
captured = io.StringIO()
with redirect_stdout(captured):
    from src.domains.agents.registry.semantic_inventory import collect_static_manifests
    manifests = collect_static_manifests()
    from src.infrastructure.account_preferences import LayoutPreferencePatch
    from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_tool_strict
    ensure_tools_loaded()
    from src.core.config import settings
    if settings.devops_enabled:
        from src.domains.agents.tools import claude_server_task_tool
        assert get_tool_strict('claude_server_task_tool') is claude_server_task_tool
assert manifests
assert 'src.main' not in sys.modules
assert LayoutPreferencePatch.model_fields
assert 'conditional_tool_import_failed' not in captured.getvalue(), captured.getvalue()
assert 'partially initialized module' not in captured.getvalue(), captured.getvalue()
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", source],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=COLD_IMPORT_HANG_GUARD_SECONDS,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_briefing_constants_do_not_eagerly_import_routes_and_public_router_survives() -> None:
    source = """
import io
import sys
from contextlib import redirect_stdout
with redirect_stdout(io.StringIO()):
    from src.domains.briefing.constants import SECTION_NAMES
    assert SECTION_NAMES
    assert 'src.domains.briefing.router' not in sys.modules
    from src.domains.briefing import briefing_router
    from src.domains.briefing.router import router
assert briefing_router is router
assert router.routes
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", source],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=COLD_IMPORT_HANG_GUARD_SECONDS,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("reciprocal", [False, True])
def test_product_adjacency_is_not_required_to_be_a_dependency_dag(reciprocal: bool) -> None:
    graph = {
        name: DomainConfig(
            name=name,
            display_name=name,
            description="Product adjacency oracle",
            agent_names=[f"{name}_agent"],
            result_key=f"{name}s",
            related_domains=related,
        )
        for name, related in {"alpha": ["beta"], "beta": ["gamma"], "gamma": ["alpha"]}.items()
    }
    if reciprocal:
        graph["beta"].related_domains.append("alpha")
    with patch.dict(DOMAIN_REGISTRY, graph, clear=True):
        errors = validate_domain_registry()
    if reciprocal:
        assert errors and all("alpha" in error and "beta" in error for error in errors)
    else:
        assert errors == []
