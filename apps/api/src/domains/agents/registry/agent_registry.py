"""
Agent Registry - Centralized Agent Management.

Provides a centralized registry for managing LangGraph agents with:
- Automatic checkpointer injection (shared across all agents)
- Automatic store injection (shared context store)
- Lazy initialization (build on first access)
- Singleton pattern (one registry per application)
- Thread-safe registration and retrieval

This pattern follows LangGraph v1.0 best practices for multi-agent systems
where agents share a common checkpointer and store for state persistence
and context management.

Architecture:
    Application Level:
        AgentService → AgentRegistry (singleton)
                            ↓
                    Checkpointer (PostgreSQL)
                    Store (InMemory/Redis)
                            ↓
            ┌───────────────┼───────────────┐
            ↓               ↓               ↓
    contact_agent    email_agent    event_agent
        (subgraph)      (subgraph)      (subgraph)

Usage:
    # Initialize registry once at app startup
    registry = AgentRegistry(
        checkpointer=postgres_checkpointer,
        store=in_memory_store
    )

    # Register agent builders (lazy)
    registry.register_agent("contact_agent", build_contact_agent)
    registry.register_agent("email_agent", build_email_agent)

    # Retrieve compiled agent (auto-injects deps)
    agent = registry.get_agent("contact_agent")

    # Agent can be used in graph nodes
    async def contact_agent_node(state, config):
        result = await agent.ainvoke(state, config)
        return {"messages": result["messages"], ...}

Compliance: LangGraph v1.0 + LangChain v1.0 best practices
"""

import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from src.core.config import get_settings
from src.core.constants import (
    AGENT_REGISTRY_CACHE_TTL,
    AGENT_REGISTRY_FILTERED_CACHE_TTL,
)
from src.core.field_names import FIELD_PARAMETERS
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    planner_domain_filtering_cache_hits,
)

from .catalogue import (
    AgentManifest,
    AgentManifestAlreadyRegistered,
    AgentManifestNotFound,
    ToolManifest,
    ToolManifestAlreadyRegistered,
    ToolManifestNotFound,
)
from .domain_taxonomy import DOMAIN_REGISTRY, is_mcp_domain

logger = get_logger(__name__)


class AgentRegistryError(Exception):
    """Raised when agent registry operations fail."""

    pass


class AgentNotFoundError(AgentRegistryError):
    """Raised when requested agent is not registered."""

    pass


class AgentAlreadyRegisteredError(AgentRegistryError):
    """Raised when attempting to register an agent that already exists."""

    pass


