"""Tool selection and wrapping for ReAct execution mode (ADR-293).

The loop binds the AVAILABLE tools (filtered by active connectors) by
RELEVANCE, from the global order the router computed with the query embedding
it already paid for: the detected domains' tools, then every other family's
``CATALOGUE_DOMAIN_COVERAGE_TOP_N`` best-ranked tools — plus the delegation
door of an expanded user MCP server — then the first ``react_tool_semantic_top_k``
of the order; the rest is dropped by relevance and ``react_agent_max_tools``
stays the safety net, trimming by the same tiers. Without a ranking, or with
K = 0, every available tool is bound in registration order and only the cap
trims it. A blind positional truncation here used to drop the SAME families
on every turn whatever the question, the user's own MCP tools among them.

A BINDING UNIT is bound whole or not at all (2026-09-20). Tools declaring the
same ``binding_unit`` on their manifest are one affordance — a skill is
activated, its script run, its resources read — and each alone is a dead end:
measured on dev, the ranking placed ``activate_skill_tool`` and dropped
``run_skill_script``, so the loop activated the skill, could not run its
script and answered in prose (the production motif on both skills). A unit
ranks as its best member, takes ONE coverage seat, rides the semantic tail
whole, and the cap drops it whole rather than cutting inside it.

Filtering chain (same as pipeline):
1. Global registry tools
2. Minus admin-disabled MCP servers (per user)
3. Plus user-enabled MCP tools
4. Only tools whose manifest is in the per-request available set
   (respects active connectors)

Also builds a hitl_map (tool_name → bool) for the execute_tools node to know
which tools require HITL approval via interrupt().
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

import structlog

from src.core.config import settings
from src.core.constants import (
    CATALOGUE_DOMAIN_COVERAGE_TOP_N,
    EXECUTION_MODE_REACT,
    MCP_ITERATIVE_TASK_SUFFIX,
    MCP_USER_TOOL_NAME_PREFIX,
)
from src.core.context import get_request_tool_manifests, user_mcp_tools_ctx
from src.domains.agents.registry.catalogue import manifests_for_mode
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.agents.tools.tool_resolution import resolve_tool_instance
from src.infrastructure.mcp.registration import declares_destructive_tool
from src.infrastructure.observability.metrics_react import (
    react_cross_turn_cache_fallback_total,
    react_tool_selector_capped_total,
    react_tools_bound,
    react_tools_resolved,
)

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = structlog.get_logger(__name__)


class DetectedDomains(Protocol):
    """What the selector reads of a turn's intelligence: the detected domains."""

    @property
    def domains(self) -> Sequence[str]: ...


class _Resolved(NamedTuple):
    """One tool a manifest binds: its name, instance, HITL flag, and whether it is
    the delegation door (task tool) of an expanded iterative user MCP server.
    """

    name: str
    instance: BaseTool
    hitl: bool
    door: bool = False


class _Row(NamedTuple):
    """A resolved tool with what the composition reads about it."""

    tool: ReactToolWrapper
    priority: bool
    name: str
    family: str
    door: bool
    unit: str | None = None


#: Token cost of a bound tool's schema, by tool name — static per process, so
#: measured once; a user MCP tool re-registered with a new schema keeps a
#: stale count for a metric, which is harmless.
_schema_tokens_by_name: dict[str, int] = {}


