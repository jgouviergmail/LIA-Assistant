"""
Semantic Expansion Service - ISO-FUNCTIONAL

Semantic expansion service that reproduces EXACTLY the current
hardcoded behavior, but via lookup in the type registry.

Current behavior to reproduce (query_analyzer_service.py _expand_domains_for_semantic_types):
    if has_person_reference:
        if "physical_address" in required_types:
            domains_to_add.add("contacts")
        if "email_address" in required_types:
            domains_to_add.add("contacts")

Phase 1 (ISO-FUNCTIONAL): Exact reproduction via registry
Phase 2 (SMART): Intelligent expansion with reasoning (Step 2)
"""

from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.type_registry import TypeRegistry, get_registry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class SemanticExpansionService:
    """
    ISO-FUNCTIONAL semantic expansion service.

    Reproduces EXACTLY the current hardcoded behavior,
    but via lookup in the type registry.

    Principles:
    - Zero regression: identical behavior to current code
    - Lookup via registry instead of hardcoded conditions
    - Detailed logging for traceability
    - Support for the same use cases

    Examples:
        >>> service = SemanticExpansionService()
        >>> # Query: "directions to my brother's place"
        >>> result = await service.expand_domains_iso_functional(
        ...     domains=["routes"],
        ...     has_person_reference=True,
        ...     required_semantic_types={"physical_address"},
        ...     query="itinéraire chez mon frère"
        ... )
        >>> result
        ["routes", "contacts"]  # Contacts added because it provides physical_address

        >>> # Query: "recherche mes 2 prochains rdv"
        >>> result = await service.expand_domains_iso_functional(
        ...     domains=["calendar"],
        ...     has_person_reference=False,
        ...     required_semantic_types={"datetime"},
        ...     query="recherche mes 2 prochains rdv"
        ... )
        >>> result
        ["calendar"]  # NO expansion (no person reference)
    """

    def __init__(self, registry: TypeRegistry | None = None) -> None:
        """
        Initialize the expansion service.

        Args:
            registry: Type registry (if None, uses the global one)
        """
        self.registry = registry or get_registry()

        # Ensure core types are loaded
        if len(self.registry) == 0:
            logger.info("expansion_service_init", message="Registry empty, loading core types")
            load_core_types(self.registry)

        logger.debug(
            "expansion_service_initialized",
            total_types=len(self.registry),
            message="SemanticExpansionService initialized",
        )

    async def expand_domains_iso_functional(
        self,
        domains: list[str],
        has_person_reference: bool,
        required_semantic_types: set[str],
        query: str = "",
    ) -> list[str]:
        """
        ISO-FUNCTIONAL domain expansion.

        Reproduces EXACTLY the current behavior:
        ```python
        if has_person_reference:
            if "physical_address" in required_types:
                domains_to_add.add("contacts")
            if "email_address" in required_types:
                domains_to_add.add("contacts")
        ```

        But via registry lookup instead of hardcode.

        Args:
            domains: Domains already selected by the router
            has_person_reference: True if the query contains a person reference
                                  (detected by memory resolution)
            required_semantic_types: Semantic types required by the tools
                                    of the selected domains
            query: Original query (for logging)

        Returns:
            List of domains (original + added)

        ISO-FUNCTIONAL behavior:
        - IF has_person_reference == False -> NO expansion
        - IF has_person_reference == True:
            - For each required type, check if "contacts" provides it
            - If so, add "contacts" only once

        Examples:
            >>> # Case 1: With person reference + physical_address required
            >>> await expand_domains_iso_functional(
            ...     domains=["routes"],
            ...     has_person_reference=True,
            ...     required_semantic_types={"physical_address"},
            ...     query="itinéraire chez mon frère"
            ... )
            ["routes", "contacts"]

            >>> # Case 2: WITHOUT person reference (no expansion)
            >>> await expand_domains_iso_functional(
            ...     domains=["calendar"],
            ...     has_person_reference=False,
            ...     required_semantic_types={"physical_address"},
            ...     query="recherche mes 2 prochains rdv"
            ... )
            ["calendar"]  # NO expansion

            >>> # Case 3: With person reference + email_address required
            >>> await expand_domains_iso_functional(
            ...     domains=["calendar"],
            ...     has_person_reference=True,
            ...     required_semantic_types={"email_address"},
            ...     query="rdv avec mon frère"
            ... )
            ["calendar", "contacts"]
        """
        # Validation
        if not domains:
            logger.debug("expansion_no_domains", query=query, message="No domains to expand")
            return domains

        # ISO-FUNCTIONAL: No person reference means no expansion
        if not has_person_reference:
            logger.debug(
                "expansion_no_person_ref",
                query=query,
                domains=domains,
                message="No person reference, skipping expansion",
            )
            return domains

        # Expand only if person reference is present
        domains_to_add = []

        # For each required semantic type
        for semantic_type in required_semantic_types:
            # Lookup in the registry
            type_def = self.registry.get(semantic_type)

            if not type_def:
                logger.debug(
                    "expansion_type_not_found",
                    semantic_type=semantic_type,
                    message=f"Type '{semantic_type}' not found in registry",
                )
                continue

            # Check if "contact" provides this type
            # ISO-FUNCTIONAL: we only check "contact"
            # (current code only checks contact)
            if "contact" in type_def.source_domains:
                # Add contact if not already present
                if "contact" not in domains and "contact" not in domains_to_add:
                    domains_to_add.append("contact")

                    logger.info(
                        "semantic_expansion_iso",
                        added_domain="contact",
                        reason=f"provides {semantic_type}",
                        has_person_ref=True,
                        query=query,
                        original_domains=domains,
                        required_type=semantic_type,
                    )

        # Final result
        expanded_domains = domains + domains_to_add

        if domains_to_add:
            logger.info(
                "semantic_expansion_applied",
                original_domains=domains,
                expanded_domains=expanded_domains,
                added_domains=domains_to_add,
                query=query,
                has_person_ref=has_person_reference,
                required_types=list(required_semantic_types),
            )
        else:
            logger.debug(
                "semantic_expansion_no_change",
                domains=domains,
                query=query,
                has_person_ref=has_person_reference,
                required_types=list(required_semantic_types),
                message="No domains added",
            )

        return expanded_domains

    def get_providers_for_type(self, semantic_type: str) -> list[str]:
        """
        Return the provider domains for a semantic type.

        Args:
            semantic_type: Semantic type name

        Returns:
            List of domains providing this type

        Example:
            >>> service.get_providers_for_type("physical_address")
            ["contacts", "places", "calendar", "routes"]
            >>> service.get_providers_for_type("email_address")
            ["contacts", "emails", "calendar"]
        """
        type_def = self.registry.get(semantic_type)

        if not type_def:
            logger.warning(
                "get_providers_type_not_found",
                semantic_type=semantic_type,
                message=f"Type '{semantic_type}' not found in registry",
            )
            return []

        return type_def.source_domains

    def get_types_for_domain(self, domain: str) -> set[str]:
        """
        Return the semantic types provided by a domain.

        Args:
            domain: Domain name

        Returns:
            Set of type names provided by this domain

        Example:
            >>> service.get_types_for_domain("contacts")
            {"email_address", "phone_number", "person_name", "physical_address", "contact_id"}
        """
        return self.registry.get_by_domain(domain)

    def validate_expansion_logic(self) -> dict:
        """
        Validate that the ISO-FUNCTIONAL expansion logic is correct.

        Checks that:
        - "contacts" properly provides "email_address" and "physical_address"
        - Explicit types exist in the registry
        - Hierarchy is consistent

        Returns:
            Validation dictionary with any errors
        """
        errors = []

        # Verify that all 5 explicit types exist
        explicit_types = [
            "email_address",
            "physical_address",
            "phone_number",
            "person_name",
            "coordinate",
        ]

        for type_name in explicit_types:
            if type_name not in self.registry:
                errors.append(f"Explicit type '{type_name}' not found in registry")

        # Verify that contact provides email_address and physical_address
        # (required for ISO-FUNCTIONAL behavior)
        email_providers = self.get_providers_for_type("email_address")
        if "contact" not in email_providers:
            errors.append(
                "ISO-FUNCTIONAL requirement violated: " "'contact' must provide 'email_address'"
            )

        address_providers = self.get_providers_for_type("physical_address")
        if "contact" not in address_providers:
            errors.append(
                "ISO-FUNCTIONAL requirement violated: " "'contact' must provide 'physical_address'"
            )

        # Validate hierarchy
        hierarchy_errors = self.registry.validate_hierarchy()
        errors.extend(hierarchy_errors)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "registry_stats": self.registry.get_stats(),
        }

    async def expand_domains_semantic(
        self,
        primary_domains: list[str],
        required_semantic_types: set[str],
        threshold: float = 0.7,
        query: str = "",
    ) -> list[str]:
        """
        Expansion sémantique INTELLIGENTE des domaines.

        Contrairement à expand_domains_iso_functional(), cette méthode:
        - Vérifie TOUS les domaines providers (pas seulement "contacts")
        - Ajoute les providers qui fournissent les types requis (via source_domains)

        Le threshold contrôle l'ajout de providers:
        - threshold < 1.0: Ajoute tous les providers listés dans source_domains du type
        - threshold = 1.0: N'ajoute aucun provider (désactive l'expansion)

        Note: Le threshold est un toggle simple (< 1.0 = on, = 1.0 = off).
        Une future évolution pourrait utiliser la distance Wu & Palmer pour un
        filtrage plus granulaire basé sur la similarité sémantique.

        Args:
            primary_domains: Domaines déjà sélectionnés par le router
            required_semantic_types: Types sémantiques requis par les tools
            threshold: Seuil pour ajouter providers. < 1.0 = active, 1.0 = désactivé
            query: Query originale (pour logging)

        Returns:
            Liste de domaines (originaux + providers ajoutés)

        Example:
            >>> service = SemanticExpansionService()
            >>> # Query: "send email to Jean" (needs email_address)
            >>> result = await service.expand_domains_semantic(
            ...     primary_domains=["emails"],
            ...     required_semantic_types={"email_address"},
            ...     threshold=0.5,
            ...     query="send email to Jean"
            ... )
            >>> "contacts" in result
            True  # Contacts is listed in email_address.source_domains
        """
        if not primary_domains:
            logger.debug("semantic_expansion_no_domains", query=query)
            return primary_domains

        if not required_semantic_types:
            logger.debug("semantic_expansion_no_types", query=query, domains=primary_domains)
            return primary_domains

        expanded = set(primary_domains)
        added_domains: list[str] = []

        for sem_type in required_semantic_types:
            type_def = self.registry.get(sem_type)
            if not type_def:
                logger.debug(
                    "semantic_expansion_type_not_found",
                    semantic_type=sem_type,
                    query=query,
                )
                continue

            # Check ALL providers (not just "contacts")
            # If a provider is listed in source_domains, it provides this type
            for provider in type_def.source_domains:
                if provider in expanded:
                    continue

                # Provider is listed → it provides the type
                # Only threshold=1.0 would block it
                if threshold < 1.0:
                    expanded.add(provider)
                    added_domains.append(provider)

                    logger.info(
                        "semantic_expansion_added",
                        added_domain=provider,
                        semantic_type=sem_type,
                        threshold=threshold,
                        query=query,
                    )

        if added_domains:
            logger.info(
                "semantic_expansion_complete",
                original_domains=primary_domains,
                added_domains=added_domains,
                expanded_domains=list(expanded),
                required_types=list(required_semantic_types),
                query=query,
            )

        return list(expanded)

    def _get_primary_type_for_domain(self, domain: str) -> str:
        """
        Get the primary semantic type for a domain.

        Used for Wu & Palmer distance calculation.

        Args:
            domain: Domain name (e.g., "contacts", "emails")

        Returns:
            Primary semantic type name (e.g., "person_name", "message_id")
        """
        # Mapping of domains to their primary types (most representative)
        domain_primary_types = {
            "contact": "person_name",
            "email": "message_id",
            "event": "event_id",
            "task": "task_id",
            "file": "file_id",
            "place": "place_id",
            "route": "physical_address",
            "weather": "coordinate",
            "wikipedia": "text",
            "perplexity": "text",
            "reminder": "reminder_id",
        }
        return domain_primary_types.get(domain, "text")


