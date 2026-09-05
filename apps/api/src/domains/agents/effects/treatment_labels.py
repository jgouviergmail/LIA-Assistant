"""Naming a consultation for a human (ADR-263, lot 4).

A treatment row records WHICH capability answered, never what was asked, so its
readable name cannot be built from the call the way an effect's label is. It is
built from the capability's **domain** — and the domain vocabulary already has
a single source of truth in this codebase (``DOMAIN_REGISTRY``).

That is a deliberate choice over the alternative, and it was measured before
being made. Reusing the gear trace's ``execution.steps`` wording would have
covered 81 of the 119 registered tools with progress sentences ("Activating
Hue scene..."), leaving 38 tools showing a raw technical name and costing six
new strings for every tool ever added. Twenty-eight domain nouns cover
everything, forever, and the tool name is shown next to them, so the technical
half is not lost — it is simply not the half a person reads first.

Resolution order, most authoritative first:

1. an explicit entry, for the few whose name says nothing (``get_calls``);
2. the tool's manifest, whose ``agent`` names its domain (96 of 119);
3. the tool's NAME, matched against the same registry (the 23 with no manifest
   — the browser sub-tools and the legacy readers);
4. :data:`UNKNOWN_DOMAIN`, which the boot guard refuses to let grow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import structlog

from src.core.constants import MCP_TOOL_NAME_PREFIX
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.domains.agents.registry import AgentRegistry

logger = structlog.get_logger(__name__)

#: What a row says when nothing else could be established. It IS a translatable
#: key: a register must never show a technical name, not even for a surprise.
UNKNOWN_DOMAIN: Final[str] = "unknown"

#: Prefix under which a draft executor is recorded (``draft:email``).
DRAFT_TOOL_PREFIX: Final[str] = "draft:"

#: Leading segments that name an action rather than a subject.
_VERB_SEGMENTS: Final[frozenset[str]] = frozenset(
    {
        "activate",
        "append",
        "apply",
        "cancel",
        "compare",
        "complete",
        "control",
        "create",
        "delegate",
        "delete",
        "detect",
        "edit",
        "fetch",
        "find",
        "forward",
        "generate",
        "get",
        "import",
        "list",
        "read",
        "remove",
        "reply",
        "resolve",
        "run",
        "search",
        "send",
        "set",
        "toggle",
        "unified",
        "update",
        "write",
    }
)

#: Names whose subject is not the domain they belong to. Each entry is a fact
#: about the vocabulary, not a workaround: "calls" is not a domain, telephony
#: is; a peer message belongs to the peer domain, not to messaging.
TREATMENT_DOMAIN_OVERRIDES: Final[dict[str, str]] = {
    "get_calls_tool": "telephony",
    "local_query_engine_tool": "query",
    "claude_server_task_tool": "devops",
    "delegate_to_sub_agent_tool": "sub_agent",
    "resolve_reference": "context",
    "activate_skill": "skill",
    "import_user_skill": "skill",
    "read_skill_resource": "skill",
    "run_skill_script": "skill",
    "run_python_tool": "python_sandbox",
    "search_user_documents_tool": "document",
    "get_open_loops_tool": "peer",
    "get_person_overview_tool": "contact",
    # ``place_phone_call`` starts with a segment that IS a domain: without this
    # entry the name derivation would read a phone call as a PLACE. It resolves
    # correctly through its manifest today, so the defect would only appear the
    # day the manifest is absent — an override is the honest fix.
    "place_phone_call_tool": "telephony",
}


def _reverse_agent_map() -> dict[str, str]:
    """Map each agent name to the domain that declares it.

    Returns:
        ``{"contact_agent": "contact", ...}``, built from the taxonomy so the
        domain of a manifest is READ from the registry rather than parsed.
    """
    return {
        agent_name: domain
        for domain, config in DOMAIN_REGISTRY.items()
        for agent_name in config.agent_names
    }


_AGENT_TO_DOMAIN: Final[dict[str, str]] = _reverse_agent_map()

#: Memoised resolutions. The write path resolves the domain of EVERY row it
#: persists, and a manifest read takes the registry's lock — a runaway batch
#: would take it once per row. Same doctrine as ``resolve_policy``: only
#: answers that cannot change are cached, so a lookup made before the catalogue
#: loaded never freezes.
_domain_cache: dict[str, str] = {}


def reset_domain_cache() -> None:
    """Forget the memoised domains (tests, and a catalogue reload)."""
    _domain_cache.clear()


def _from_manifest(tool_name: str, registry: AgentRegistry | None) -> str | None:
    """The domain the tool's own manifest declares, when it has one.

    Args:
        tool_name: The registered tool name.
        registry: The registry to read, or None to read the global one.

    Returns:
        The domain, or None when the tool has no manifest.
    """
    try:
        if registry is None:
            from src.domains.agents.registry import get_global_registry

            registry = get_global_registry()
        agent = registry.get_tool_manifest(tool_name).agent
    except Exception:  # noqa: BLE001 - no manifest, or no registry loaded yet
        return None
    known = _AGENT_TO_DOMAIN.get(agent)
    if known is not None:
        return known
    # An agent may qualify its family (``devops_diagnostics_agent``): the
    # taxonomy knows ``devops`` and not the qualified spelling, so the leading
    # segment is tried before falling back to the whole name. Measured
    # 2026-09-04: without this, the four self-diagnostics tools resolved to
    # ``devops_diagnostics``, which no wording table names — and the boot guard
    # correctly refused to start the API.
    stem = agent.removesuffix("_agent")
    head = stem.split("_")[0]
    return (head if head in DOMAIN_REGISTRY else stem) or None


def _from_name(tool_name: str) -> str | None:
    """The domain the NAME names, matched against the taxonomy.

    ``search_emails_tool`` gives ``emails`` gives ``email``;
    ``browser_click_tool`` gives ``browser``; ``get_current_weather_tool``
    gives ``weather``, which is why the LAST segment is tried too — an
    adjective can lead ("current weather") as easily as a subject can.
    Nothing is invented: every candidate is looked up in the registry, so a
    spelling that matches no domain yields nothing rather than a guess.

    Args:
        tool_name: The registered tool name.

    Returns:
        The domain, or None.
    """
    segments = [
        segment
        for index, segment in enumerate(tool_name.removesuffix("_tool").split("_"))
        if not (index == 0 and segment in _VERB_SEGMENTS)
    ]
    if not segments:
        return None
    body = "_".join(segments)
    for candidate in (body, body.removesuffix("_details"), segments[0], segments[-1]):
        for spelling in (candidate, candidate.removesuffix("s")):
            if spelling in DOMAIN_REGISTRY:
                return spelling
    return None


def treatment_domain(tool_name: str, registry: AgentRegistry | None = None) -> str:
    """The domain a consultation belongs to, for reading.

    Args:
        tool_name: The registered tool name, or a ``draft:<family>`` executor.
        registry: The registry to read, or None to read the global one.

    Returns:
        A domain key, always translatable — :data:`UNKNOWN_DOMAIN` at worst.
    """
    if tool_name.startswith(MCP_TOOL_NAME_PREFIX):
        # A server names and shapes its own tools; reading meaning into that
        # name would be guessing on someone else's vocabulary (ADR-255).
        return "mcp"
    if tool_name.startswith(DRAFT_TOOL_PREFIX):
        family = tool_name.removeprefix(DRAFT_TOOL_PREFIX)
        return family if family in DOMAIN_REGISTRY else UNKNOWN_DOMAIN
    override = TREATMENT_DOMAIN_OVERRIDES.get(tool_name)
    if override is not None:
        return override
    cached = _domain_cache.get(tool_name)
    if cached is not None:
        return cached

    declared = _from_manifest(tool_name, registry)
    if declared is not None:
        # Authoritative and stable: worth remembering.
        _domain_cache[tool_name] = declared
        return declared
    # A manifest MISS is not cached: tools resolve before the catalogue loads,
    # and freezing the name-derived answer would outrank a manifest that lands
    # a moment later — the very precedence this function declares.
    return _from_name(tool_name) or UNKNOWN_DOMAIN


def assert_treatment_domain_completeness(registry: AgentRegistry | None = None) -> None:
    """Refuse to boot with a capability nobody could read in the register.

    ADR-085 placement: a register that shows ``get_calls_tool`` to a user is a
    silent failure of the surface, not of the pipeline, so it is caught where
    every other completeness rule is — at boot, and in CI before that.

    Args:
        registry: The registry to read, or None to read the global one.

    Raises:
        AssertionError: Listing every capability with no readable domain.
    """
    from src.core.i18n import DEFAULT_LANGUAGE
    from src.core.i18n_treatments import TREATMENT_DOMAIN_LABELS
    from src.domains.agents.tools.tool_registry import get_all_tools

    # The table is language-major, so membership is asked of ONE language's
    # wordings; that the six agree is the neighbouring test's property, not
    # this guard's. Asking it of the outer mapping compares a domain to a
    # language code and finds nothing — which is how this guard first read
    # "all 119 capabilities are unreadable".
    known = set(TREATMENT_DOMAIN_LABELS.get(DEFAULT_LANGUAGE, TREATMENT_DOMAIN_LABELS["en"]))
    unreadable = sorted(
        name for name in get_all_tools() if treatment_domain(name, registry) not in known
    )
    if unreadable:
        raise AssertionError(
            f"{len(unreadable)} capability(ies) have no readable domain in the "
            f"consultation register: {unreadable}. Declare the domain in "
            "``DOMAIN_REGISTRY``, or add an entry to "
            "``TREATMENT_DOMAIN_OVERRIDES`` with the reason its name says nothing."
        )
