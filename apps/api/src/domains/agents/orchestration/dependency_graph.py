"""
Dependency Graph Analysis for Parallel Execution.

Implements topological sort to calculate execution waves from ExecutionPlan.
Each wave contains steps that can execute in parallel (no mutual dependencies).

Phase 5.2B: Core algorithm for Map-Reduce orchestration.
Phase 5.3: Will extend for HITL coordination in parallel branches.

Architecture:
- DependencyGraph: Main class for dependency analysis
- CyclicDependencyError: Exception for cycle detection
- Algorithms: Topological sort, cycle detection via DFS

Best Practices (2025):
- Immutable analysis (no side effects)
- Clear separation of concerns (validation vs execution)
- Extensive logging for debugging
- Generic design (works with any ExecutionPlan)

Example:
    >>> plan = ExecutionPlan(steps=[
    ...     Step(id="A", tool="tool1"),
    ...     Step(id="B", tool="tool2"),
    ...     Step(id="C", tool="tool3", depends_on=["A", "B"]),
    ... ])
    >>> graph = DependencyGraph(plan)
    >>> waves = graph.compute_all_waves()
    >>> print(waves)
    [{"A", "B"}, {"C"}]  # Wave 0: parallel, Wave 1: sequential
"""

import json
import re
from collections import defaultdict
from typing import Any

import structlog