# Singleton global service
_global_expansion_service: SemanticExpansionService | None = None


def get_expansion_service() -> SemanticExpansionService:
    """
    Retrieve the global expansion service instance.

    Singleton pattern for a single shared service.

    Returns:
        Global SemanticExpansionService instance
    """
    global _global_expansion_service
    if _global_expansion_service is None:
        _global_expansion_service = SemanticExpansionService()
        logger.info(
            "global_expansion_service_created",
            message="Global SemanticExpansionService instance created",
        )
    return _global_expansion_service


def reset_expansion_service() -> None:
    """
    Reset the global expansion service.

    Useful for unit tests.
    """
    global _global_expansion_service
    _global_expansion_service = None
    logger.debug("global_expansion_service_reset", message="Global SemanticExpansionService reset")


def _get_output_paths_by_semantic_type(
    semantic_type: str,
    domains: list[str],
    max_paths: int = 2,
) -> list[tuple[str, str]]:
    """
    Find output paths in catalogue manifests that provide a given semantic_type.

    This helper scans tool manifests for outputs matching the semantic_type,
    returning actionable Jinja2-compatible paths.

    Args:
        semantic_type: The semantic type to search for (e.g., "email_address")
        domains: List of domains to search in
        max_paths: Maximum paths to return per type

    Returns:
        List of tuples (tool_name, output_path) for matching outputs.
        Path uses array notation [0] instead of [].

    Example:
        >>> _get_output_paths_by_semantic_type("email_address", ["contacts"])
        [("get_contacts_tool", "contacts[0].emailAddresses[0].value")]
    """
    from src.domains.agents.registry import get_global_registry

    paths: list[tuple[str, str]] = []

    try:
        registry = get_global_registry()
        all_manifests = registry.list_tool_manifests()

        for manifest in all_manifests:
            # Filter by domain - extract domain from agent name
            # Pattern: "contacts_agent" → "contacts"
            agent_domain = manifest.agent.removesuffix("_agent") if manifest.agent else ""
            if agent_domain not in domains:
                continue

            # Search outputs for matching semantic_type
            for output in manifest.outputs:
                if output.semantic_type == semantic_type:
                    # Convert array notation: contacts[] → contacts[0]
                    output_path = output.path.replace("[]", "[0]")
                    paths.append((manifest.name, output_path))

                    if len(paths) >= max_paths:
                        return paths

    except Exception as e:
        logger.debug(
            "get_output_paths_by_semantic_type_error",
            semantic_type=semantic_type,
            domains=domains,
            error=str(e),
        )

    return paths


