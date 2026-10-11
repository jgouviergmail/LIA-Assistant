"""Serializable proof invalidation, isolated to one pipeline execution plan."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig

from src.domains.agents.registry.catalogue import is_read_only_tool
from src.domains.agents.semantic.manifest_semantics import available_manifest
from src.domains.agents.semantic.value_bindings import SEMANTIC_SOURCE_VALID_AFTER_KEY

_CLOCK_KEY = "_semantic_plan_proof_clock"


def plan_proof_config(config: RunnableConfig) -> RunnableConfig:
    """Copy request config and give only this plan a shared JSON-compatible clock."""
    configurable = dict(config.get("configurable") or {})
    configurable[_CLOCK_KEY] = {"valid_after": effective_source_cutoff(config)}
    return {**config, "configurable": configurable, "metadata": dict(config.get("metadata") or {})}


def effective_source_cutoff(config: RunnableConfig) -> str | None:
    """Read the latest plan-local mutation bound immediately before observation."""
    configurable = config.get("configurable") or {}
    clock = configurable.get(_CLOCK_KEY)
    cutoff = (
        clock.get("valid_after")
        if isinstance(clock, dict)
        else configurable.get(SEMANTIC_SOURCE_VALID_AFTER_KEY)
    )
    return cutoff if isinstance(cutoff, str) else None


def mark_plan_mutation_attempt(config: RunnableConfig, tool_name: str) -> None:
    """Advance only a plan's private clock just before a mutation is invoked.

    Failed, timed-out or delegated invocations may have changed remote data,
    so they invalidate older facts. A guard failure before invocation does not.
    The shared request config and historical registry cards remain unchanged.
    """
    clock = (config.get("configurable") or {}).get(_CLOCK_KEY)
    manifest = available_manifest(tool_name)
    if not isinstance(clock, dict) or manifest is None:
        return
    if is_read_only_tool(manifest) and not manifest.delegates_execution:
        return
    clock["valid_after"] = datetime.now(UTC).isoformat()


@contextmanager
def plan_mutation_scope(config: RunnableConfig, tool_name: str) -> Iterator[None]:
    """Reads completed during an in-flight write are stale after it returns or fails."""
    mark_plan_mutation_attempt(config, tool_name)
    try:
        yield
    finally:
        mark_plan_mutation_attempt(config, tool_name)
