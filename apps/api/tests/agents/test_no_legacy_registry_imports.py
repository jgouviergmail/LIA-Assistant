"""
Non-regression tests for AgentManifest/AgentRegistry refactoring.

These tests ensure that:
1. NO production code imports orchestration.registry (Phase 1-4 LEGACY)
2. ALL production tools have catalogue manifests (Phase 5 PRODUCTION)
3. Catalogue manifests are complete and valid

Context:
- Phase 1-4: orchestration/registry.py (simple dataclasses) - DEPRECATED
- Phase 5+: registry/catalogue.py + agent_registry.py (rich validation) - PRODUCTION
- Migration: ALREADY COMPLETE, these tests prevent regression during cleanup

See: docs/agents/current_vs_target_flow.md
"""

import ast
from pathlib import Path

import pytest

from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.catalogue_loader import initialize_catalogue


class TestNoLegacyRegistryImports:
    """Vérifie qu'AUCUN code production n'importe orchestration.registry."""

    @pytest.fixture
    def production_source_files(self) -> list[Path]:
        """Liste tous les fichiers Python de production (src/)."""
        src_dir = Path(__file__).parents[2] / "src"

        # Exclude legacy manifest files that we plan to delete
        legacy_files = {
            "domains/agents/context/manifest.py",
            "domains/agents/google_contacts/manifest.py",
        }

        all_files = list(src_dir.rglob("*.py"))
        return [
            f
            for f in all_files
            if not any(f.as_posix().endswith(legacy) for legacy in legacy_files)
        ]

    def test_no_orchestration_registry_imports(self, production_source_files: list[Path]):
        """
        Vérifie qu'AUCUN fichier production n'importe orchestration.registry.

        Regression protection: Ensures no new code uses deprecated registry system.
        """
        violations = []

        for file_path in production_source_files:
            try:
                with open(file_path, encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=str(file_path))

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        # Check for: from src.domains.agents.orchestration.registry import ...
                        if node.module and "orchestration.registry" in node.module:
                            violations.append(
                                f"{file_path.relative_to(file_path.parents[2])}: "
                                f"line {node.lineno} imports {node.module}"
                            )

                    elif isinstance(node, ast.Import):
                        # Check for: import src.domains.agents.orchestration.registry
                        for alias in node.names:
                            if "orchestration.registry" in alias.name:
                                violations.append(
                                    f"{file_path.relative_to(file_path.parents[2])}: "
                                    f"line {node.lineno} imports {alias.name}"
                                )

            except (SyntaxError, UnicodeDecodeError):
                # Skip files that can't be parsed (shouldn't happen in production code)
                continue

        if violations:
            msg = (
                "❌ REGRESSION DETECTED: Production code imports deprecated orchestration.registry\n\n"
                "The following files must be updated to use registry.catalogue instead:\n"
                + "\n".join(f"  - {v}" for v in violations)
                + "\n\nMigration guide: Use registry/catalogue.py (Phase 5 system)"
            )
            pytest.fail(msg)


