"""Which domain does a tool belong to — asked of the MANIFEST, not the name.

Two guards need this answer and both used to derive it from the tool NAME,
which lies whenever a tool is named after anything but its domain:

- ``place_phone_call_tool`` starts with ``place_``, so it resolved to the
  ``places`` domain: a single-step call plan looked like it had dropped its own
  ``telephony`` domain, firing the "primary_domain_uncovered" rule (and its LLM
  validation) on every call request — while the two-step plan that genuinely
  dropped it went unchecked (prod 2026-08-01);
- ``browser_task_tool`` matched ``task`` and answered ``tasks`` where it
  actually produces ``browsers``.

Same doctrine as ``plan_predicates._declared_mutation_flag``: an explicitly
declared catalogue value WINS over the heuristic, which survives as the
fallback for tools with no manifest (MCP, skills, tests).

Lives beside ``domain_taxonomy`` rather than inside it: that module is frozen
at its audited size, and this is a cohesive question of its own — "place this
tool" — with the registry as its only dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.agents.registry.catalogue import ToolManifest


def _manifest_or_none(tool_name: str) -> ToolManifest | None:
    """The catalogue manifest for ``tool_name``, or None when there is none.

    Args:
        tool_name: Tool name to look up in the global catalogue.

    Returns:
        The manifest, or ``None`` for an unregistered tool (MCP, skill) or when
        the registry is not available yet (early boot, isolated tests).
    """
    # Local import: the registry imports the taxonomy, which imports this
    # module. Keeping the edge inside the call avoids the cycle while leaving
    # it visible to readers.
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.catalogue import ToolManifestNotFound

    try:
        return get_global_registry().get_tool_manifest(tool_name)
    except (ToolManifestNotFound, KeyError, ValueError, AttributeError, RuntimeError):
        return None


def declared_result_key(tool_name: str) -> str | None:
    """The result_key a manifest DECLARES, through its ``context_key``.

    ``context_key`` is the collection the tool saves its items under, which is
    exactly the key a ``$steps.<step>.<key>`` reference addresses — so it is
    the declaration to trust over any naming convention.

    Args:
        tool_name: Tool name to look up.

    Returns:
        The declared key, or ``None`` when the tool has no manifest or declares
        no ``context_key`` (an action tool produces no collection). The caller
        then falls back to the name convention.
    """
    manifest = _manifest_or_none(tool_name)
    if manifest is None:
        return None
    return str(manifest.context_key) if manifest.context_key else None


def tool_serves_domain(tool_name: str, domain: str) -> bool | None:
    """Whether a tool belongs to ``domain`` according to its manifest.

    Both halves of "belongs" count: the tool's home domain (derived from its
    agent) AND every domain it declares in ``serves_domains``. Reading only the
    home would break the 360° tool, which lives in ``contact`` and serves
    ``peer`` (ADR-191) — a single-step 360° on a peer would look like it had
    dropped its primary domain and be sent back for a replan.

    Args:
        tool_name: Tool to place.
        domain: Singular domain name from QueryIntelligence (e.g. "telephony").

    Returns:
        ``True``/``False`` when the tool has a manifest, ``None`` when it has
        none — the caller then has no evidence about that step.
    """
    manifest = _manifest_or_none(tool_name)
    if manifest is None:
        return None
    home = (manifest.agent or "").removesuffix("_agent")
    return home == domain or domain in (manifest.serves_domains or [])


__all__ = ["declared_result_key", "tool_serves_domain"]