def generate_semantic_dependencies_for_prompt(
    domains: list[str],
    include_jinja2_patterns: bool = True,
) -> str:
    """
    Generate dynamic semantic dependencies section for planner prompt.

    This function creates a concise text describing cross-domain type dependencies
    for the given domains. It helps the LLM understand which tools provide
    and consume specific semantic types.

    When include_jinja2_patterns=True (default), includes concrete Jinja2 reference
    patterns that the planner can use directly for cross-domain linking.

    Args:
        domains: List of domain names (e.g., ["emails", "contacts"])
        include_jinja2_patterns: Whether to include Jinja2 reference examples

    Returns:
        Formatted string for prompt injection describing semantic dependencies.

    Example output for ["emails", "contacts"]:
        - email_address: provided by [contacts], used by [send_email_tool]
          → Example: $steps.get_contacts.contacts[0].emailAddresses[0].value
        - physical_address: provided by [contacts], used by [get_route_tool]
          → Example: $steps.get_contacts.contacts[0].addresses[0].formattedValue
    """
    from src.core.config import get_settings
    from src.core.constants import (
        SEMANTIC_DEPS_NO_CROSS_DOMAIN,
        SEMANTIC_DEPS_NO_DOMAINS,
        SEMANTIC_DEPS_NO_TYPES_FOUND,
    )

    settings = get_settings()

    # Check if semantic linking is enabled
    if not settings.semantic_linking_enabled:
        return SEMANTIC_DEPS_NO_CROSS_DOMAIN

    if not domains:
        logger.debug(
            "semantic_deps_no_domains", message="No domains provided for semantic dependencies"
        )
        return SEMANTIC_DEPS_NO_DOMAINS

    try:
        service = get_expansion_service()
        registry = service.registry

        # Collect all semantic types relevant to these domains
        types_by_domain: dict[str, set[str]] = {}
        for domain in domains:
            types_by_domain[domain] = registry.get_by_domain(domain)

        # Find "bridge" types - types that link domains together
        all_types: set[str] = set()
        for types in types_by_domain.values():
            all_types.update(types)

        if not all_types:
            logger.debug(
                "semantic_deps_no_types",
                domains=domains,
                message="No semantic types found for domains",
            )
            return SEMANTIC_DEPS_NO_TYPES_FOUND

        # Build dependency descriptions
        lines: list[str] = []

        # Focus on cross-domain types (provided by one domain, used by tools in another)
        for type_name in sorted(all_types):
            type_def = registry.get(type_name)
            if not type_def:
                continue

            # Only include types that are:
            # 1. Provided by at least one of the selected domains
            # 2. Used by tools (have consumers)
            providers = [d for d in type_def.source_domains if d in domains]
            if not providers or not type_def.used_in_tools:
                continue

            # Format: type_name: provided by [domains], used by [tools]
            providers_str = ", ".join(providers)
            tools_str = ", ".join(type_def.used_in_tools[:3])  # Limit to 3 tools
            if len(type_def.used_in_tools) > 3:
                tools_str += f" (+{len(type_def.used_in_tools) - 3} more)"

            line = f"   - {type_name}: provided by [{providers_str}], used by [{tools_str}]"

            # Add Jinja2 reference examples if enabled
            if include_jinja2_patterns:
                output_paths = _get_output_paths_by_semantic_type(
                    type_name,
                    providers,  # Search in provider domains
                    max_paths=1,
                )
                if output_paths:
                    tool_name, path = output_paths[0]
                    # Extract step_id from tool_name (e.g., get_contacts_tool → get_contacts)
                    step_id = tool_name.replace("_tool", "")
                    jinja2_ref = f"$steps.{step_id}.{path}"
                    line += f"\n     → Reference: {jinja2_ref}"

            lines.append(line)

        if not lines:
            logger.debug(
                "semantic_deps_no_cross_domain",
                domains=domains,
                types_count=len(all_types),
                message="No cross-domain semantic dependencies found",
            )
            return SEMANTIC_DEPS_NO_CROSS_DOMAIN

        logger.debug(
            "semantic_deps_generated",
            domains=domains,
            dependency_count=len(lines),
            include_jinja2=include_jinja2_patterns,
            message="Generated semantic dependencies for prompt",
        )
        return "\n".join(lines)

    except Exception as e:
        logger.warning(
            "semantic_deps_generation_failed",
            domains=domains,
            error=str(e),
            error_type=type(e).__name__,
            message="Failed to generate semantic dependencies, returning fallback",
        )
        return SEMANTIC_DEPS_NO_CROSS_DOMAIN


