"""Iterative MCP membership uses the adapter's exact server identity."""

from collections.abc import Mapping

from langchain_core.tools import BaseTool

from src.core.constants import MCP_ITERATIVE_TASK_SUFFIX
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter


def user_tools_for_prefix(
    prefix: str, instances: Mapping[str, BaseTool]
) -> list[UserMCPToolAdapter]:
    """Resolve the allocated server label to one full UUID; ambiguity admits no tool."""
    ids = {
        instance.server_id
        for instance in instances.values()
        if isinstance(instance, UserMCPToolAdapter)
        and instance.server_name_label == f"user_{prefix}"
    }
    if len(ids) != 1:
        return []
    return [
        instance
        for instance in instances.values()
        if isinstance(instance, UserMCPToolAdapter) and instance.server_id in ids
    ]


def _task_owns_instance(task_name: str, server_key: object, name: str, instance: BaseTool) -> bool:
    if name == task_name:
        return False
    if isinstance(server_key, str):
        return isinstance(instance, UserMCPToolAdapter) and str(instance.server_id) == server_key
    # Compatibility for legacy contexts which have no server identity metadata.
    prefix = task_name.removesuffix(MCP_ITERATIVE_TASK_SUFFIX)
    return name.startswith(f"{prefix}_")


def iterative_user_instances(
    task_name: str, server_key: object, instances: Mapping[str, BaseTool]
) -> list[tuple[str, BaseTool]]:
    return [
        (name, instance)
        for name, instance in instances.items()
        if _task_owns_instance(task_name, server_key, name, instance)
    ]
