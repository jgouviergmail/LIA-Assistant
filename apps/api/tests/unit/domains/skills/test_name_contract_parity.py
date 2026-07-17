"""Anti-drift parity tests (ADR-118, S4).

Three copies of the skill-name contract exist by necessity — the loader
(boot-time scan), the import service (import-time strict validation), and the
sandboxed generator script ``validate_skill.py`` (which cannot import app
modules). These tests pin them together so a change in one place fails CI
instead of silently diverging.

Also pins the generator script's hardcoded ``VALID_AGENTS`` against the
``DOMAIN_REGISTRY`` single source of truth: a renamed/removed agent would
otherwise silently break every generated plan_template, and a NEW agent must
be a conscious decision (either added to the script or to the exclusion list
below).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from src.core.constants import (
    SKILLS_DESCRIPTION_MAX_LENGTH,
    SKILLS_NAME_MAX_LENGTH,
)
from src.domains.skills import import_service, loader

pytestmark = pytest.mark.unit

# Agents present in DOMAIN_REGISTRY but deliberately NOT offered to generated
# plan_templates. Adding a new agent to the taxonomy without deciding its
# generator exposure fails the parity test below — extend either the script's
# VALID_AGENTS or this list, consciously.
GENERATOR_EXCLUDED_AGENTS = frozenset(
    {
        "devops_agent",  # admin-only in-container CLI
        "health_agent",  # personal health data, feature-flagged
        "sub_agent_agent",  # internal delegation, not a plan-executable domain agent
        # Real paid outbound calls to real people, feature-flagged, HITL-confirmed
        # per call — generated skills must never be able to place phone calls.
        "telephony_agent",
    }
)


def _find_validator_script() -> Path | None:
    """Locate the generator's validate_skill.py from any checkout/mount layout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "skills" / "system" / "skill-generator"
        script = candidate / "scripts" / "validate_skill.py"
        if script.is_file():
            return script
    return None


def _load_validator_module() -> ModuleType:
    script = _find_validator_script()
    if script is None:
        pytest.skip("skill-generator validate_skill.py not found in this checkout")
    spec = importlib.util.spec_from_file_location("skill_validator_under_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestNameContractParity:
    def test_loader_and_import_service_patterns_match(self) -> None:
        assert loader.SKILL_NAME_PATTERN.pattern == import_service._SKILL_NAME_PATTERN.pattern

    def test_validator_script_pattern_matches(self) -> None:
        validator = _load_validator_module()
        assert validator.NAME_PATTERN.pattern == import_service._SKILL_NAME_PATTERN.pattern

    def test_reserved_prefixes_match(self) -> None:
        validator = _load_validator_module()
        assert set(validator.RESERVED_PREFIXES) == set(import_service._RESERVED_PREFIXES)

    def test_length_limits_match_constants(self) -> None:
        validator = _load_validator_module()
        assert validator.NAME_MAX_LENGTH == SKILLS_NAME_MAX_LENGTH
        assert validator.DESCRIPTION_MAX_LENGTH == SKILLS_DESCRIPTION_MAX_LENGTH


class TestValidAgentsParity:
    def _taxonomy_agents(self) -> set[str]:
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

        return {agent for domain in DOMAIN_REGISTRY.values() for agent in domain.agent_names}

    def test_every_validator_agent_exists_in_taxonomy(self) -> None:
        """A renamed/removed agent must fail here, not in silent generation errors."""
        validator = _load_validator_module()
        unknown = set(validator.VALID_AGENTS) - self._taxonomy_agents()
        assert not unknown, (
            f"validate_skill.py VALID_AGENTS references agents absent from "
            f"DOMAIN_REGISTRY: {sorted(unknown)} — update the script"
        )

    def test_new_taxonomy_agents_are_consciously_classified(self) -> None:
        """Every taxonomy agent is either generator-exposed or explicitly excluded."""
        validator = _load_validator_module()
        unclassified = (
            self._taxonomy_agents() - set(validator.VALID_AGENTS) - GENERATOR_EXCLUDED_AGENTS
        )
        assert not unclassified, (
            f"New agents in DOMAIN_REGISTRY not classified for the skill generator: "
            f"{sorted(unclassified)} — add them to validate_skill.py VALID_AGENTS "
            f"(and tool-catalogue.md) or to GENERATOR_EXCLUDED_AGENTS in this test"
        )