def get_semantic_provider_tool_names(domains: list[str]) -> set[str]:
    """
    Get tool names that provide cross-domain semantic types for the given domains.

    For multi-domain queries (e.g., ["emails", "contacts"]), identifies tools
    that PROVIDE data needed by tools in other domains.

    This is used by catalogue filtering to protect provider tools from being
    excluded by low semantic scores. Without this, a query like "send email
    to Marie" would exclude get_contacts_tool (score 0.000 for email queries)
    even though it's needed to resolve the recipient's email address.

    Args:
        domains: List of active domain names

    Returns:
        Set of tool manifest names that provide cross-domain semantic types.
        Empty set if fewer than 2 domains or on any error.

    Example:
        >>> get_semantic_provider_tool_names(["emails", "contacts"])
        {"get_contacts_tool"}  # Provides email_address type used by send_email_tool
    """
    if len(domains) < 2:
        return set()  # Single domain = no cross-domain dependencies

    try:
        service = get_expansion_service()
        registry = service.registry

        # Collect all semantic types for active domains
        all_types: set[str] = set()
        for domain in domains:
            all_types.update(registry.get_by_domain(domain))

        provider_tools: set[str] = set()

        for type_name in all_types:
            type_def = registry.get(type_name)
            if not type_def or not type_def.used_in_tools:
                continue

            # Only include types provided by at least one active domain
            providers = [d for d in type_def.source_domains if d in domains]
            if not providers:
                continue

            # Find actual provider tool names from manifests
            output_paths = _get_output_paths_by_semantic_type(
                type_name,
                providers,
                max_paths=3,
            )
            for tool_name, _ in output_paths:
                provider_tools.add(tool_name)

        if provider_tools:
            logger.debug(
                "semantic_provider_tools_resolved",
                domains=domains,
                provider_tools=sorted(provider_tools),
            )

        return provider_tools

    except Exception as e:
        logger.debug(
            "semantic_provider_tools_error",
            domains=domains,
            error=str(e),
        )
        return set()