class AgentRegistry:
    """
    Centralized registry for LangGraph agents with dependency injection.

    This class manages the lifecycle of agents in a multi-agent system,
    providing:
    - Centralized agent registration and retrieval
    - Automatic checkpointer injection (shared PostgreSQL persistence)
    - Automatic store injection (shared context store)
    - Lazy initialization (agents built on first access)
    - Thread-safe operations (for concurrent requests)

    Pattern: Registry + Factory with Dependency Injection

    Attributes:
        _checkpointer: Shared checkpointer for all agents (PostgreSQL)
        _store: Shared store for context management (InMemory/Redis)
        _builders: Registry of agent builder functions (lazy)
        _agents: Cache of compiled agents (built on first access)
        _lock: Thread lock for safe concurrent access

    Example:
        >>> # Startup
        >>> registry = AgentRegistry(
        ...     checkpointer=postgres_checkpointer,
        ...     store=in_memory_store
        ... )
        >>> registry.register_agent("contact_agent", build_contact_agent)
        >>> registry.register_agent("email_agent", build_email_agent)
        >>>
        >>> # Runtime (in AgentService)
        >>> contact_agent = registry.get_agent("contact_agent")
        >>> result = await contact_agent.ainvoke(state, config)
    """

    def __init__(self, checkpointer: Any | None = None, store: Any | None = None) -> None:
        """
        Initialize agent registry with shared dependencies.

        Args:
            checkpointer: Shared checkpointer for state persistence (e.g., PostgresCheckpointer).
                         If None, agents will not persist state between runs.
            store: Shared store for context management (e.g., InMemoryStore, RedisStore).
                   If None, context tools will not have access to shared state.

        Note:
            Checkpointer and store are optional but highly recommended for production.
            Without them:
            - No state persistence (conversations lost on restart)
            - No context sharing between agents
            - HITL interrupts will not persist
        """
        self._checkpointer = checkpointer
        self._store = store
        self._builders: dict[str, Callable[[], Any]] = {}
        self._agents: dict[str, Any] = {}
        self._lock = threading.RLock()

        # Catalogue manifests (Phase 1 - Planner)
        self._tool_manifests: dict[str, ToolManifest] = {}
        self._agent_manifests: dict[str, AgentManifest] = {}
        self._catalogue_lock = threading.RLock()

        # Cache for export_for_prompt() - Performance optimization (Phase 2)
        # Avoids rebuilding full catalogue export on every planner invocation (50-100ms saved)
        self._prompt_export_cache: dict[str, Any] | None = None
        self._cache_timestamp: float | None = None
        self._cache_ttl_seconds: float = float(AGENT_REGISTRY_CACHE_TTL)

        # Domain indexing for dynamic filtering (Phase 3 - Multi-Domain Architecture)
        # Maps domain names to agents and tools for fast filtered lookups
        self._domain_to_agents: dict[str, list[str]] = {}
        self._domain_to_tools: dict[str, list[str]] = {}
        # Filtered cache: key = frozenset of domains, value = filtered catalogue
        # Example: frozenset({"contacts", "email"}) -> {agents: [...], tools: [...]}
        self._filtered_cache: dict[str, dict[str, Any]] = {}
        self._filtered_cache_ttl: float = float(AGENT_REGISTRY_FILTERED_CACHE_TTL)

        # Tool instances for semantic architecture (LLM-Native Phase 5)
        # Maps tool names to actual LangChain StructuredTool instances
        # Used by tool_executor_node to invoke tools directly
        self._tool_instances: dict[str, Any] = {}
        self._tool_instances_lock = threading.RLock()

        logger.info(
            "agent_registry_initialized",
            has_checkpointer=checkpointer is not None,
            has_store=store is not None,
        )

    def register_agent(self, name: str, builder: Callable[[], Any], override: bool = False) -> None:
        """
        Register an agent builder function.

        The builder function will be called lazily on first access via get_agent().
        This allows for efficient startup (agents built only when needed).

        Args:
            name: Unique agent identifier (e.g., "contact_agent", "email_agent").
            builder: Callable that returns a compiled agent (no arguments).
                    Should return result of build_generic_agent() or similar.
            override: If True, allows overriding existing registration (default: False).

        Raises:
            AgentAlreadyRegisteredError: If agent already registered and override=False.
            ValueError: If name or builder is invalid.

        Example:
            >>> from src.domains.agents.graphs import build_contact_agent
            >>> registry.register_agent("contact_agent", build_contact_agent)
        """
        if not name or not isinstance(name, str):
            raise ValueError(f"Invalid agent name: {name} (must be non-empty string)")

        if not callable(builder):
            raise ValueError(f"Invalid builder for agent '{name}': must be callable")

        with self._lock:
            if name in self._builders and not override:
                raise AgentAlreadyRegisteredError(
                    f"Agent '{name}' is already registered. "
                    f"Use override=True to replace existing registration."
                )

            self._builders[name] = builder

            # Clear cached agent if overriding
            if override and name in self._agents:
                del self._agents[name]
                logger.info("agent_cache_cleared", agent_name=name, reason="override")

            logger.info(
                "agent_registered",
                agent_name=name,
                builder_name=builder.__name__ if hasattr(builder, "__name__") else "lambda",
                override=override,
            )

    def get_agent(self, name: str) -> Any:
        """
        Retrieve a compiled agent by name (lazy initialization).

        On first access:
        1. Calls the registered builder function
        2. Injects checkpointer and store (if available)
        3. Caches the result for subsequent calls

        On subsequent access:
        - Returns cached agent (no rebuild)

        Args:
            name: Agent identifier (must be registered via register_agent()).

        Returns:
            Compiled agent ready for .ainvoke() / .astream().

        Raises:
            AgentNotFoundError: If agent not registered.

        Example:
            >>> agent = registry.get_agent("contact_agent")
            >>> result = await agent.ainvoke(state, config)

        Note:
            The agent is built once and cached. If you need to rebuild
            (e.g., after config change), use rebuild_agent().
        """
        with self._lock:
            # Check if already built (cache hit)
            if name in self._agents:
                logger.debug("agent_cache_hit", agent_name=name)
                return self._agents[name]

            # Check if builder registered
            if name not in self._builders:
                available = list(self._builders.keys())
                raise AgentNotFoundError(
                    f"Agent '{name}' not found in registry. "
                    f"Available agents: {available}. "
                    f"Did you forget to call register_agent()?"
                )

            # Build agent (lazy initialization)
            logger.info("agent_building", agent_name=name)

            try:
                builder = self._builders[name]
                agent = builder()

                # Note: LangChain v1.0 agents don't have a .compile() method
                # The checkpointer and store are injected at the graph level,
                # not at the individual agent level. Agents are already compiled
                # by build_generic_agent() or create_agent().
                #
                # The checkpointer and store will be provided when the agent
                # is used within a parent graph via graph.compile(checkpointer=..., store=...)

                # Cache the built agent
                self._agents[name] = agent

                logger.info(
                    "agent_built_successfully",
                    agent_name=name,
                    agent_type=type(agent).__name__,
                )

                return agent

            except Exception as e:
                logger.error(
                    "agent_build_failed",
                    agent_name=name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise AgentRegistryError(
                    f"Failed to build agent '{name}': {type(e).__name__}: {e}"
                ) from e

    def rebuild_agent(self, name: str) -> Any:
        """
        Force rebuild of an agent (clears cache and rebuilds).

        Use this when:
        - Agent configuration has changed
        - Need to refresh agent after code changes
        - Troubleshooting agent issues

        Args:
            name: Agent identifier (must be registered).

        Returns:
            Newly built agent.

        Raises:
            AgentNotFoundError: If agent not registered.

        Example:
            >>> # After changing agent config
            >>> agent = registry.rebuild_agent("contact_agent")
        """
        with self._lock:
            # Clear cache
            if name in self._agents:
                del self._agents[name]
                logger.info("agent_cache_cleared", agent_name=name, reason="rebuild")

            # Rebuild via get_agent (lazy init)
            return self.get_agent(name)

    def list_agents(self) -> list[str]:
        """
        List all registered agents.

        Returns:
            List of agent names (registered via register_agent()).

        Example:
            >>> agents = registry.list_agents()
            >>> print(agents)
            ['contact_agent', 'email_agent', 'event_agent']
        """
        with self._lock:
            return list(self._builders.keys())

    def is_registered(self, name: str) -> bool:
        """
        Check if an agent is registered.

        Args:
            name: Agent identifier.

        Returns:
            True if agent is registered, False otherwise.

        Example:
            >>> if registry.is_registered("contact_agent"):
            ...     agent = registry.get_agent("contact_agent")
        """
        with self._lock:
            return name in self._builders

    def is_built(self, name: str) -> bool:
        """
        Check if an agent has been built (cached).

        Args:
            name: Agent identifier.

        Returns:
            True if agent is built and cached, False otherwise.

        Example:
            >>> if not registry.is_built("contact_agent"):
            ...     # First access, will trigger build
            ...     agent = registry.get_agent("contact_agent")
        """
        with self._lock:
            return name in self._agents

    def clear_cache(self) -> None:
        """
        Clear all cached agents (force rebuild on next access).

        Use this when:
        - Multiple agents need to be rebuilt
        - Cleanup during testing
        - Memory management (though agents are lightweight)

        Example:
            >>> # After major config change
            >>> registry.clear_cache()
            >>> # Next get_agent() will rebuild
        """
        with self._lock:
            count = len(self._agents)
            self._agents.clear()
            logger.info("agent_cache_cleared_all", count=count)

    # ========================================================================
    # Catalogue Manifest Management (Phase 1 - Planner)
    # ========================================================================

    def register_agent_manifest(self, manifest: AgentManifest, override: bool = False) -> None:
        """
        Register an agent manifest in the catalogue.

        Args:
            manifest: AgentManifest describing the agent
            override: If True, allows overriding existing manifest

        Raises:
            AgentManifestAlreadyRegistered: If manifest already exists and override=False

        Example:
            >>> manifest = AgentManifest(
            ...     name="contact_agent",
            ...     description="Agent for Google Contacts",
            ...     tools=["search_contacts_tool"],
            ...     version="1.0.0"
            ... )
            >>> registry.register_agent_manifest(manifest)
        """
        with self._catalogue_lock:
            if manifest.name in self._agent_manifests and not override:
                raise AgentManifestAlreadyRegistered(manifest.name)

            self._agent_manifests[manifest.name] = manifest

            # Invalidate cache since catalogue changed
            self._invalidate_prompt_cache()

            logger.info(
                "catalogue_agent_registered",
                agent=manifest.name,
                version=manifest.version,
                tool_count=len(manifest.tools),
                override=override,
            )

    def register_tool_manifest(self, manifest: ToolManifest, override: bool = False) -> None:
        """
        Register a tool manifest in the catalogue.

        Args:
            manifest: ToolManifest describing the tool
            override: If True, allows overriding existing manifest

        Raises:
            ToolManifestAlreadyRegistered: If manifest already exists and override=False

        Example:
            >>> manifest = ToolManifest(
            ...     name="search_contacts_tool",
            ...     agent="contact_agent",
            ...     description="Search Google Contacts",
            ...     parameters=[...],
            ...     cost=CostProfile(...),
            ...     permissions=PermissionProfile(...),
            ...     version="1.0.0"
            ... )
            >>> registry.register_tool_manifest(manifest)
        """
        with self._catalogue_lock:
            if manifest.name in self._tool_manifests and not override:
                raise ToolManifestAlreadyRegistered(manifest.name)

            # Log warning if agent manifest not registered yet
            if manifest.agent not in self._agent_manifests:
                logger.warning(
                    "catalogue_tool_orphan",
                    tool=manifest.name,
                    agent=manifest.agent,
                    message=f"Tool '{manifest.name}' registered before agent '{manifest.agent}'",
                )

            self._tool_manifests[manifest.name] = manifest

            # Invalidate cache since catalogue changed
            self._invalidate_prompt_cache()

            logger.info(
                "catalogue_tool_registered",
                tool=manifest.name,
                agent=manifest.agent,
                version=manifest.version,
                override=override,
            )

    def get_agent_manifest(self, name: str) -> AgentManifest:
        """
        Retrieve an agent manifest by name.

        Args:
            name: Agent name

        Returns:
            AgentManifest

        Raises:
            AgentManifestNotFound: If manifest not found

        Example:
            >>> manifest = registry.get_agent_manifest("contact_agent")
            >>> print(manifest.description)
        """
        with self._catalogue_lock:
            if name not in self._agent_manifests:
                raise AgentManifestNotFound(name)
            return self._agent_manifests[name]

    def get_tool_manifest(self, name: str) -> ToolManifest:
        """
        Retrieve a tool manifest by name.

        Args:
            name: Tool name

        Returns:
            ToolManifest

        Raises:
            ToolManifestNotFound: If manifest not found

        Example:
            >>> manifest = registry.get_tool_manifest("search_contacts_tool")
            >>> print(manifest.cost.est_tokens_in)
        """
        with self._catalogue_lock:
            if name not in self._tool_manifests:
                raise ToolManifestNotFound(name)
            return self._tool_manifests[name]

    # ========================================================================
    # Tool Instance Management (LLM-Native Semantic Architecture - Phase 5)
    # ========================================================================

    def register_tool_instance(self, name: str, tool_instance: Any, override: bool = False) -> None:
        """
        Register a tool instance (LangChain StructuredTool) for direct invocation.

        This is used by the semantic architecture's tool_executor_node to invoke
        tools directly without going through agent subgraphs.

        Args:
            name: Tool name (must match the manifest name)
            tool_instance: LangChain BaseTool/StructuredTool instance
            override: If True, allows overriding existing instance

        Raises:
            ValueError: If name is empty or tool_instance is None

        Example:
            >>> from src.domains.agents.tools.emails_tools import search_emails_tool
            >>> registry.register_tool_instance("search_emails_tool", search_emails_tool)
        """
        if not name:
            raise ValueError("Tool name cannot be empty")
        if tool_instance is None:
            raise ValueError(f"Tool instance for '{name}' cannot be None")

        with self._tool_instances_lock:
            if name in self._tool_instances and not override:
                logger.warning(
                    "tool_instance_already_registered",
                    tool_name=name,
                    message="Use override=True to replace",
                )
                return

            self._tool_instances[name] = tool_instance
            logger.info(
                "tool_instance_registered",
                tool_name=name,
                tool_type=type(tool_instance).__name__,
                override=override,
            )

    def get_tool_instance(self, name: str) -> Any | None:
        """
        Retrieve a tool instance by name.

        Used by tool_executor_node in the semantic architecture to invoke
        tools directly.

        Args:
            name: Tool name

        Returns:
            LangChain BaseTool/StructuredTool instance, or None if not found

        Example:
            >>> tool = registry.get_tool_instance("search_emails_tool")
            >>> if tool:
            ...     result = await tool.ainvoke({"query": "test"}, config=config)
        """
        with self._tool_instances_lock:
            return self._tool_instances.get(name)

    def list_tool_instances(self) -> list[str]:
        """
        List all registered tool instance names.

        Returns:
            List of tool names with registered instances
        """
        with self._tool_instances_lock:
            return list(self._tool_instances.keys())

    def list_agent_manifests(self) -> list[AgentManifest]:
        """
        List all registered agent manifests.

        Returns:
            List of AgentManifest

        Example:
            >>> manifests = registry.list_agent_manifests()
            >>> for m in manifests:
            ...     print(f"{m.name} v{m.version}")
        """
        with self._catalogue_lock:
            return list(self._agent_manifests.values())

    def list_tool_manifests(self, agent: str | None = None) -> list[ToolManifest]:
        """
        List tool manifests (optionally filtered by agent).

        Args:
            agent: If provided, only return tools for this agent

        Returns:
            List of ToolManifest

        Example:
            >>> # All tools
            >>> all_tools = registry.list_tool_manifests()
            >>> # Tools for contacts agent only
            >>> contacts_tools = registry.list_tool_manifests(agent="contact_agent")
        """
        with self._catalogue_lock:
            manifests = list(self._tool_manifests.values())
            if agent:
                manifests = [m for m in manifests if m.agent == agent]
            return manifests

    def export_catalogue(self) -> dict[str, Any]:
        """
        Export complete catalogue (for storage/backup).

        Returns:
            Dictionary with all agents and tools manifests

        Example:
            >>> catalogue = registry.export_catalogue()
            >>> print(f"Agents: {len(catalogue['agents'])}")
            >>> print(f"Tools: {len(catalogue['tools'])}")
        """
        with self._catalogue_lock:
            from datetime import UTC, datetime

            return {
                "agents": {name: asdict(m) for name, m in self._agent_manifests.items()},
                "tools": {name: asdict(m) for name, m in self._tool_manifests.items()},
                "exported_at": datetime.now(UTC).isoformat(),
                "version": "1.0.0",
            }

    def export_for_prompt(self) -> dict[str, Any]:
        """
        Export catalogue optimized for LLM planner prompt.

        Returns concise format suitable for prompt injection.
        Includes only essential info for plan generation.

        Performance: Cached for 1 hour to avoid rebuilding on every planner invocation (50-100ms saved).
        Cache is automatically invalidated when tools or agents are registered.

        Returns:
            Dictionary optimized for planner LLM

        Example:
            >>> prompt_data = registry.export_for_prompt()
            >>> # Use in planner prompt:
            >>> prompt = f"Available tools: {json.dumps(prompt_data)}"
        """
        # Check cache first (Performance optimization - Phase 2)
        current_time = time.time()
        if (
            self._prompt_export_cache is not None
            and self._cache_timestamp is not None
            and (current_time - self._cache_timestamp) < self._cache_ttl_seconds
        ):
            logger.debug("catalogue_export_cache_hit")
            return self._prompt_export_cache

        logger.debug("catalogue_export_cache_miss")

        # Cache miss - rebuild catalogue export
        with self._catalogue_lock:
            agents_data: list[dict[str, Any]] = []

            for agent_manifest in self._agent_manifests.values():
                tools_data = []

                for tool_name in agent_manifest.tools:
                    if tool_name in self._tool_manifests:
                        tm = self._tool_manifests[tool_name]

                        # Format parameters for prompt (include semantic_type for LLM reasoning)
                        params_data = []
                        for p in tm.parameters:
                            param_dict = {
                                "name": p.name,
                                "type": p.type,
                                "required": p.required,
                                "description": p.description,
                            }
                            # Include semantic_type if defined (enables cross-domain reasoning)
                            # Ex: destination with semantic_type="physical_address" tells LLM
                            # it needs an address, not a person name
                            if hasattr(p, "semantic_type") and p.semantic_type:
                                param_dict["semantic_type"] = p.semantic_type
                            params_data.append(param_dict)

                        tool_data = {
                            "name": tm.name,
                            "description": tm.description,
                            FIELD_PARAMETERS: params_data,
                            "cost_estimate": {
                                "tokens": tm.cost.est_tokens_in + tm.cost.est_tokens_out,
                                "latency_ms": tm.cost.est_latency_ms,
                            },
                            "requires_approval": tm.permissions.hitl_required,
                        }

                        # Include response_schema if defined (for LLM planner guidance)
                        # Support both new format (response_schema) and old format (outputs)
                        if hasattr(tm, "response_schema") and tm.response_schema:
                            tool_data["response_schema"] = tm.response_schema
                        elif hasattr(tm, "outputs") and tm.outputs:
                            # Convert OutputFieldSchema list to simple dict for planner
                            outputs_dict = {}
                            # Track semantic types for cross-domain reasoning
                            # Maps semantic_type -> list of output paths that provide it
                            semantic_outputs: dict[str, list[str]] = {}

                            for output in tm.outputs:
                                # Extract field name from path (e.g. "contacts[].name" -> "contacts")
                                field = output.path.split("[")[0].split(".")[0]
                                if field not in outputs_dict:
                                    outputs_dict[field] = {
                                        "type": output.type,
                                        "description": output.description,
                                    }
                                # Track semantic_type outputs for cross-domain reasoning
                                # Ex: contacts provides "physical_address" at addresses[].formattedValue
                                if hasattr(output, "semantic_type") and output.semantic_type:
                                    if output.semantic_type not in semantic_outputs:
                                        semantic_outputs[output.semantic_type] = []
                                    semantic_outputs[output.semantic_type].append(output.path)

                            tool_data["response_fields"] = outputs_dict
                            # Include semantic_outputs for LLM cross-domain reasoning
                            # Ex: {"physical_address": ["contacts[].addresses[].formattedValue"]}
                            if semantic_outputs:
                                tool_data["provides_semantic_types"] = semantic_outputs

                        # Include field_mappings if defined (for parameter normalization)
                        if hasattr(tm, "field_mappings") and tm.field_mappings:
                            tool_data["field_mappings"] = tm.field_mappings

                        # Include reference_examples if defined (for Planner guidance)
                        # This helps the Planner generate correct $steps references
                        if hasattr(tm, "reference_examples") and tm.reference_examples:
                            tool_data["reference_examples"] = tm.reference_examples

                        tools_data.append(tool_data)

                agents_data.append(
                    {
                        "agent": agent_manifest.name,
                        "tools": tools_data,
                    }
                )

            # Build reference guide at top level for planner visibility
            # This extracts reference_examples from buried tool definitions
            # to make them prominent for LLM plan generation
            reference_guide: dict[str, list[str]] = {}
            for agent_data in agents_data:
                tools_list = agent_data.get("tools", [])
                if isinstance(tools_list, list):
                    for tool_data in tools_list:
                        if isinstance(tool_data, dict):
                            tool_name = str(tool_data.get("name", ""))
                            ref_examples = tool_data.get("reference_examples", [])
                            if ref_examples and isinstance(ref_examples, list):
                                reference_guide[tool_name] = [str(ex) for ex in ref_examples]

            # TODO: Move these to settings
            from src.core.config import get_settings

            settings = get_settings()

            result = {
                # CRITICAL: Reference guide at TOP LEVEL for planner visibility
                # This is the PRIMARY source for valid $steps.STEP_ID.PATH references
                "reference_guide": reference_guide,
                "agents": agents_data,
                "max_plan_cost_usd": getattr(settings, "planner_max_cost_usd", 10.0),
                "max_plan_steps": getattr(settings, "planner_max_steps", 50),
            }

            # Update cache (Performance optimization - Phase 2)
            self._prompt_export_cache = result
            self._cache_timestamp = current_time

            return result

    def export_for_prompt_filtered(
        self,
        domains: list[str] | None = None,
        max_tools_per_domain: int = 10,
        include_context_utilities: bool = True,
        tool_strategy: str = "full",
    ) -> dict[str, Any]:
        """
        Export catalogue optimized for LLM planner prompt with domain filtering.

        This method enables dynamic loading of manifests based on detected domains,
        preventing prompt explosion in multi-domain systems (10+ domains).

        Architecture Pattern: Hybrid (Registry Metadata + LLM Reasoning)
        - Router detects relevant domains from user query
        - SemanticIntentDetector determines tool strategy from query
        - Planner loads ONLY tools from detected domains with strategy filtering
        - Token reduction: 90% (40K → 4K tokens for single-domain queries)

        Args:
            domains: List of domain identifiers to include (e.g., ["contacts", "email"]).
                    If None, returns full catalogue (backward compatible with export_for_prompt()).
            max_tools_per_domain: Maximum tools per domain (performance tuning).
                                 Default: 10 tools per domain.
            include_context_utilities: Whether to include context/query utility tools.
                                      Default: True. Set False for first message in conversation.
            tool_strategy: Tool loading strategy based on SemanticIntentDetector.
                          - "full": All tools for domain (default, ~6 tools/domain)
                          - "send": BASE + send only (emails, notifications, reminders)
                          - "create": BASE + create only (events, contacts, tasks)
                          - "update": BASE + update + details (need to see before edit)
                          - "delete": BASE + delete + details (need to confirm before delete)
                          - "detail": BASE + details + readonly (for detail queries)
                          - "search": BASE + readonly (for search queries)
                          - "list": BASE + readonly (for list queries)

                          BASE always includes: search, list, system tools.
                          Token savings: ~70% for all strategies vs "full".

        Returns:
            Dictionary optimized for planner LLM with filtered catalogue.
            Format matches export_for_prompt() but includes only requested domains.

        Performance:
            - Filtered cache: 5 min TTL (keyed by domain set)
            - Cache hit: O(1) lookup
            - Cache miss: O(n) where n = tools in requested domains
            - Token savings: 80-90% for single/dual-domain queries

        Example:
            >>> # Single domain (contacts)
            >>> filtered = registry.export_for_prompt_filtered(domains=["contacts"])
            >>> # Result: ~4K tokens (3 tools from contacts)
            >>>
            >>> # Multi-domain (contacts + email)
            >>> filtered = registry.export_for_prompt_filtered(
            ...     domains=["contacts", "email"],
            ...     max_tools_per_domain=5
            ... )
            >>> # Result: ~8K tokens (5 tools from each domain)
            >>>
            >>> # Backward compatible: no filtering
            >>> full = registry.export_for_prompt_filtered(domains=None)
            >>> # Result: Same as export_for_prompt() (all tools)

        Design Notes:
            - Backward compatible: domains=None → export_for_prompt()
            - Cache key: frozenset of sorted domain names (order-independent)
            - Includes metadata: domains_loaded, total_tools, filtering_applied
            - Generic: Works for any domain in DOMAIN_REGISTRY
            - Thread-safe: Uses catalogue_lock

        Best Practices (LangGraph v1.0):
            - Domain detection in Router node (lightweight LLM call)
            - Dynamic loading in Planner node (filtered catalogue)
            - Fallback: Load full catalogue if confidence < 0.7

        Migration from export_for_prompt():
            ```python
            # Old (Phase 2)
            catalogue = registry.export_for_prompt()  # All tools loaded

            # New (Phase 3 - Domain Filtering)
            detected_domains = router_output.domains  # From router
            if detected_domains:
                catalogue = registry.export_for_prompt_filtered(
                    domains=detected_domains
                )
            else:
                catalogue = registry.export_for_prompt()  # Fallback
            ```
        """
        # Backward compatible: domains=None → full catalogue
        if domains is None:
            logger.debug("catalogue_export_filtered_none_fallback")
            return self.export_for_prompt()

        # Check filtered cache (keyed by domain set + context flag + strategy)
        ctx_suffix = "_ctx" if include_context_utilities else "_noctx"
        strategy_suffix = f"_{tool_strategy}"
        cache_key = (
            "_".join(sorted(domains)) + ctx_suffix + strategy_suffix
        )  # Order-independent key
        current_time = time.time()

        if cache_key in self._filtered_cache:
            cached_entry = self._filtered_cache[cache_key]
            cache_time = cached_entry.get("_cache_timestamp", 0)

            if (current_time - cache_time) < self._filtered_cache_ttl:
                # Metric: Cache hit
                planner_domain_filtering_cache_hits.labels(
                    cache_status="hit", domains=cache_key
                ).inc()

                logger.debug(
                    "catalogue_filtered_cache_hit",
                    domains=domains,
                    cache_age_seconds=int(current_time - cache_time),
                )
                # Return copy without internal metadata
                result = {k: v for k, v in cached_entry.items() if not k.startswith("_")}
                return result

        # Metric: Cache miss
        planner_domain_filtering_cache_hits.labels(cache_status="miss", domains=cache_key).inc()

        logger.debug("catalogue_filtered_cache_miss", domains=domains)

        # Cache miss - build filtered catalogue
        with self._catalogue_lock:
            agents_data = []
            total_tools = 0

            # Phase B Token Optimization (2025-12-08):
            # Cross-domain utilities are now CONDITIONAL based on include_context_utilities.
            # - context: resolve_reference, get_context_list - ONLY needed for multi-turn
            # - query: local_query_engine_tool - ONLY needed for GROUP/filter operations
            # When include_context_utilities=False, we save ~6 tools (~2K tokens)
            domains_to_load = list(domains)  # Make a copy

            if include_context_utilities:
                cross_domain_utilities = ["context", "query"]
                for utility_domain in cross_domain_utilities:
                    if utility_domain not in domains_to_load:
                        domains_to_load.append(utility_domain)

                logger.debug(
                    "catalogue_filtered_cross_domain_auto_included",
                    requested_domains=domains,
                    loaded_domains=domains_to_load,
                    auto_included=[d for d in cross_domain_utilities if d not in domains],
                    reason="Cross-domain utilities included (has_active_context=True)",
                )
            else:
                logger.debug(
                    "catalogue_filtered_cross_domain_skipped",
                    requested_domains=domains,
                    loaded_domains=domains_to_load,
                    reason="Cross-domain utilities skipped (no active context)",
                )

            for domain in domains_to_load:
                # Get agents for this domain
                agent_names = self._domain_to_agents.get(domain, [])

                if not agent_names:
                    logger.warning(
                        "catalogue_filtered_domain_not_found",
                        domain=domain,
                        message=f"Domain '{domain}' has no registered agents. "
                        f"Available domains: {list(self._domain_to_agents.keys())}",
                    )
                    continue

                for agent_name in agent_names:
                    if agent_name not in self._agent_manifests:
                        logger.warning(
                            "catalogue_filtered_agent_manifest_missing",
                            agent=agent_name,
                            domain=domain,
                        )
                        continue

                    agent_manifest = self._agent_manifests[agent_name]
                    tools_data = []

                    # Get tools for this agent (with limit)
                    tool_names = agent_manifest.tools[:max_tools_per_domain]

                    # =================================================================
                    # SEMANTIC INTENT-BASED FILTERING (2025-12-25)
                    # =================================================================
                    # Replaces keyword-based filtering with category-based approach.
                    # Uses tool_category from manifest (or inferred from tool name).
                    #
                    # Strategy mapping (from SemanticIntentDetector):
                    # - "full": All tools (no filtering)
                    # - "action": BASE + CRUD + send tools
                    # - "detail": BASE + details + readonly tools
                    # - "search": BASE only (search + list)
                    # - "list": BASE only (search + list)
                    #
                    # BASE always includes: search, list, system tools
                    # =================================================================
                    from src.domains.agents.registry.catalogue import (
                        SYSTEM_TOOL_NAMES,
                        get_tool_category,
                    )

                    if tool_strategy != "full":
                        filtered_tool_names = []

                        # Define which categories to include based on strategy
                        # BASE categories (always included)
                        base_categories = {"search", "list", "system"}

                        # =============================================================
                        # GRANULAR ACTION SUB-STRATEGIES (2025-12-28)
                        # =============================================================
                        # Each action type loads only its specific tool category.
                        # Token savings: ~70% vs old "action" strategy that loaded ALL.
                        #
                        # Example: "send email" → only "send" category (~2 tools)
                        #          vs old "action" → all CRUD tools (~10 tools)
                        # =============================================================
                        if tool_strategy == "send":
                            # Send: BASE + send only (emails, notifications, reminders)
                            allowed_categories = base_categories | {"send"}
                        elif tool_strategy == "create":
                            # Create: BASE + create only (events, contacts, tasks)
                            allowed_categories = base_categories | {"create"}
                        elif tool_strategy == "update":
                            # Update: BASE + update + details (need to see before edit)
                            allowed_categories = base_categories | {"update", "details"}
                        elif tool_strategy == "delete":
                            # Delete: BASE + delete + details (need to confirm before delete)
                            allowed_categories = base_categories | {"delete", "details"}
                        elif tool_strategy == "detail":
                            # Detail: BASE + details + readonly
                            allowed_categories = base_categories | {"details", "readonly"}
                        elif tool_strategy in ("search", "list"):
                            # Search/List: BASE only
                            allowed_categories = base_categories | {"readonly"}
                        else:
                            # Unknown strategy (including legacy "action"): default to all
                            allowed_categories = {
                                "search",
                                "list",
                                "details",
                                "create",
                                "update",
                                "delete",
                                "send",
                                "readonly",
                                "system",
                            }

                        for tn in tool_names:
                            # System tools always included
                            if tn in SYSTEM_TOOL_NAMES:
                                filtered_tool_names.append(tn)
                                continue

                            # Get tool manifest and category
                            if tn in self._tool_manifests:
                                tm = self._tool_manifests[tn]
                                category = get_tool_category(tm)

                                if category in allowed_categories:
                                    filtered_tool_names.append(tn)

                        tool_names = filtered_tool_names

                        logger.debug(
                            "catalogue_tools_filtered_by_strategy",
                            strategy=tool_strategy,
                            agent=agent_name,
                            original_count=len(agent_manifest.tools[:max_tools_per_domain]),
                            filtered_count=len(filtered_tool_names),
                            allowed_categories=list(allowed_categories),
                        )

                    for tool_name in tool_names:
                        if tool_name not in self._tool_manifests:
                            logger.warning(
                                "catalogue_filtered_tool_manifest_missing",
                                tool=tool_name,
                                agent=agent_name,
                            )
                            continue

                        tm = self._tool_manifests[tool_name]

                        # Format parameters for prompt (same as export_for_prompt)
                        # Include semantic_type for cross-domain reasoning
                        params_data = []
                        for p in tm.parameters:
                            param_dict = {
                                "name": p.name,
                                "type": p.type,
                                "required": p.required,
                                "description": p.description,
                            }
                            # Include semantic_type if defined (enables cross-domain reasoning)
                            if hasattr(p, "semantic_type") and p.semantic_type:
                                param_dict["semantic_type"] = p.semantic_type
                            params_data.append(param_dict)

                        tool_data = {
                            "name": tm.name,
                            "description": tm.description,
                            FIELD_PARAMETERS: params_data,
                            "cost_estimate": {
                                "tokens": tm.cost.est_tokens_in + tm.cost.est_tokens_out,
                                "latency_ms": tm.cost.est_latency_ms,
                            },
                            "requires_approval": tm.permissions.hitl_required,
                        }

                        # Include response_schema if defined (same as export_for_prompt)
                        if hasattr(tm, "response_schema") and tm.response_schema:
                            tool_data["response_schema"] = tm.response_schema
                        elif hasattr(tm, "outputs") and tm.outputs:
                            outputs_dict = {}
                            # Track semantic types for cross-domain reasoning
                            semantic_outputs: dict[str, list[str]] = {}

                            for output in tm.outputs:
                                field = output.path.split("[")[0].split(".")[0]
                                if field not in outputs_dict:
                                    outputs_dict[field] = {
                                        "type": output.type,
                                        "description": output.description,
                                    }
                                # Track semantic_type outputs for cross-domain reasoning
                                if hasattr(output, "semantic_type") and output.semantic_type:
                                    if output.semantic_type not in semantic_outputs:
                                        semantic_outputs[output.semantic_type] = []
                                    semantic_outputs[output.semantic_type].append(output.path)

                            tool_data["response_fields"] = outputs_dict
                            # Include semantic_outputs for LLM cross-domain reasoning
                            if semantic_outputs:
                                tool_data["provides_semantic_types"] = semantic_outputs

                        # Include field_mappings if defined
                        if hasattr(tm, "field_mappings") and tm.field_mappings:
                            tool_data["field_mappings"] = tm.field_mappings

                        # Include reference_examples if defined (for Planner guidance)
                        if hasattr(tm, "reference_examples") and tm.reference_examples:
                            tool_data["reference_examples"] = tm.reference_examples

                        tools_data.append(tool_data)
                        total_tools += 1

                    agents_data.append(
                        {
                            "agent": agent_manifest.name,
                            "domain": domain,
                            "tools": tools_data,
                        }
                    )

            # Build reference guide at top level for planner visibility
            # Same pattern as export_for_prompt()
            reference_guide: dict[str, list[str]] = {}
            for agent_data in agents_data:
                tools_list = agent_data.get("tools", [])
                if isinstance(tools_list, list):
                    for tool_data in tools_list:
                        if isinstance(tool_data, dict):
                            tool_name = str(tool_data.get("name", ""))
                            ref_examples = tool_data.get("reference_examples", [])
                            if ref_examples and isinstance(ref_examples, list):
                                reference_guide[tool_name] = [str(ex) for ex in ref_examples]

            # Get settings (same as export_for_prompt)
            from src.core.config import get_settings

            settings = get_settings()

            result = {
                # CRITICAL: Reference guide at TOP LEVEL for planner visibility
                "reference_guide": reference_guide,
                "agents": agents_data,
                "domains_loaded": domains_to_load,  # Use actual loaded domains (includes context)
                "total_tools": total_tools,  # NEW: Metadata for monitoring
                "filtering_applied": True,  # NEW: Flag for observability
                "tool_strategy": tool_strategy,  # Phase C: Token optimization strategy
                "max_plan_cost_usd": getattr(
                    settings.planner_max_cost_usd, "planner_max_cost_usd", 50.0
                ),
                "max_plan_steps": getattr(settings.planner_max_steps, "planner_max_steps", 50),
            }

            # Cache result with timestamp
            cache_entry = {**result, "_cache_timestamp": current_time}
            self._filtered_cache[cache_key] = cache_entry

            logger.info(
                "catalogue_filtered_built",
                domains=domains,
                agents_count=len(agents_data),
                tools_count=total_tools,
                max_tools_per_domain=max_tools_per_domain,
                tool_strategy=tool_strategy,
            )

            return result

    def _invalidate_prompt_cache(self) -> None:
        """
        Invalidate the export_for_prompt() cache.

        Called automatically when tools or agents are registered to ensure
        fresh catalogue data on next export.

        Performance: This is a cheap operation (just setting to None), while
        cache hits save 50-100ms per planner invocation.
        """
        self._prompt_export_cache = None
        self._cache_timestamp = None
        logger.debug("catalogue_export_cache_invalidated")

    def _build_domain_index(self) -> None:
        """
        Build reverse index: domain -> agents -> tools.

        This index enables fast filtered lookups for dynamic domain loading.
        Called automatically after catalogue initialization.

        Architecture:
            - Extracts domain from agent name (e.g., "contact_agent" -> "contacts")
            - Cross-references with DOMAIN_REGISTRY for validation
            - Builds bidirectional mappings for O(1) lookups

        Example Index:
            _domain_to_agents = {
                "contacts": ["contact_agent"],
                "email": ["email_agent"],
            }
            _domain_to_tools = {
                "contacts": ["search_contacts_tool", "list_contacts_tool"],
                "email": ["send_email_tool", "search_emails_tool"],
            }

        Design Notes:
            - Generic extraction: agent_name.split("_")[0] -> domain
            - Falls back to full agent_name if no underscore
            - Validates against DOMAIN_REGISTRY (warns if mismatch)
            - Thread-safe via catalogue_lock

        Performance:
            - O(n) build time where n = number of agents + tools
            - O(1) lookup time via dict index
            - Called once at startup or when catalogue changes
        """
        with self._catalogue_lock:
            # Clear existing index
            self._domain_to_agents.clear()
            self._domain_to_tools.clear()
            self._filtered_cache.clear()  # Invalidate filtered cache

            # Build agent index
            for agent_name, agent_manifest in self._agent_manifests.items():
                # Extract domain from agent name
                # Convention: "{domain}_agent" -> domain
                # Examples: "contact_agent" -> "contacts", "email_agent" -> "email"
                domain = self._extract_domain_from_agent_name(agent_name)

                # Validate against DOMAIN_REGISTRY (skip warning for dynamic MCP domains)
                if domain not in DOMAIN_REGISTRY and not is_mcp_domain(domain):
                    logger.warning(
                        "domain_index_agent_unknown_domain",
                        agent=agent_name,
                        extracted_domain=domain,
                        message=f"Agent domain '{domain}' not in DOMAIN_REGISTRY. "
                        f"Add to domain_taxonomy.py for proper filtering.",
                    )
                    # Still index it (defensive programming)

                # Add agent to domain mapping
                if domain not in self._domain_to_agents:
                    self._domain_to_agents[domain] = []
                self._domain_to_agents[domain].append(agent_name)

                # Build tool index for this agent
                if domain not in self._domain_to_tools:
                    self._domain_to_tools[domain] = []

                for tool_name in agent_manifest.tools:
                    if tool_name in self._tool_manifests:
                        self._domain_to_tools[domain].append(tool_name)

            logger.info(
                "domain_index_built",
                domains=list(self._domain_to_agents.keys()),
                agents_count=sum(len(agents) for agents in self._domain_to_agents.values()),
                tools_count=sum(len(tools) for tools in self._domain_to_tools.values()),
            )

    def rebuild_domain_index(self) -> None:
        """
        Rebuild the domain → agents/tools index.

        Public wrapper for _build_domain_index(). Call after registering
        new agents or tools dynamically (e.g., MCP tools at startup).
        """
        self._build_domain_index()

    def _extract_domain_from_agent_name(self, agent_name: str) -> str:
        """
        Extract domain identifier from agent name.

        Convention: "{domain}_agent" -> domain

        Supports compound domains like "web_search_agent" -> "web_search"
        by checking DOMAIN_REGISTRY for longest matching prefix.
        Also supports dynamic MCP domains like "mcp_google_flights_agent"
        -> "mcp_google_flights" (not in static DOMAIN_REGISTRY).

        Args:
            agent_name: Full agent name (e.g., "contact_agent", "web_search_agent")

        Returns:
            Domain identifier (e.g., "contacts", "web_search", "mcp_google_flights")

        Examples:
            >>> self._extract_domain_from_agent_name("contact_agent")
            "contact"
            >>> self._extract_domain_from_agent_name("web_search_agent")
            "web_search"
            >>> self._extract_domain_from_agent_name("mcp_google_flights_agent")
            "mcp_google_flights"

        Design Notes:
            - Tries compound domains first (web_search before web)
            - Checks for dynamic MCP domains before shorter static matches
            - Validates against DOMAIN_REGISTRY for accuracy
            - Falls back to first word if no registry match
        """
        parts = agent_name.split("_")
        if len(parts) <= 1:
            # No underscore - return full name (defensive)
            logger.warning(
                "domain_extraction_no_underscore",
                agent=agent_name,
                message="Agent name has no underscore, using full name as domain",
            )
            return agent_name

        # Check for dynamic MCP domains first (not in static DOMAIN_REGISTRY).
        # Must be checked before the DOMAIN_REGISTRY loop, otherwise
        # "mcp_google_flights_agent" would match static "mcp" domain at i=1.
        candidate_full = "_".join(parts[:-1])
        if is_mcp_domain(candidate_full):
            return candidate_full

        # Try compound domains (longest to shortest prefix) in DOMAIN_REGISTRY
        # For "web_search_agent": try "web_search" first, then "web"
        for i in range(len(parts) - 1, 0, -1):
            candidate = "_".join(parts[:i])
            if candidate in DOMAIN_REGISTRY:
                return candidate

        # Fallback to first part (original behavior)
        return parts[0]

    # ========================================================================
    # Semantic Tool Selector (Router Enhancement)
    # ========================================================================

    async def initialize_semantic_tool_selector(self) -> None:
        """
        Initialize the SemanticToolSelector with tool manifests.

        Optional pre-warming method for the semantic tool selector.
        The selector is also lazily initialized by router_node when needed.

        Prerequisites:
            - Tool manifests must be registered before calling this method
            - OpenAI API key must be configured for embeddings

        Performance:
            - Embedding computation: ~100-500ms depending on tool count
            - Results are cached in the tool selector singleton

        Example:
            >>> # Optional pre-warming during app startup
            >>> await registry.initialize_semantic_tool_selector()
        """
        settings = get_settings()

        from src.domains.agents.services import SemanticToolSelector

        # Get tool manifests for initialization
        with self._catalogue_lock:
            tool_manifests = list(self._tool_manifests.values())

        if not tool_manifests:
            logger.warning(
                "semantic_tool_selector_skip",
                reason="No tool manifests registered",
            )
            return

        logger.info(
            "semantic_tool_selector_initializing",
            tool_count=len(tool_manifests),
            softmax_temperature=settings.v3_tool_softmax_temperature,
            calibrated_primary_min=settings.v3_tool_calibrated_primary_min,
            max_tools=settings.semantic_tool_selector_max_tools,
        )

        try:
            # Get the singleton instance and initialize it with settings
            selector = await SemanticToolSelector.get_instance()
            await selector.initialize(
                tool_manifests=tool_manifests,
                max_tools=settings.semantic_tool_selector_max_tools,
                softmax_temperature=settings.v3_tool_softmax_temperature,
                calibrated_primary_min=settings.v3_tool_calibrated_primary_min,
            )

            logger.info(
                "semantic_tool_selector_initialized",
                tool_count=len(tool_manifests),
            )

        except Exception as e:
            logger.error(
                "semantic_tool_selector_initialization_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    # ========================================================================
    # HITL (Human-in-the-Loop) Helper Methods
    # ========================================================================

    def get_tools_requiring_hitl(self) -> list[str]:
        """
        Get list of tool names that require HITL approval.

        Queries all registered tool manifests and returns names where
        permissions.hitl_required = True.

        Returns:
            List of tool names requiring approval.

        Example:
            >>> registry.get_tools_requiring_hitl()
            ['search_contacts_tool', 'delete_contact', 'send_email']

        Note:
            This method is thread-safe and uses the catalogue lock.
            It's the authoritative source for HITL approval requirements.

        Best Practice (LangGraph v1.0):
            HITL approval requirements should be declarative (manifest-driven)
            not imperative (settings-driven). This follows the principle of
            "configuration as code" where tool metadata lives with tool definition.
        """
        with self._catalogue_lock:
            hitl_tools = [
                name
                for name, manifest in self._tool_manifests.items()
                if manifest.permissions.hitl_required
            ]

            logger.debug(
                "hitl_tools_query",
                count=len(hitl_tools),
                tools=hitl_tools,
            )

            return hitl_tools

    def requires_tool_approval(self, tool_name: str) -> bool:
        """
        Check if a specific tool requires HITL approval.

        Queries the tool's manifest for permissions.hitl_required field.
        This is the single source of truth for HITL approval requirements.

        Args:
            tool_name: Name of the tool to check.

        Returns:
            True if tool requires approval, False otherwise.
            Returns False if tool not found (defensive behavior).

        Example:
            >>> registry.requires_tool_approval('search_contacts_tool')
            True
            >>> registry.requires_tool_approval('get_context_state')
            False
            >>> registry.requires_tool_approval('unknown_tool')
            False  # Defensive: missing manifest = no approval

        Note:
            This method is thread-safe and uses the catalogue lock.
            Defensive programming: Returns False if manifest not found
            to prevent crashes in runtime approval checks.

        Migration Note:
            - Legacy: Pattern matching against settings.tool_approval_required
            - Current: Manifest-driven via permissions.hitl_required
            - Benefit: Single source of truth, no duplication, type-safe
        """
        with self._catalogue_lock:
            if tool_name not in self._tool_manifests:
                logger.warning(
                    "tool_manifest_not_found_hitl_check",
                    tool_name=tool_name,
                    message="Tool not in registry, defaulting to no approval required (defensive)",
                )
                return False

            manifest = self._tool_manifests[tool_name]
            requires_hitl = manifest.permissions.hitl_required

            logger.debug(
                "tool_approval_check",
                tool_name=tool_name,
                requires_approval=requires_hitl,
                source="manifest.permissions.hitl_required",
            )

            return requires_hitl

    # ========================================================================
    # Semantic Type Analysis (Cross-Domain Intelligence)
    # ========================================================================

    def get_semantic_type_providers(self, semantic_type: str) -> dict[str, list[str]]:
        """
        Find which domains/tools provide a given semantic type.

        Used by QueryAnalyzerService to auto-expand domains when a required
        semantic type is not available in the currently selected domains.

        Args:
            semantic_type: The semantic type to find providers for (e.g., "physical_address")

        Returns:
            Dict mapping domain names to list of tools that provide this semantic type.
            Example: {"contacts": ["get_contacts_tool"]}

        Example:
            >>> providers = registry.get_semantic_type_providers("physical_address")
            >>> # Returns: {"contacts": ["get_contacts_tool"]}
            >>> # Meaning: contacts domain has tools that output physical_address

        Architecture Note:
            This enables intelligent cross-domain expansion:
            1. routes domain needs "physical_address" for destination
            2. User query has a person name (from memory resolution)
            3. System finds contacts provides "physical_address"
            4. Domain selector auto-expands to include contacts
            5. Planner can now chain: contacts → get address → routes
        """
        providers: dict[str, list[str]] = {}

        with self._catalogue_lock:
            for tool_name, manifest in self._tool_manifests.items():
                # Check outputs for semantic_type
                if hasattr(manifest, "outputs") and manifest.outputs:
                    for output in manifest.outputs:
                        if (
                            hasattr(output, "semantic_type")
                            and output.semantic_type == semantic_type
                        ):
                            # Extract domain from agent name
                            domain = self._extract_domain_from_agent_name(manifest.agent)
                            if domain not in providers:
                                providers[domain] = []
                            if tool_name not in providers[domain]:
                                providers[domain].append(tool_name)

        return providers

    def get_required_semantic_types_for_domains(
        self, domains: list[str]
    ) -> dict[str, list[tuple[str, str]]]:
        """
        Get semantic types required by tools in the specified domains.

        Used by QueryAnalyzerService to determine if domain expansion is needed
        based on what semantic types the selected tools require.

        Args:
            domains: List of domain names to analyze (e.g., ["routes"])

        Returns:
            Dict mapping semantic_type to list of (tool_name, param_name) tuples.
            Example: {"physical_address": [("get_route_tool", "destination")]}

        Example:
            >>> required = registry.get_required_semantic_types_for_domains(["routes"])
            >>> # Returns: {"physical_address": [("get_route_tool", "destination"), ("get_route_tool", "origin")]}

        Architecture Note:
            Combined with get_semantic_type_providers(), enables:
            1. Check what semantic types routes tools need (physical_address)
            2. Check if query provides this (person name != physical_address)
            3. Find which domain provides it (contacts)
            4. Auto-expand domains to include provider
        """
        required_types: dict[str, list[tuple[str, str]]] = {}

        with self._catalogue_lock:
            for tool_name, manifest in self._tool_manifests.items():
                # Check if tool belongs to one of the requested domains
                tool_domain = self._extract_domain_from_agent_name(manifest.agent)
                if tool_domain not in domains:
                    continue

                # Check parameters for semantic_type requirements
                for param in manifest.parameters:
                    if hasattr(param, "semantic_type") and param.semantic_type:
                        sem_type = param.semantic_type
                        if sem_type not in required_types:
                            required_types[sem_type] = []
                        required_types[sem_type].append((tool_name, param.name))

        return required_types

    def get_domains_providing_semantic_type(self, semantic_type: str) -> list[str]:
        """
        Get list of domain names that provide a given semantic type.

        Simplified version of get_semantic_type_providers() that returns just domain names.

        Args:
            semantic_type: The semantic type to find (e.g., "physical_address")

        Returns:
            List of domain names that have tools providing this semantic type.

        Example:
            >>> domains = registry.get_domains_providing_semantic_type("physical_address")
            >>> # Returns: ["contacts"]
        """
        providers = self.get_semantic_type_providers(semantic_type)
        return list(providers.keys())

    def get_provided_semantic_types_for_domains(self, domains: list[str]) -> set[str]:
        """
        Get semantic types provided by tools in the specified domains.

        Used for reverse semantic expansion: if domain X provides physical_address,
        check if any filtered domains require it.

        Args:
            domains: List of domain names to check

        Returns:
            Set of semantic types provided by these domains' tools.

        Example:
            >>> provided = registry.get_provided_semantic_types_for_domains(["calendar"])
            >>> # Returns: {"physical_address"} (from events[].location)
        """
        provided_types: set[str] = set()

        for domain_name in domains:
            agent_def = self._agents.get(domain_name)
            if not agent_def:
                continue

            for tool_name in agent_def.tool_names:
                manifest = self._tools.get(tool_name)
                if not manifest:
                    continue

                for output in manifest.outputs or []:
                    if hasattr(output, "semantic_type") and output.semantic_type:
                        provided_types.add(output.semantic_type)

        return provided_types

    def get_domains_requiring_semantic_type(self, semantic_type: str) -> list[str]:
        """
        Get list of domain names that require a given semantic type.

        Used for reverse semantic expansion: find which domains need a semantic type
        so they can be re-added if a provider domain is selected.

        Args:
            semantic_type: The semantic type to find (e.g., "physical_address")

        Returns:
            List of domain names that have tools requiring this semantic type.

        Example:
            >>> domains = registry.get_domains_requiring_semantic_type("physical_address")
            >>> # Returns: ["routes"] (get_route_tool requires destination)
        """
        requiring_domains: list[str] = []

        for domain_name, agent_def in self._agents.items():
            for tool_name in agent_def.tool_names:
                manifest = self._tools.get(tool_name)
                if not manifest:
                    continue

                for param in manifest.parameters or []:
                    if hasattr(param, "semantic_type") and param.semantic_type == semantic_type:
                        if domain_name not in requiring_domains:
                            requiring_domains.append(domain_name)
                        break  # Found one, no need to check more params

        return requiring_domains

    # ========================================================================
    # Existing Helper Methods
    # ========================================================================

    def get_checkpointer(self) -> Any | None:
        """
        Get the shared checkpointer.

        Returns:
            Checkpointer instance or None if not configured.

        Example:
            >>> checkpointer = registry.get_checkpointer()
            >>> if checkpointer:
            ...     # Checkpointer is available
        """
        return self._checkpointer

    def get_store(self) -> Any | None:
        """
        Get the shared store.

        Returns:
            Store instance or None if not configured.

        Example:
            >>> store = registry.get_store()
            >>> if store:
            ...     # Store is available
        """
        return self._store

    def get_stats(self) -> dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with registry stats (registered, built, catalogue, etc.).

        Example:
            >>> stats = registry.get_stats()
            >>> print(f"Registered: {stats['registered']}, Built: {stats['built']}")
            >>> print(f"Catalogue: {stats['catalogue']['agent_manifests']} agents, {stats['catalogue']['tool_manifests']} tools")
        """
        with self._lock:
            with self._catalogue_lock:
                return {
                    "registered": len(self._builders),
                    "built": len(self._agents),
                    "has_checkpointer": self._checkpointer is not None,
                    "has_store": self._store is not None,
                    "agents": {
                        "registered": list(self._builders.keys()),
                        "built": list(self._agents.keys()),
                    },
                    "catalogue": {
                        "agent_manifests": len(self._agent_manifests),
                        "tool_manifests": len(self._tool_manifests),
                        "agents": list(self._agent_manifests.keys()),
                        "tools": list(self._tool_manifests.keys()),
                    },
                }


# ============================================================================
# Global Registry Singleton
# ============================================================================

_global_registry: AgentRegistry | None = None
_global_registry_lock = threading.Lock()


def get_global_registry() -> AgentRegistry:
    """
    Get the global agent registry singleton.

    This function ensures a single registry instance across the application.
    The registry is initialized lazily on first access.

    Returns:
        Global AgentRegistry instance.

    Example:
        >>> # In AgentService.__init__
        >>> registry = get_global_registry()
        >>> agent = registry.get_agent("contact_agent")

    Note:
        The global registry is initialized without checkpointer/store.
        You should call set_global_registry() during app startup with
        the actual checkpointer and store instances.
    """
    global _global_registry

    if _global_registry is None:
        with _global_registry_lock:
            if _global_registry is None:
                logger.warning(
                    "global_registry_lazy_init",
                    message="Global registry not initialized, creating without deps. "
                    "Consider calling set_global_registry() at app startup.",
                )
                _global_registry = AgentRegistry()

    return _global_registry


def set_global_registry(registry: AgentRegistry) -> None:
    """
    Set the global agent registry singleton.

    Call this during application startup to configure the registry
    with checkpointer and store.

    Args:
        registry: Configured AgentRegistry instance.

    Example:
        >>> # In main.py or startup event
        >>> registry = AgentRegistry(
        ...     checkpointer=postgres_checkpointer,
        ...     store=in_memory_store
        ... )
        >>> registry.register_agent("contact_agent", build_contact_agent)
        >>> set_global_registry(registry)

    Note:
        This should be called once during app startup, before any
        agent access via get_global_registry().
    """
    global _global_registry

    with _global_registry_lock:
        _global_registry = registry
        logger.info("global_registry_set", stats=registry.get_stats())


def reset_global_registry() -> None:
    """
    Reset the global registry singleton (for testing).

    Example:
        >>> # In test teardown
        >>> reset_global_registry()
    """
    global _global_registry

    with _global_registry_lock:
        _global_registry = None
        logger.debug("global_registry_reset")


__all__ = [
    "AgentAlreadyRegisteredError",
    "AgentNotFoundError",
    "AgentRegistry",
    "AgentRegistryError",
    "get_global_registry",
    "reset_global_registry",
    "set_global_registry",
]