from src.core.constants import FOR_EACH_ITEM_INDEX_REF, FOR_EACH_ITEM_REF
from src.core.field_names import (
    FIELD_CORRELATION_PARENT_ID,
    FIELD_REGISTRY_ID,
    FIELD_WAVE_ID,
)
from src.domains.agents.orchestration.for_each_utils import (
    PATTERN_ITEM_REF,
    PATTERN_PATH_SPLIT,
    extract_step_references,
    parse_for_each_reference,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.infrastructure.observability.profiling import profile_performance

logger = structlog.get_logger(__name__)


class CyclicDependencyError(Exception):
    """
    Raised when dependency graph contains a cycle.

    Cycles make execution impossible (deadlock).
    This should be caught during plan validation (validator.py).

    Attributes:
        cycle: List of step_ids forming the cycle.

    Example:
        >>> raise CyclicDependencyError(["A", "B", "C", "A"])
        CyclicDependencyError: Cyclic dependency detected: A → B → C → A
    """

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        cycle_path = " → ".join(cycle)
        super().__init__(f"Cyclic dependency detected: {cycle_path}")


class DependencyGraph:
    """
    Analyzes ExecutionPlan dependencies and computes execution waves.

    Features:
    - Cycle detection via DFS (Depth-First Search)
    - Topological sort for wave calculation
    - Supports TOOL and CONDITIONAL steps
    - Handles dynamic branching (CONDITIONAL on_success/on_fail)

    Algorithm (Topological Sort):
        1. Build adjacency list (step_id → dependencies)
        2. Find Wave 0: All steps with no dependencies
        3. Mark Wave 0 as completed
        4. Find Wave N: All steps whose deps are in waves 0..N-1
        5. Repeat until all steps assigned to waves

    Example Execution:
        Steps: A, B (no deps), C (depends on A,B), D (depends on C)

        Wave 0: [A, B]  ← parallel execution
        Wave 1: [C]     ← after A,B complete
        Wave 2: [D]     ← after C completes

    Phase 5.3 Extension:
        - HITL steps will create synchronization points
        - CONDITIONAL branches evaluated at runtime determine next wave dynamically
        - May need wave recomputation after CONDITIONAL evaluation

    Performance:
        - O(V + E) where V = steps, E = dependencies
        - Cycle detection: O(V + E) via DFS
        - Suitable for plans with hundreds of steps
    """

    def __init__(self, plan: ExecutionPlan):
        """
        Initialize dependency graph from ExecutionPlan.

        Args:
            plan: Validated ExecutionPlan with steps and dependencies.

        Raises:
            CyclicDependencyError: If graph contains cycles.

        Note:
            This constructor validates the graph structure.
            Cycles are detected early to fail fast.
        """
        self.plan = plan
        self.steps_by_id = {s.step_id: s for s in plan.steps}

        # Build adjacency list: step_id → set of step_ids it depends on
        self.dependencies: dict[str, set[str]] = self._build_dependency_graph()

        # Reverse graph: step_id → set of step_ids that depend on it
        self.dependents: dict[str, set[str]] = self._build_reverse_graph()

        # Detect cycles early (fail fast)
        self._validate_no_cycles()

        logger.debug(
            "dependency_graph_built",
            step_count=len(self.steps_by_id),
            dependencies={k: list(v) for k, v in self.dependencies.items()},
        )

    def _build_dependency_graph(self) -> dict[str, set[str]]:
        """
        Build forward dependency graph from ExecutionPlan steps.

        Returns:
            Dict mapping step_id to set of step_ids it depends on.

        Dependencies come from:
        1. Explicit depends_on field
        2. Implicit refs in CONDITIONAL condition expressions
        3. Implicit CONDITIONAL branching (on_success/on_fail steps depend on CONDITIONAL)
        """
        graph: dict[str, set[str]] = defaultdict(set)

        # Pre-compute valid step_ids for filtering obsolete refs after FOR_EACH expansion
        valid_step_ids = set(self.steps_by_id.keys())

        for step in self.plan.steps:
            # Add explicit depends_on
            if step.depends_on:
                graph[step.step_id].update(step.depends_on)

            # CONDITIONAL steps implicitly depend on condition references
            if step.step_type == StepType.CONDITIONAL and step.condition:
                referenced_steps = self._extract_step_references(step.condition)
                valid_refs = referenced_steps & valid_step_ids
                self._log_obsolete_refs_if_any(step.step_id, referenced_steps, valid_refs)
                graph[step.step_id].update(valid_refs)

            # TOOL steps implicitly depend on $steps references in parameters
            if step.parameters:
                params_str = json.dumps(step.parameters)
                referenced_steps = self._extract_step_references(params_str)
                valid_refs = referenced_steps & valid_step_ids
                self._log_obsolete_refs_if_any(step.step_id, referenced_steps, valid_refs)
                graph[step.step_id].update(valid_refs)

            # Ensure all steps are in graph (even with no deps)
            if step.step_id not in graph:
                graph[step.step_id] = set()

        # Add implicit dependencies from CONDITIONAL branching
        # Steps referenced in on_success/on_fail depend on the CONDITIONAL step
        for step in self.plan.steps:
            if step.step_type == StepType.CONDITIONAL:
                if step.on_success and step.on_success in graph:
                    graph[step.on_success].add(step.step_id)
                if step.on_fail and step.on_fail in graph:
                    graph[step.on_fail].add(step.step_id)

        # =================================================================
        # SEQUENTIAL MODE: Chain implicit dependencies
        # =================================================================
        # When execution_mode is "sequential", steps should execute in list
        # order even if LLM forgot to specify depends_on.
        # This is a safety net for plans where the LLM didn't explicitly
        # chain dependencies (e.g., local_query_engine_tool needs search results).
        #
        # Algorithm: For each step without explicit depends_on, add implicit
        # dependency on the previous step in the list (if any).
        # This preserves explicit depends_on when present but chains
        # unconnected steps sequentially.
        # =================================================================
        if getattr(self.plan, "execution_mode", "sequential") == "sequential":
            step_ids = [s.step_id for s in self.plan.steps]
            for i, step in enumerate(self.plan.steps):
                if i > 0:
                    # If this step has no dependencies AND no Jinja/$ references
                    # to previous steps, add implicit dependency on previous step
                    explicit_deps = graph.get(step.step_id, set())
                    if not explicit_deps:
                        # No explicit dependencies - chain to previous step
                        prev_step_id = step_ids[i - 1]
                        graph[step.step_id].add(prev_step_id)
                        logger.debug(
                            "sequential_implicit_dependency_added",
                            step_id=step.step_id,
                            depends_on=prev_step_id,
                            reason="execution_mode=sequential, no explicit deps",
                        )

        return dict(graph)

    @profile_performance(func_name="dependency_graph_reverse", log_threshold_ms=50.0)
    def _build_reverse_graph(self) -> dict[str, set[str]]:
        """
        Build reverse graph (who depends on me).

        Returns:
            Dict mapping step_id to set of step_ids that depend on it.

        Use case:
            When a step completes, we need to know which steps
            are now eligible for execution (deps satisfied).
        """
        reverse: dict[str, set[str]] = defaultdict(set)

        for step_id, deps in self.dependencies.items():
            for dep in deps:
                reverse[dep].add(step_id)
            # Ensure all steps exist in reverse graph
            if step_id not in reverse:
                reverse[step_id] = set()

        return dict(reverse)

    def _extract_step_references(self, condition: str) -> set[str]:
        """
        Extract step_ids referenced in condition expression.

        Delegates to shared extract_step_references() from for_each_utils.

        Args:
            condition: Python expression or Jinja template string

        Returns:
            Set of referenced step_ids.

        Examples:
            >>> graph._extract_step_references("len($steps.search.contacts) > 0")
            {"search"}

            >>> graph._extract_step_references("$steps.a.x > $steps.b.y")
            {"a", "b"}

            >>> graph._extract_step_references("{% for g in steps.group.groups %}")
            {"group"}
        """
        return extract_step_references(condition)

    def _log_obsolete_refs_if_any(
        self,
        step_id: str,
        referenced_steps: set[str],
        valid_refs: set[str],
    ) -> None:
        """
        Log when obsolete step references are filtered.

        This occurs after FOR_EACH expansion: original step_id (e.g., step_2)
        is replaced by expanded IDs (step_2_item_0, step_2_item_1, etc.).
        Parameters may still reference the original step_id which no longer exists.

        These references are safely filtered because:
        1. FOR_EACH results are aggregated under the original step_id
        2. Parameter resolution will find data at $steps.step_2.places

        Args:
            step_id: The step whose dependencies are being analyzed.
            referenced_steps: All step references found in parameters/conditions.
            valid_refs: References that exist in current plan (after filtering).

        See also:
            - parallel_executor._aggregate_for_each_results() for aggregation logic
            - docs/plan_planner.md Section 6.2 for FOR_EACH expansion
        """
        if valid_refs != referenced_steps:
            obsolete_refs = referenced_steps - valid_refs
            logger.debug(
                "implicit_dependency_obsolete_refs_filtered",
                step_id=step_id,
                obsolete_refs=list(obsolete_refs),
                valid_refs=list(valid_refs),
                note="FOR_EACH expansion creates step_id_item_N; results aggregated under original",
            )

    def _validate_no_cycles(self) -> None:
        """
        Detect cycles using DFS (Depth-First Search).

        Raises:
            CyclicDependencyError: If cycle detected.

        Algorithm:
            - White-Gray-Black coloring
            - White: Not visited
            - Gray: Being visited (in current DFS path)
            - Black: Fully visited
            - Back edge (Gray → Gray) = Cycle found

        Complexity: O(V + E) where V = steps, E = dependencies
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color = dict.fromkeys(self.steps_by_id, WHITE)

        def dfs(node: str, path: list[str]) -> list[str] | None:
            """
            DFS with cycle detection.

            Args:
                node: Current step_id being visited.
                path: Current DFS path (for cycle reconstruction).

            Returns:
                Cycle path if found, None otherwise.
            """
            if color[node] == GRAY:
                # Back edge found → cycle detected
                # Reconstruct cycle from path
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]

            if color[node] == BLACK:
                return None  # Already fully explored

            # Mark as being visited (gray)
            color[node] = GRAY
            path.append(node)

            # Visit all dependencies
            for neighbor in self.dependencies.get(node, []):
                cycle = dfs(neighbor, path)
                if cycle:
                    return cycle

            # Mark as fully visited (black)
            path.pop()
            color[node] = BLACK
            return None

        # Run DFS from all unvisited nodes
        for step_id in self.steps_by_id:
            if color[step_id] == WHITE:
                cycle = dfs(step_id, [])
                if cycle:
                    logger.error(
                        "cyclic_dependency_detected",
                        cycle=cycle,
                        dependencies=self.dependencies,
                    )
                    raise CyclicDependencyError(cycle)

    def get_next_wave(self, completed: set[str], excluded: set[str] | None = None) -> set[str]:
        """
        Calculate next wave of steps that can execute.

        Args:
            completed: Set of step_ids that have completed execution.
            excluded: Set of step_ids to exclude (e.g., skipped CONDITIONAL branches).

        Returns:
            Set of step_ids whose dependencies are all satisfied.
            Empty set if no more steps can execute.

        Algorithm:
            For each uncompleted, non-excluded step:
                If all its dependencies are in completed set:
                    Add to next wave

        Example:
            >>> completed = {"A", "B"}
            >>> graph.get_next_wave(completed)
            {"C", "D"}  # All steps depending only on A,B

            >>> graph.get_next_wave(completed, excluded={"D"})
            {"C"}  # D is excluded (e.g., CONDITIONAL on_fail branch)

        Use Case:
            - Called by wave_aggregator_node after each wave completes
            - Enables dynamic wave calculation (CONDITIONAL can change flow)
            - excluded param added for CONDITIONAL branch skipping
        """
        next_wave = set()
        excluded = excluded or set()

        for step_id, deps in self.dependencies.items():
            # Skip if already completed or explicitly excluded
            if step_id in completed or step_id in excluded:
                continue

            # Check if all dependencies satisfied
            if deps <= completed:  # deps is subset of completed
                next_wave.add(step_id)

        return next_wave

    def compute_all_waves(self) -> list[set[str]]:
        """
        Compute complete wave schedule for entire plan.

        Returns:
            List of waves, each wave is a set of step_ids.

        Example:
            >>> graph.compute_all_waves()
            [
                {"A", "B"},      # Wave 0: no dependencies
                {"C"},           # Wave 1: depends on A,B
                {"D", "E"},      # Wave 2: depends on C
            ]

        Note:
            This is for planning/visualization ONLY.
            Actual execution uses get_next_wave() dynamically.

            Why? CONDITIONAL steps can change flow at runtime:
            - If condition true → follow on_success path
            - If condition false → follow on_fail path
            - Cannot predict which path before execution

        Use Cases:
            - Plan validation (detect deadlocks)
            - Metrics (estimate parallelism)
            - Grafana dashboards (visualize wave structure)
        """
        waves = []
        completed = set()

        while len(completed) < len(self.steps_by_id):
            wave = self.get_next_wave(completed)

            if not wave:
                # No more steps can execute but graph not complete
                # This should never happen if _validate_no_cycles passed
                remaining = set(self.steps_by_id.keys()) - completed
                logger.error(
                    "dependency_graph_deadlock",
                    completed=list(completed),
                    remaining=list(remaining),
                    dependencies={
                        k: list(v) for k, v in self.dependencies.items() if k in remaining
                    },
                )
                raise RuntimeError(
                    f"Dependency deadlock: cannot execute {remaining}. "
                    f"This indicates a bug in dependency analysis or validation."
                )

            waves.append(wave)
            completed.update(wave)

        logger.info(
            "dependency_waves_computed",
            wave_count=len(waves),
            waves=[list(w) for w in waves],
            max_parallelism=max(len(w) for w in waves) if waves else 0,
            critical_path_length=len(waves),
        )

        return waves

    def get_max_parallelism(self) -> int:
        """
        Calculate maximum number of steps that can execute in parallel.

        Returns:
            Max size of any wave in complete schedule.

        Use Cases:
            - Resource allocation (DB connections, API rate limits)
            - Performance estimation
            - Prometheus metric thresholds

        Example:
            >>> graph.get_max_parallelism()
            5  # Wave 2 has 5 parallel steps

        Caveat:
            Returns 0 if graph is empty (no steps).
        """
        waves = self.compute_all_waves()
        return max(len(w) for w in waves) if waves else 0

    def estimate_critical_path_length(self) -> int:
        """
        Estimate minimum number of sequential steps (critical path).

        Returns:
            Number of waves = minimum execution time in "steps".

        Note:
            Actual wall-clock time depends on step durations.
            This gives lower bound on latency.

        Example:
            >>> graph.estimate_critical_path_length()
            3  # At least 3 sequential waves

        Use Cases:
            - Performance estimation
            - SLA calculations
            - Bottleneck identification
        """
        return len(self.compute_all_waves())

    def get_all_dependencies(self, step_id: str) -> set[str]:
        """
        Get all dependencies (direct and transitive) for a step.

        Traverses the dependency graph recursively to find all steps
        that must complete before the given step can execute.

        Args:
            step_id: The step to get dependencies for.

        Returns:
            Set of step_ids that must complete before step_id.

        Example:
            >>> # Given: A → B → C (C depends on B, B depends on A)
            >>> graph.get_all_dependencies("C")
            {"A", "B"}

        Use Cases:
            - FOR_EACH HITL pre-execution: Find all steps needed before provider
            - Debugging dependency chains
            - Critical path analysis
        """
        all_deps: set[str] = set()
        to_process: list[str] = list(self.dependencies.get(step_id, set()))

        # Safety limit to prevent infinite loops (even though cycles are validated at init)
        max_iterations = len(self.steps_by_id) * 2
        iterations = 0

        while to_process and iterations < max_iterations:
            iterations += 1
            dep_id = to_process.pop()
            if dep_id not in all_deps:
                all_deps.add(dep_id)
                # Add transitive dependencies
                to_process.extend(self.dependencies.get(dep_id, set()))

        if iterations >= max_iterations:
            logger.warning(
                "get_all_dependencies_hit_safety_limit",
                step_id=step_id,
                iterations=iterations,
                deps_found=len(all_deps),
            )

        return all_deps

    def get_wave_info(self) -> dict[str, Any]:
        """
        Get detailed wave information for observability.

        Returns:
            Dict with wave structure, parallelism, and metrics.

        Example:
            >>> graph.get_wave_info()
            {
                "total_waves": 3,
                "max_parallelism": 5,
                "critical_path_length": 3,
                "waves": [
                    {FIELD_WAVE_ID: 0, "steps": ["A", "B"], "size": 2},
                    {FIELD_WAVE_ID: 1, "steps": ["C"], "size": 1},
                    {FIELD_WAVE_ID: 2, "steps": ["D", "E", "F"], "size": 3}
                ],
                "average_parallelism": 2.0
            }

        Use Cases:
            - Logging and debugging
            - Prometheus metrics
            - Grafana dashboards
        """
        waves = self.compute_all_waves()

        return {
            "total_waves": len(waves),
            "max_parallelism": max(len(w) for w in waves) if waves else 0,
            "critical_path_length": len(waves),
            "waves": [
                {
                    FIELD_WAVE_ID: idx,
                    "steps": sorted(wave),  # Sort for deterministic output
                    "size": len(wave),
                }
                for idx, wave in enumerate(waves)
            ],
            "average_parallelism": sum(len(w) for w in waves) / len(waves) if waves else 0,
        }

    # =========================================================================
    # FOR_EACH EXPANSION (plan_planner.md Section 6.2)
    # =========================================================================

    def expand_for_each_steps(
        self,
        step_results: dict[str, Any],
    ) -> tuple[list["ExecutionStep"], dict[str, list[str]]]:
        """
        Expand for_each steps into multiple concrete steps at runtime.

        This method is called AFTER the provider step completes, to dynamically
        expand the consumer step into N parallel sub-steps (one per item).

        Args:
            step_results: Results from completed steps, keyed by step_id.
                          Contains the arrays to iterate over.

        Returns:
            Tuple of:
            - List of expanded ExecutionStep objects (originals replaced)
            - Dict mapping original step_id to list of expanded step_ids

        Algorithm:
            1. Find steps with for_each field
            2. Resolve for_each reference to get array from step_results
            3. Apply for_each_max limit (safety cap)
            4. Clone step N times with $item substituted
            5. Update depends_on for downstream steps

        Example:
            Original: step_2 with for_each="$steps.step_1.places"
            step_1.places = [place_a, place_b, place_c]

            Expanded:
            - step_2_item_0: parameters with $item → place_a
            - step_2_item_1: parameters with $item → place_b
            - step_2_item_2: parameters with $item → place_c

            Downstream steps depending on step_2 now depend on ALL expanded steps.

        Notes:
            - Uses JinjaEvaluator for $item substitution (Phase 3)
            - Respects for_each_max limit (default 10, max 100)
            - Original step is removed, replaced by expanded steps
        """
        from copy import deepcopy

        from src.domains.agents.orchestration.plan_schemas import ExecutionStep

        expanded_steps: list[ExecutionStep] = []
        expansion_map: dict[str, list[str]] = {}  # original_id → [expanded_ids]
        for_each_step_ids = set()

        # Pass 1: Identify for_each steps and expand them
        for step in self.plan.steps:
            if not step.is_for_each_step:
                expanded_steps.append(step)
                continue

            # This is a for_each step - expand it
            for_each_step_ids.add(step.step_id)
            array_ref = step.for_each  # e.g., "$steps.step_1.places"

            # Resolve the array reference
            items = self._resolve_for_each_reference(array_ref, step_results)

            if not items:
                logger.warning(
                    "for_each_empty_array",
                    step_id=step.step_id,
                    for_each=array_ref,
                    reason="Array is empty or could not be resolved",
                )
                # Keep original step but mark as skipped? Or remove entirely?
                # Decision: Remove - no items to iterate means no execution
                expansion_map[step.step_id] = []
                continue

            # Apply for_each_max limit (safety cap)
            max_items = min(step.for_each_max, len(items))
            if len(items) > step.for_each_max:
                logger.warning(
                    "for_each_max_applied",
                    step_id=step.step_id,
                    original_count=len(items),
                    capped_count=max_items,
                    for_each_max=step.for_each_max,
                )
            items = items[:max_items]

            # Expand step into N copies
            expanded_ids: list[str] = []
            for idx, item in enumerate(items):
                expanded_id = f"{step.step_id}_item_{idx}"
                expanded_ids.append(expanded_id)

                # Clone step with modified id and parameters
                expanded_params = self._substitute_item_in_params(
                    params=step.parameters,
                    item=item,
                    item_index=idx,
                )

                # Propagate parent registry_id for correlated display
                # The FIELD_REGISTRY_ID is added to items in structured_data by parallel_executor
                if isinstance(item, dict) and FIELD_REGISTRY_ID in item:
                    expanded_params[FIELD_CORRELATION_PARENT_ID] = item[FIELD_REGISTRY_ID]
                    logger.info(
                        "for_each_correlation_parent_propagated",
                        step_id=step.step_id,
                        expanded_id=expanded_id,
                        parent_registry_id=item[FIELD_REGISTRY_ID],
                    )
                elif isinstance(item, dict):
                    logger.warning(
                        "for_each_item_missing_registry_id",
                        step_id=step.step_id,
                        expanded_id=expanded_id,
                        item_keys=list(item.keys())[:10],  # First 10 keys for debug
                    )

                expanded_step = ExecutionStep(
                    step_id=expanded_id,
                    step_type=step.step_type,
                    agent_name=step.agent_name,
                    tool_name=step.tool_name,
                    parameters=expanded_params,
                    depends_on=deepcopy(step.depends_on),
                    condition=step.condition,
                    on_success=step.on_success,
                    on_fail=step.on_fail,
                    # Clear for_each fields - this is now a concrete step
                    for_each=None,
                    for_each_max=step.for_each_max,
                    on_item_error=step.on_item_error,
                    delay_between_items_ms=step.delay_between_items_ms,
                )
                expanded_steps.append(expanded_step)

            expansion_map[step.step_id] = expanded_ids

            logger.info(
                "for_each_step_expanded",
                original_step_id=step.step_id,
                expanded_count=len(expanded_ids),
                expanded_ids=expanded_ids,
                for_each_max=step.for_each_max,
            )

        # Pass 2: Update depends_on for downstream steps
        # Steps that depended on original for_each step must now depend on ALL expanded steps
        final_steps: list[ExecutionStep] = []
        for step in expanded_steps:
            if step.depends_on:
                new_depends_on = []
                for dep in step.depends_on:
                    if dep in expansion_map:
                        # Replace dependency on for_each step with ALL expanded steps
                        new_depends_on.extend(expansion_map[dep])
                    else:
                        new_depends_on.append(dep)

                if new_depends_on != step.depends_on:
                    # Create new step with updated depends_on
                    step = ExecutionStep(
                        step_id=step.step_id,
                        step_type=step.step_type,
                        agent_name=step.agent_name,
                        tool_name=step.tool_name,
                        parameters=step.parameters,
                        depends_on=new_depends_on,
                        condition=step.condition,
                        on_success=step.on_success,
                        on_fail=step.on_fail,
                        for_each=step.for_each,
                        for_each_max=step.for_each_max,
                        on_item_error=step.on_item_error,
                        delay_between_items_ms=step.delay_between_items_ms,
                    )

            final_steps.append(step)

        return final_steps, expansion_map

    def _resolve_for_each_reference(
        self,
        array_ref: str,
        step_results: dict[str, Any],
    ) -> list[Any]:
        """
        Resolve for_each reference to actual array.

        Args:
            array_ref: Reference string like "$steps.step_1.places" or "$steps.step_1.contacts[*]"
            step_results: Completed step results

        Returns:
            List of items to iterate over

        Examples:
            "$steps.step_1.places" → step_results["step_1"]["places"]
            "$steps.step_1.contacts" → step_results["step_1"]["contacts"]
        """
        # Use shared parse_for_each_reference for DRY
        step_id, field_path = parse_for_each_reference(array_ref)

        if not step_id or not field_path:
            logger.error(
                "for_each_invalid_reference",
                array_ref=array_ref,
                expected_format="$steps.step_id.field_path",
            )
            return []

        # Get step result
        if step_id not in step_results:
            logger.error(
                "for_each_step_not_found",
                array_ref=array_ref,
                step_id=step_id,
                available_steps=list(step_results.keys()),
            )
            return []

        result = step_results[step_id]

        # Navigate field path (supports nested like "data.items")
        for part in field_path.split("."):
            if isinstance(result, dict):
                result = result.get(part)
            elif isinstance(result, list) and part.isdigit():
                idx = int(part)
                result = result[idx] if idx < len(result) else None
            else:
                result = getattr(result, part, None)

            if result is None:
                logger.warning(
                    "for_each_field_not_found",
                    array_ref=array_ref,
                    step_id=step_id,
                    field_path=field_path,
                    failed_at=part,
                )
                return []

        # Ensure result is a list
        if not isinstance(result, list):
            logger.warning(
                "for_each_not_array",
                array_ref=array_ref,
                actual_type=type(result).__name__,
            )
            # Wrap single item in list for consistency
            return [result] if result is not None else []

        return result

    def _substitute_item_in_params(
        self,
        params: dict[str, Any] | None,
        item: Any,
        item_index: int,
    ) -> dict[str, Any]:
        """
        Substitute $item references in parameters with actual item value.

        Args:
            params: Original parameters dict
            item: Current item from iteration
            item_index: Index of current item (for $item_index)

        Returns:
            New parameters dict with $item substituted

        Substitution rules:
            - "$item" → entire item object
            - "$item.field" → item["field"] or item.field
            - "$item_index" → item_index (0-based)

        Example:
            params = {"email": "$item.emailAddresses[0].value", "name": "$item.displayName"}
            item = {"displayName": "John", "emailAddresses": [{"value": "john@x.com"}]}

            Result: {"email": "john@x.com", "name": "John"}
        """
        if not params:
            return {}

        from copy import deepcopy

        # Pre-process: Replace exact "$item_index" values with actual integer
        # before JSON serialization (so they become integers, not strings)
        def preprocess_params(obj: Any) -> Any:
            """Recursively replace $item_index with actual integer."""
            if isinstance(obj, dict):
                return {k: preprocess_params(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [preprocess_params(v) for v in obj]
            elif isinstance(obj, str) and obj == FOR_EACH_ITEM_INDEX_REF:
                return item_index  # Return as integer
            return obj

        params = preprocess_params(deepcopy(params))

        # Serialize to JSON for string replacement
        params_str = json.dumps(params)

        # Use pre-compiled pattern for $item references
        def resolve_item_ref(match: re.Match) -> str:
            """Resolve single $item reference.

            IMPORTANT: The regex replacement happens on JSON-serialized params,
            so "$item.field" is INSIDE a quoted string context in JSON.

            Example JSON: {"to": "$item.email"}
            After json.dumps: {"to": "$item.email"} (quotes escaped internally)

            When we replace $item.email with "alice@x.com", we need to ensure
            proper escaping WITHOUT adding outer quotes (they already exist).
            """
            ref = match.group(0)

            if ref == FOR_EACH_ITEM_REF:
                # Return entire item as JSON - will replace the whole quoted value
                # Remove outer quotes since we're already inside a string context
                item_json = json.dumps(item)
                # If it's an object/array, it replaces the whole string value
                return item_json

            # Note: $item_index is handled in preprocess_params() before JSON serialization

            # Parse path after "$item."
            path = ref[len(FOR_EACH_ITEM_REF) + 1 :]  # Remove "$item." prefix
            value = item

            # Use shared pre-compiled pattern for path splitting
            for part in PATTERN_PATH_SPLIT.split(path):
                if not part:
                    continue

                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, list):
                    try:
                        idx = int(part)
                        value = value[idx] if idx < len(value) else None
                    except ValueError:
                        value = None
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    value = None

                if value is None:
                    break

            # Return value for substitution
            # CRITICAL: Since $item.field is inside a JSON string (already quoted),
            # we must NOT add quotes for string values - just escape special chars.
            if isinstance(value, str):
                # Escape special JSON characters in the string, but no outer quotes
                # json.dumps adds quotes, so we strip them
                escaped = json.dumps(value)
                return escaped[1:-1]  # Remove surrounding quotes from json.dumps
            elif value is None:
                return "null"
            elif isinstance(value, bool):
                return "true" if value else "false"
            elif isinstance(value, int | float):
                return str(value)
            else:
                # Complex types (dict, list) - replace entirely
                return json.dumps(value)

        # Replace all $item references using shared pre-compiled pattern
        # Note: $item_index is handled in preprocess_params() above
        params_str = PATTERN_ITEM_REF.sub(resolve_item_ref, params_str)

        try:
            return json.loads(params_str)
        except json.JSONDecodeError as e:
            logger.error(
                "for_each_param_substitution_failed",
                error=str(e),
                params_str=params_str[:200],
            )
            return params or {}
