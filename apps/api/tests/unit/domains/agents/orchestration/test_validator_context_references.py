"""Tests for ``$context.<result_key>`` reference validation in PlanValidator (ADR-102).

Plan steps address prior results via ``$context.<result_key>`` references, where
``<result_key>`` is the canonical plural result key of a domain — the agent
builders emit ``$context.files.0``, ``$context.events.0``, ``$context.contacts.0``…

The validator's allow-list historically read ``{contacts, emails, events, tasks,
drive}``: it carried the legacy ``drive`` token (nothing ever emits
``$context.drive``) and OMITTED ``files`` (the file domain's result_key), so a
legitimate ``$context.files.0`` reference was silently rejected and the whole
plan invalidated. The allow-list is now derived from ``DOMAIN_REGISTRY`` result
keys (see :data:`VALID_CONTEXT_REFERENCE_DOMAINS`).
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.orchestration.validator import PlanValidator, ValidationResult
from src.domains.agents.registry.agent_registry import AgentRegistry

pytestmark = [pytest.mark.unit]


def _validator() -> PlanValidator:
    return PlanValidator(AgentRegistry())


def _step_with_context_ref(ref: str) -> ExecutionStep:
    return ExecutionStep(
        step_id="use",
        step_type=StepType.TOOL,
        agent_name="file_agent",
        tool_name="get_files_tool",
        parameters={"file_id": ref},
    )


def _invalid_context_domain_errors(result: ValidationResult, domain: str) -> list:
    return [e for e in result.errors if e.context.get("invalid_domain") == domain]


def test_context_files_reference_is_accepted() -> None:
    """``$context.files.0`` (the file domain's result_key) must NOT be rejected."""
    validator = _validator()
    result = ValidationResult(is_valid=True)

    validator._validate_step_references([_step_with_context_ref("$context.files.0.id")], result)

    assert not _invalid_context_domain_errors(result, "files")


def test_context_contacts_reference_still_accepted() -> None:
    """Existing valid result_keys keep working (regression guard)."""
    validator = _validator()
    result = ValidationResult(is_valid=True)

    validator._validate_step_references(
        [_step_with_context_ref("$context.contacts.0.resource_name")], result
    )

    assert not _invalid_context_domain_errors(result, "contacts")


def test_context_unknown_domain_is_rejected() -> None:
    """An off-vocabulary token is still flagged — validation stays strict."""
    validator = _validator()
    result = ValidationResult(is_valid=True)

    validator._validate_step_references([_step_with_context_ref("$context.bogus.0.id")], result)

    assert _invalid_context_domain_errors(result, "bogus")
