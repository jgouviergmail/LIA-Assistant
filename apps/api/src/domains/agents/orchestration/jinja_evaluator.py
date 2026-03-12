"""
Jinja2 Template Evaluator for Step Parameters
Phase: Issue #41 - Template Evaluation with Safety Enhancements

Security:
- SandboxedEnvironment (no code injection)
- Recursion depth limit (max_depth=10)
- Empty result detection (fail-fast)
- JS syntax compatibility (auto-translation)

Author: Claude Code
Date: 2025-11-24
Issue: #41
"""

import re
from typing import Any

from jinja2 import TemplateSyntaxError, UndefinedError, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class TemplateEvaluationError(Exception):
    """Raised when template evaluation fails critically."""

    pass


class EmptyResultError(TemplateEvaluationError):
    """Raised when template evaluates to empty string for required parameter."""

    pass


class JinjaTemplateEvaluator:
    """
    Evaluates Jinja2 templates in step parameters with safety enhancements.

    Features:
    - Sandboxed execution (no code injection)
    - JS syntax compatibility (.length → | length)
    - Empty result detection (fail-fast)
    - Recursion depth limit (max 10 levels)

    Example:
        >>> evaluator = JinjaTemplateEvaluator()
        >>> template = "{% if steps.search.emails | length >= 2 %}{{ steps.search.emails[1].id }}{% endif %}"
        >>> context = {"steps": {"search": {"emails": [{"id": "123"}, {"id": "456"}]}}}
        >>> result = evaluator.evaluate(template, context, "get_second_email")
        >>> print(result)  # "456"
    """

    def __init__(self, max_recursion_depth: int = 10):
        """
        Initialize evaluator with safety limits.

        Args:
            max_recursion_depth: Maximum nesting depth for recursive evaluation.
                                Note: Jinja2 templates themselves use Python's
                                recursion limit (default 1000).
        """
        self.max_recursion_depth = max_recursion_depth

        # Sandboxed environment - security first
        # Use custom Undefined that logs warnings but doesn't crash
        self.env = SandboxedEnvironment(
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=self._make_logging_undefined(),
        )

        # Custom filters for robustness
        self.env.filters["length"] = self._safe_length
        self.env.filters["get"] = self._safe_get
        self.env.filters["default"] = self._safe_default
        self.env.filters["first"] = self._safe_first
        self.env.filters["last"] = self._safe_last

    @classmethod
    def _make_logging_undefined(cls):
        """
        Create a custom Undefined class that logs warnings but doesn't crash.

        This makes templates more resilient to missing data while still
        providing debug information in logs.
        """
        from jinja2 import Undefined

        class LoggingUndefined(Undefined):
            """Undefined that logs access attempts and returns empty/safe values."""

            def _log_undefined(self):
                """Log the undefined access for debugging."""
                logger.warning(
                    "jinja_undefined_access",
                    name=self._undefined_name,
                    hint=str(self._undefined_hint) if self._undefined_hint else None,
                )

            def __str__(self):
                self._log_undefined()
                return ""

            def __iter__(self):
                self._log_undefined()
                return iter([])

            def __bool__(self):
                return False

            def __len__(self):
                return 0

            def __getattr__(self, name):
                # Return another LoggingUndefined for chained access
                return LoggingUndefined(
                    hint=f"{self._undefined_hint}.{name}" if self._undefined_hint else name,
                    name=name,
                )

            def __getitem__(self, key):
                # Return another LoggingUndefined for index access
                return LoggingUndefined(
                    hint=f"{self._undefined_hint}[{key}]" if self._undefined_hint else f"[{key}]",
                    name=str(key),
                )

        return LoggingUndefined

    @staticmethod
    def _safe_length(value: Any) -> int:
        """Safe length filter - handles None, dicts, lists, strings."""
        if value is None:
            return 0
        if isinstance(value, list | dict | str):
            return len(value)
        return 0

    @staticmethod
    def _safe_get(dictionary: dict, key: str, default=None) -> Any:
        """Safe dict.get() - returns default if key missing."""
        if not isinstance(dictionary, dict):
            return default
        return dictionary.get(key, default)

    @staticmethod
    def _safe_default(value: Any, default_value: Any = "") -> Any:
        """Safe default filter - returns default if value is None or empty."""
        if value is None:
            return default_value
        if isinstance(value, str) and value.strip() == "":
            return default_value
        if isinstance(value, list | dict) and len(value) == 0:
            return default_value
        return value

    @staticmethod
    def _safe_first(value: Any, default=None) -> Any:
        """Safe first filter - returns first element or default."""
        if value is None:
            return default
        if isinstance(value, list | tuple) and len(value) > 0:
            return value[0]
        return default

    @staticmethod
    def _safe_last(value: Any, default=None) -> Any:
        """Safe last filter - returns last element or default."""
        if value is None:
            return default
        if isinstance(value, list | tuple) and len(value) > 0:
            return value[-1]
        return default

    @staticmethod
    def _js_compatibility_preprocess(template_str: str) -> str:
        """
        Auto-translate common JS syntax and escaped Jinja2 to Python/Jinja2.

        Translations:
        - $steps → steps (remove $ prefix for Jinja2 compatibility)
        - .length → | length
        - .get(key) → (not supported - log warning)
        - {{% %}} → {% %} (unescape double-brace Jinja2 blocks)
        - {{{{ }}}} → {{ }} (unescape double-brace Jinja2 variables)

        Issue #53 FIX: The planner prompt uses escaped Jinja2 syntax ({{% %}}, {{{{ }}}})
        to avoid premature template evaluation. We must unescape them here before
        the actual Jinja2 evaluation.

        BugFix 2025-12-08: LLM sometimes generates {{ $steps.X }} which is invalid Jinja2.
        The $ character is not valid in Jinja2 variable names. We strip it here.

        Args:
            template_str: Original template (may contain JS syntax or escaped Jinja2)

        Returns:
            Preprocessed template (Jinja2 compatible)
        """
        original = template_str

        # BugFix 2025-12-08: Strip $ prefix from $steps references inside Jinja2 templates
        # Pattern: $steps → steps (Jinja2 doesn't support $ in variable names)
        # Example: "{{ $steps.search.contacts[0] }}" → "{{ steps.search.contacts[0] }}"
        template_str = re.sub(r"\$steps\b", "steps", template_str)

        # Issue #53 FIX: Unescape double-brace Jinja2 syntax from planner output
        # Pattern: {{% ... %}} → {% ... %}
        # This handles: {{% for %}} {{% if %}} {{% endif %}} {{% endfor %}} etc.
        template_str = re.sub(r"\{\{%\s*", "{% ", template_str)
        template_str = re.sub(r"\s*%\}\}", " %}", template_str)

        # Pattern: {{{{ ... }}}} → {{ ... }}
        # This handles: {{{{ c.resource_name }}}} → {{ c.resource_name }}
        template_str = re.sub(r"\{\{\{\{\s*", "{{ ", template_str)
        template_str = re.sub(r"\s*\}\}\}\}", " }}", template_str)

        # Pattern 1: var.length → var | length
        # Example: "steps.search.emails.length" → "steps.search.emails | length"
        template_str = re.sub(r"(\w+(?:\.\w+)*?)\.length\b", r"\1 | length", template_str)

        # Pattern 2: var.get(key) → var | get('key')
        # NOTE: Complex regex, log warning if detected
        if ".get(" in template_str:
            logger.warning(
                "js_syntax_get_detected",
                template=original,
                message="'.get()' detected - may need manual Jinja2 translation",
            )

        # Log if translation occurred
        if template_str != original:
            logger.info("js_syntax_translated", original=original, translated=template_str)

        return template_str

    def contains_jinja_syntax(self, value: str) -> bool:
        """
        Detect Jinja2 syntax: {{ ... }}, {% ... %}, {# ... #}
        Also detects escaped syntax: {{{{ }}}}, {{% %}}, {{# #}}

        Issue #53 FIX: The planner generates escaped Jinja2 syntax that needs to
        be detected and unescaped before evaluation.

        Args:
            value: String to check

        Returns:
            True if value contains Jinja2 template markers (escaped or unescaped)
        """
        if not isinstance(value, str):
            return False

        # Standard Jinja2 markers
        jinja_markers = ["{{", "{%", "{#"]
        # Escaped markers from planner prompt (Issue #53)
        escaped_markers = ["{{{{", "{{% ", "{{#"]

        return any(marker in value for marker in jinja_markers + escaped_markers)

    def evaluate(
        self,
        template_str: str,
        context: dict[str, Any],
        step_id: str,
        parameter_name: str | None = None,
        is_required: bool = False,
    ) -> str | None:
        """
        Evaluate Jinja2 template with given context.

        Args:
            template_str: Template string (may contain {{ }}, {% %}, etc.)
            context: Dict with 'steps' key containing completed_steps
            step_id: Current step ID (for logging)
            parameter_name: Name of parameter being evaluated (for error messages)
            is_required: If True, raise EmptyResultError for empty results

        Returns:
            Evaluated string, or None if evaluation fails

        Raises:
            EmptyResultError: If is_required=True and result is empty

        Example:
            >>> evaluator.evaluate(
            ...     "{% if steps.search.emails | length >= 2 %}{{ steps.search.emails[1].id }}{% endif %}",
            ...     {"steps": {"search": {"emails": [{"id": "1"}, {"id": "2"}]}}},
            ...     "get_second",
            ...     "message_id",
            ...     is_required=True
            ... )
            "2"
        """
        # Preprocess JS syntax
        original_template = template_str
        template_str = self._js_compatibility_preprocess(template_str)

        try:
            template = self.env.from_string(template_str)
            result = template.render(**context)

            # =====================================================================
            # ENHANCED LOGGING: Detect and log empty results with full context
            # =====================================================================
            is_empty = result is None or result.strip() == ""

            if is_empty:
                # Extract available context info for debugging
                steps_context = context.get("steps", {})
                available_steps = (
                    list(steps_context.keys()) if isinstance(steps_context, dict) else []
                )

                # Extract step data summary for debugging
                step_summaries = {}
                for step_name, step_data in (
                    steps_context.items() if isinstance(steps_context, dict) else []
                ):
                    if isinstance(step_data, dict):
                        step_summaries[step_name] = {
                            "keys": list(step_data.keys())[:10],  # First 10 keys
                            "groups_count": (
                                len(step_data.get("groups", [])) if "groups" in step_data else None
                            ),
                            "contacts_count": (
                                len(step_data.get("contacts", []))
                                if "contacts" in step_data
                                else None
                            ),
                        }

                if is_required:
                    error_msg = (
                        f"Template evaluated to empty for required parameter '{parameter_name}'"
                    )
                    logger.error(
                        "jinja_template_empty_required",
                        step_id=step_id,
                        parameter_name=parameter_name,
                        template=template_str,
                        original_template=(
                            original_template if original_template != template_str else None
                        ),
                        available_steps=available_steps,
                        step_summaries=step_summaries,
                        error=error_msg,
                    )
                    raise EmptyResultError(error_msg)
                else:
                    # WARNING log for non-required empty results (helps debug)
                    logger.warning(
                        "jinja_template_empty_result",
                        step_id=step_id,
                        parameter_name=parameter_name,
                        template=template_str,
                        original_template=(
                            original_template if original_template != template_str else None
                        ),
                        available_steps=available_steps,
                        step_summaries=step_summaries,
                        hint="Template produced empty string - check step dependencies and data availability",
                    )

            # Log successful non-empty evaluation
            if not is_empty:
                logger.info(
                    "jinja_template_evaluated",
                    step_id=step_id,
                    parameter_name=parameter_name,
                    template_length=len(template_str),
                    result_length=len(result) if result else 0,
                    result_preview=result[:100] if result and len(result) > 100 else result,
                )

            return result

        except EmptyResultError:
            # Re-raise (critical error)
            raise

        except TemplateSyntaxError as e:
            # Check if error might be JS syntax
            if ".length" in template_str or ".get(" in template_str:
                logger.error(
                    "jinja_template_possible_js_syntax",
                    step_id=step_id,
                    template=template_str,
                    error=str(e),
                    hint="Use '| length' instead of '.length'",
                )
            else:
                logger.error(
                    "jinja_template_syntax_error",
                    step_id=step_id,
                    template=template_str,
                    error=str(e),
                    lineno=e.lineno if hasattr(e, "lineno") else None,
                )
            return None

        except UndefinedError as e:
            logger.error(
                "jinja_template_undefined_reference",
                step_id=step_id,
                template=template_str,
                error=str(e),
            )
            return None

        except Exception as e:
            logger.error(
                "jinja_template_unexpected_error",
                step_id=step_id,
                template=template_str,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def evaluate_parameters(
        self,
        parameters: dict[str, Any],
        completed_steps: dict[str, Any],
        step_id: str,
        required_params: list[str] | None = None,
        _depth: int = 0,
    ) -> dict[str, Any]:
        """
        Recursively evaluate Jinja2 templates in all parameter values.

        Args:
            parameters: Step parameters (may contain templates)
            completed_steps: Data from previous steps
            step_id: Current step ID
            required_params: List of parameter names that cannot be empty
            _depth: Internal recursion depth tracker (DO NOT SET MANUALLY)

        Returns:
            Parameters with templates evaluated

        Raises:
            RecursionError: If recursion depth exceeds limit
            EmptyResultError: If required parameter evaluates to empty

        Example:
            >>> evaluator.evaluate_parameters(
            ...     {"message_id": "{% if steps.search.emails | length >= 2 %}{{ steps.search.emails[1].id }}{% endif %}"},
            ...     {"search": {"emails": [{"id": "1"}, {"id": "2"}]}},
            ...     "get_second",
            ...     required_params=["message_id"]
            ... )
            {"message_id": "2"}
        """
        # Check recursion depth
        if _depth > self.max_recursion_depth:
            error_msg = f"Recursion depth limit ({self.max_recursion_depth}) exceeded"
            logger.error(
                "template_evaluation_recursion_limit",
                step_id=step_id,
                depth=_depth,
                limit=self.max_recursion_depth,
            )
            raise RecursionError(error_msg)

        # Expose steps both at root level and under "steps" key for compatibility
        # This allows both syntaxes to work:
        #   - {{ steps.contacts_1.contacts[0].resource_name }} (documented)
        #   - {{ contacts_1.contacts[0].resource_name }} (LLM variation)
        # BugFix 2025-12-25: LLM sometimes omits $steps. prefix, causing undefined errors
        context = {"steps": completed_steps, **completed_steps}
        required_params = required_params or []

        def _evaluate_recursive(
            value: Any, param_name: str | None = None, current_depth: int = 0
        ) -> Any:
            """Internal recursive evaluator with depth tracking."""
            # Check depth for nested structures
            if current_depth > self.max_recursion_depth:
                error_msg = f"Recursion depth limit ({self.max_recursion_depth}) exceeded at depth {current_depth}"
                logger.error(
                    "template_evaluation_recursion_limit_nested",
                    step_id=step_id,
                    depth=current_depth,
                    limit=self.max_recursion_depth,
                )
                raise RecursionError(error_msg)

            if isinstance(value, str):
                if self.contains_jinja_syntax(value):
                    is_required = param_name in required_params
                    evaluated = self.evaluate(
                        template_str=value,
                        context=context,
                        step_id=step_id,
                        parameter_name=param_name,
                        is_required=is_required,
                    )
                    # If evaluate() returns None (error), keep original
                    return evaluated if evaluated is not None else value
                return value

            elif isinstance(value, dict):
                # Recursive evaluation for nested dicts (increment depth)
                return {
                    k: _evaluate_recursive(v, param_name=k, current_depth=current_depth + 1)
                    for k, v in value.items()
                }

            elif isinstance(value, list):
                # Recursive evaluation for lists (increment depth)
                return [
                    _evaluate_recursive(
                        item, param_name=param_name, current_depth=current_depth + 1
                    )
                    for item in value
                ]

            else:
                # Primitive values (int, float, bool, None) - return as-is
                return value

        # Evaluate all parameters (starting at depth 1 since parameters dict is level 0)
        return {
            k: _evaluate_recursive(v, param_name=k, current_depth=1) for k, v in parameters.items()
        }
