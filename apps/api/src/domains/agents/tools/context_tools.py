"""
Universal context resolution tools for LangGraph v1.0 agents.

Provides generic tools for resolving contextual references across ALL agent types.
These tools are 100% generic - work for contacts, emails, calendar events, etc.

Migration to LangChain v1.0 best practices:
- Tools use ToolRuntime for unified access to config, store, state, etc.
- ToolRuntime replaces InjectedStore + RunnableConfig pattern

Pattern:
    @tool
    async def my_tool(
        arg: str,
        runtime: ToolRuntime,  # Unified access to runtime resources
    ) -> str:
        user_id = runtime.config.get("configurable", {}).get("user_id")
        data = await runtime.store.get(...)
        # Use runtime.config, runtime.store, runtime.state, etc.

Usage:
    # In agent builder
    from src.domains.agents.tools.context_tools import resolve_reference

    tools = [
        resolve_reference,  # Universal reference resolver
        # ... other tools ...
    ]

Example Flow:
    User: "liste mes contacts"
    → Tool: search_contacts_tool returns [Jean, Marie, Paul]
    → Auto-saved to Store with indexes

    User: "affiche le détail du 2ème"
    → Tool: resolve_reference(reference="2ème", domain="contacts")
    → Resolves to Marie Martin
    → Returns: {"success": True, "item": {...}, "confidence": 1.0}
"""

from typing import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.core.config import get_settings
from src.core.field_names import FIELD_QUERY, FIELD_TIMESTAMP, FIELD_TURN_ID
from src.core.i18n import _
from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.registry import ContextTypeRegistry
from src.domains.agents.context.resolver import ReferenceResolver
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    handle_tool_exception,
    validate_runtime_config,
)
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = get_logger(__name__)

# Agent name for context tools (generic utility agent)
AGENT_CONTEXT = "context_agent"


