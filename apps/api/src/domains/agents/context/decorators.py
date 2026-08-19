"""
Decorators for automatic tool context persistence.

Provides zero-boilerplate auto-save functionality for LangChain tools.

Usage:
    @tool
    @auto_save_context("contacts")
    async def search_contacts_tool(
        query: str,
        runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    ) -> str:
        # ... tool logic ...
        return json.dumps({"success": True, "contacts": [...]})

    # Context automatically saved to Store after successful execution.
    # Config and store are taken from the injected ToolRuntime (ADR-231) —
    # the former config/store parameters are gone.

Data Registry Mode Support (Phase 5.2 BugFix 2025-11-26):
    Registry-enabled tools return UnifiedToolOutput instead of JSON string.
    This decorator now detects UnifiedToolOutput (and legacy StandardToolOutput) and:
    1. Skips JSON parsing (already structured data)
    2. Extracts contacts/emails from registry_updates for context saving
    3. Returns output unchanged (for parallel_executor to handle)

    Migration (2025-12-30): Updated to check for both UnifiedToolOutput and StandardToolOutput.
"""

import json
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, Union

from langchain.tools import ToolRuntime

from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.tools.output import StandardToolOutput, UnifiedToolOutput

logger = get_logger(__name__)


def _resolve_runtime(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> ToolRuntime[LiaRuntimeContext, Any] | None:
    """Find the ToolRuntime the tool layer injected, keyword or positional.

    Both output paths of ``auto_save_context`` need it, and before ADR-231 each
    resolved it differently: the registry path scanned positional arguments, the
    JSON path did not. Same intent, two implementations, one weaker — so a tool
    returning a JSON string with a positional runtime silently skipped its save.

    Args:
        args: Positional arguments the wrapped tool received.
        kwargs: Keyword arguments the wrapped tool received.

    Returns:
        The injected ToolRuntime, or None when the tool ran outside the agent
        layer (auto-save is a side effect and must never break its tool).
    """
    runtime = kwargs.get("runtime")
    if runtime is not None:
        return runtime
    return next((arg for arg in args if isinstance(arg, ToolRuntime)), None)


def auto_save_context(
    context_type: str,
    context_save_mode: ContextSaveMode | None = None,
) -> Callable:
    """
    Decorator for automatic tool context persistence.

    Automatically saves successful tool results to LangGraph BaseStore
    with zero boilerplate in tool code.

    Requirements:
        - Tool must accept an injected ``runtime: ToolRuntime`` parameter (the
          decorator reads config and store from it — ADR-231; the former
          config/store parameters are gone)
        - Tool must return a JSON string with {"success": True, "{context_type}s":
          [...]} or a UnifiedToolOutput carrying registry_updates

    Args:
        context_type: Context type identifier ("contacts", "emails", "events").
        context_save_mode: Explicit LIST/DETAILS override for auto-save classification.
            If None, uses name-based heuristic in classify_save_mode().

    Returns:
        Decorator function.

    Example:
        @tool
        @auto_save_context("contacts")
        async def search_contacts_tool(
            query: str,
            runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
        ) -> str:
            # Tool logic
            results = await search_contacts(query)

            # Return JSON (auto-saved by decorator)
            return json.dumps({
                "success": True,
                "contacts": results,  # Key must match context_type + "s"
                FIELD_QUERY: query
            })

    Flow:
        1. Execute original tool function
        2. Parse JSON result
        3. If success=True → Auto-save to Store via ToolContextManager
        4. If error or success=False → Skip auto-save
        5. Return original result (unmodified)

    Error Handling:
        - Auto-save failures are logged but DO NOT fail the tool
        - Tool always returns its original result
        - Fail-safe: context persistence never breaks tool execution

    Integration:
        - Works with LangChain @tool decorator
        - Compatible with ReAct agents
        - Store arrives on the injected ToolRuntime (no manual wiring)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(
            *args: Any, **kwargs: Any
        ) -> Union[str, "StandardToolOutput", "UnifiedToolOutput"]:
            # Execute original tool
            tool_result = await func(*args, **kwargs)

            # ============================================================================
            # DATA REGISTRY MODE SUPPORT (Phase 5.2 BugFix 2025-11-26)
            # ============================================================================
            # Registry-enabled tools return UnifiedToolOutput (or legacy StandardToolOutput).
            # Detect structured output and handle accordingly:
            # 1. Extract data from registry_updates for context saving
            # 2. Return output unchanged (parallel_executor handles it)
            # ============================================================================
            from src.domains.agents.tools.output import StandardToolOutput, UnifiedToolOutput

            if isinstance(tool_result, StandardToolOutput | UnifiedToolOutput):
                # Registry mode: Structured output returned
                logger.debug(
                    "auto_save_registry_mode_detected",
                    context_type=context_type,
                    tool_name=func.__name__,
                    registry_items_count=len(tool_result.registry_updates),
                )

                # Attempt auto-save from registry_updates (fail-safe)
                try:
                    runtime = _resolve_runtime(args, kwargs)

                    # No ToolRuntime means the tool ran outside the agent layer.
                    # The former fallback read ``config["store"]`` — one nesting
                    # level above where LIA writes it (``configurable["store"]``)
                    # — so it could only ever yield None, and it was unreachable
                    # anyway: no tool declares a ``config`` parameter. Skipping is
                    # the honest behaviour; auto-save is a side effect and must
                    # never break the tool it wraps (ADR-231).
                    if not runtime:
                        logger.debug(
                            "auto_save_registry_skipped_missing_runtime",
                            context_type=context_type,
                            tool_name=func.__name__,
                        )
                        return tool_result

                    config = runtime.config
                    store = runtime.store

                    if store and config:
                        # Extract data from registry_updates based on context_type
                        items_list = []
                        for _item_id, registry_item in tool_result.registry_updates.items():
                            # registry_item is a RegistryItem with type and payload
                            item_type = (
                                registry_item.type.value
                                if hasattr(registry_item.type, "value")
                                else str(registry_item.type)
                            )
                            # Flexible matching: Allow plural/singular mismatch
                            # e.g. "CONTACT" (item) matches "contacts" (context)
                            # e.g. "PLACE" (item) matches "places" (context)
                            item_type_upper = item_type.upper()
                            context_type_upper = context_type.upper()

                            if context_type_upper.startswith(
                                item_type_upper
                            ) or item_type_upper.startswith(context_type_upper):
                                items_list.append(registry_item.payload)

                        if items_list:
                            # Build result_data for ToolContextManager
                            # Smart pluralization for key generation (must match manager.py logic)
                            items_key = (
                                f"{context_type}s"
                                if not context_type.endswith("s")
                                else context_type
                            )

                            # Inject tool_name so manager can classify save mode correctly
                            from src.core.field_names import FIELD_TOOL_NAME

                            result_data = {
                                "success": True,
                                items_key: items_list,
                                FIELD_TOOL_NAME: func.__name__,
                            }

                            # Tool's own context_save_mode wins over decorator's static mode.
                            # Unified tools set LIST (search) or CURRENT (ID fetch) per-call.
                            effective_mode = (
                                tool_result.context_save_mode
                                if hasattr(tool_result, "context_save_mode")
                                and tool_result.context_save_mode is not None
                                else context_save_mode
                            )

                            manager = ToolContextManager()
                            await manager.auto_save(
                                context_type=context_type,
                                result_data=result_data,
                                config=config,
                                store=store,
                                explicit_mode=effective_mode,
                            )

                            # Mark as saved so parallel_executor.auto_save_wave_contexts
                            # can skip the duplicate save path for decorated tools.
                            tool_result.tool_metadata["_tcm_saved"] = True

                            logger.debug(
                                "auto_save_registry_completed",
                                context_type=context_type,
                                tool_name=func.__name__,
                                items_count=len(items_list),
                            )
                        else:
                            logger.debug(
                                "auto_save_registry_skipped_no_matching_items",
                                context_type=context_type,
                                tool_name=func.__name__,
                                registry_types=[
                                    (
                                        item.type.value
                                        if hasattr(item.type, "value")
                                        else str(item.type)
                                    )
                                    for item in tool_result.registry_updates.values()
                                ],
                            )
                    else:
                        logger.debug(
                            "auto_save_registry_skipped_missing_store",
                            context_type=context_type,
                            tool_name=func.__name__,
                        )

                except Exception as e:
                    # Never fail tool if auto-save fails
                    logger.error(
                        "auto_save_registry_failed",
                        context_type=context_type,
                        tool_name=func.__name__,
                        error=str(e),
                        exc_info=True,
                    )

                # Return structured output unchanged for parallel_executor
                return tool_result

            # ============================================================================
            # LEGACY MODE: JSON string result
            # ============================================================================
            result_json = tool_result

            # Attempt auto-save (fail-safe - never break tool)
            try:
                # Parse result
                result = json.loads(result_json)

                # Only save if success
                if not result.get("success"):
                    logger.debug(
                        "auto_save_skipped_not_success",
                        context_type=context_type,
                        tool_name=func.__name__,
                    )
                    return result_json

                # The ToolRuntime is the only supported injection path; see the
                # registry branch above for why the config+store fallback was
                # removed (wrong nesting level, and unreachable).
                runtime = _resolve_runtime(args, kwargs)
                if not runtime:
                    logger.warning(
                        "auto_save_skipped_missing_runtime",
                        context_type=context_type,
                        tool_name=func.__name__,
                    )
                    return result_json

                config = runtime.config
                store = runtime.store

                if not store:
                    logger.warning(
                        "auto_save_skipped_missing_store",
                        context_type=context_type,
                        tool_name=func.__name__,
                    )
                    return result_json

                # Auto-save via manager
                manager = ToolContextManager()
                await manager.auto_save(
                    context_type=context_type,
                    result_data=result,
                    config=config,
                    store=store,
                    explicit_mode=context_save_mode,
                )

                logger.debug(
                    "auto_save_completed",
                    context_type=context_type,
                    tool_name=func.__name__,
                )

            except json.JSONDecodeError as e:
                logger.error(
                    "auto_save_failed_invalid_json",
                    context_type=context_type,
                    tool_name=func.__name__,
                    error=str(e),
                )
            except Exception as e:
                # Never fail tool if auto-save fails
                logger.error(
                    "auto_save_failed",
                    context_type=context_type,
                    tool_name=func.__name__,
                    error=str(e),
                    exc_info=True,
                )

            # Always return original result
            return result_json

        return wrapper

    return decorator
