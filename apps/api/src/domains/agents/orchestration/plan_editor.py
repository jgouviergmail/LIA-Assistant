"""
Execution plan editor for HITL Plan-Level.

This module allows the user to modify execution plans
before final approval: edit parameters, remove steps,
or reorder steps.

Phase 3 OPTIMPLAN:
- EnhancedPlanEditor: Pydantic schema validation for tool_args
- SecurePlanEditor: Injection pattern detection (eval, exec, etc.)
- Modification history for undo
- Prometheus metrics (edit_operations, validation_failures, injection_blocked)

References:
- OPTIMPLAN/PLAN.md Section 5 - Phase 3
- schema_validator.py for Pydantic validation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from src.core.field_names import FIELD_PARAMETERS
from src.domains.agents.orchestration.approval_schemas import (
    PlanModification,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep

if TYPE_CHECKING:
    from src.domains.agents.services.hitl.schema_validator import HitlSchemaValidator

logger = structlog.get_logger(__name__)


class PlanModificationError(Exception):
    """Error raised when applying a modification to a plan fails."""

    pass


class InjectionDetectedError(PlanModificationError):
    """Error raised when an injection pattern is detected in parameters."""

    def __init__(self, pattern: str, field: str, value: str) -> None:
        self.pattern = pattern
        self.field = field
        self.value = value
        super().__init__(
            f"Injection pattern '{pattern}' detected in field '{field}': {value[:50]}..."
        )


class SchemaValidationError(PlanModificationError):
    """Error raised when schema validation fails."""

    def __init__(self, tool_name: str, errors: list[str]) -> None:
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(f"Schema validation failed for tool '{tool_name}': {'; '.join(errors)}")


@dataclass
class EditAuditEntry:
    """Audit entry for a plan modification."""

    modification: PlanModification
    timestamp: str
    original_params: dict[str, Any] | None = None
    new_params: dict[str, Any] | None = None
    validation_warnings: list[str] = field(default_factory=list)


@dataclass
class EnhancedEditResult:
    """Result of a plan modification with advanced validations."""

    modified_plan: ExecutionPlan
    warnings: list[str] = field(default_factory=list)
    audit_entries: list[EditAuditEntry] = field(default_factory=list)
    schema_validated: bool = False
    injection_checked: bool = False


class PlanEditor:
    """
    Execution plan editor.

    Applies user modifications to an ExecutionPlan
    and validates modification consistency.
    """

    @staticmethod
    def apply_modifications(
        plan: ExecutionPlan, modifications: list[PlanModification]
    ) -> ExecutionPlan:
        """
        Applique une liste de modifications à un plan d'exécution.

        Args:
            plan: Plan d'exécution original
            modifications: Liste de modifications à appliquer

        Returns:
            Nouveau plan modifié (deep copy)

        Raises:
            PlanModificationError: Si une modification est invalide ou échoue
        """
        # Create a deep copy to avoid modifying the original
        # Note: ExecutionPlan is frozen, so we must recreate
        modified_steps = list(plan.steps)  # Shallow copy of list

        try:
            for modification in modifications:
                if modification.modification_type == "edit_params":
                    modified_steps = PlanEditor._apply_edit_params(modified_steps, modification)
                elif modification.modification_type == "remove_step":
                    modified_steps = PlanEditor._apply_remove_step(modified_steps, modification)
                elif modification.modification_type == "reorder_steps":
                    modified_steps = PlanEditor._apply_reorder_steps(modified_steps, modification)
                else:
                    raise PlanModificationError(
                        f"Unknown modification type: {modification.modification_type}"
                    )

            # Create a new plan with the modified steps
            # ExecutionPlan is frozen, so we use model_copy with update
            modified_plan = plan.model_copy(update={"steps": modified_steps})

            logger.info(
                "plan_modifications_applied",
                plan_id=plan.plan_id,
                modification_count=len(modifications),
                original_step_count=len(plan.steps),
                modified_step_count=len(modified_steps),
            )

            return modified_plan

        except Exception as e:
            logger.error(
                "plan_modification_failed",
                plan_id=plan.plan_id,
                error=str(e),
                exc_info=True,
            )
            raise PlanModificationError(f"Failed to apply modifications: {str(e)}") from e

    @staticmethod
    def _apply_edit_params(
        steps: list[ExecutionStep], modification: PlanModification
    ) -> list[ExecutionStep]:
        """Apply a parameter modification to a step."""
        if not modification.step_id:
            raise PlanModificationError("step_id is required for edit_params")

        if not modification.new_parameters:
            raise PlanModificationError("new_parameters is required for edit_params")

        # Find the step index
        step_index = None
        for i, step in enumerate(steps):
            if step.step_id == modification.step_id:
                step_index = i
                break

        if step_index is None:
            raise PlanModificationError(f"Step not found: {modification.step_id}")

        # Create a new step with modified parameters
        # ExecutionStep is frozen, so we use model_copy
        original_step = steps[step_index]

        # Merge parameters (update existing, add new)
        merged_parameters = {**original_step.parameters}
        merged_parameters.update(modification.new_parameters)

        modified_step = original_step.model_copy(update={FIELD_PARAMETERS: merged_parameters})

        # Replace in the list
        new_steps = steps.copy()
        new_steps[step_index] = modified_step

        logger.info(
            "step_parameters_edited",
            step_id=modification.step_id,
            original_params=original_step.parameters,
            new_params=merged_parameters,
        )

        return new_steps

    @staticmethod
    def _apply_remove_step(
        steps: list[ExecutionStep], modification: PlanModification
    ) -> list[ExecutionStep]:
        """Remove a step from the plan."""
        if not modification.step_id:
            raise PlanModificationError("step_id is required for remove_step")

        # Find the step to remove
        step_to_remove = None
        for step in steps:
            if step.step_id == modification.step_id:
                step_to_remove = step
                break

        if step_to_remove is None:
            raise PlanModificationError(f"Step not found: {modification.step_id}")

        # Check dependencies: no other step must depend on this one
        dependent_steps = []
        for step in steps:
            if modification.step_id in step.depends_on:
                dependent_steps.append(step.step_id)

        if dependent_steps:
            raise PlanModificationError(
                f"Cannot remove step {modification.step_id}: steps {dependent_steps} depend on it"
            )

        # Filter the list to remove the step
        new_steps = [s for s in steps if s.step_id != modification.step_id]

        logger.info(
            "step_removed",
            step_id=modification.step_id,
            remaining_steps=len(new_steps),
        )

        return new_steps

    @staticmethod
    def _apply_reorder_steps(
        steps: list[ExecutionStep], modification: PlanModification
    ) -> list[ExecutionStep]:
        """Reorder the plan steps."""
        if not modification.new_order:
            raise PlanModificationError("new_order is required for reorder_steps")

        # Verify all step_ids are present
        current_step_ids = {step.step_id for step in steps}
        new_order_set = set(modification.new_order)

        if current_step_ids != new_order_set:
            missing = current_step_ids - new_order_set
            extra = new_order_set - current_step_ids
            raise PlanModificationError(f"Invalid reorder: missing={missing}, extra={extra}")

        # Create a step_id -> step mapping
        step_map = {step.step_id: step for step in steps}

        # Reorder according to new_order
        new_steps = [step_map[step_id] for step_id in modification.new_order]

        # Check dependencies: each step must come AFTER its dependencies
        for i, step in enumerate(new_steps):
            for dependency in step.depends_on:
                # Find the dependency index
                dep_index = None
                for j, s in enumerate(new_steps):
                    if s.step_id == dependency:
                        dep_index = j
                        break

                if dep_index is None:
                    raise PlanModificationError(
                        f"Dependency not found: {dependency} for step {step.step_id}"
                    )

                if dep_index >= i:
                    raise PlanModificationError(
                        f"Invalid order: step {step.step_id} at index {i} "
                        f"depends on {dependency} at index {dep_index} "
                        f"(dependencies must come before dependent steps)"
                    )

        logger.info(
            "steps_reordered",
            original_order=[s.step_id for s in steps],
            new_order=modification.new_order,
        )

        return new_steps

    @staticmethod
    def validate_modifications(
        plan: ExecutionPlan, modifications: list[PlanModification]
    ) -> list[str]:
        """
        Valide une liste de modifications sans les appliquer.

        Args:
            plan: Plan d'exécution original
            modifications: Liste de modifications à valider

        Returns:
            List of errors (empty if all valid)
        """
        errors = []

        try:
            # Try to apply the modifications
            PlanEditor.apply_modifications(plan, modifications)
        except PlanModificationError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"Unexpected error during validation: {str(e)}")

        return errors

    @staticmethod
    def generate_diff(original: ExecutionPlan, modified: ExecutionPlan) -> dict[str, Any]:
        """
        Generate a diff between two plans.

        Args:
            original: Original plan
            modified: Modified plan

        Returns:
            Dict containing the differences
        """
        diff: dict[str, Any] = {
            "steps_added": [],
            "steps_removed": [],
            "steps_modified": [],
            "steps_reordered": False,
        }

        original_ids = {step.step_id for step in original.steps}
        modified_ids = {step.step_id for step in modified.steps}

        # Added/removed steps
        diff["steps_added"] = list(modified_ids - original_ids)
        diff["steps_removed"] = list(original_ids - modified_ids)

        # Modified steps (different parameters)
        for orig_step in original.steps:
            if orig_step.step_id not in modified_ids:
                continue

            mod_step = next(s for s in modified.steps if s.step_id == orig_step.step_id)

            if orig_step.parameters != mod_step.parameters:
                diff["steps_modified"].append(
                    {
                        "step_id": orig_step.step_id,
                        "original_params": orig_step.parameters,
                        "modified_params": mod_step.parameters,
                    }
                )

        # Reordering
        original_order = [s.step_id for s in original.steps]
        modified_order = [s.step_id for s in modified.steps]

        # Filter common IDs to compare ordering
        common_ids = original_ids & modified_ids
        original_common_order = [sid for sid in original_order if sid in common_ids]
        modified_common_order = [sid for sid in modified_order if sid in common_ids]

        diff["steps_reordered"] = original_common_order != modified_common_order

        return diff


# ============================================================================
# PHASE 3 OPTIMPLAN: ENHANCED PLAN EDITOR
# ============================================================================


class EnhancedPlanEditor(PlanEditor):
    """
    PlanEditor with advanced validations (Phase 3 OPTIMPLAN).

    Features:
    - Schema validation via HitlSchemaValidator
    - Broken reference detection BEFORE applying modifications
    - Edit history for undo support
    - Audit logging of all modifications

    Usage:
        >>> editor = EnhancedPlanEditor(schema_validator=HitlSchemaValidator())
        >>> result = await editor.apply_with_validation(plan, modifications)
        >>> if result.warnings:
        ...     logger.warning("Modifications applied with warnings", warnings=result.warnings)
        >>> previous = editor.undo()  # Rollback last modification
    """

    def __init__(self, schema_validator: HitlSchemaValidator | None = None) -> None:
        """
        Initialize EnhancedPlanEditor.

        Args:
            schema_validator: Optional HitlSchemaValidator for Pydantic validation.
                            If not provided, schema validation is skipped.
        """
        self._schema_validator = schema_validator
        self._history: list[ExecutionPlan] = []
        self._max_history_size = 10  # Limit memory usage

    @property
    def history_size(self) -> int:
        """Return current history size."""
        return len(self._history)

    def apply_with_validation(
        self,
        plan: ExecutionPlan,
        modifications: list[PlanModification],
    ) -> EnhancedEditResult:
        """
        Apply modifications with schema validation and reference checking.

        This method extends the base apply_modifications() with:
        1. Schema validation of new_parameters against tool Pydantic schemas
        2. Broken reference detection for depends_on after step removal
        3. Audit logging of all changes

        Args:
            plan: Original execution plan
            modifications: List of modifications to apply

        Returns:
            EnhancedEditResult with modified plan, warnings, and audit entries

        Raises:
            SchemaValidationError: If schema validation fails (when validator provided)
            PlanModificationError: If modification application fails

        Example:
            >>> editor = EnhancedPlanEditor(schema_validator=HitlSchemaValidator())
            >>> result = editor.apply_with_validation(
            ...     plan=plan,
            ...     modifications=[
            ...         PlanModification(
            ...             modification_type="edit_params",
            ...             step_id="step_1",
            ...             new_parameters={"query": "test"}
            ...         )
            ...     ]
            ... )
            >>> assert result.schema_validated
        """
        from src.core.time_utils import now_utc

        # Import metrics with graceful degradation
        try:
            from src.infrastructure.observability.metrics_agents import (
                plan_edit_operations_total,
                plan_edit_schema_validation_failures_total,
            )

            metrics_available = True
        except ImportError:
            metrics_available = False

        # Save to history (before modification)
        self._push_history(plan)

        warnings: list[str] = []
        audit_entries: list[EditAuditEntry] = []
        schema_validated = False

        # Step 1: Schema validation for edit_params modifications
        if self._schema_validator:
            for mod in modifications:
                if mod.modification_type == "edit_params" and mod.new_parameters:
                    # Find the step to get tool_name
                    step = self._find_step(plan, mod.step_id)
                    if step:
                        # Merge original params with new params
                        merged_params = {**step.parameters, **mod.new_parameters}

                        # Validate against tool schema
                        validation_result = self._schema_validator.validate_tool_args(
                            tool_name=step.tool_name,
                            merged_args=merged_params,
                        )

                        if not validation_result.is_valid:
                            logger.warning(
                                "plan_editor_schema_validation_failed",
                                tool_name=step.tool_name,
                                step_id=mod.step_id,
                                errors=validation_result.errors,
                            )
                            if metrics_available:
                                plan_edit_schema_validation_failures_total.labels(
                                    tool_name=step.tool_name,
                                ).inc()
                            raise SchemaValidationError(
                                tool_name=step.tool_name,
                                errors=validation_result.errors,
                            )

            schema_validated = True

        # Step 2: Apply modifications (base class logic)
        try:
            modified_plan = self.apply_modifications(plan, modifications)
        except PlanModificationError:
            # Pop from history on failure (no change applied)
            self._pop_history()
            raise

        # Step 3: Detect broken references after removal
        # (apply_modifications already checks before removal, but we double-check)
        ref_warnings = self._detect_broken_references(modified_plan)
        warnings.extend(ref_warnings)

        # Step 4: Build audit entries
        timestamp = now_utc().isoformat()
        for mod in modifications:
            original_params = None
            new_params = None

            if mod.modification_type == "edit_params" and mod.step_id:
                original_step = self._find_step(plan, mod.step_id)
                modified_step = self._find_step(modified_plan, mod.step_id)
                original_params = original_step.parameters if original_step else None
                new_params = modified_step.parameters if modified_step else None

            audit_entries.append(
                EditAuditEntry(
                    modification=mod,
                    timestamp=timestamp,
                    original_params=original_params,
                    new_params=new_params,
                )
            )

            # Track metrics
            if metrics_available:
                plan_edit_operations_total.labels(
                    operation=mod.modification_type,
                ).inc()

        logger.info(
            "plan_editor_modifications_applied",
            plan_id=plan.plan_id,
            modification_count=len(modifications),
            warning_count=len(warnings),
            schema_validated=schema_validated,
        )

        return EnhancedEditResult(
            modified_plan=modified_plan,
            warnings=warnings,
            audit_entries=audit_entries,
            schema_validated=schema_validated,
            injection_checked=False,  # Set by SecurePlanEditor
        )

    def undo(self) -> ExecutionPlan | None:
        """
        Undo the last modification by restoring previous plan.

        Returns:
            Previous ExecutionPlan if history exists, None otherwise

        Example:
            >>> editor = EnhancedPlanEditor()
            >>> result = editor.apply_with_validation(plan, modifications)
            >>> previous_plan = editor.undo()  # Restore original
        """
        return self._pop_history()

    def _push_history(self, plan: ExecutionPlan) -> None:
        """Push plan to history stack with size limit."""
        self._history.append(plan)
        # Limit history size to prevent memory issues
        while len(self._history) > self._max_history_size:
            self._history.pop(0)

    def _pop_history(self) -> ExecutionPlan | None:
        """Pop and return last plan from history."""
        return self._history.pop() if self._history else None

    def _find_step(self, plan: ExecutionPlan, step_id: str | None) -> ExecutionStep | None:
        """Find step by ID in plan."""
        if not step_id:
            return None
        for step in plan.steps:
            if step.step_id == step_id:
                return step
        return None

    def _detect_broken_references(self, plan: ExecutionPlan) -> list[str]:
        """
        Detect broken depends_on references in plan.

        Returns:
            List of warning messages for broken references
        """
        warnings = []
        step_ids = {step.step_id for step in plan.steps}

        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    warnings.append(
                        f"Step '{step.step_id}' has broken dependency: '{dep}' not found"
                    )

        return warnings


# ============================================================================
# PHASE 3 OPTIMPLAN: SECURE PLAN EDITOR (Production Bulletproof)
# ============================================================================


class SecurePlanEditor(EnhancedPlanEditor):
    """
    EnhancedPlanEditor with injection detection (Production Bulletproof).

    Extends EnhancedPlanEditor with:
    - Injection pattern detection (eval, exec, import, template injection)
    - Security metrics (injection_blocked)
    - Strict validation mode

    Security Patterns Blocked:
    - Python dunder attributes (__.*__)
    - eval()/exec() calls
    - import statements
    - Template injection (${...}, {{...}})

    Usage:
        >>> editor = SecurePlanEditor(schema_validator=HitlSchemaValidator())
        >>> result = editor.apply_with_validation(plan, modifications)
        >>> assert result.injection_checked
    """

    # Regex patterns for injection detection
    INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
        ("dunder_attribute", re.compile(r"__\w+__")),
        ("eval_call", re.compile(r"\beval\s*\(")),
        ("exec_call", re.compile(r"\bexec\s*\(")),
        ("import_statement", re.compile(r"\bimport\s+")),
        ("template_dollar", re.compile(r"\$\{[^}]+\}")),
        ("template_jinja", re.compile(r"\{\{[^}]+\}\}")),
        ("os_system", re.compile(r"\bos\.system\s*\(")),
        ("subprocess", re.compile(r"\bsubprocess\.")),
    ]

    def __init__(
        self,
        schema_validator: HitlSchemaValidator | None = None,
        strict_mode: bool = True,
    ) -> None:
        """
        Initialize SecurePlanEditor.

        Args:
            schema_validator: Optional HitlSchemaValidator for Pydantic validation.
            strict_mode: If True, raise exception on injection detection.
                        If False, log warning and continue (not recommended for prod).
        """
        super().__init__(schema_validator=schema_validator)
        self._strict_mode = strict_mode

    def apply_with_validation(
        self,
        plan: ExecutionPlan,
        modifications: list[PlanModification],
    ) -> EnhancedEditResult:
        """
        Apply modifications with injection detection and schema validation.

        Extends parent with injection checking BEFORE schema validation.

        Args:
            plan: Original execution plan
            modifications: List of modifications to apply

        Returns:
            EnhancedEditResult with injection_checked=True

        Raises:
            InjectionDetectedError: If injection pattern found (strict_mode=True)
            SchemaValidationError: If schema validation fails
            PlanModificationError: If modification application fails
        """
        # Import metrics with graceful degradation
        try:
            from src.infrastructure.observability.metrics_agents import (
                plan_edit_injection_blocked_total,
            )

            metrics_available = True
        except ImportError:
            metrics_available = False

        # Step 0: Injection detection (BEFORE any modification)
        for mod in modifications:
            if mod.modification_type == "edit_params" and mod.new_parameters:
                for field_name, value in mod.new_parameters.items():
                    if isinstance(value, str):
                        injection_result = self._check_injection(field_name, value)
                        if injection_result:
                            pattern_name, matched = injection_result

                            logger.warning(
                                "plan_editor_injection_detected",
                                pattern=pattern_name,
                                field=field_name,
                                value_preview=value[:100],
                                step_id=mod.step_id,
                            )

                            if metrics_available:
                                plan_edit_injection_blocked_total.labels(
                                    pattern=pattern_name,
                                ).inc()

                            if self._strict_mode:
                                raise InjectionDetectedError(
                                    pattern=pattern_name,
                                    field=field_name,
                                    value=value,
                                )

        # Call parent implementation (schema validation + apply)
        result = super().apply_with_validation(plan, modifications)

        # Mark as injection-checked
        result.injection_checked = True

        return result

    def _check_injection(
        self,
        field_name: str,
        value: str,
    ) -> tuple[str, str] | None:
        """
        Check value for injection patterns.

        Args:
            field_name: Name of the field being checked
            value: String value to check

        Returns:
            Tuple of (pattern_name, matched_text) if injection found, None otherwise
        """
        for pattern_name, pattern in self.INJECTION_PATTERNS:
            match = pattern.search(value)
            if match:
                return (pattern_name, match.group(0))
        return None