def generate_jinja2_suggestions(
    target_tool: str,
    target_param: str,
    available_step_ids: list[str],
    max_suggestions: int = 5,
    *,
    step_tool_mapping: dict[str, str] | None = None,
) -> list[str]:
    """
    Generate structured Jinja2 reference suggestions for a parameter.

    This function creates actionable Jinja2 references that the planner can use
    to link outputs from previous steps to inputs of subsequent steps based on
    semantic_type matching.

    Args:
        target_tool: Tool name for which to find parameter sources (e.g., "get_route_tool")
        target_param: Parameter name to find sources for (e.g., "destination")
        available_step_ids: List of step IDs that have already executed or are planned
        max_suggestions: Maximum suggestions to return (default: 5)
        step_tool_mapping: Optional mapping from step_id to tool_name for precise matching.
            When provided, uses exact tool_name lookup instead of heuristic matching.
            Format: {"search_contacts": "get_contacts_tool", "fetch_events": "get_events_tool"}

    Returns:
        List of Jinja2 reference strings like ["$steps.get_contacts.contacts[0].addresses[0].formattedValue"]

    Example:
        >>> suggestions = generate_jinja2_suggestions(
        ...     target_tool="get_route_tool",
        ...     target_param="destination",
        ...     available_step_ids=["search_contacts", "fetch_events"],
        ...     step_tool_mapping={
        ...         "search_contacts": "get_contacts_tool",
        ...         "fetch_events": "get_events_tool",
        ...     },
        ... )
        >>> suggestions
        ["$steps.search_contacts.contacts[0].addresses[0].formattedValue",
         "$steps.fetch_events.events[0].location"]
    """
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.agent_registry import ToolManifestNotFound

    suggestions: list[str] = []

    try:
        registry = get_global_registry()

        # Get the target parameter's semantic_type
        try:
            target_manifest = registry.get_tool_manifest(target_tool)
        except ToolManifestNotFound:
            logger.debug(
                "jinja2_suggestions_tool_not_found",
                target_tool=target_tool,
                target_param=target_param,
            )
            return []

        # Find the parameter schema
        target_param_schema = None
        for param in target_manifest.parameters:
            if param.name == target_param:
                target_param_schema = param
                break

        if not target_param_schema or not target_param_schema.semantic_type:
            logger.debug(
                "jinja2_suggestions_no_semantic_type",
                target_tool=target_tool,
                target_param=target_param,
                message="Parameter has no semantic_type",
            )
            return []

        target_semantic_type = target_param_schema.semantic_type

        # Search for matching outputs in available steps
        for step_id in available_step_ids:
            # Determine tool_name for this step
            step_tool_name: str | None = None

            if step_tool_mapping and step_id in step_tool_mapping:
                # Precise matching via mapping
                step_tool_name = step_tool_mapping[step_id]
            else:
                # Fallback: heuristic matching (step_id often contains tool name or vice versa)
                all_manifests = registry.list_tool_manifests()
                for manifest in all_manifests:
                    tool_name = manifest.name
                    # Convention: step_id often matches tool_name pattern
                    # e.g., step_id="get_contacts" matches tool_name="get_contacts_tool"
                    tool_base = tool_name.replace("_tool", "")
                    if tool_base in step_id or step_id in tool_base or tool_name == step_id:
                        step_tool_name = tool_name
                        break

            if not step_tool_name:
                logger.debug(
                    "jinja2_suggestions_no_tool_for_step",
                    step_id=step_id,
                    target_tool=target_tool,
                    target_param=target_param,
                )
                continue

            # Get manifest for this step's tool
            try:
                step_manifest = registry.get_tool_manifest(step_tool_name)
            except ToolManifestNotFound:
                continue

            # Search outputs for matching semantic_type
            for output in step_manifest.outputs:
                if output.semantic_type == target_semantic_type:
                    # Build Jinja2 reference
                    # Handle array paths: contacts[].email → contacts[0].email
                    output_path = output.path.replace("[]", "[0]")
                    jinja2_ref = f"$steps.{step_id}.{output_path}"

                    if jinja2_ref not in suggestions:
                        suggestions.append(jinja2_ref)
                        logger.debug(
                            "jinja2_suggestion_found",
                            target_tool=target_tool,
                            target_param=target_param,
                            source_step=step_id,
                            source_tool=step_tool_name,
                            source_path=output.path,
                            semantic_type=target_semantic_type,
                        )

                    if len(suggestions) >= max_suggestions:
                        break

            if len(suggestions) >= max_suggestions:
                break

        if suggestions:
            logger.info(
                "jinja2_suggestions_generated",
                target_tool=target_tool,
                target_param=target_param,
                semantic_type=target_semantic_type,
                suggestion_count=len(suggestions),
                suggestions=suggestions,
            )

        return suggestions

    except Exception as e:
        logger.warning(
            "jinja2_suggestions_failed",
            target_tool=target_tool,
            target_param=target_param,
            error=str(e),
            error_type=type(e).__name__,
        )
        return []