class TestAllProductionToolsHaveCatalogueManifests:
    """Verify that ALL production tools have catalogue manifests."""

    @pytest.fixture
    def agent_registry(self):
        """Create and initialize AgentRegistry with production catalogues."""
        registry = AgentRegistry()
        initialize_catalogue(registry)
        return registry

    def test_all_expected_tools_registered(self, agent_registry):
        """
        Vérifie que TOUS les 7 outils de production sont enregistrés.

        Expected tools:
        - Google Contacts: list_contacts, search_contacts, get_contact_details
        - Context Management: get_context, set_context, delete_context, list_contexts

        Regression protection: Ensures no tools are lost during refactoring.
        """
        expected_tools = {
            # Google Contacts tools (3)
            "list_contacts_tool",
            "search_contacts_tool",
            "get_contact_details_tool",
            # Context Management tools (4)
            "resolve_reference",
            "set_current_item",
            "get_context_state",
            "list_active_domains",
        }

        # Get all registered tool names from catalogue
        all_manifests = agent_registry.list_tool_manifests()
        registered_tools = {manifest.name for manifest in all_manifests}

        missing_tools = expected_tools - registered_tools

        if missing_tools:
            pytest.fail(
                f"❌ REGRESSION DETECTED: {len(missing_tools)} production tools are NOT registered:\n"
                + "\n".join(f"  - {tool}" for tool in sorted(missing_tools))
                + "\n\nAll production tools MUST have catalogue manifests."
            )

    def test_all_tools_use_catalogue_manifests(self, agent_registry):
        """
        Vérifie que TOUS les outils utilisent catalogue.ToolManifest (Phase 5).

        Catalogue manifests have 'outputs' attribute (orchestration.registry manifests don't).

        Regression protection: Ensures no tools accidentally use legacy manifest format.
        """
        violations = []

        for manifest in agent_registry.list_tool_manifests():
            tool_name = manifest.name

            # Catalogue manifests are instances of catalogue.ToolManifest
            if not isinstance(manifest, ToolManifest):
                violations.append(
                    f"{tool_name}: type={type(manifest).__name__} (expected catalogue.ToolManifest)"
                )

            # Catalogue manifests have 'outputs' field (orchestration.registry manifests don't)
            elif not hasattr(manifest, "outputs"):
                violations.append(
                    f"{tool_name}: missing 'outputs' field (not a catalogue.ToolManifest)"
                )

        if violations:
            pytest.fail(
                "❌ REGRESSION DETECTED: Tools using wrong manifest format:\n"
                + "\n".join(f"  - {v}" for v in violations)
                + "\n\nAll tools MUST use registry/catalogue.py manifests (Phase 5 system)."
            )


