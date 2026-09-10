"""Administrable platform capabilities.

An operator must be able to switch speech, images, documents or the browser
off without a deployment — on a public demonstrator, but equally on a private
instance whose owner does not want to pay for image generation this month.

Design:

- **Two bounds, the smallest wins.** The environment flag is the DEPLOYMENT
  ceiling; the admin switch acts inside it. An operator can always turn a
  capability OFF, never on what the deployment forbids. Same doctrine as the
  instance spend ceiling (ADR-216); here the composition is a plain AND.
- **One declaration feeds everything.** ``CAPABILITY_SPECS`` generates the
  settings-store entries (see ``system_settings/registry.py``), so a new
  capability cannot ship with an undeclared key — the store's own boot assert
  covers it for free.
- **A switch that governs nothing is a lie.** Each capability names the agents
  it removes and/or declares that routes enforce it; the boot checks the named
  agents actually exist.
- **Reading never raises.** These checks sit on the request path: any failure
  resolves to the environment value — today's behaviour — never to a surprise
  "on" or a 500.

Vocabulary: ``PlatformCapability`` is what an OPERATOR switches.
``DirectiveCapability`` (``agents/capability_directives.py``, ADR-191) is what
a CLIENT invokes by name. Different registries, different lifetimes,
deliberately different names.

Created: 2026-08-06 (live-demonstrator programme, lot 3)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_CAPABILITY_PREFIX
from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.registry import (
    SETTING_SPECS,
    SettingSpec,
    decode_bool,
    encode_bool,
    read_setting,
)

if TYPE_CHECKING:
    from src.domains.agents.registry import AgentRegistry

logger = structlog.get_logger(__name__)


class PlatformCapability(str, Enum):
    """A capability an administrator can switch on or off at runtime."""

    STT = "stt"
    TTS = "tts"
    IMAGE_GENERATION = "image_generation"
    DOCUMENT_GENERATION = "document_generation"
    ATTACHMENTS = "attachments"
    RAG_SPACES = "rag_spaces"
    WEB_SEARCH = "web_search"
    BROWSER = "browser"
    SKILLS = "skills"
    MCP = "mcp"
    TELEPHONY = "telephony"
    MEETINGS = "meetings"
    # B7 (2026-09-10) — thirteen features that shipped without a switch. The
    # panel offered twelve capabilities while the product had a workboard,
    # journals, habits, proactive notifications, peer connections, a
    # psychological profile, external channels, open loops, long-term memory,
    # interest tracking, relationship debriefs, delegated sub-agents and an
    # ephemeral Python sandbox.
    WORKBOARD = "workboard"
    JOURNALS = "journals"
    HABITS = "habits"
    HEARTBEAT = "heartbeat"
    PEERS = "peers"
    PSYCHE = "psyche"
    CHANNELS = "channels"
    OPEN_LOOPS = "open_loops"
    MEMORY = "memory"
    INTERESTS = "interests"
    RELATION_DEBRIEF = "relation_debrief"
    SUB_AGENTS = "sub_agents"
    PYTHON_SANDBOX = "python_sandbox"


@dataclass(frozen=True)
class CapabilitySpec:
    """How one capability is bounded, stored and enforced.

    Attributes:
        capability: The member this spec describes.
        env_flag: Settings attribute carrying the deployment ceiling.
        setting_key: Settings-store key carrying the operator switch.
        agents: Agent names removed from the planner catalogue when off.
            Empty when the capability has no agent of its own.
        tools: Tool names removed from the planner catalogue when off, for a
            capability that owns NO agent — delegation lives in the graph
            (ADR-083 removed its REST surface) and the sandbox is one tool
            (ADR-249). A planner that SEES a tool it cannot run plans an
            invented dead end, and the person reads a failure where they should
            have read « I cannot do that ». Never declared beside ``agents``:
            an agent's manifests already carry every tool it owns, and two
            sources for one hiding is two authorities.
        route_enforced: Whether an HTTP/WebSocket router refuses it when off.
        service_enforced: Whether an internal service chokepoint refuses it
            when off. Speech synthesis has no route of its own — it is
            produced inside the chat stream — so a router dependency would
            enforce nothing.
        label_key: i18n key the frontend resolves for the switch label.
        family: Which group the admin panel draws it in. Twenty-five switches
            in one column is a wall an operator scrolls past; grouped, the
            panel answers « what can this instance do » by section. Declared
            here rather than in the frontend so the two cannot disagree about
            where a capability belongs.
    """

    capability: PlatformCapability
    env_flag: str
    setting_key: SystemSettingKey
    agents: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    route_enforced: bool = False
    service_enforced: bool = False
    label_key: str = field(default="")
    family: str = "assistant"

    def __post_init__(self) -> None:
        if not self.label_key:
            object.__setattr__(self, "label_key", f"capabilities.items.{self.capability.value}")


CAPABILITY_SPECS: dict[PlatformCapability, CapabilitySpec] = {
    PlatformCapability.STT: CapabilitySpec(
        capability=PlatformCapability.STT,
        family="media",
        env_flag="voice_stt_enabled",
        setting_key=SystemSettingKey.CAPABILITY_STT_ENABLED,
        # Speech has no agent: it is a transport (WebSocket) plus routes.
        route_enforced=True,
    ),
    PlatformCapability.TTS: CapabilitySpec(
        capability=PlatformCapability.TTS,
        family="media",
        env_flag="voice_tts_enabled",
        setting_key=SystemSettingKey.CAPABILITY_TTS_ENABLED,
        # No route of its own: speech is synthesized inside the chat stream,
        # so the gate lives at the single voice-synthesis chokepoint.
        service_enforced=True,
    ),
    PlatformCapability.IMAGE_GENERATION: CapabilitySpec(
        capability=PlatformCapability.IMAGE_GENERATION,
        family="media",
        env_flag="image_generation_enabled",
        setting_key=SystemSettingKey.CAPABILITY_IMAGE_GENERATION_ENABLED,
        agents=("image_generation_agent",),
        route_enforced=True,
    ),
    PlatformCapability.DOCUMENT_GENERATION: CapabilitySpec(
        capability=PlatformCapability.DOCUMENT_GENERATION,
        family="media",
        env_flag="document_generation_enabled",
        setting_key=SystemSettingKey.CAPABILITY_DOCUMENT_GENERATION_ENABLED,
        agents=("document_generation_agent",),
        # No route of its own: the gate lives at the generate_document tool
        # entry (settings flag + user opt-in), like TTS's synthesis chokepoint.
        service_enforced=True,
    ),
    PlatformCapability.ATTACHMENTS: CapabilitySpec(
        capability=PlatformCapability.ATTACHMENTS,
        family="media",
        env_flag="attachments_enabled",
        setting_key=SystemSettingKey.CAPABILITY_ATTACHMENTS_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.RAG_SPACES: CapabilitySpec(
        capability=PlatformCapability.RAG_SPACES,
        family="knowledge",
        env_flag="rag_spaces_enabled",
        setting_key=SystemSettingKey.CAPABILITY_RAG_SPACES_ENABLED,
        agents=("document_agent",),
        route_enforced=True,
    ),
    PlatformCapability.WEB_SEARCH: CapabilitySpec(
        capability=PlatformCapability.WEB_SEARCH,
        family="reach",
        env_flag="web_search_enabled",
        setting_key=SystemSettingKey.CAPABILITY_WEB_SEARCH_ENABLED,
        agents=(
            "brave_agent",
            "perplexity_agent",
            "web_search_agent",
            "web_fetch_agent",
        ),
    ),
    PlatformCapability.BROWSER: CapabilitySpec(
        capability=PlatformCapability.BROWSER,
        family="reach",
        env_flag="browser_enabled",
        setting_key=SystemSettingKey.CAPABILITY_BROWSER_ENABLED,
        agents=("browser_agent",),
    ),
    PlatformCapability.SKILLS: CapabilitySpec(
        capability=PlatformCapability.SKILLS,
        family="reach",
        env_flag="skills_enabled",
        setting_key=SystemSettingKey.CAPABILITY_SKILLS_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.MCP: CapabilitySpec(
        capability=PlatformCapability.MCP,
        family="reach",
        env_flag="mcp_enabled",
        setting_key=SystemSettingKey.CAPABILITY_MCP_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.TELEPHONY: CapabilitySpec(
        capability=PlatformCapability.TELEPHONY,
        family="media",
        env_flag="telephony_enabled",
        setting_key=SystemSettingKey.CAPABILITY_TELEPHONY_ENABLED,
        agents=("telephony_agent",),
        route_enforced=True,
    ),
    # Meeting recording & minutes (ADR-258). No agent of its own: the feature is
    # a recording lifecycle plus a processing job, reached through its router.
    PlatformCapability.MEETINGS: CapabilitySpec(
        capability=PlatformCapability.MEETINGS,
        family="media",
        env_flag="meetings_enabled",
        setting_key=SystemSettingKey.CAPABILITY_MEETINGS_ENABLED,
        route_enforced=True,
    ),
    # ------------------------------------------------------------------ B7 --
    # A switch removes the ABILITY, never the RECORD. Where the router IS the
    # ability — a board, a set of connections, a live channel — the guard sits
    # on the router. Where the ability is a BACKGROUND act that fills a record
    # the person keeps reading — extracting a memory, learning an interest,
    # writing a debrief — the guard sits at the act, and the record's own
    # router stays open (the ADR-279 lesson, generalised).
    PlatformCapability.WORKBOARD: CapabilitySpec(
        capability=PlatformCapability.WORKBOARD,
        family="work",
        env_flag="workboard_enabled",
        setting_key=SystemSettingKey.CAPABILITY_WORKBOARD_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.JOURNALS: CapabilitySpec(
        capability=PlatformCapability.JOURNALS,
        family="knowledge",
        env_flag="journals_enabled",
        setting_key=SystemSettingKey.CAPABILITY_JOURNALS_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.HABITS: CapabilitySpec(
        capability=PlatformCapability.HABITS,
        family="knowledge",
        env_flag="habits_enabled",
        setting_key=SystemSettingKey.CAPABILITY_HABITS_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.HEARTBEAT: CapabilitySpec(
        capability=PlatformCapability.HEARTBEAT,
        family="work",
        env_flag="heartbeat_enabled",
        setting_key=SystemSettingKey.CAPABILITY_HEARTBEAT_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.PEERS: CapabilitySpec(
        capability=PlatformCapability.PEERS,
        family="people",
        env_flag="peers_enabled",
        setting_key=SystemSettingKey.CAPABILITY_PEERS_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.PSYCHE: CapabilitySpec(
        capability=PlatformCapability.PSYCHE,
        family="knowledge",
        env_flag="psyche_enabled",
        setting_key=SystemSettingKey.CAPABILITY_PSYCHE_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.CHANNELS: CapabilitySpec(
        capability=PlatformCapability.CHANNELS,
        family="reach",
        env_flag="channels_enabled",
        setting_key=SystemSettingKey.CAPABILITY_CHANNELS_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.OPEN_LOOPS: CapabilitySpec(
        capability=PlatformCapability.OPEN_LOOPS,
        family="work",
        env_flag="open_loops_enabled",
        setting_key=SystemSettingKey.CAPABILITY_OPEN_LOOPS_ENABLED,
        route_enforced=True,
    ),
    # Extraction, not reading: switching memory off stops LIA learning new
    # things, and leaves every memory the person already has readable and
    # deletable.
    PlatformCapability.MEMORY: CapabilitySpec(
        capability=PlatformCapability.MEMORY,
        family="knowledge",
        env_flag="memory_extraction_enabled",
        setting_key=SystemSettingKey.CAPABILITY_MEMORY_ENABLED,
        service_enforced=True,
    ),
    PlatformCapability.INTERESTS: CapabilitySpec(
        capability=PlatformCapability.INTERESTS,
        family="knowledge",
        env_flag="interest_extraction_enabled",
        setting_key=SystemSettingKey.CAPABILITY_INTERESTS_ENABLED,
        service_enforced=True,
    ),
    # ADR-269. The Relations page itself is always mounted — it is a LENS over
    # contacts and messages, with no state of its own; what an operator
    # switches is the dated synthesis LIA writes, which costs model calls.
    PlatformCapability.RELATION_DEBRIEF: CapabilitySpec(
        capability=PlatformCapability.RELATION_DEBRIEF,
        family="people",
        env_flag="relation_debrief_enabled",
        setting_key=SystemSettingKey.CAPABILITY_RELATION_DEBRIEF_ENABLED,
        service_enforced=True,
    ),
    # ADR-083: no REST router at all — the delegation runs inside the graph, so
    # the switch lives at the tool's own entry.
    PlatformCapability.SUB_AGENTS: CapabilitySpec(
        capability=PlatformCapability.SUB_AGENTS,
        tools=("delegate_to_sub_agent_tool",),
        family="reach",
        env_flag="sub_agents_enabled",
        setting_key=SystemSettingKey.CAPABILITY_SUB_AGENTS_ENABLED,
        service_enforced=True,
    ),
    # ADR-249 — code a model wrote, run in the SKILLS sandbox. An operator who
    # wants that off should not have to redeploy.
    PlatformCapability.PYTHON_SANDBOX: CapabilitySpec(
        capability=PlatformCapability.PYTHON_SANDBOX,
        tools=("run_python_tool",),
        family="reach",
        env_flag="python_sandbox_tool_enabled",
        setting_key=SystemSettingKey.CAPABILITY_PYTHON_SANDBOX_ENABLED,
        service_enforced=True,
    ),
}


def _register_in_settings_store() -> None:
    """Declare one boolean setting per capability, in the generic store.

    Generated rather than hand-written: ten near-identical blocks would drift.
    The dependency points ONE way — this domain knows the store, the store
    knows nothing about its clients (putting the generation on the store side
    closed a domain import cycle, the same lesson as ADR-216).

    Runs at import; ``startup/registries.py`` imports this module before the
    store asserts its own completeness, so a missing capability spec is a
    boot failure rather than a silent fallback.
    """
    for spec in CAPABILITY_SPECS.values():
        SETTING_SPECS[spec.setting_key] = SettingSpec(
            key=spec.setting_key,
            # Absent means enabled: a fresh instance behaves exactly as it did
            # before any switch existed. The deployment flag still applies.
            default=True,
            decode=decode_bool,
            serialize=encode_bool,
            redis_key=f"{REDIS_KEY_CAPABILITY_PREFIX}{spec.capability.value}",
        )


_register_in_settings_store()


def get_capability_spec(capability: PlatformCapability) -> CapabilitySpec:
    """Return the declaration for ``capability``.

    Args:
        capability: The capability to look up.

    Returns:
        Its spec.
    """
    return CAPABILITY_SPECS[capability]


def deployment_allows(capability: PlatformCapability) -> bool:
    """Whether the DEPLOYMENT permits this capability at all.

    Args:
        capability: The capability to test.

    Returns:
        The environment ceiling, independent of any operator switch.
    """
    return bool(getattr(settings, CAPABILITY_SPECS[capability].env_flag, False))


async def is_capability_enabled(capability: PlatformCapability) -> bool:
    """Whether the capability is effectively available right now.

    Deployment ceiling AND operator switch. A deployment that forbids the
    capability short-circuits: there is nothing an operator could change.

    Never raises — a failing store resolves to the deployment value, which is
    the behaviour that existed before any switch was introduced.

    Args:
        capability: The capability to test.

    Returns:
        True when both bounds allow it.
    """
    if not deployment_allows(capability):
        return False
    spec = CAPABILITY_SPECS[capability]
    try:
        enabled: bool = await read_setting(spec.setting_key)
        return enabled
    except Exception as exc:  # noqa: BLE001 — a switch never breaks a request
        logger.error(
            "capability_switch_read_failed",
            capability=capability.value,
            error_type=type(exc).__name__,
        )
        return True


async def disabled_capabilities() -> frozenset[PlatformCapability]:
    """Every capability currently switched off, read in one pass.

    Used on the request path to filter the planner catalogue, so the reads
    run concurrently rather than one after another.

    Returns:
        The disabled set; empty when anything goes wrong (degrading to the
        full product beats amputating it on a transient failure — the routes
        remain the enforcing layer).
    """
    try:
        capabilities = list(CAPABILITY_SPECS)
        states = await asyncio.gather(
            *(is_capability_enabled(capability) for capability in capabilities)
        )
        return frozenset(
            capability
            for capability, enabled in zip(capabilities, states, strict=True)
            if not enabled
        )
    except Exception as exc:  # noqa: BLE001 — never break planning
        logger.error("capability_states_read_failed", error_type=type(exc).__name__)
        return frozenset()


def disabled_agent_names(disabled: frozenset[PlatformCapability]) -> frozenset[str]:
    """Agent names to hide, given the set of disabled capabilities.

    Args:
        disabled: Capabilities currently off.

    Returns:
        The union of their declared agents.
    """
    return frozenset(
        agent for capability in disabled for agent in CAPABILITY_SPECS[capability].agents
    )


def disabled_tool_names(
    disabled: frozenset[PlatformCapability] | set[PlatformCapability],
) -> set[str]:
    """Tool names to hide for capabilities that own NO agent (B7).

    The agent walk covers every capability with an agent of its own; these two
    have none, so their tools would stay in the planner catalogue while the
    switch refused them at call time.

    Args:
        disabled: Capabilities currently off.

    Returns:
        The union of their directly declared tools.
    """
    return {tool for capability in disabled for tool in CAPABILITY_SPECS[capability].tools}


def assert_capability_tools_exist(registry: AgentRegistry) -> None:
    """Refuse to boot when a capability names a tool that does not exist.

    The sibling of :func:`assert_capability_agents_exist`, for the two
    capabilities that own no agent (delegation lives in the graph, the sandbox
    is one tool). A misspelled name would hide NOTHING while looking like it
    works: the planner would keep offering a tool an operator switched off, and
    the only symptom would be a plan dying at call time (ADR-085 doctrine).

    Flag-gated capabilities are skipped when their deployment flag is off,
    exactly as the agent guard reasons: their manifests are legitimately absent
    and demanding them would fail a valid configuration.

    Args:
        registry: The populated agent registry.

    Raises:
        AssertionError: Listing every capability/tool pair that is unknown.
    """
    known = {manifest.name for manifest in registry.list_tool_manifests()}
    problems = [
        f"{capability.value} -> unknown tool '{tool}'"
        for capability, spec in CAPABILITY_SPECS.items()
        if deployment_allows(capability)
        for tool in spec.tools
        if tool not in known
    ]
    assert not problems, "Capability registry names tools that are not registered: " + "; ".join(
        sorted(problems)
    )


def assert_capability_agents_exist(registry: AgentRegistry) -> None:
    """Refuse to boot when a capability names an agent that does not exist.

    A switch whose agents are misspelled would filter nothing while looking
    like it works (ADR-085 doctrine).

    Checked against the CATALOGUE (the manifests the planner is offered),
    not against the executable agent list: several capabilities ship a
    manifest with no LangGraph agent behind it — image generation is a direct
    tool call, and filtering it means removing it from the catalogue.

    Flag-gated capabilities are skipped when their deployment flag is off:
    their manifests are legitimately absent, and demanding them would make
    the boot fail on a perfectly valid configuration.

    Args:
        registry: The populated agent registry.

    Raises:
        AssertionError: Listing every capability/agent pair that is unknown.
    """
    known = {manifest.name for manifest in registry.list_agent_manifests()}
    problems = [
        f"{capability.value} -> unknown agent '{agent}'"
        for capability, spec in CAPABILITY_SPECS.items()
        if deployment_allows(capability)
        for agent in spec.agents
        if agent not in known
    ]
    assert not problems, "Capability registry names agents that are not registered: " + "; ".join(
        sorted(problems)
    )