def generate_linking_hints_for_plan(
    plan_steps: list[dict],
    max_suggestions_per_param: int = 3,
) -> dict[str, list[str]]:
    """
    Generate semantic linking hints for all parameters in a plan.

    This function analyzes an execution plan and generates Jinja2 reference
    suggestions for each parameter that has a semantic_type, based on outputs
    from preceding steps.

    Args:
        plan_steps: List of step dictionaries with "step_id", "tool_name", "parameters"
        max_suggestions_per_param: Maximum suggestions per parameter

    Returns:
        Dictionary mapping "{step_id}.{param_name}" to list of Jinja2 suggestions.

    Example:
        >>> hints = generate_linking_hints_for_plan([
        ...     {"step_id": "search_contacts", "tool_name": "get_contacts_tool", "parameters": {}},
        ...     {"step_id": "send_message", "tool_name": "send_email_tool", "parameters": {"to": ""}},
        ... ])
        >>> hints
        {"send_message.to": ["$steps.search_contacts.contacts[0].emailAddresses[0].value"]}
    """
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.agent_registry import ToolManifestNotFound

    hints: dict[str, list[str]] = {}

    try:
        registry = get_global_registry()

        # Build mapping of step_id → tool_name for precise matching
        step_tool_mapping: dict[str, str] = {}
        preceding_step_ids: list[str] = []

        for step in plan_steps:
            step_id = step.get("step_id", "")
            tool_name = step.get("tool_name", "")

            if not tool_name:
                preceding_step_ids.append(step_id)
                continue

            # Build mapping for precise matching in generate_jinja2_suggestions
            step_tool_mapping[step_id] = tool_name

            try:
                manifest = registry.get_tool_manifest(tool_name)
            except ToolManifestNotFound:
                preceding_step_ids.append(step_id)
                continue

            # For each parameter with semantic_type, generate suggestions
            for param in manifest.parameters:
                if not param.semantic_type:
                    continue

                # Only generate hints if there are preceding steps
                if preceding_step_ids:
                    suggestions = generate_jinja2_suggestions(
                        target_tool=tool_name,
                        target_param=param.name,
                        available_step_ids=preceding_step_ids,
                        max_suggestions=max_suggestions_per_param,
                        step_tool_mapping=step_tool_mapping,
                    )

                    if suggestions:
                        hints[f"{step_id}.{param.name}"] = suggestions

            # Add this step to preceding for next iteration
            preceding_step_ids.append(step_id)

        if hints:
            logger.info(
                "linking_hints_generated",
                total_hints=len(hints),
                hints_keys=list(hints.keys()),
            )

        return hints

    except Exception as e:
        logger.warning(
            "linking_hints_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return {}