class TestCatalogueManifestsCompleteness:
    """Verify the completeness and validity of catalogue manifests."""

    @pytest.fixture
    def agent_registry(self):
        """Create and initialize AgentRegistry with production catalogues."""
        registry = AgentRegistry()
        initialize_catalogue(registry)
        return registry

    def test_all_manifests_have_required_fields(self, agent_registry):
        """
        Vérifie que TOUS les manifests catalogue ont les champs obligatoires.

        Required fields:
        - outputs: List[OutputFieldSchema] (for structured output)
        - cost: CostProfile (for rate limiting and cost tracking)
        - permissions: PermissionProfile (for security and RBAC)
        - examples: List[dict] (for LLM few-shot learning)

        Regression protection: Ensures manifests remain complete during refactoring.
        """
        violations = []

        for manifest in agent_registry.list_tool_manifests():
            tool_name = manifest.name

            # Check outputs field (must be non-empty list)
            if not hasattr(manifest, "outputs"):
                violations.append(f"{tool_name}: missing 'outputs' field")
            elif not isinstance(manifest.outputs, list):
                violations.append(f"{tool_name}: 'outputs' is not a list")
            elif len(manifest.outputs) == 0:
                violations.append(f"{tool_name}: 'outputs' is empty (should define output schema)")

            # Check cost field
            if not hasattr(manifest, "cost"):
                violations.append(f"{tool_name}: missing 'cost' field")
            elif manifest.cost is None:
                violations.append(f"{tool_name}: 'cost' is None (should define CostProfile)")

            # Check permissions field
            if not hasattr(manifest, "permissions"):
                violations.append(f"{tool_name}: missing 'permissions' field")
            elif manifest.permissions is None:
                violations.append(
                    f"{tool_name}: 'permissions' is None (should define PermissionProfile)"
                )

            # Check examples field (must exist and be a list, but can be empty)
            if not hasattr(manifest, "examples"):
                violations.append(f"{tool_name}: missing 'examples' field")
            elif not isinstance(manifest.examples, list):
                violations.append(f"{tool_name}: 'examples' is not a list")
            # Note: Empty examples list is OK for now (not all tools have examples yet)

        if violations:
            pytest.fail(
                "❌ REGRESSION DETECTED: Incomplete catalogue manifests:\n"
                + "\n".join(f"  - {v}" for v in violations)
                + "\n\nAll manifests MUST be complete for production use."
            )

    def test_all_manifests_pass_validation(self, agent_registry):
        """
        Vérifie que TOUS les manifests passent la validation Pydantic.

        Catalogue manifests use frozen dataclasses with __post_init__ validation.
        If they're registered, they've already passed validation at startup.

        This test ensures validation remains strict during refactoring.

        Regression protection: Ensures manifest quality doesn't degrade.
        """
        # If we got here, all manifests passed validation at import time
        # (catalogue manifests use frozen dataclasses with strict validation)

        all_manifests = agent_registry.list_tool_manifests()
        tool_count = len(all_manifests)

        assert tool_count >= 7, (
            f"Expected at least 7 production tools, found {tool_count}. "
            f"Tools may have failed validation during startup."
        )

        # Additional check: Verify CostProfile validation
        violations = []
        for manifest in all_manifests:
            tool_name = manifest.name

            if hasattr(manifest, "cost") and manifest.cost:
                cost = manifest.cost

                # CostProfile must have reasonable estimates (non-negative)
                # Validation happens in __post_init__, but we check they were set
                if cost.est_tokens_in < 0 or cost.est_tokens_out < 0:
                    violations.append(f"{tool_name}: CostProfile has negative token estimates")
                if cost.est_cost_usd < 0 or cost.est_latency_ms < 0:
                    violations.append(
                        f"{tool_name}: CostProfile has negative cost/latency estimates"
                    )

        if violations:
            pytest.fail(
                "❌ VALIDATION REGRESSION: Invalid CostProfiles:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )


class TestLegacyManifestFilesIsolation:
    """Verify that legacy files are NOT used by production code."""

    def test_legacy_manifests_not_used_by_production(self):
        """
        Verify that legacy manifests are NOT used by production code.

        Context:
        - context/manifest.py and google_contacts/manifest.py define orchestration.registry manifests
        - They are imported by their respective __init__.py files (dead exports)
        - NO production code actually imports these manifest objects
        - Safe to delete in Step 2 (after removing dead exports from __init__.py)

        Regression protection: Ensures they remain unused before deletion.
        """
        # These are the legacy manifest variable names exported by __init__.py
        legacy_manifest_names = {
            # From context/__init__.py
            "context_agent_manifest",
            "get_context_state_manifest",
            "list_active_domains_manifest",
            "resolve_reference_manifest",
            "set_current_item_manifest",
            # From google_contacts/__init__.py
            "google_contacts_agent_manifest",
            "search_contacts_manifest",
            "list_contacts_manifest",
            "get_contact_details_manifest",
        }

        # Scan all production source files for usage
        src_dir = Path(__file__).parents[2] / "src"
        violations = []

        for file_path in src_dir.rglob("*.py"):
            # Skip the legacy manifest files themselves, their __init__.py, and orchestration/registry.py
            # (orchestration/registry.py is deprecated and will be deleted in Step 4)
            if "manifest.py" in file_path.name or "__init__.py" in file_path.name:
                continue
            if "orchestration" in str(file_path) and "registry.py" in file_path.name:
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                # Check for any usage of legacy manifest names
                for manifest_name in legacy_manifest_names:
                    if manifest_name in content:
                        violations.append(
                            f"{file_path.relative_to(src_dir)}: uses '{manifest_name}'"
                        )
            except (UnicodeDecodeError, PermissionError):
                continue

        if violations:
            pytest.fail(
                "❌ REGRESSION DETECTED: Production code uses legacy manifests:\n"
                + "\n".join(f"  - {v}" for v in violations)
                + "\n\nThese manifests use deprecated orchestration.registry and should not be used."
            )
