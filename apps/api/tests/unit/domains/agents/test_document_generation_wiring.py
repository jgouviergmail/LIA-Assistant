"""Wiring: taxonomy, manifests, loader gating, timeout family (ADR-226)."""

import pytest

from src.core.config import settings
from src.domains.agents.constants import AGENT_DOCUMENT_GENERATION
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY


@pytest.mark.unit
class TestDomainTaxonomy:
    """The document_generation domain is routable with a derived result_key."""

    def test_domain_registered_and_routable(self) -> None:
        cfg = DOMAIN_REGISTRY["document_generation"]
        assert cfg.result_key == "document_generations"
        assert cfg.is_routable is True
        assert AGENT_DOCUMENT_GENERATION in cfg.agent_names


@pytest.mark.unit
class TestCatalogueManifests:
    """Agent + tool manifests exist and publish the enforced doc_type set."""

    def test_agent_manifest_wraps_the_tool(self) -> None:
        from src.domains.agents.document_generation.catalogue_manifests import (
            document_agent_manifest,
        )

        assert document_agent_manifest.name == AGENT_DOCUMENT_GENERATION
        assert document_agent_manifest.tools == ["generate_document"]

    def test_manifest_publishes_doc_type_enum(self) -> None:
        from src.domains.agents.document_generation.catalogue_manifests import (
            generate_document_catalogue_manifest,
        )
        from src.domains.document_generation.schemas import DocumentType

        doc_type_param = next(
            p for p in generate_document_catalogue_manifest.parameters if p.name == "doc_type"
        )
        assert doc_type_param.required is True
        enum_constraints = [c for c in doc_type_param.constraints if c.kind == "enum"]
        assert len(enum_constraints) == 1
        # An enforced constraint must be published (ADR-184): the planner sees
        # the exact enum the tool validates against.
        assert set(enum_constraints[0].value) == {t.value for t in DocumentType}


@pytest.mark.unit
class TestTimeoutFamily:
    """ADR-160: dedicated floor/ceiling — the planner can never undercut reality."""

    def test_floor_applies_when_planner_is_silent(self) -> None:
        from src.domains.agents.orchestration.parallel_executor import (
            _DOCUMENT_TOOL_NAMES,
            _compute_step_timeout,
        )

        assert "generate_document" in _DOCUMENT_TOOL_NAMES
        resolved = _compute_step_timeout("generate_document", None)
        assert resolved == settings.document_generation_tool_timeout_seconds

    def test_planner_cannot_undercut_the_floor(self) -> None:
        from src.domains.agents.orchestration.parallel_executor import (
            _compute_step_timeout,
        )

        resolved = _compute_step_timeout("generate_document", 5.0)
        assert resolved >= settings.document_generation_tool_timeout_seconds

    def test_ceiling_caps_the_planner(self) -> None:
        from src.domains.agents.orchestration.parallel_executor import (
            _compute_step_timeout,
        )

        resolved = _compute_step_timeout("generate_document", 100000.0)
        assert resolved == settings.max_document_generation_tool_timeout_seconds