# ============================================================================
# RESOLVE REFERENCE TOOL
# ============================================================================
#
# Note: Session ID validation is now centralized in runtime_helpers.py
# All tools use validate_runtime_config() for comprehensive validation.
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="resolve_reference",
    agent_name=AGENT_CONTEXT,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().rate_limit_default_read_calls,
    window_seconds=lambda: get_settings().rate_limit_default_read_window,
    scope="user",
)
async def resolve_reference(
    reference: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    domain: str | None = None,
) -> UnifiedToolOutput:
    """
    Résout une référence contextuelle en un identifiant.

    Cet outil est 100% générique - fonctionne pour contacts, emails, events, etc.
    La résolution est automatiquement adaptée selon le ContextTypeDefinition.

    Migration LangChain v1.0 best practices:
    - Utilise ToolRuntime pour accès unifié aux ressources (config, store, state, etc.)
    - runtime.config contient user_id dans configurable
    - runtime.store permet l'accès au store persistant

    Args:
        reference: Référence utilisateur ("2", "2ème", "dernier", "Jean Dupond", etc.)
        runtime: ToolRuntime injecté automatiquement (accès config, store, etc.)
        domain: Domaine à interroger ("contacts", "emails", "events").
                Optionnel - si non fourni, auto-détection basée sur domaines actifs.

    Returns:
        JSON string avec résultat ou erreur.

    Formats de retour:
        Success:
            {
                "success": true,
                "item": {"index": 2, "name": "Marie Martin", ...},
                "confidence": 1.0,
                "match_type": "index"
            }

        Error (not found):
            {
                "success": false,
                "error": "not_found",
                "message": "'Jean' non trouvé dans la liste."
            }

        Error (ambiguous):
            {
                "success": false,
                "error": "ambiguous",
                "message": "Plusieurs correspondances trouvées.",
                "candidates": [
                    {"index": 1, "name": "Jean Dupond", "confidence": 0.8},
                    {"index": 3, "name": "Jean-Marie", "confidence": 0.75}
                ]
            }

        Error (no context):
            {
                "success": false,
                "error": "no_context",
                "message": "Aucune liste 'contacts' active en mémoire."
            }

    Example Usage:
        User: "affiche le détail du 2ème"
        → resolve_reference(reference="2ème", context_type="contacts")
        → Returns: {"success": true, "item": {...Marie...}, "confidence": 1.0}

        User: "ouvre Jean"
        → resolve_reference(reference="Jean", context_type="contacts")
        → Returns: {"success": true, "item": {...Jean Dupond...}, "confidence": 0.85}

    Strategies (priority order):
        1. Numeric index: "2", "2ème", "deuxième"
        2. Keywords: "premier", "dernier", "last"
        3. Fuzzy match: "Jean" → "Jean Dupond"

    Note:
        This tool is READ-ONLY (no approval required).
        It only resolves references - actual actions (get_contact_details, etc.)
        are performed by subsequent tool calls.
    """
    try:
        # 0. Validate runtime config (user_id, session_id, store) using helper
        config = validate_runtime_config(runtime, "resolve_reference")
        if isinstance(config, UnifiedToolOutput):
            return config  # Early return on validation error

        # Extract validated config
        user_id = config.user_id
        session_id = config.session_id
        store = config.store

        manager = ToolContextManager()

        # 2. Auto-detect domain if not provided
        if not domain:
            active_domains = await manager.list_active_domains(user_id, session_id, store)

            if len(active_domains) == 0:
                logger.debug(
                    "resolve_reference_no_active_domains",
                    user_id=str(user_id),
                    reference=reference,
                )
                return UnifiedToolOutput.failure(
                    message=_("No active domain. Please perform a search first."),
                    error_code="no_context",
                )
            elif len(active_domains) == 1:
                # Single active domain → Use it
                domain = active_domains[0]["domain"]
                logger.info(
                    "domain_auto_detected",
                    user_id=str(user_id),
                    domain=domain,
                    reason="single_active_domain",
                )
            else:
                # Multiple domains → Try to resolve in each domain (most recent first)
                # Return the first domain where resolution succeeds
                sorted_domains = sorted(
                    active_domains, key=lambda d: d[FIELD_TURN_ID], reverse=True
                )

                resolved_in_domain = None
                for candidate in sorted_domains:
                    candidate_domain = candidate["domain"]
                    try:
                        # Check if domain is valid
                        candidate_def = ContextTypeRegistry.get_definition(candidate_domain)

                        # Get context list for this domain
                        candidate_list = await manager.get_list(
                            user_id=user_id,
                            session_id=session_id,
                            domain=candidate_domain,
                            store=store,
                        )

                        if candidate_list and candidate_list.items:
                            # Try to resolve reference in this domain
                            candidate_resolver = ReferenceResolver(candidate_def)
                            candidate_result = candidate_resolver.resolve(
                                reference, candidate_list.items
                            )

                            if candidate_result.success:
                                resolved_in_domain = candidate_domain
                                logger.info(
                                    "domain_auto_detected",
                                    user_id=str(user_id),
                                    domain=candidate_domain,
                                    reason="reference_resolved_successfully",
                                    turn_id=candidate[FIELD_TURN_ID],
                                    alternatives=[d["domain"] for d in active_domains],
                                )
                                break
                    except (ValueError, Exception) as e:
                        logger.debug(
                            "domain_candidate_resolution_failed",
                            domain=candidate_domain,
                            error=str(e),
                        )
                        continue

                if resolved_in_domain:
                    domain = resolved_in_domain
                else:
                    # Fallback: use most recent domain
                    domain = sorted_domains[0]["domain"]
                    logger.info(
                        "domain_auto_detected",
                        user_id=str(user_id),
                        domain=domain,
                        reason="fallback_most_recent",
                        turn_id=sorted_domains[0][FIELD_TURN_ID],
                        alternatives=[d["domain"] for d in active_domains],
                    )

        # 3. Validate domain exists in registry
        try:
            definition = ContextTypeRegistry.get_definition(domain)
        except ValueError:
            available_domains = ContextTypeRegistry.list_all()
            error_msg = _(
                "Domain '{domain}' not registered. Available domains: {available}"
            ).format(domain=domain, available=available_domains if available_domains else _("none"))

            logger.warning(
                "resolve_reference_invalid_domain",
                domain=domain,
                available_domains=available_domains,
                reference=reference,
            )

            return UnifiedToolOutput.failure(
                message=error_msg,
                error_code="invalid_domain",
                metadata={"available_domains": available_domains},
            )

        # 4. Get active context list from Store
        context_list = await manager.get_list(
            user_id=user_id,
            session_id=session_id,
            domain=domain,
            store=store,
        )

        if not context_list or not context_list.items:
            logger.debug(
                "resolve_reference_no_context",
                user_id=str(user_id),
                domain=domain,
                reference=reference,
            )

            return UnifiedToolOutput.failure(
                message=_(
                    "No active '{domain}' list in memory. Please perform a search first to create a context."
                ).format(domain=domain),
                error_code="no_context",
            )

        # 5. Resolve reference using generic resolver
        resolver = ReferenceResolver(definition)
        result = resolver.resolve(reference, context_list.items)

        # 6. Log resolution outcome
        if result.success:
            logger.info(
                "reference_resolved_successfully",
                user_id=str(user_id),
                domain=domain,
                reference=reference,
                resolved_name=(
                    result.item.get(definition.display_name_field) if result.item else None
                ),
                confidence=result.confidence,
                match_type=result.match_type,
            )
        else:
            logger.debug(
                "reference_resolution_failed",
                user_id=str(user_id),
                domain=domain,
                reference=reference,
                error=result.error,
            )

        # 7. Add aliases for backwards compatibility with LLM cache and prompt variants
        # Google API returns resourceName (camelCase) but some prompts use resource_name (snake_case)
        # This ensures both work for plan references like $steps.resolve_first.item.resource_name
        if result.success and result.item:
            # CONTACTS: resourceName → resource_name alias
            if "resourceName" in result.item:
                result.item["resource_name"] = result.item["resourceName"]

            # PLACES: id → place_id alias (for homogeneous pattern with contacts)
            # Primary field is "id" but prompts may use "place_id" for clarity
            if domain == "places" and "id" in result.item:
                result.item["place_id"] = result.item["id"]

        # 8. Return structured result
        if result.success:
            return UnifiedToolOutput.action_success(
                message=_("Reference '{reference}' resolved successfully").format(
                    reference=reference
                ),
                data=result.model_dump(exclude_none=True),
            )
        else:
            # Resolution failed (not found, ambiguous, etc.)
            return UnifiedToolOutput.failure(
                message=result.message
                or _("Reference '{reference}' not found").format(reference=reference),
                error_code=result.error or "resolution_failed",
                metadata={"candidates": result.candidates} if result.candidates else {},
            )

    except Exception as e:
        return handle_tool_exception(
            e,
            "resolve_reference",
            {"domain": domain, "reference": reference},
        )


