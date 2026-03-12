"""
Shared condition evaluation logic for orchestration.

This module provides safe condition evaluation for CONDITIONAL steps,
with reference resolution and AST validation.

Extracted from parallel_executor.py and step_executor_node.py to eliminate
194 lines of duplication (Phase 1 - Code Duplication Refactoring).

Author: Originally duplicated in parallel_executor + step_executor_node
Refactored: 2025-11-16 (Session 15)
"""

import ast
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Reference Resolver
# ============================================================================


class ReferenceResolver:
    """
    Resolves $steps.X.field and $contexts.field references in execution context.

    Supports:
    - $steps.STEP_ID.path - Reference to completed step result
    - $contexts.path - Reference to conversation context
    - $context.path - Singular form (planner variant)
    - context.path - Without $ prefix (planner variant)
    - items[N].field - Reference to registry item by index (LLM fallback pattern)
    - DOMAIN[N].field - Generic domain reference (emails[0].id, contacts[1].name)
      This handles LLM-generated references that use domain names directly.

    Examples:
        >>> resolver = ReferenceResolver()
        >>> completed_steps = {"search": {"results": [{"id": 1}]}}
        >>> resolver.resolve("$steps.search.results[0].id", completed_steps)
        1
        >>> # Domain reference (resolved from context)
        >>> resolver.resolve("emails[0].id", {}, context={"emails": [{"id": "abc123"}]})
        "abc123"
    """

    # Pattern for items[N].field syntax (LLM fallback pattern)
    ITEMS_PATTERN = re.compile(r"^items\[(\d+)\]\.(.+)$")

    # Pattern for DOMAIN[N].field syntax (generic domain reference)
    # Matches: emails[0].id, contacts[1].resource_name, events[2].summary, etc.
    # Group 1: domain name, Group 2: index, Group 3: field path
    DOMAIN_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]\.(.+)$")

    def is_reference(self, value: Any) -> bool:
        """Check if a value is a $steps, $contexts, $context, context, items[N], or DOMAIN[N] reference."""
        if not isinstance(value, str):
            return False
        return (
            value.startswith("$steps.")
            or value.startswith("$contexts.")
            or value.startswith("$context.")  # Planner also generates singular with $
            or value.startswith("context.")  # Planner generates this without $
            or self.ITEMS_PATTERN.match(value) is not None  # items[N].field pattern
            or self.DOMAIN_PATTERN.match(value)
            is not None  # DOMAIN[N].field pattern (LLM generated)
        )

    def is_items_reference(self, value: Any) -> bool:
        """Check if value is an items[N].field reference (LLM fallback pattern)."""
        return isinstance(value, str) and self.ITEMS_PATTERN.match(value) is not None

    def _is_comma_separated_references(self, value: Any) -> bool:
        """
        Check if value contains multiple comma-separated $steps references.

        Handles planner-generated patterns like:
        "$steps.step_1.contacts[0].email,$steps.step_2.contacts[0].email"

        This is different from embedded references - here the entire value
        is multiple complete references joined by comma.
        """
        if not isinstance(value, str):
            return False
        # Must start with $steps. AND contain comma followed by another $steps.
        return value.startswith("$steps.") and bool(re.search(r",\s*\$steps\.", value))

    def _resolve_comma_separated_references(
        self,
        value: str,
        completed_steps: dict[str, dict[str, Any]],
        context: dict[str, Any] | None = None,
        registry: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        """
        Resolve multiple comma-separated $steps references.

        Args:
            value: String with comma-separated references
                   e.g., "$steps.step_1.contacts[0].email,$steps.step_2.contacts[0].email"
            completed_steps: Map of step_id -> step result data
            context: Conversation context data
            registry: Data registry from state

        Returns:
            Comma-separated resolved values
            e.g., "user1@example.com,user2@example.com"
        """
        # Split by comma followed by $steps to get individual references
        # Use regex to split on comma that precedes $steps
        parts = re.split(r",\s*(?=\$steps\.)", value)

        resolved_parts = []
        for part in parts:
            part = part.strip()
            if part:
                try:
                    resolved = self.resolve(part, completed_steps, context, registry)
                    # Handle case where resolved is a list (for [*] references)
                    if isinstance(resolved, list):
                        resolved_parts.extend(str(item) for item in resolved)
                    else:
                        resolved_parts.append(str(resolved))
                except (KeyError, ValueError) as e:
                    # Log and re-raise to let caller handle
                    raise KeyError(
                        f"Failed to resolve comma-separated reference part '{part}': {e}"
                    ) from e

        return ",".join(resolved_parts)

    def resolve(
        self,
        reference: str,
        completed_steps: dict[str, dict[str, Any]],
        context: dict[str, Any] | None = None,
        registry: dict[str, dict[str, Any]] | None = None,
    ) -> Any:
        """
        Resolve a reference to a value. Supports multiple reference formats.

        Supported formats:
        - $steps.STEP_ID.path - Reference to completed step result
        - $contexts.path / $context.path / context.path - Reference to conversation context
        - items[N].field - Reference to registry item by index
        - DOMAIN[N].field - LLM-generated domain reference (emails[0].id, contacts[1].name)

        Args:
            reference: Reference to resolve (e.g., "$steps.search.contacts[0].resource_name"
                      or "context.contacts[0].resource_name" or "items[0].id" or "emails[0].id")
            completed_steps: Map of step_id -> step result data
            context: Conversation context data (required for context.X and DOMAIN[N] resolution)
            registry: Data registry from state (required for items[N].field resolution)

        Returns:
            Resolved value

        Raises:
            ValueError: If reference format invalid, step/domain not found, or index out of bounds
            KeyError: If path doesn't exist in result
        """
        # Check if it's an items[N].field reference (LLM fallback pattern)
        items_match = self.ITEMS_PATTERN.match(reference)
        if items_match:
            return self._resolve_items_reference(items_match, registry, reference)

        # Check if it's a DOMAIN[N].field reference (LLM-generated domain reference)
        # Examples: emails[0].id, contacts[1].resource_name, events[2].summary
        domain_match = self.DOMAIN_PATTERN.match(reference)
        if domain_match:
            return self._resolve_domain_reference(domain_match, context, reference)

        # Check if it's a $contexts, $context, or context reference (Planner generates all three)
        if (
            reference.startswith("$contexts.")
            or reference.startswith("$context.")
            or reference.startswith("context.")
        ):
            # Pattern: $contexts.path or $context.path or context.path
            pattern = r"^(?:\$contexts|\$context|context)\.(.+)$"
            match = re.match(pattern, reference)

            if not match:
                raise ValueError(f"Invalid context reference format: {reference}")

            path = match.group(1)

            # Check context is provided
            if context is None:
                raise ValueError(
                    f"Cannot resolve {reference}: context not provided. "
                    "This is a bug - executor should pass context."
                )

            # Navigate path in context
            return self._navigate_path(context, path, reference)

        # Otherwise, it's a $steps reference
        # Pattern: $steps.STEP_ID.path
        pattern = r"^\$steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.(.+)$"
        match = re.match(pattern, reference)

        if not match:
            raise ValueError(f"Invalid reference format: {reference}")

        step_id = match.group(1)
        path = match.group(2)

        # Check step exists
        if step_id not in completed_steps:
            raise ValueError(
                f"Reference to non-existent step: {step_id}. "
                f"Available: {list(completed_steps.keys())}"
            )

        # Navigate path
        return self._navigate_path(completed_steps[step_id], path, reference)

    def _resolve_items_reference(
        self,
        match: re.Match,
        registry: dict[str, dict[str, Any]] | None,
        original_ref: str,
    ) -> Any:
        """
        Resolve items[N].field reference from registry.

        This handles LLM fallback pattern where planner generates "items[0].id"
        instead of using resolve_reference tool. The registry contains items
        indexed by their registry_id (e.g., "place_f3c52c").

        Args:
            match: Regex match with groups (index, field)
            registry: Data registry from state (dict of registry_id -> RegistryItem)
            original_ref: Original reference for error messages

        Returns:
            Resolved value from registry item's payload

        Raises:
            ValueError: If registry not provided or index out of bounds
            KeyError: If field not found in item payload
        """
        index = int(match.group(1))
        field = match.group(2)

        if registry is None:
            raise ValueError(
                f"Cannot resolve {original_ref}: registry not provided. "
                "This is a bug - executor should pass registry from state."
            )

        # Get registry items sorted by timestamp (oldest first = insertion order)
        registry_items = list(registry.values())
        if not registry_items:
            raise ValueError(
                f"Cannot resolve {original_ref}: registry is empty. "
                "No items from previous search to reference."
            )

        # Sort by timestamp to get insertion order
        try:
            registry_items.sort(
                key=lambda x: x.get("meta", {}).get("timestamp", ""),
            )
        except (TypeError, AttributeError):
            # If sorting fails, use original order (dict insertion order)
            pass

        if index >= len(registry_items):
            raise ValueError(
                f"Cannot resolve {original_ref}: index {index} out of bounds. "
                f"Registry contains {len(registry_items)} items (0-{len(registry_items) - 1})."
            )

        item = registry_items[index]
        payload = item.get("payload", {})

        # Navigate field path in payload (may be nested like "location.lat")
        return self._navigate_path(payload, field, original_ref)

    def _resolve_domain_reference(
        self,
        match: re.Match,
        context: dict[str, Any] | None,
        original_ref: str,
    ) -> Any:
        """
        Resolve DOMAIN[N].field reference from context.

        This handles LLM-generated references where planner uses domain names directly
        like "emails[0].id" or "contacts[1].resource_name" instead of proper
        $steps.STEP_ID.domain[N].field syntax or resolve_reference tool.

        The context contains domain data from previous search results, keyed by domain name.
        Example: context = {"emails": [{"id": "abc123", ...}, ...], "contacts": [...]}

        Args:
            match: Regex match with groups (domain, index, field)
            context: Conversation context data (dict with domain -> items list)
            original_ref: Original reference for error messages

        Returns:
            Resolved value from context domain item

        Raises:
            ValueError: If context not provided, domain not found, or index out of bounds
            KeyError: If field not found in item
        """
        domain = match.group(1)  # e.g., "emails", "contacts"
        index = int(match.group(2))  # e.g., 0, 1, 2
        field = match.group(3)  # e.g., "id", "resource_name"

        if context is None:
            raise ValueError(
                f"Cannot resolve {original_ref}: context not provided. "
                "This is a bug - executor should pass context."
            )

        # Check if domain exists in context
        if domain not in context:
            available_domains = [k for k in context.keys() if isinstance(context[k], list)]
            raise ValueError(
                f"Cannot resolve {original_ref}: domain '{domain}' not found in context. "
                f"Available domains with data: {available_domains}"
            )

        domain_data = context[domain]

        # Ensure domain data is a list
        if not isinstance(domain_data, list):
            raise ValueError(
                f"Cannot resolve {original_ref}: domain '{domain}' data is not a list "
                f"(got {type(domain_data).__name__}). Expected list of items."
            )

        # Check index bounds
        if not domain_data:
            raise ValueError(
                f"Cannot resolve {original_ref}: domain '{domain}' is empty. "
                "No items from previous search to reference."
            )

        if index >= len(domain_data):
            raise ValueError(
                f"Cannot resolve {original_ref}: index {index} out of bounds. "
                f"Domain '{domain}' contains {len(domain_data)} items (0-{len(domain_data) - 1})."
            )

        item = domain_data[index]

        # Log successful resolution
        logger.info(
            "domain_reference_resolved",
            original_ref=original_ref,
            domain=domain,
            index=index,
            field=field,
            item_keys=list(item.keys()) if isinstance(item, dict) else None,
        )

        # Navigate field path in item (may be nested like "emailAddresses[0].value")
        return self._navigate_path(item, field, original_ref)

    def resolve_args(
        self,
        args: dict[str, Any],
        completed_steps: dict[str, dict[str, Any]],
        context: dict[str, Any] | None = None,
        registry: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Resolve all $steps, $contexts, and items[N] references in arguments dict.

        Supports:
        - Direct references: "$steps.search.contacts"
        - Embedded references: "from:($steps.search.contacts[*].emailAddresses) to:me"
        - Items references: "items[0].id" (LLM fallback pattern)

        Args:
            args: Arguments dict with potential references
            completed_steps: Map of step_id -> step result data
            context: Conversation context data (optional, required for context.X resolution)
            registry: Data registry from state (optional, required for items[N].field resolution)

        Returns:
            Arguments with resolved values
        """
        resolved = {}
        for key, value in args.items():
            # Check for comma-separated references FIRST (before single reference check)
            # e.g., "$steps.step_1.contacts[0].email,$steps.step_2.contacts[0].email"
            if self._is_comma_separated_references(value):
                resolved[key] = self._resolve_comma_separated_references(
                    value, completed_steps, context, registry
                )
            elif self.is_reference(value):
                resolved[key] = self.resolve(value, completed_steps, context, registry)
            elif isinstance(value, str) and self._has_embedded_reference(value):
                # Handle embedded references like "from:($steps.X.Y) to:me"
                resolved[key] = self._resolve_embedded_references(value, completed_steps, context)
            elif isinstance(value, dict):
                resolved[key] = self.resolve_args(value, completed_steps, context, registry)
            elif isinstance(value, list):
                resolved[key] = [
                    (
                        self.resolve(item, completed_steps, context, registry)
                        if self.is_reference(item)
                        else (
                            self._resolve_embedded_references(item, completed_steps, context)
                            if isinstance(item, str) and self._has_embedded_reference(item)
                            else item
                        )
                    )
                    for item in value
                ]
            else:
                resolved[key] = value
        return resolved

    def _has_embedded_reference(self, value: str) -> bool:
        """Check if a string contains embedded references.

        Supports two patterns:
        1. Parenthesized: "from:($steps.X.Y) to:me"
        2. Inline: "from:$steps.X.Y" (including multi-line content)

        Note: Direct references that START with $steps are handled by is_reference().
        This method handles references embedded within other text.
        """
        # Pattern 1: Parenthesized references ($steps.X.Y)
        if re.search(r"\(\$(?:steps|contexts?|context)\.[^)]+\)", value):
            return True

        # Pattern 2: Inline references (not at start of string)
        # Look for $steps. that doesn't start the string
        # FIX: Use [\s\S]+ instead of .+ to match newlines (multi-line content_instruction)
        if re.search(r"[\s\S]+\$(?:steps|contexts?|context)\.", value):
            return True

        return False

    def _resolve_embedded_references(
        self,
        value: str,
        completed_steps: dict[str, dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Resolve embedded references in a string.

        Supports two patterns:
        1. Parenthesized: "from:($steps.X.Y) to:me" -> "from:(email1 OR email2) to:me"
        2. Inline: "from:$steps.X.Y" -> "from:(email1 OR email2)"

        Args:
            value: String with embedded references
            completed_steps: Map of step_id -> step result data
            context: Conversation context data

        Returns:
            String with resolved references
        """
        result = value

        # Pattern 1: Parenthesized references ($steps.X.Y)
        paren_pattern = r"\((\$(?:steps|contexts?|context)\.[^)]+)\)"
        result = re.sub(
            paren_pattern,
            lambda m: self._format_resolved_value(m.group(1), completed_steps, context, m.group(0)),
            result,
        )

        # Pattern 2: Inline references (not at start, no parentheses)
        # Match $steps.X.Y[...] patterns that are not at start of string
        # Use word boundary or common prefixes like "from:", "to:", etc.
        inline_pattern = (
            r"(\$(?:steps|contexts?|context)\."
            r"[a-zA-Z_][a-zA-Z0-9_]*"
            r"(?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\]|\[\*\])*)"
        )

        def replace_inline(match: re.Match) -> str:
            reference = match.group(1)
            # Only replace if not at start (already handled by is_reference)
            start_pos = match.start()
            if start_pos == 0:
                return match.group(0)
            return self._format_resolved_value(reference, completed_steps, context, match.group(0))

        result = re.sub(inline_pattern, replace_inline, result)

        return result

    def _format_resolved_value(
        self,
        reference: str,
        completed_steps: dict[str, dict[str, Any]],
        context: dict[str, Any] | None,
        original: str,
    ) -> str:
        """Format a resolved reference value for embedding in a string."""
        try:
            resolved_value = self.resolve(reference, completed_steps, context)

            # Format the resolved value for embedding
            if isinstance(resolved_value, list):
                # Flatten nested lists (e.g., emailAddresses is a list per contact)
                flat_values = []
                for item in resolved_value:
                    if isinstance(item, list):
                        flat_values.extend(item)
                    else:
                        flat_values.append(item)

                # Join with OR for Gmail query syntax
                if flat_values:
                    return "(" + " OR ".join(str(v) for v in flat_values) + ")"
                return "()"
            return f"({resolved_value})"
        except (ValueError, KeyError) as e:
            logger.warning(
                "embedded_reference_resolution_failed",
                reference=reference,
                error=str(e),
            )
            # Return original on failure to allow debugging
            return original

    def _navigate_path(self, data: Any, path: str, original_ref: str) -> Any:
        """
        Navigate through object with JSONPath-like syntax.

        Supports:
        - Field access: .field_name
        - Array indexing: [0], [1], [2]
        - Wildcard extraction: [*].field_name (extracts field from all array items)

        Args:
            data: Starting data
            path: Path (e.g., "contacts[0].resource_name" or "contacts[*].resource_name")
            original_ref: Original reference for error messages

        Returns:
            Value at end of path (list if wildcard used)

        Raises:
            KeyError: If path doesn't exist

        Examples:
            >>> # Numeric index
            >>> _navigate_path([{"id": 1}, {"id": 2}], "[0].id", "...")
            1
            >>> # Wildcard extraction
            >>> _navigate_path([{"id": 1}, {"id": 2}], "[*].id", "...")
            [1, 2]
            >>> # JSONPath filter
            >>> _navigate_path([{"name": "A", "id": 1}, {"name": "B", "id": 2}], "[?(@.name=='B')].id", "...")
            2
        """
        current = data

        # Parse path: .field or [index] or [*] or [?(@.field=='value')]
        # Group 1: field name (alphanumeric)
        # Group 2: numeric index
        # Group 3: wildcard [*]
        # Group 4: JSONPath filter [?(@.field=='value')] or [?(@.field=="value")]
        parts = re.findall(
            r"\.?([a-zA-Z_][a-zA-Z0-9_]*)|\[(\d+)\]|\[(\*)\]|\[\?\(@\.([a-zA-Z_][a-zA-Z0-9_]*)==['\"]([^'\"]+)['\"]\)\]",
            path,
        )

        for field, index, wildcard, filter_field, filter_value in parts:
            try:
                if field:
                    # Regular field access
                    current = current[field]
                elif index:
                    # Numeric array index
                    current = current[int(index)]
                elif wildcard:
                    # Wildcard extraction: [*]
                    # Must be applied to a list, and remaining path extracts field from each item
                    if not isinstance(current, list):
                        raise TypeError(
                            f"Wildcard [*] can only be applied to arrays, got {type(current).__name__}"
                        )

                    # Get remaining parts after [*]
                    current_idx = parts.index((field, index, wildcard, filter_field, filter_value))
                    remaining_parts = parts[current_idx + 1 :]

                    if not remaining_parts:
                        # [*] with no following path - return the array as-is
                        return current

                    # Extract field from each item in array
                    results = []
                    for item in current:
                        # Navigate remaining path for this item
                        item_value = item
                        for (
                            rem_field,
                            rem_index,
                            rem_wildcard,
                            rem_filter_field,
                            rem_filter_value,
                        ) in remaining_parts:
                            if rem_field:
                                item_value = item_value[rem_field]
                            elif rem_index:
                                item_value = item_value[int(rem_index)]
                            elif rem_wildcard:
                                raise ValueError(f"Nested wildcards not supported: {original_ref}")
                            elif rem_filter_field and rem_filter_value:
                                raise ValueError(
                                    f"Nested JSONPath filters not supported: {original_ref}"
                                )
                        results.append(item_value)

                    return results

                elif filter_field and filter_value:
                    # JSONPath filter: [?(@.field=='value')]
                    # Find the first item matching the filter condition
                    if not isinstance(current, list):
                        raise TypeError(
                            f"JSONPath filter can only be applied to arrays, got {type(current).__name__}"
                        )

                    # Find matching item (case-insensitive comparison)
                    matched_item = None
                    filter_value_lower = filter_value.lower()
                    for item in current:
                        if isinstance(item, dict):
                            item_value = item.get(filter_field, "")
                            if (
                                isinstance(item_value, str)
                                and item_value.lower() == filter_value_lower
                            ):
                                matched_item = item
                                break

                    if matched_item is None:
                        raise KeyError(
                            f"No item found with {filter_field}=='{filter_value}' in array"
                        )

                    current = matched_item

            except (KeyError, IndexError, TypeError) as e:
                raise KeyError(
                    f"Failed to resolve {original_ref}: "
                    f"path '{path}' not found in step result. Error: {e}"
                ) from e

        return current


# ============================================================================
# Condition Evaluator
# ============================================================================


class ConditionEvaluator:
    """
    Evaluates CONDITIONAL step conditions safely.

    Whitelist:
        - Comparisons: ==, !=, <, >, <=, >=, in, not in
        - Booleans: and, or, not
        - Function: len()
        - References: $steps.X.field

    Examples:
        >>> evaluator = ConditionEvaluator()
        >>> completed_steps = {"search": {"results": [1, 2, 3]}}
        >>> evaluator.evaluate("len($steps.search.results) > 0", completed_steps)
        True
    """

    def __init__(self) -> None:
        """Initialize evaluator with reference resolver."""
        self.resolver = ReferenceResolver()

    def evaluate(
        self,
        condition: str,
        completed_steps: dict[str, dict[str, Any]],
    ) -> bool:
        """
        Evaluate condition safely.

        Args:
            condition: Python expression (e.g., "len($steps.search.results) > 0")
            completed_steps: Map of step_id -> result data

        Returns:
            True if condition true, False otherwise

        Raises:
            ValueError: If condition invalid or unsafe
            KeyError: If reference to non-existent step
        """
        # Resolve references in condition
        eval_condition = self._resolve_references_in_condition(condition, completed_steps)

        # Parse expression
        try:
            tree = ast.parse(eval_condition, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid condition syntax: {e}") from e

        # Validate AST whitelist
        self._validate_ast_safe(tree, condition)

        # Evaluate with restricted builtins
        try:
            result = eval(  # Safe: AST validated + restricted builtins
                compile(tree, "<condition>", "eval"),
                {"__builtins__": {"len": len}},
                {},
            )
            return bool(result)
        except Exception as e:
            logger.error(
                "condition_evaluation_failed",
                condition=condition,
                resolved=eval_condition,
                error=str(e),
            )
            raise ValueError(f"Condition evaluation failed: {e}") from e

    def _resolve_references_in_condition(
        self,
        condition: str,
        completed_steps: dict[str, dict[str, Any]],
    ) -> str:
        """
        Resolve $steps.X.field references in condition.

        Replaces references with repr() values and normalizes JSON booleans.

        Args:
            condition: Condition with references
            completed_steps: Map of step_id -> result data

        Returns:
            Condition with resolved values
        """
        # 1. Normalize JSON-style booleans to Python
        condition = re.sub(r"\btrue\b", "True", condition)
        condition = re.sub(r"\bfalse\b", "False", condition)
        condition = re.sub(r"\bnull\b", "None", condition)

        # 2. Resolve $steps references
        pattern = r"\$steps\.([a-zA-Z_][a-zA-Z0-9_]*)((?:\.[a-zA-Z_][a-zA-Z0-9_]*|\[\d+\])*)"

        def replace_ref(match: Any) -> str:
            step_id = match.group(1)
            path = match.group(2)

            # Check step exists
            if step_id not in completed_steps:
                raise KeyError(
                    f"Reference to non-existent step: {step_id}. "
                    f"Available: {list(completed_steps.keys())}"
                )

            # Navigate path
            value = completed_steps[step_id]

            if path:
                # Parse path (e.g., .results[0].name)
                parts = re.findall(r"\.([a-zA-Z_][a-zA-Z0-9_]*)|\[(\d+)\]", path)
                for field, index in parts:
                    if field:
                        value = value[field]
                    elif index:
                        value = value[int(index)]

            # Return repr() for safety (prevent injection)
            return repr(value)

        return re.sub(pattern, replace_ref, condition)

    def _validate_ast_safe(self, tree: Any, original_condition: str) -> None:
        """
        Validate AST contains only safe nodes (whitelist).

        Args:
            tree: Parsed AST
            original_condition: Original condition (for error messages)

        Raises:
            ValueError: If AST contains unsafe nodes
        """
        allowed_nodes = {
            ast.Expression,
            ast.Compare,
            ast.BoolOp,
            ast.UnaryOp,
            ast.Call,
            ast.Name,
            ast.Constant,
            ast.Attribute,
            ast.Subscript,
            ast.List,
            ast.Tuple,
            ast.Dict,
            ast.Load,
            ast.Eq,
            ast.NotEq,
            ast.Lt,
            ast.LtE,
            ast.Gt,
            ast.GtE,
            ast.And,
            ast.Or,
            ast.Not,
            ast.In,
            ast.NotIn,
        }

        for node in ast.walk(tree):
            if type(node) not in allowed_nodes:
                raise ValueError(
                    f"Unsafe AST node in condition: {node.__class__.__name__}. "
                    f"Condition: {original_condition}"
                )

            # Only allow len() function
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id != "len":
                    func_name = node.func.id if isinstance(node.func, ast.Name) else "unknown"
                    raise ValueError(
                        f"Only len() function allowed in conditions, got: {func_name}. "
                        f"Condition: {original_condition}"
                    )