def bound_tool_tokens(tools: Sequence[BaseTool]) -> int:
    """Tokens the bound schemas add to EVERY model call of the turn.

    Measured 2026-09-17: 331 tokens per native schema on average, 26 155 for
    the 80 the cap kept — 95 % of the first call's prompt. The number the
    ``react_delivered_context_tokens`` histogram never saw, since it counts
    messages.

    Args:
        tools: The tools bound to the loop.

    Returns:
        The token count of their OpenAI-format schemas, 0 when it cannot be measured.
    """
    total = 0
    for tool in tools:
        cached = _schema_tokens_by_name.get(tool.name)
        if cached is None:
            try:
                from langchain_core.utils.function_calling import convert_to_openai_tool

                from src.domains.agents.utils.token_utils import count_tokens

                cached = count_tokens(json.dumps(convert_to_openai_tool(tool), ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001 — a metric never breaks the turn
                logger.debug("react_tool_schema_tokens_unmeasured", tool=tool.name, error=str(exc))
                cached = 0
            _schema_tokens_by_name[tool.name] = cached
        total += cached
    return total


def every_tool_token_budget() -> int | None:
    """Tokens every tool's schemas may take in one call, or None when unknown (ADR-308).

    The ``react_cross_turn_cache_max_window_fraction`` share of the ReAct slot's
    own window (ADR-278), read through the seam the tool result budget reads. An
    unknown or unreadable window sets no budget: the cap still bounds the count.

    Returns:
        The budget in tokens, or None.
    """
    window = 0
    # Best-effort read: a catalogue hiccup leaves the cap as the only bound,
    # never breaks the turn.
    with contextlib.suppress(Exception):
        from src.core.llm_config_helper import get_effective_context_window_for_slot

        window = get_effective_context_window_for_slot("react_agent")
    if window <= 0:
        return None
    return int(window * settings.react_cross_turn_cache_max_window_fraction)


class ReactToolSelector:
    """Select and wrap the tools the ReAct loop binds for a turn.

    Resolves every available manifest to its tool instances (registry, then
    the per-request user MCP context), composes them by relevance when the
    router ranked the turn, and applies the cap as a safety net.
    """

    def select(
        self,
        intelligence: DetectedDomains | None,
        ranking: Sequence[str] | None = None,
    ) -> tuple[list[ReactToolWrapper], dict[str, bool]]:
        """Select the tools the ReAct agent binds this turn.

        Uses the same per-request manifest filtering as the pipeline (respects
        active connectors, admin-disabled MCP servers, user MCP tools), then
        maps manifest names to actual BaseTool instances from the registry.

        With a ``ranking`` (the turn's global relevance order, computed by the
        router from the query embedding it already paid for) and a positive
        ``react_tool_semantic_top_k``, the loop binds the detected domains'
        tools, the best-ranked tools of EVERY other family (so no family is
        out of reach when the router under-detected) and the first K of the
        ranking — the rest is dropped by relevance, and the cap stays the
        safety net (ADR-293). Without a ranking, or with K = 0, every
        available tool is bound in registration order; only the cap trims it,
        the detected domains' tools first, then one family coverage, then
        the rest.

        Args:
            intelligence: Query intelligence. Its detected domains give their
                agents' tools priority: bound first, and first to SURVIVE the
                max_tools cap.
            ranking: Manifest names, most relevant first, for the whole turn.

        Returns:
            Tuple of (wrapped_tools, hitl_map).
            - wrapped_tools: List of ReactToolWrapper instances.
            - hitl_map: Dict mapping tool_name → hitl_required (for execute_tools HITL logic).
        """
        # Use per-request manifests (filtered by active connectors + MCP settings)
        # Same source of truth as pipeline: build_request_tool_manifests()
        available_manifests = manifests_for_mode(get_request_tool_manifests(), EXECUTION_MODE_REACT)

        priority_agents = self._domain_priority_agents(intelligence)
        rows: list[_Row] = []
        hitl_map: dict[str, bool] = {}
        skipped: list[str] = []
        for manifest in available_manifests:
            family = str(getattr(manifest, "agent", "") or "")
            unit = getattr(manifest, "binding_unit", None) or None
            resolved = self._manifest_tools(manifest)
            if resolved is None:
                skipped.append(manifest.name)
                continue
            for item in resolved:
                wrapper = ReactToolWrapper(original_tool=item.instance, hitl_required=item.hitl)
                rows.append(
                    _Row(wrapper, family in priority_agents, item.name, family, item.door, unit)
                )
                hitl_map[item.name] = item.hitl

        # Cap at max_tools. Measured on the RESOLVED tool count, not the manifest
        # count: iterative expansion can emit more tools than there are manifests
        # (one task manifest → N individual tools), so the cap must be evaluated
        # (and reported) on what is actually bound.
        max_tools = settings.react_agent_max_tools
        resolved_count = len(rows)
        # ADR-256: observed on EVERY turn, not only when the cap bites. A counter
        # of cap events fires once capabilities are already lost; this
        # distribution is what shows a deployment creeping towards its ceiling.
        react_tools_resolved.observe(resolved_count)
        # ADR-308: the same tools, in the same order, on every turn — or, when
        # they cannot all be bound, the relevance selection of a known-good turn.
        every_tool = (
            self._every_tool(rows, max_tools) if settings.react_cross_turn_cache_enabled else None
        )
        if every_tool is not None:
            wrapped_tools = every_tool
        else:
            wrapped_tools, hitl_map = self._by_relevance(rows, hitl_map, ranking, priority_agents)

        if skipped:
            logger.debug(
                "react_tool_selector_skipped",
                skipped=skipped,
                reason="manifest_without_registered_tool",
            )

        react_tools_bound.observe(len(wrapped_tools))
        logger.info(
            "react_tool_selector_complete",
            available_manifests=len(available_manifests),
            resolved_count=resolved_count,
            tool_count=len(wrapped_tools),
            hitl_count=sum(1 for v in hitl_map.values() if v),
            capped=resolved_count > max_tools,
            every_tool=every_tool is not None,
        )

        return wrapped_tools, hitl_map

    def _by_relevance(
        self,
        rows: list[_Row],
        hitl_map: dict[str, bool],
        ranking: Sequence[str] | None,
        priority_agents: set[str],
    ) -> tuple[list[ReactToolWrapper], dict[str, bool]]:
        """The relevance composition of ADR-293, then the cap.

        Args:
            rows: The resolved tools, in registration order.
            hitl_map: Tool name → HITL required, for every resolved tool.
            ranking: The turn's global relevance order, or None.
            priority_agents: The detected domains' agents.

        Returns:
            The bound tools and their HITL map.
        """
        max_tools = settings.react_agent_max_tools
        resolved_count = len(rows)
        top_k = settings.react_tool_semantic_top_k
        relevance_on = bool(ranking) and top_k > 0
        wrapped_tools, tiers, units, kept_names, dropped_by_relevance = self._compose(
            rows, ranking if relevance_on else None, top_k
        )
        if relevance_on:
            hitl_map = {k: v for k, v in hitl_map.items() if k in kept_names}
            logger.info(
                "react_tool_selector_relevance",
                resolved_count=resolved_count,
                bound_count=len(wrapped_tools),
                top_k=top_k,
                priority_agents=sorted(priority_agents),
                dropped_by_relevance=len(dropped_by_relevance),
            )
            logger.debug(
                "react_tool_selector_relevance_dropped", dropped_tools=dropped_by_relevance
            )
        return self._apply_cap(
            wrapped_tools, tiers, units, hitl_map, max_tools, priority_agents, resolved_count
        )

    @staticmethod
    def _every_tool(rows: list[_Row], max_tools: int) -> list[ReactToolWrapper] | None:
        """Every resolved tool in registration order, or None when they cannot all be bound.

        None sends the turn back to the relevance selection (ADR-308): above the
        operator's cap a cut would have to choose, and a cut that follows the
        question is exactly the changing prefix the flag exists to avoid; beyond
        the allowed share of the slot's window the schemas would crowd out the
        conversation. Each fallback is counted by reason.

        Args:
            rows: The resolved tools, in registration order.
            max_tools: The operator's cap.

        Returns:
            The tools to bind, or None.
        """
        tools = [row.tool for row in rows]
        reason: str | None = None
        if len(tools) > max_tools:
            reason = "cap"
        else:
            budget = every_tool_token_budget()
            if budget is not None and bound_tool_tokens(tools) > budget:
                reason = "window"
        if reason is None:
            return tools
        react_cross_turn_cache_fallback_total.labels(reason=reason).inc()
        logger.warning(
            "react_cross_turn_cache_fallback",
            reason=reason,
            resolved_count=len(tools),
            max_tools=max_tools,
        )
        return None

    def _manifest_tools(self, manifest: Any) -> list[_Resolved] | None:
        """The tools one manifest binds, or None when unresolvable.

        ReAct already IS an iterative loop, so the per-server "task tool"
        indirection (designed for the single-shot pipeline planner) only
        hides the descriptive individual tools from the LLM, which then
        falls back to generic web search. For iterative USER MCP servers,
        expose the individual tools directly so the model can recognise and
        pick them by description — EXCEPT MCP App servers, which keep the
        task tool (they need the dedicated MCP-app prompt + model).

        The task tool is bound AS WELL, never replaced: it is the only
        delegation affordance for identity- or multi-step asks the
        individual tools cannot express (measured 2026-09-02 on a public
        code-hosting toolset: "list MY repos" has no individual tool, so
        a model shown only per-repo tools rationally asked the user for
        their username — while the pipeline, which keeps the task tool,
        delegated to the sub-agent and answered).

        HITL is read straight from the in-hand manifest: the agent_registry
        does not know user MCP tools, so looking it up there would silently
        disable approval gates on user MCP mutation tools.

        Args:
            manifest: The candidate tool manifest.

        Returns:
            The tools to bind, or None when no instance resolves (skipped).
        """
        tool_name = manifest.name
        permissions = getattr(manifest, "permissions", None)
        manifest_hitl = bool(permissions and permissions.hitl_required)
        expanded = self._expand_iterative_user_mcp(manifest)
        if expanded is not None:
            tools = [_Resolved(name, instance, hitl) for name, instance, hitl in expanded]
            task_instance = resolve_tool_instance(tool_name)
            if task_instance is not None:
                tools.append(_Resolved(tool_name, task_instance, manifest_hitl, door=True))
            return tools
        # Resolve across the global registry AND the per-request user MCP
        # ContextVar — same two-step lookup as the pipeline executor, so user
        # MCP tools (instances live only in the ContextVar) are not dropped.
        base_tool = resolve_tool_instance(tool_name)
        if base_tool is None:
            return None
        return [_Resolved(tool_name, base_tool, manifest_hitl)]

    @staticmethod
    def _apply_cap(
        wrapped_tools: list[ReactToolWrapper],
        tiers: list[int],
        units: list[str | None],
        hitl_map: dict[str, bool],
        max_tools: int,
        priority_agents: set[str],
        resolved_count: int,
    ) -> tuple[list[ReactToolWrapper], dict[str, bool]]:
        """The safety net: a stable sort on tiers, then the truncation.

        The detected domains' tools first, then one coverage per family, then
        the rest — so the truncation sacrifices generic tools instead of the
        very tools the query needs, and never a whole family. Order is
        untouched when the count fits the cap. A cut that falls inside a
        binding unit drops the unit whole: a partial affordance is worth less
        than the seats it holds, and the cap is a bound, never a target.

        Args:
            wrapped_tools: The bound tools, in binding order.
            tiers: A tier per tool (0 priority, 1 coverage, 2 the rest).
            units: The binding unit of each tool, None for a tool on its own.
            hitl_map: Tool name → HITL required.
            max_tools: The cap.
            priority_agents: The detected domains' agents (for the log).
            resolved_count: How many tools resolved before any selection.

        Returns:
            The tools that survive and their HITL map.
        """
        if len(wrapped_tools) <= max_tools:
            return wrapped_tools, hitl_map
        react_tool_selector_capped_total.inc()
        ordered = sorted(zip(wrapped_tools, tiers, units, strict=True), key=lambda i: i[1])
        kept = ReactToolSelector._whole_units(ordered[:max_tools], ordered[max_tools:])
        kept_tools = [w for w, _tier, _unit in kept]
        kept_names = {t.name for t in kept_tools}
        dropped = [w.name for w, _tier, _unit in ordered if w.name not in kept_names]
        logger.warning(
            "react_tool_selector_capped",
            resolved_count=resolved_count,
            max_tools=max_tools,
            priority_agents=sorted(priority_agents),
            dropped_tools=dropped,
        )
        return kept_tools, {k: v for k, v in hitl_map.items() if k in kept_names}

    @staticmethod
    def _whole_units(
        kept: list[tuple[ReactToolWrapper, int, str | None]],
        cut: list[tuple[ReactToolWrapper, int, str | None]],
    ) -> list[tuple[ReactToolWrapper, int, str | None]]:
        """``kept`` without a binding unit the cut split — the unit goes whole.

        The members of a unit are adjacent in the order (same tier, same rank,
        registered together), so popping from the end removes it whole.
        """
        cut_unit = kept[-1][2] if kept else None
        if cut_unit is None or all(unit != cut_unit for _w, _t, unit in cut):
            return kept
        while kept and kept[-1][2] == cut_unit:
            kept.pop()
        return kept

    @staticmethod
    def _compose(
        rows: list[_Row],
        ranking: Sequence[str] | None,
        top_k: int,
    ) -> tuple[list[ReactToolWrapper], list[int], list[str | None], set[str], list[str]]:
        """Order the resolved tools: priority, family coverage, semantic top-K, the rest.

        Priority tools (the detected domains' agents) come first, in
        registration order. Then every OTHER family keeps its
        ``CATALOGUE_DOMAIN_COVERAGE_TOP_N`` best-ranked tools — registration
        order when no ranking exists — so a family the router did not name
        stays reachable through its most relevant doors; an expanded user MCP
        server keeps its delegation door beside them, on no seat of its own and
        ranked as its best tool, because it is the one affordance for what its
        individual tools cannot express. Then, with a ranking, the first
        ``top_k`` of it; what remains
        is dropped by relevance. Without a ranking nothing is dropped and the
        registration order stands: the tiers alone decide who survives the cap.
        A binding unit ranks as its best member and holds one seat, so it
        lands whole in whichever tier reaches it.

        Args:
            rows: The resolved tools, in registration order.
            ranking: Manifest names, most relevant first — None when relevance is off.
            top_k: How many of the ranking to bind.

        Returns:
            ``(kept, tiers, units, kept_manifest_names, dropped_names)`` — a
            tier per kept tool (0 priority, 1 coverage, 2 the rest) so the
            cap's stable sort keeps this order whatever the binding order, and
            the binding unit of each so the cap never cuts inside one.
        """
        rank = ReactToolSelector._ranker(rows, ranking)
        priority, coverage = ReactToolSelector._tiered(rows, rank)
        tier_of = {id(row.tool): 0 for row in priority}
        tier_of.update({id(row.tool): 1 for row in coverage})
        if ranking is None:
            return (
                [row.tool for row in rows],
                [tier_of.get(id(row.tool), 2) for row in rows],
                [row.unit for row in rows],
                {row.name for row in rows},
                [],
            )
        tail, dropped = ReactToolSelector._semantic_tail(rows, set(tier_of), rank, top_k)
        kept = priority + coverage + tail
        tiers = [0] * len(priority) + [1] * len(coverage) + [2] * len(tail)
        units = [row.unit for row in kept]
        return [row.tool for row in kept], tiers, units, {row.name for row in kept}, dropped

    @staticmethod
    def _ranker(rows: list[_Row], ranking: Sequence[str] | None) -> Callable[[_Row], int]:
        """The rank of a row in the turn's order — unranked rows beyond every ranked one.

        A delegation door has no vector of its own: it ranks as the best tool
        behind it, so it sits beside its family in every order — the coverage
        sort and the cap's — rather than last among the unscored. A binding
        unit's members all rank as the unit's best member, for the same reason:
        one affordance, one place in every order.
        """
        rank_of = {name: index for index, name in enumerate(ranking or ())}
        beyond = len(rows) + len(rank_of)
        family_best: dict[str, int] = {}
        unit_best: dict[str, int] = {}
        for row in rows:
            if not row.door:
                own = rank_of.get(row.name, beyond)
                family_best[row.family] = min(own, family_best.get(row.family, beyond))
                if row.unit is not None:
                    unit_best[row.unit] = min(own, unit_best.get(row.unit, beyond))

        def rank(row: _Row) -> int:
            if row.door:
                return family_best.get(row.family, beyond)
            if row.unit is not None:
                return unit_best.get(row.unit, beyond)
            return rank_of.get(row.name, beyond)

        return rank

    @staticmethod
    def _tiered(rows: list[_Row], rank: Callable[[_Row], int]) -> tuple[list[_Row], list[_Row]]:
        """The priority rows (registration order) and the family coverage (by rank).

        Coverage keeps, per family outside the detected domains, its
        ``CATALOGUE_DOMAIN_COVERAGE_TOP_N`` best-ranked seats and, beside them,
        its delegation door when the family is an expanded user MCP server. A
        binding unit is ONE seat: its members sit together or not at all.
        """
        priority = [row for row in rows if row.priority]
        by_family: dict[str, list[_Row]] = {}
        for row in rows:
            if not row.priority:
                by_family.setdefault(row.family, []).append(row)
        coverage: list[_Row] = []
        for members in by_family.values():
            doors = [row for row in members if row.door]
            seats = ReactToolSelector._seats(members, rank)
            coverage.extend(doors)
            for seat in seats[:CATALOGUE_DOMAIN_COVERAGE_TOP_N]:
                coverage.extend(seat)
        coverage.sort(key=rank)
        return priority, coverage

    @staticmethod
    def _seats(members: list[_Row], rank: Callable[[_Row], int]) -> list[list[_Row]]:
        """The seats a family competes with, by rank: a unit's members on one seat."""
        seats: list[list[_Row]] = []
        seat_of_unit: dict[str, list[_Row]] = {}
        for row in members:
            if row.door:
                continue
            if row.unit is None:
                seats.append([row])
                continue
            seat = seat_of_unit.get(row.unit)
            if seat is None:
                seat = seat_of_unit[row.unit] = []
                seats.append(seat)
            seat.append(row)
        return sorted(seats, key=lambda seat: rank(seat[0]))

    @staticmethod
    def _semantic_tail(
        rows: list[_Row], placed: set[int], rank: Callable[[_Row], int], top_k: int
    ) -> tuple[list[_Row], list[str]]:
        """The first ``top_k`` of the ranking among the rows not yet placed, and the dropped names."""
        remaining = [row for row in rows if id(row.tool) not in placed]
        tail = sorted((row for row in remaining if rank(row) < top_k), key=rank)
        kept = {id(row.tool) for row in tail}
        dropped = [row.name for row in remaining if id(row.tool) not in kept]
        return tail, dropped

    @staticmethod
    def _domain_priority_agents(intelligence: DetectedDomains | None) -> set[str]:
        """Resolve the agents owning the detected domains via DOMAIN_REGISTRY.

        Their tools get priority to survive the ``react_agent_max_tools`` cap.
        Unknown domains resolve to no agents (no priority), never an error.

        Args:
            intelligence: Query intelligence carrying the detected domains.

        Returns:
            Set of agent names (e.g. ``{"event_agent"}``); empty when there is
            no intelligence or no detected domain.
        """
        if intelligence is None or not getattr(intelligence, "domains", None):
            return set()

        from src.domains.agents.registry.domain_taxonomy import get_domain_config

        agents: set[str] = set()
        for domain in intelligence.domains:
            config = get_domain_config(domain)
            if config is not None:
                agents.update(config.agent_names)
        return agents

    @staticmethod
    def _expand_iterative_user_mcp(
        manifest: Any,
    ) -> list[tuple[str, BaseTool, bool]] | None:
        """Expand an iterative user MCP task manifest into its individual tools.

        Iterative user MCP servers expose a single opaque ``mcp_user_{id}_task``
        manifest to the planner, while their individual tools live in the
        per-request ``user_mcp_tools_ctx``. In ReAct mode the individual tools are
        surfaced directly (their descriptions let the LLM pick them), except for
        MCP App servers, which keep the task tool for the dedicated app workflow.

        Args:
            manifest: The candidate tool manifest being processed by ``select``.

        Returns:
            A list of ``(tool_name, instance, hitl_required)`` for the server's
            individual tools, or ``None`` when expansion is disabled by feature
            flag, when the manifest is not an iterative user MCP task tool, when
            the server is an MCP App, or when no individual tools are available
            (all of which fall back to normal single-manifest resolution).
        """
        if not settings.react_mcp_expand_iterative_enabled:
            return None

        tool_name = getattr(manifest, "name", "")
        if not (
            tool_name.startswith(f"{MCP_USER_TOOL_NAME_PREFIX}_")
            and tool_name.endswith(MCP_ITERATIVE_TASK_SUFFIX)
        ):
            return None

        user_ctx = user_mcp_tools_ctx.get()
        if user_ctx is None:
            return None

        # Strip the "_task" suffix to get the per-server instance-name prefix.
        prefix = tool_name[: -len(MCP_ITERATIVE_TASK_SUFFIX)]
        individual: list[tuple[str, BaseTool]] = []
        is_app_server = False
        for name, instance in user_ctx.tool_instances.items():
            if name == tool_name or not name.startswith(f"{prefix}_"):
                continue
            if getattr(instance, "app_resource_uri", None):
                is_app_server = True
            individual.append((name, instance))

        # No hidden individual tools, or an MCP App server → keep the task tool
        # (return None routes back to the normal single-manifest resolution).
        if not individual or is_app_server:
            return None

        permissions = getattr(manifest, "permissions", None)
        server_hitl = bool(permissions and permissions.hitl_required)
        # The server setting is per SERVER; a destructive tool is a per TOOL
        # fact. Without this, turning confirmation off for a mostly read-only
        # server also turns it off for the few tools that delete something.
        return [
            (
                name,
                instance,
                server_hitl or declares_destructive_tool(getattr(instance, "annotations", None)),
            )
            for name, instance in individual
        ]