@tool
@track_tool_metrics(
    tool_name="list_active_domains",
    agent_name=AGENT_CONTEXT,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().rate_limit_default_read_calls,
    window_seconds=lambda: get_settings().rate_limit_default_read_window,
    scope="user",
)
async def list_active_domains(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """
    Liste tous les domaines actifs disponibles pour l'utilisateur.

    Utile pour debugging ou pour informer l'utilisateur des références disponibles.

    Args:
        runtime: ToolRuntime injecté automatiquement (accès config, store, etc.)

    Returns:
        UnifiedToolOutput avec liste des domaines actifs.

    Note:
        This tool is READ-ONLY and provides visibility into available contexts.
    """
    try:
        # Validate runtime config using helper (validates user_id, session_id, and store)
        config = validate_runtime_config(runtime, "list_active_domains")
        if isinstance(config, UnifiedToolOutput):
            return config  # Early return on validation error

        # Extract validated config
        user_id = config.user_id
        session_id = config.session_id
        store = config.store

        # Get all active domains
        manager = ToolContextManager()
        active_domains = await manager.list_active_domains(user_id, session_id, store)

        logger.debug(
            "list_active_domains_completed",
            user_id=str(user_id),
            active_count=len(active_domains),
        )

        if not active_domains:
            return UnifiedToolOutput.action_success(
                message=_("No active domains"),
                structured_data={"active_domains": [], "count": 0},
            )

        return UnifiedToolOutput.action_success(
            message=_("{count} active domain(s)").format(count=len(active_domains)),
            structured_data={"active_domains": active_domains, "count": len(active_domains)},
        )

    except Exception as e:
        logger.error(
            "list_active_domains_error",
            error=str(e),
            exc_info=True,
        )

        return handle_tool_exception(e, "list_active_domains")


@tool
@track_tool_metrics(
    tool_name="set_current_item",
    agent_name=AGENT_CONTEXT,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().rate_limit_default_write_calls,
    window_seconds=lambda: get_settings().rate_limit_default_write_window,
    scope="user",
)
async def set_current_item(
    reference: str,
    domain: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """
    Marque un item comme "courant" pour un domaine spécifique.

    Permet à l'utilisateur de sélectionner explicitement un item dans une liste,
    qui devient alors la référence implicite pour les commandes suivantes.

    Args:
        reference: Référence à l'item ("2", "dernier", "Jean Dupond").
        domain: Domaine concerné ("contacts", "emails", "events").
        runtime: ToolRuntime injecté automatiquement (accès config, store, etc.)

    Returns:
        UnifiedToolOutput avec l'item courant ou erreur.

    Note:
        Cet outil résout d'abord la référence via resolve_reference,
        puis marque l'item résolu comme "courant" (set_by="explicit").
    """
    try:
        # Validate runtime config using helper
        config = validate_runtime_config(runtime, "set_current_item")
        if isinstance(config, UnifiedToolOutput):
            return config  # Early return on validation error

        # Extract validated config
        user_id = config.user_id
        session_id = config.session_id
        store = config.store

        # 1. Resolve the reference first (returns UnifiedToolOutput)
        resolution_result = await resolve_reference.coroutine(reference, runtime, domain)

        if not resolution_result.success:
            # Reference resolution failed → Return error
            return resolution_result

        # 2. Extract resolved item from structured_data
        item = resolution_result.structured_data.get("item")
        if not item:
            return UnifiedToolOutput.failure(
                message=_("Resolution succeeded but no item found"),
                error_code="no_item",
            )

        # 3. Extract turn_id from config metadata
        turn_id = runtime.config.get("configurable", {}).get(FIELD_TURN_ID, 0)

        # 4. Set as current_item
        manager = ToolContextManager()
        await manager.set_current_item(
            user_id=user_id,
            session_id=session_id,
            domain=domain,
            item=item,
            set_by="explicit",
            turn_id=turn_id,
            store=store,
        )

        logger.info(
            "current_item_set_explicitly",
            user_id=str(user_id),
            domain=domain,
            item_index=item.get("index"),
            reference=reference,
        )

        return UnifiedToolOutput.action_success(
            message=_("Item {index} marked as current in {domain}.").format(
                index=item.get("index"), domain=domain
            ),
            structured_data={"current_item": item, "domain": domain},
        )

    except Exception as e:
        return handle_tool_exception(
            e,
            "set_current_item",
            {"domain": domain, "reference": reference},
        )


@tool
@track_tool_metrics(
    tool_name="get_context_state",
    agent_name=AGENT_CONTEXT,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().rate_limit_default_read_calls,
    window_seconds=lambda: get_settings().rate_limit_default_read_window,
    scope="user",
)
async def get_context_state(
    domain: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """
    Récupère l'état contextuel actuel pour un domaine.

    Fournit un résumé de la liste active et de l'item courant (si défini).

    Args:
        domain: Domaine concerné ("contacts", "emails", "events").
        runtime: ToolRuntime injecté automatiquement (accès config, store, etc.)

    Returns:
        UnifiedToolOutput avec état contextuel.

    Note:
        Cet outil est en lecture seule et permet à l'agent de consulter
        l'état sans modifier quoi que ce soit.
    """
    try:
        # Validate runtime config using helper
        config = validate_runtime_config(runtime, "get_context_state")
        if isinstance(config, UnifiedToolOutput):
            return config  # Early return on validation error

        # Extract validated config
        user_id = config.user_id
        session_id = config.session_id
        store = config.store

        # Get list and current_item
        manager = ToolContextManager()
        context_list = await manager.get_list(user_id, session_id, domain, store)
        current_item = await manager.get_current_item(user_id, session_id, domain, store)

        if not context_list:
            return UnifiedToolOutput.failure(
                message=_("No active context for domain '{domain}'.").format(domain=domain),
                error_code="no_context",
            )

        logger.debug(
            "context_state_retrieved",
            user_id=str(user_id),
            domain=domain,
            items_count=len(context_list.items),
            has_current_item=current_item is not None,
        )

        return UnifiedToolOutput.action_success(
            message=_("Context state for '{domain}': {count} items").format(
                domain=domain, count=len(context_list.items)
            ),
            structured_data={
                "domain": domain,
                "items_count": len(context_list.items),
                "current_item": current_item,
                "last_query": context_list.metadata.query,
                FIELD_TIMESTAMP: context_list.metadata.timestamp,
                FIELD_TURN_ID: context_list.metadata.turn_id,
            },
        )

    except Exception as e:
        return handle_tool_exception(e, "get_context_state", {"domain": domain})


@tool
@track_tool_metrics(
    tool_name="get_context_list",
    agent_name=AGENT_CONTEXT,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().rate_limit_default_read_calls,
    window_seconds=lambda: get_settings().rate_limit_default_read_window,
    scope="user",
)
async def get_context_list(
    domain: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> UnifiedToolOutput:
    """
    Récupère la liste complète des items pour un domaine depuis le contexte.

    Cet outil permet d'accéder à TOUS les items d'une liste active (contacts, emails, etc.)
    issue d'une recherche précédente. Retourne le tableau complet (limité à MAX_CONTEXT_BATCH_SIZE).

    Args:
        domain: Domaine à interroger ("contacts", "emails", "events").
        runtime: ToolRuntime injecté automatiquement (accès config, store, etc.)

    Returns:
        UnifiedToolOutput avec items et metadata.

    Note:
        - READ-ONLY (pas d'approbation HITL requise)
        - Retourne les items AVEC leurs index originaux (0, 1, 2...)
        - Limite de sécurité: MAX_CONTEXT_BATCH_SIZE (évite OOM sur grandes listes)
    """
    try:
        # Validate runtime config using helper (validates user_id, session_id, and store)
        config = validate_runtime_config(runtime, "get_context_list")
        if isinstance(config, UnifiedToolOutput):
            return config  # Early return on validation error

        # Extract validated config
        user_id = config.user_id
        session_id = config.session_id
        store = config.store

        # Validate domain exists in registry
        try:
            ContextTypeRegistry.get_definition(domain)
        except ValueError:
            available_domains = ContextTypeRegistry.list_all()
            error_msg = _(
                "Domain '{domain}' not registered. Available domains: {available}"
            ).format(domain=domain, available=available_domains if available_domains else _("none"))

            logger.warning(
                "get_context_list_invalid_domain",
                domain=domain,
                available_domains=available_domains,
            )

            return UnifiedToolOutput.failure(
                message=error_msg,
                error_code="invalid_domain",
                metadata={"available_domains": available_domains},
            )

        # Get list from Store
        manager = ToolContextManager()
        context_list = await manager.get_list(
            user_id=user_id,
            session_id=session_id,
            domain=domain,
            store=store,
        )

        if not context_list or not context_list.items:
            logger.debug(
                "get_context_list_no_context",
                user_id=str(user_id),
                domain=domain,
            )

            return UnifiedToolOutput.failure(
                message=_(
                    "No active '{domain}' list in memory. Please perform a search first to create a context."
                ).format(domain=domain),
                error_code="no_context",
            )

        # Apply batch size limit (security + performance)
        settings = get_settings()
        max_batch_size = settings.MAX_CONTEXT_BATCH_SIZE
        total_available = len(context_list.items)
        truncated = total_available > max_batch_size

        if truncated:
            items = context_list.items[:max_batch_size]
            logger.warning(
                "context_list_truncated",
                user_id=str(user_id),
                domain=domain,
                total_available=total_available,
                returned=max_batch_size,
                turn_id=context_list.metadata.turn_id,
            )
        else:
            items = context_list.items

        # Return full list with metadata
        logger.info(
            "context_list_retrieved",
            user_id=str(user_id),
            domain=domain,
            items_count=len(items),
            truncated=truncated,
            turn_id=context_list.metadata.turn_id,
        )

        result_data = {
            "domain": domain,
            "items": items,
            "total_count": len(items),
            "truncated": truncated,
            FIELD_TURN_ID: context_list.metadata.turn_id,
            FIELD_QUERY: context_list.metadata.query,
            FIELD_TIMESTAMP: context_list.metadata.timestamp,
        }

        if truncated:
            result_data["total_available"] = total_available
            message = _("List truncated to {limit} items ({available} available)").format(
                limit=max_batch_size, available=total_available
            )
        else:
            message = _("{count} items retrieved for '{domain}'").format(
                count=len(items), domain=domain
            )

        return UnifiedToolOutput.action_success(message=message, structured_data=result_data)

    except Exception as e:
        logger.error(
            "get_context_list_error",
            domain=domain,
            error=str(e),
            exc_info=True,
        )

        return handle_tool_exception(e, "get_context_list", {"domain": domain})
