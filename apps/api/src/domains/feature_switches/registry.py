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


@dataclass(frozen=True)
class CapabilitySpec:
    """How one capability is bounded, stored and enforced.

    Attributes:
        capability: The member this spec describes.
        env_flag: Settings attribute carrying the deployment ceiling.
        setting_key: Settings-store key carrying the operator switch.
        agents: Agent names removed from the planner catalogue when off.
            Empty when the capability has no agent of its own.
        route_enforced: Whether an HTTP/WebSocket router refuses it when off.
        service_enforced: Whether an internal service chokepoint refuses it
            when off. Speech synthesis has no route of its own — it is
            produced inside the chat stream — so a router dependency would
            enforce nothing.
        label_key: i18n key the frontend resolves for the switch label.
    """

    capability: PlatformCapability
    env_flag: str
    setting_key: SystemSettingKey
    agents: tuple[str, ...] = ()
    route_enforced: bool = False
    service_enforced: bool = False
    label_key: str = field(default="")

    def __post_init__(self) -> None:
        if not self.label_key:
            object.__setattr__(self, "label_key", f"capabilities.items.{self.capability.value}")


CAPABILITY_SPECS: dict[PlatformCapability, CapabilitySpec] = {
    PlatformCapability.STT: CapabilitySpec(
        capability=PlatformCapability.STT,
        env_flag="voice_stt_enabled",
        setting_key=SystemSettingKey.CAPABILITY_STT_ENABLED,
        # Speech has no agent: it is a transport (WebSocket) plus routes.
        route_enforced=True,
    ),
    PlatformCapability.TTS: CapabilitySpec(
        capability=PlatformCapability.TTS,
        env_flag="voice_tts_enabled",
        setting_key=SystemSettingKey.CAPABILITY_TTS_ENABLED,
        # No route of its own: speech is synthesized inside the chat stream,
        # so the gate lives at the single voice-synthesis chokepoint.
        service_enforced=True,
    ),
    PlatformCapability.IMAGE_GENERATION: CapabilitySpec(
        capability=PlatformCapability.IMAGE_GENERATION,
        env_flag="image_generation_enabled",
        setting_key=SystemSettingKey.CAPABILITY_IMAGE_GENERATION_ENABLED,
        agents=("image_generation_agent",),
        route_enforced=True,
    ),
    PlatformCapability.DOCUMENT_GENERATION: CapabilitySpec(
        capability=PlatformCapability.DOCUMENT_GENERATION,
        env_flag="document_generation_enabled",
        setting_key=SystemSettingKey.CAPABILITY_DOCUMENT_GENERATION_ENABLED,
        agents=("document_generation_agent",),
        # No route of its own: the gate lives at the generate_document tool
        # entry (settings flag + user opt-in), like TTS's synthesis chokepoint.
        service_enforced=True,
    ),
    PlatformCapability.ATTACHMENTS: CapabilitySpec(
        capability=PlatformCapability.ATTACHMENTS,
        env_flag="attachments_enabled",
        setting_key=SystemSettingKey.CAPABILITY_ATTACHMENTS_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.RAG_SPACES: CapabilitySpec(
        capability=PlatformCapability.RAG_SPACES,
        env_flag="rag_spaces_enabled",
        setting_key=SystemSettingKey.CAPABILITY_RAG_SPACES_ENABLED,
        agents=("document_agent",),
        route_enforced=True,
    ),
    PlatformCapability.WEB_SEARCH: CapabilitySpec(
        capability=PlatformCapability.WEB_SEARCH,
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
        env_flag="browser_enabled",
        setting_key=SystemSettingKey.CAPABILITY_BROWSER_ENABLED,
        agents=("browser_agent",),
    ),
    PlatformCapability.SKILLS: CapabilitySpec(
        capability=PlatformCapability.SKILLS,
        env_flag="skills_enabled",
        setting_key=SystemSettingKey.CAPABILITY_SKILLS_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.MCP: CapabilitySpec(
        capability=PlatformCapability.MCP,
        env_flag="mcp_enabled",
        setting_key=SystemSettingKey.CAPABILITY_MCP_ENABLED,
        route_enforced=True,
    ),
    PlatformCapability.TELEPHONY: CapabilitySpec(
        capability=PlatformCapability.TELEPHONY,
        env_flag="telephony_enabled",
        setting_key=SystemSettingKey.CAPABILITY_TELEPHONY_ENABLED,
        agents=("telephony_agent",),
        route_enforced=True,
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
