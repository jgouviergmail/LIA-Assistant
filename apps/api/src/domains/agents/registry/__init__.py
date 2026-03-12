"""
Agent Registry Package.

Centralized registry for agent management with automatic dependency injection.

Compliance: LangGraph v1.0 + LangChain v1.0 best practices
"""

from .agent_registry import (
    AgentAlreadyRegisteredError,
    AgentNotFoundError,
    AgentRegistry,
    AgentRegistryError,
    get_global_registry,
    reset_global_registry,
    set_global_registry,
)

__all__ = [
    "AgentAlreadyRegisteredError",
    "AgentNotFoundError",
    "AgentRegistry",
    "AgentRegistryError",
    "get_global_registry",
    "reset_global_registry",
    "set_global_registry",
]
