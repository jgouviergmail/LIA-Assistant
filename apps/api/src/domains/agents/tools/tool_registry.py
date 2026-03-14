"""
Central Tool Registry with Auto-Registration Decorator.

This module provides a decorator-based approach for tool registration,
eliminating the need for hardcoded tool lists in multiple files.

Architecture:
    - @registered_tool decorator wraps @tool and auto-registers
    - Global registry accessible via get_all_tools() / get_tool()
    - Thread-safe singleton pattern
    - Lazy loading support

Usage:
    # In any *_tools.py module:
    from src.domains.agents.tools.tool_registry import registered_tool

    @registered_tool
    async def my_new_tool(param: str) -> dict:
        '''Tool description for LLM.'''
        return {"result": "value"}

    # The tool is automatically registered and available everywhere!

    # To access tools:
    from src.domains.agents.tools.tool_registry import get_all_tools, get_tool
    all_tools = get_all_tools()  # Returns dict[str, BaseTool]
    my_tool = get_tool("my_new_tool")  # Returns single tool or None

Best Practices (2025):
    - Use @registered_tool instead of @tool for all agent tools
    - Tools auto-register on module import
    - No manual registration needed anywhere
    - Single source of truth

Migration:
    Replace: from langchain_core.tools import tool
             @tool
             async def my_tool(...):

    With:    from src.domains.agents.tools.tool_registry import registered_tool
             @registered_tool
             async def my_tool(...):
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, overload

import structlog
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.tools import tool as langchain_tool

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# =============================================================================
# Global Registry (Thread-Safe Singleton)
# =============================================================================

_TOOL_REGISTRY: dict[str, BaseTool] = {}
_REGISTRY_LOCK = threading.RLock()
_INITIALIZED = False

F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# Decorator: @registered_tool
# =============================================================================


@overload
def registered_tool[F: Callable[..., Any]](func: F) -> StructuredTool: ...


@overload
def registered_tool(
    *,
    return_direct: bool = False,
    args_schema: type | None = None,
    infer_schema: bool = True,
) -> Callable[[F], StructuredTool]: ...


def registered_tool[F: Callable[..., Any]](
    func: F | None = None,
    *,
    return_direct: bool = False,
    args_schema: type | None = None,
    infer_schema: bool = True,
) -> StructuredTool | Callable[[F], StructuredTool]:
    """
    Decorator that creates a LangChain tool AND auto-registers it.

    This is a drop-in replacement for @tool that also registers the tool
    in the global registry, making it available throughout the application.

    Args:
        func: The function to wrap (when used without parentheses)
        return_direct: Whether to return the tool output directly
        args_schema: Pydantic model for argument validation
        infer_schema: Whether to infer schema from function signature

    Returns:
        StructuredTool instance (registered in global registry)

    Example:
        @registered_tool
        async def get_weather(city: str) -> dict:
            '''Get weather for a city.'''
            return {"temp": 20}

        # Or with options:
        @registered_tool(return_direct=True)
        async def search_tool(query: str) -> str:
            '''Search for information.'''
            return "results"
    """

    def decorator(fn: F) -> StructuredTool:
        # Apply LangChain's @tool decorator
        wrapped_tool = langchain_tool(
            fn,
            return_direct=return_direct,
            args_schema=args_schema,
            infer_schema=infer_schema,
        )

        # Auto-register in global registry
        _register_tool(wrapped_tool)

        return wrapped_tool

    # Handle both @registered_tool and @registered_tool(...) syntax
    if func is not None:
        return decorator(func)
    return decorator


def _register_tool(tool_instance: BaseTool) -> None:
    """
    Register a tool in the global registry.

    Thread-safe registration with duplicate detection.

    Args:
        tool_instance: LangChain BaseTool to register
    """
    with _REGISTRY_LOCK:
        tool_name = tool_instance.name

        if tool_name in _TOOL_REGISTRY:
            # Already registered (can happen with module reloads)
            logger.debug(
                "tool_already_registered",
                tool_name=tool_name,
            )
            return

        _TOOL_REGISTRY[tool_name] = tool_instance
        logger.debug(
            "tool_auto_registered",
            tool_name=tool_name,
            tool_type=type(tool_instance).__name__,
        )


def register_external_tool(tool_instance: BaseTool) -> None:
    """
    Register an externally-created tool (e.g. MCP) into the central registry.

    Unlike @registered_tool (decorator for static tools defined at import time),
    this function supports dynamic tool registration at runtime. Used by MCP
    integration to register tools discovered from external servers.

    Thread-safe: delegates to _register_tool() which uses _REGISTRY_LOCK.

    Args:
        tool_instance: A BaseTool instance to register.

    Example:
        adapter = MCPToolAdapter.from_mcp_tool(server_name, tool_name, ...)
        register_external_tool(adapter)
    """
    _register_tool(tool_instance)


# =============================================================================
# Registry Access Functions
# =============================================================================


def get_tool(name: str) -> BaseTool | None:
    """
    Get a tool by name from the global registry.

    Args:
        name: Tool name (e.g., "get_contacts_tool")

    Returns:
        BaseTool instance or None if not found

    Example:
        tool = get_tool("get_route_tool")
        if tool:
            result = await tool.ainvoke(args, config)
    """
    with _REGISTRY_LOCK:
        return _TOOL_REGISTRY.get(name)


def get_tool_strict(name: str) -> BaseTool:
    """
    Get a tool by name, raising KeyError if not found.

    Args:
        name: Tool name

    Returns:
        BaseTool instance

    Raises:
        KeyError: If tool not found
    """
    with _REGISTRY_LOCK:
        if name not in _TOOL_REGISTRY:
            available = ", ".join(sorted(_TOOL_REGISTRY.keys()))
            raise KeyError(f"Tool '{name}' not found. Available: {available}")
        return _TOOL_REGISTRY[name]


def get_all_tools() -> dict[str, BaseTool]:
    """
    Get all registered tools.

    Returns:
        Dict mapping tool names to BaseTool instances

    Example:
        all_tools = get_all_tools()
        for name, tool in all_tools.items():
            print(f"{name}: {tool.description}")
    """
    with _REGISTRY_LOCK:
        return dict(_TOOL_REGISTRY)


def list_tool_names() -> list[str]:
    """
    List all registered tool names.

    Returns:
        Sorted list of tool names
    """
    with _REGISTRY_LOCK:
        return sorted(_TOOL_REGISTRY.keys())


def has_tool(name: str) -> bool:
    """Check if a tool is registered."""
    with _REGISTRY_LOCK:
        return name in _TOOL_REGISTRY


def tool_count() -> int:
    """Get the number of registered tools."""
    with _REGISTRY_LOCK:
        return len(_TOOL_REGISTRY)


# =============================================================================
# Initialization & Import Trigger
# =============================================================================


def ensure_tools_loaded() -> None:
    """
    Ensure all tool modules are imported (triggering auto-registration).

    Call this once at application startup to ensure all tools are registered.
    Tools auto-register on import, so this just imports all *_tools modules.

    This is called automatically by get_all_tools() if registry is empty,
    but can be called explicitly for eager loading.
    """
    global _INITIALIZED

    if _INITIALIZED:
        return

    with _REGISTRY_LOCK:
        if _INITIALIZED:
            return

        logger.info("tool_registry_loading_all_modules")

        # Import all tool modules to trigger @registered_tool decorators
        # Order doesn't matter - each module registers its own tools
        _import_tool_modules()

        _INITIALIZED = True

        logger.info(
            "tool_registry_initialized",
            total_tools=len(_TOOL_REGISTRY),
            tools=list(_TOOL_REGISTRY.keys()),
        )


def _import_tool_modules() -> None:
    """
    Import all tool modules and auto-register their tools.

    Supports two modes:
    1. Tools decorated with @registered_tool auto-register on import
    2. Tools decorated with @tool (legacy) are collected and registered

    This provides backward compatibility while encouraging migration
    to @registered_tool for new tools.
    """

    # List of (module_path, module_name) to import
    tool_modules = [
        # Google Services (OAuth)
        ("src.domains.agents.tools.calendar_tools", "calendar_tools"),
        ("src.domains.agents.tools.drive_tools", "drive_tools"),
        ("src.domains.agents.tools.emails_tools", "emails_tools"),
        ("src.domains.agents.tools.google_contacts_tools", "google_contacts_tools"),
        ("src.domains.agents.tools.labels_tools", "labels_tools"),
        ("src.domains.agents.tools.tasks_tools", "tasks_tools"),
        # Google Services (API Key)
        ("src.domains.agents.tools.places_tools", "places_tools"),
        ("src.domains.agents.tools.routes_tools", "routes_tools"),
        # External APIs
        ("src.domains.agents.tools.brave_tools", "brave_tools"),
        ("src.domains.agents.tools.perplexity_tools", "perplexity_tools"),
        ("src.domains.agents.tools.weather_tools", "weather_tools"),
        ("src.domains.agents.tools.web_search_tools", "web_search_tools"),
        ("src.domains.agents.tools.web_fetch_tools", "web_fetch_tools"),
        ("src.domains.agents.tools.wikipedia_tools", "wikipedia_tools"),
        # Internal Tools
        ("src.domains.agents.tools.context_tools", "context_tools"),
        ("src.domains.agents.tools.reminder_tools", "reminder_tools"),
        ("src.domains.agents.tools.local_query_tool", "local_query_tool"),
    ]

    # Skills tools: only register when feature is enabled
    from src.core.config import get_settings

    if getattr(get_settings(), "skills_enabled", False):
        tool_modules.append(("src.domains.skills.tools", "skills_tools"))

    for module_path, module_name in tool_modules:
        try:
            # Dynamic import
            import importlib

            module = importlib.import_module(module_path)

            # Auto-collect tools from module (backward compatibility)
            # This finds tools decorated with @tool (not @registered_tool)
            _collect_tools_from_module(module, module_name)

        except ImportError as e:
            logger.warning(
                "tool_module_import_failed",
                module=module_name,
                error=str(e),
            )
        except Exception as e:
            logger.error(
                "tool_module_load_error",
                module=module_name,
                error=str(e),
            )


def _collect_tools_from_module(module: Any, module_name: str) -> None:
    """
    Collect and register BaseTool instances from a module.

    This provides backward compatibility for tools using @tool decorator
    instead of @registered_tool.

    Args:
        module: Imported module object
        module_name: Module name for logging
    """
    collected_count = 0

    for attr_name in dir(module):
        # Skip private attributes
        if attr_name.startswith("_"):
            continue

        try:
            attr = getattr(module, attr_name)

            # Check if it's a BaseTool instance (from @tool decorator)
            if isinstance(attr, BaseTool):
                tool_name = attr.name

                # Register if not already registered
                with _REGISTRY_LOCK:
                    if tool_name not in _TOOL_REGISTRY:
                        _TOOL_REGISTRY[tool_name] = attr
                        collected_count += 1
                        logger.debug(
                            "tool_collected_from_module",
                            tool_name=tool_name,
                            module=module_name,
                        )

        except Exception:
            # Skip attributes that can't be accessed
            pass

    if collected_count > 0:
        logger.debug(
            "tools_collected_from_module",
            module=module_name,
            count=collected_count,
        )


# =============================================================================
# Reset (for testing)
# =============================================================================


def reset_registry() -> None:
    """
    Reset the global registry (for testing only).

    WARNING: Only use in tests! This clears all registered tools.
    """
    global _INITIALIZED
    with _REGISTRY_LOCK:
        _TOOL_REGISTRY.clear()
        _INITIALIZED = False
        logger.warning("tool_registry_reset")
