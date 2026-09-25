"""Live read-only tools on an owner call — the agents half (lots 7-8).

During a call with the account holder, the vendor's voice agent may look
something up in LIA through a **webhook tool** that calls this API back. This
module owns what the telephony half (``domains/telephony/live_tools.py``)
cannot without importing ``agents``:

- the **rule** that derives the tool set from the catalogue (lot 8, owner
  decision 2026-09-16: the phone reads everything the chat reads): every
  tool that only reads — a ``search`` tool or an explicit ``read`` policy,
  never the ``readonly`` inference fallback where the sandbox sits
  (ADR-263) — that is not a ``system`` tool (those answer inside a turn, and
  a call has none), runs outside the pipeline's executor, belongs to a domain
  the phone offers (``shared/phone_domains``), and whose required parameters a
  voice can speak (an identifier nobody can say hides its parameter, and a
  tool with no speakable required parameter is left out);
- the **native lookups** the catalogue has no tool for: the person's
  memories, read through the chat's own profile builder;
- the **boot guard**: every derived entry files under a section the
  ``phone_call`` surface declares and can be described to the vendor; every
  native lookup has its own voice line;
- **provisioning**, idempotent by fingerprint: the vendor tools are created
  once per connector (concurrently, under a bound — sixty sequential
  creations would hold a dial for a minute), replaced when anything drifts (a
  wording, the host, a rotated secret), and a vendor failure leaves the call
  WITHOUT tools rather than without a dial;
- **execution** on a synthetic runtime: the registered tool runs for the
  person with its arguments validated through its own schema, under a bound
  shorter than the vendor's timeout, and its result is projected the way the
  ReAct loop projects one (items under a token budget, the cut stated).

The execution serves TWO voice surfaces through one :class:`VoiceToolHost`
(ADR-300 wave 4): the owner call, where the vendor calls this API back through
a webhook tool, and the DIRECT live session, where the browser posts the
provider's function call on the person's own session (``POST
/live/sessions/{id}/tools``). The host names where the lookup is FILED — the
consultation surface, the run id the spend lands under, the thread the tool
saves context under — and nothing else differs: same rule, same projection,
same bound.

Every line the voice agent reads besides the data lives in
``telephony_live_tool_lines.txt``; a tool's vendor description is its voice
line in ``telephony_live_tools.txt`` when one exists, else its catalogue
manifest's own words.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import structlog
from pydantic import BaseModel, ValidationError

from src.core.config import settings
from src.core.constants import (
    EXECUTION_MODE_REACT,
    TELEPHONY_LIVE_TOOL_DESCRIPTION_MAX_CHARS,
    TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS,
    TELEPHONY_LIVE_TOOL_PROVISIONING_CONCURRENCY,
)
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.tool_outcome import explicit_success
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.store import get_tool_context_store
from src.domains.agents.dependencies import ToolDependencies
from src.domains.agents.effects.treatment_labels import treatment_domain
from src.domains.agents.effects.treatment_recorder import treatment_recorder
from src.domains.agents.expressivity.activity import observe_read
from src.domains.agents.registry.catalogue import (
    POLICY_EXEMPT_CATEGORIES,
    get_tool_category,
    manifest_allows_mode,
)
from src.domains.agents.telephony.voice_projection import compact_items
from src.domains.agents.tools.react_tool_wrapper import extract_data_block
from src.domains.agents.tools.tool_registry import get_tool
from src.domains.chat.service import TrackingContext
from src.domains.shared.consultation_surfaces import (
    CONSULTATION_SURFACES,
    record_surface_consultations,
)
from src.domains.shared.phone_domains import is_phone_domain
from src.domains.telephony.client import (
    ElevenLabsAgentsClient,
    ElevenLabsAgentsError,
    first_refusal,
)
from src.domains.telephony.live_tools import (
    ARRAY_ITEM_DESCRIPTION,
    LiveToolBinding,
    LiveToolParameter,
    live_tool_token,
    live_tool_url,
    live_tools_fingerprint,
    webhook_tool_body,
)
from src.domains.telephony.spend import phone_call_run_id
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.observability.callbacks import TokenTrackingCallback
from src.infrastructure.observability.metrics_telephony import (
    telephony_live_tool_calls_total,
    telephony_live_tool_duration_seconds,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue import ToolManifest

logger = structlog.get_logger(__name__)

#: The consultation surface the PHONE's live lookups file under — the dial path's own.
SURFACE: Final = "phone_call"
#: The consultation surface a DIRECT live session's lookups file under.
LIVE_SESSION_SURFACE: Final = "live_session"
#: The node names a lookup's model spend is filed under in ``token_usage_logs``.
_SPEND_NODE: Final = "telephony_live_tool"
_LIVE_SPEND_NODE: Final = "live_session_tool"
#: Metadata keys on the telephony connector.
METADATA_IDS: Final = "live_tool_ids"
METADATA_HASH: Final = "live_tools_hash"
#: Re-exported constants the tests and the docs read from here.
LIVE_TOOL_DESCRIPTION_MAX_CHARS: Final = TELEPHONY_LIVE_TOOL_DESCRIPTION_MAX_CHARS
LIVE_TOOL_PROVISIONING_CONCURRENCY: Final = TELEPHONY_LIVE_TOOL_PROVISIONING_CONCURRENCY
#: The category of the context tools: they answer inside a turn only.
_SYSTEM_CATEGORY: Final = "system"
#: JSON schema types a voice can fill.
_SPOKEN_TYPES: Final = frozenset({"string", "integer", "number", "boolean", "array"})
#: A parameter that names an identifier — a voice agent holds none, the person
#: speaks in names and dates. The manifest's ``semantic_type`` says it first
#: (``event_id``, ``contact_id``…); the name is the fallback.
_IDENTIFIER_NAME: Final = re.compile(r"(^|_)(id|ids|token)$|^resource_names?$")
#: Parameters that drive the tool's mechanics rather than the question.
_MECHANICS: Final = frozenset(
    {"page_token", "use_cache", "force_refresh", "output_as_registry", "include_content"}
)


@dataclass(frozen=True, slots=True)
class VoiceToolHost:
    """Where a live lookup is FILED: one host per voice surface (ADR-300 wave 4).

    Attributes:
        surface: The consultation surface (``phone_call`` or ``live_session``).
        key: The host's own id — the call id or the session id — the thread
            the tool saves context under and the label of the log line.
        spend_run_id: The run id the lookup's model spend is filed under
            (the call's, the session's).
        consultation_run_id: The run id the consultation rows are filed under
            (the phone files them under the call id, the session under its run).
        spend_node: The node name the spend is filed under in ``token_usage_logs``.
    """

    surface: str
    key: str
    spend_run_id: str
    consultation_run_id: str
    spend_node: str

    @classmethod
    def phone_call(cls, call_id: UUID) -> VoiceToolHost:
        """The owner call's host: the dial path's own surface and run id."""
        return cls(
            surface=SURFACE,
            key=str(call_id),
            spend_run_id=phone_call_run_id(call_id),
            consultation_run_id=str(call_id),
            spend_node=_SPEND_NODE,
        )

    @classmethod
    def live_session(cls, session_id: str, run_id: str) -> VoiceToolHost:
        """A direct live session's host: everything under the session's run id."""
        return cls(
            surface=LIVE_SESSION_SURFACE,
            key=session_id,
            spend_run_id=run_id,
            consultation_run_id=run_id,
            spend_node=_LIVE_SPEND_NODE,
        )


@dataclass(frozen=True)
class LiveToolSpec:
    """One tool the voice agent may call during an owner call.

    Attributes:
        name: The registry (and catalogue) name of the tool, or the native
            lookup's own name.
        domain: The domain the tool reads (the register's vocabulary) — what
            the person's switches decide on.
        section: The ``phone_call`` surface section its consultation files
            under.
        parameters: The manifest parameters exposed to the voice agent, in
            order; empty for a native lookup, whose parameters are declared
            in :data:`_NATIVE_PARAMETERS`.
        native: True for a lookup the catalogue has no tool for.
    """

    name: str
    domain: str
    section: str
    parameters: tuple[str, ...]
    native: bool = False


#: The lookups the catalogue has no tool for. The chat injects the person's
#: memories itself (``memory_injection``); on the phone the agent asks.
NATIVE_LOOKUPS: Final[tuple[LiveToolSpec, ...]] = (
    LiveToolSpec("recall_memories", "context", "memories", (), True),
)
_NATIVE_PARAMETERS: Final[dict[str, tuple[LiveToolParameter, ...]]] = {
    "recall_memories": (
        LiveToolParameter(
            name="query",
            type="string",
            description="What the person is asking about, in a few words.",
            required=True,
        ),
    ),
}
#: The derived list, filled at boot by the completeness guard and lazily by
#: the first reader; tests set it directly.
_SPECS: tuple[LiveToolSpec, ...] | None = None


# ---------------------------------------------------------------------------
# Thin doors the tests replace (lazy imports: the registry and the capability
# filter load the whole catalogue, which this module must not import at
# module level).
# ---------------------------------------------------------------------------


def get_global_registry() -> AgentRegistry:
    """The process-wide agent registry."""
    from src.domains.agents.registry import get_global_registry as _get

    return _get()


async def tools_hidden_by_capabilities(registry: AgentRegistry) -> set[str]:
    """Tool names the capability switches currently hide."""
    from src.domains.agents.services.planner_capability_filter import (
        tools_hidden_by_capabilities as _hidden,
    )

    return await _hidden(registry)


async def build_psychological_profile(user_id: str, query: str) -> Any:
    """The chat's own memory briefing RANKED on the question (the native lookup's reader).

    Handed no vector, the chat's builder served the ten most recent memories
    whatever was asked; the lookup door embeds the question first (ADR-313).
    """
    from src.domains.agents.middleware.memory_injection import build_profile_for_lookup

    return await build_profile_for_lookup(user_id, query)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def tool_descriptions() -> dict[str, str]:
    """The voice line of each tool that has one, from the lines file."""
    return dict(parse_prompt_sections(read_prompt_file("telephony_live_tools"), 2))


def result_lines() -> dict[str, str]:
    """What a lookup answers besides its data, from the lines file."""
    return dict(parse_prompt_sections(read_prompt_file("telephony_live_tool_lines"), 2))


def _reads_only(manifest: ToolManifest) -> bool:
    """A search tool, or an explicit ``read`` policy — never the fallback."""
    policy = getattr(manifest, "mutation_policy", None)
    if policy == "read":
        return True
    if policy is not None:
        return False
    try:
        return str(get_tool_category(manifest)) in POLICY_EXEMPT_CATEGORIES
    except Exception:  # noqa: BLE001 — an unreadable category is not a read tool
        return False


def _is_system(manifest: ToolManifest) -> bool:
    try:
        return str(get_tool_category(manifest)) == _SYSTEM_CATEGORY
    except Exception:  # noqa: BLE001 — an unreadable category is not a system tool
        return False


def _is_identifier(parameter: Any) -> bool:
    semantic = str(getattr(parameter, "semantic_type", "") or "")
    return semantic.endswith("_id") or bool(_IDENTIFIER_NAME.search(str(parameter.name)))


def exposed_parameter_names(manifest: ToolManifest) -> tuple[str, ...]:
    """The manifest parameters a voice can fill, in the manifest's order.

    Args:
        manifest: The tool's catalogue manifest.

    Returns:
        Scalar and scalar-array parameters, minus identifiers and mechanics.
    """
    return tuple(
        p.name
        for p in getattr(manifest, "parameters", [])
        if p.type in _SPOKEN_TYPES and p.name not in _MECHANICS and not _is_identifier(p)
    )


def domain_of(manifest: ToolManifest, registry: AgentRegistry | None = None) -> str:
    """The domain a tool reads as, in the register's vocabulary.

    Args:
        manifest: The tool's catalogue manifest.
        registry: The registry to read, or None for the global one.

    Returns:
        A domain key (``unknown`` at worst).
    """
    return treatment_domain(str(manifest.name), registry)


def derive_live_tool_specs(
    manifests: Iterable[ToolManifest],
    *,
    domain_of: Callable[[ToolManifest], str] | None = None,
) -> tuple[LiveToolSpec, ...]:
    """Apply the rule to a catalogue.

    Args:
        manifests: The registered tool manifests.
        domain_of: Resolves a manifest to its domain (the global resolver by
            default; tests pass their own).

    Returns:
        The derived specs, by name, then the native lookups.
    """
    resolve = domain_of or globals()["domain_of"]
    derived: list[LiveToolSpec] = []
    for manifest in manifests:
        if not _reads_only(manifest) or _is_system(manifest):
            continue
        if not manifest_allows_mode(manifest, EXECUTION_MODE_REACT):
            continue
        domain = resolve(manifest)
        if not is_phone_domain(domain):
            continue
        names = exposed_parameter_names(manifest)
        required = [p.name for p in getattr(manifest, "parameters", []) if p.required]
        if any(name not in names for name in required):
            continue
        derived.append(LiveToolSpec(str(manifest.name), domain, domain, names))
    derived.sort(key=lambda spec: spec.name)
    return (*derived, *NATIVE_LOOKUPS)


def live_tool_specs() -> tuple[LiveToolSpec, ...]:
    """The derived list, from the global registry (memoised after boot)."""
    global _SPECS  # noqa: PLW0603 — one derivation per process
    if _SPECS is None:
        _SPECS = derive_live_tool_specs(get_global_registry().list_tool_manifests())
    return _SPECS


def spec_for(name: str) -> LiveToolSpec | None:
    """The derived entry of a tool name, or None.

    Args:
        name: A route segment or tool name.

    Returns:
        The spec, or None when the phone does not offer it.
    """
    return next((spec for spec in live_tool_specs() if spec.name == name), None)


def live_tool_description(spec: LiveToolSpec, manifest: ToolManifest | None) -> str:
    """What the vendor's model reads to decide when to call a tool.

    The voice line wins; without one, the catalogue's own words, cut at the
    first paragraph and at :data:`LIVE_TOOL_DESCRIPTION_MAX_CHARS` (the vendor
    reads every description on every turn of the call).

    Args:
        spec: The derived entry.
        manifest: Its manifest, or None for a native lookup.

    Returns:
        The description; empty when nothing describes the tool.
    """
    line = tool_descriptions().get(spec.name)
    if line:
        return line
    text = str(getattr(manifest, "description", "") or "").strip()
    first = text.split("\n\n", 1)[0].strip()
    return first[:LIVE_TOOL_DESCRIPTION_MAX_CHARS]


def assert_live_tools_completeness(
    manifests: Iterable[ToolManifest], *, registry: AgentRegistry | None = None
) -> None:
    """Derive the list at boot and refuse an entry nobody could serve.

    Args:
        manifests: The registered tool manifests.
        registry: The registry the domains are resolved on (the global one
            when None — the boot hands its own).

    Raises:
        RuntimeError: Listing every offending entry and rule.
    """
    global _SPECS  # noqa: PLW0603 — the boot fills what the readers memoise
    manifests = list(manifests)
    by_name = {str(getattr(m, "name", "")): m for m in manifests}
    sections = CONSULTATION_SURFACES[SURFACE].domains
    specs = derive_live_tool_specs(manifests, domain_of=lambda m: domain_of(m, registry))
    # Whether every phone domain is SERVED is not checked here: a domain's
    # only read tool may register behind a feature flag (telephony's own
    # calls list), and a boot with that flag off is a legitimate boot. The
    # unit test over the full catalogue holds that line instead.
    problems: list[str] = []
    for spec in specs:
        manifest = by_name.get(spec.name)
        if spec.native:
            if spec.name not in _NATIVE_PARAMETERS:
                problems.append(f"{spec.name}: native lookup without parameters")
            if spec.name not in tool_descriptions():
                problems.append(f"{spec.name}: no description line in telephony_live_tools.txt")
        elif manifest is None:
            problems.append(f"{spec.name}: not in the catalogue")
        elif not live_tool_description(spec, manifest):
            problems.append(f"{spec.name}: nothing describes it to the vendor")
        if spec.section not in sections:
            problems.append(
                f"{spec.name}: section {spec.section!r} is not on the {SURFACE} surface"
            )
    if problems:
        raise RuntimeError("Live tools list incomplete: " + "; ".join(problems))
    _SPECS = specs


def live_tool_parameters(
    spec: LiveToolSpec, manifest: ToolManifest | None
) -> tuple[LiveToolParameter, ...]:
    """Project the exposed parameters for the vendor schema.

    A numeric bound the tool enforces reaches the model in the description,
    since the vendor schema carries none (ADR-184); an enum travels as one; an
    array carries the type of its items.

    Args:
        spec: The derived entry.
        manifest: The tool's catalogue manifest, or None for a native lookup.

    Returns:
        The exposed parameters, in the spec's order.
    """
    if spec.native:
        return _NATIVE_PARAMETERS.get(spec.name, ())
    by_name = {p.name: p for p in getattr(manifest, "parameters", [])}
    return tuple(_projected_parameter(by_name[name]) for name in spec.parameters)


def _bounded_description(parameter: Any) -> tuple[str, tuple[str, ...] | None]:
    """The description carrying the enforced bounds, and the enum if any."""
    minimum = maximum = None
    enum: tuple[str, ...] | None = None
    for constraint in parameter.constraints:
        if constraint.kind == "minimum":
            minimum = constraint.value
        elif constraint.kind == "maximum":
            maximum = constraint.value
        elif constraint.kind == "enum" and isinstance(constraint.value, list):
            enum = tuple(str(v) for v in constraint.value)
    description = str(parameter.description)
    if minimum is not None and maximum is not None:
        description = f"{description} ({minimum} to {maximum})"
    elif maximum is not None:
        description = f"{description} (at most {maximum})"
    return description, enum


def _projected_parameter(parameter: Any) -> LiveToolParameter:
    """One manifest parameter as the vendor schema carries it."""
    description, enum = _bounded_description(parameter)
    items_type = None
    if parameter.type == "array":
        items = (getattr(parameter, "schema", None) or {}).get("items") or {}
        items_type = str(items.get("type") or "string")
    return LiveToolParameter(
        name=parameter.name,
        type=parameter.type,
        description=description,
        required=parameter.required,
        enum=enum,
        items_type=items_type,
    )


def _manifest_of(name: str) -> ToolManifest:
    return get_global_registry().get_tool_manifest(name)


def function_declaration(spec: LiveToolSpec) -> dict[str, Any]:
    """One derived tool as a provider-neutral function declaration (ADR-300 wave 4).

    The OpenAPI-subset shape every live provider's function calling reads
    (``name``, ``description``, ``parameters`` as a JSON-schema object) —
    the same projection the vendor webhook bodies use, without the vendor
    envelope. A result is awaited (no ``NON_BLOCKING``): the voice reads it
    back before it goes on.

    Args:
        spec: The derived entry.

    Returns:
        The declaration.
    """
    manifest = None if spec.native else _manifest_of(spec.name)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in live_tool_parameters(spec, manifest):
        prop: dict[str, Any] = {"type": parameter.type, "description": parameter.description}
        if parameter.enum:
            prop["enum"] = list(parameter.enum)
        if parameter.type == "array":
            # The items carry a description too: measured 2026-09-16 on the
            # phone and again 2026-09-19 on a live session, the vendor refuses
            # an array whose items have none (422), and a description costs
            # nothing on a wire that does not require it.
            prop["items"] = {
                "type": parameter.items_type or "string",
                "description": ARRAY_ITEM_DESCRIPTION,
            }
        properties[parameter.name] = prop
        if parameter.required:
            required.append(parameter.name)
    return {
        "name": spec.name,
        "description": live_tool_description(spec, manifest),
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


def vendor_bodies(specs: Iterable[LiveToolSpec], *, token: str) -> list[dict[str, Any]]:
    """The vendor tool bodies of a set of specs.

    Args:
        specs: The tools to provision.
        token: The derived call-back token.

    Returns:
        One body per spec, in order.
    """
    bodies: list[dict[str, Any]] = []
    for spec in specs:
        manifest = None if spec.native else _manifest_of(spec.name)
        bodies.append(
            webhook_tool_body(
                name=spec.name,
                description=live_tool_description(spec, manifest),
                url=live_tool_url(spec.name),
                token=token,
                parameters=live_tool_parameters(spec, manifest),
                timeout_seconds=settings.telephony_live_tool_timeout_seconds,
            )
        )
    return bodies


async def available_live_tools(
    *, disabled_domains: frozenset[str] = frozenset(), feature_enabled: bool | None = None
) -> tuple[LiveToolSpec, ...]:
    """The derived list minus what the flag, the capabilities and the person hide.

    Args:
        disabled_domains: The domains the person switched off for their voice.
        feature_enabled: The gate of the CALLER's feature — the telephony
            live-tools flag by default; a direct live session (ADR-300 wave 4)
            is gated by the live capability and passes True.

    Returns:
        The specs a voice may hold right now; empty when the feature is off.
    """
    gate = settings.telephony_live_tools_enabled if feature_enabled is None else feature_enabled
    if not gate:
        return ()
    hidden = await tools_hidden_by_capabilities(get_global_registry())
    return tuple(
        spec
        for spec in live_tool_specs()
        if spec.name not in hidden and spec.domain not in disabled_domains
    )


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------


async def ensure_vendor_live_tools(
    db: AsyncSession,
    *,
    connector: Any,
    api_key: str,
    api_secret: str,
    client_factory: Callable[[str], ElevenLabsAgentsClient] | None = None,
) -> tuple[LiveToolBinding, ...]:
    """Make sure the vendor holds every live tool this connector may offer.

    Idempotent by fingerprint: when nothing drifted the stored ids are
    returned without a vendor round trip. On drift the new tools are created
    first (concurrently, under :data:`LIVE_TOOL_PROVISIONING_CONCURRENCY`),
    the old ones deleted after (forced), and the metadata committed — a NEW
    dict, never a mutation (the JSONB rule). A vendor failure leaves the call
    WITHOUT tools rather than without a dial. The person's own domain switches
    are applied by the caller on the bindings: the vendor holds the whole
    set, one call attaches its subset.

    Args:
        db: Session the connector row is committed on.
        connector: The active telephony connector.
        api_key: The person's vendor key.
        api_secret: The connector's webhook secret, which the token derives from.
        client_factory: Test seam for the vendor client.

    Returns:
        The bindings the dial may attach; empty when nothing is available.
    """
    specs = await available_live_tools()
    if not specs:
        return ()
    bodies = vendor_bodies(specs, token=live_tool_token(api_secret))
    fingerprint = live_tools_fingerprint(bodies)
    metadata: dict[str, Any] = dict(connector.connector_metadata or {})
    stored: dict[str, Any] = metadata.get(METADATA_IDS) or {}
    if metadata.get(METADATA_HASH) == fingerprint and all(s.name in stored for s in specs):
        return tuple(LiveToolBinding(s.name, str(stored[s.name]), s.domain) for s in specs)

    client = (client_factory or ElevenLabsAgentsClient)(api_key)
    created = await _create_vendor_tools(client, specs, bodies)
    if created is None:
        return ()
    for old_id in stored.values():
        await client.delete_tool(str(old_id))
    connector.connector_metadata = {**metadata, METADATA_IDS: created, METADATA_HASH: fingerprint}
    await db.commit()
    logger.info("telephony_live_tools_provisioned", count=len(created))
    return tuple(LiveToolBinding(s.name, created[s.name], s.domain) for s in specs)


async def _create_vendor_tools(
    client: ElevenLabsAgentsClient,
    specs: tuple[LiveToolSpec, ...],
    bodies: list[dict[str, Any]],
) -> dict[str, str] | None:
    """Create every vendor tool, concurrently under a bound; None on a refusal.

    Never leaves half a set behind: on a vendor failure what was created is
    removed (forced) before answering None.
    """
    created: dict[str, str] = {}
    gate = asyncio.Semaphore(LIVE_TOOL_PROVISIONING_CONCURRENCY)

    async def _create(spec: LiveToolSpec, body: dict[str, Any]) -> None:
        async with gate:
            created[spec.name] = await client.create_tool(body)

    # A TaskGroup, never `gather`: on a refusal the siblings are cancelled and
    # awaited BEFORE the rollback reads the dict they were filling (measured
    # 2026-09-19 on the live session's twin: fifty creations went on after the
    # first refusal, all orphaned).
    refused: ElevenLabsAgentsError | None = None
    try:
        async with asyncio.TaskGroup() as group:
            for spec, body in zip(specs, bodies, strict=True):
                group.create_task(_create(spec, body))
    except* ElevenLabsAgentsError as refusals:
        refused = first_refusal(refusals)
    if refused is not None:
        logger.warning(
            "telephony_live_tools_provisioning_failed",
            status_code=refused.status_code,
            created=len(created),
        )
        for tool_id in list(created.values()):
            await client.delete_tool(tool_id)
        return None
    return created


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


async def _synthetic_runtime(
    *,
    user_id: UUID,
    language: str,
    timezone: str,
    display_name: str,
    host: VoiceToolHost,
    deps: ToolDependencies,
    callbacks: list[Any],
) -> Any:
    """A ``ToolRuntime`` for a tool run outside any graph, for the person.

    Mirrors the executor's hand-built runtime: no graph state, the shared
    store, a null stream writer, and a run context naming the person and
    carrying the dependency container a connector tool reads its clients
    through (measured on Docker dev 2026-09-16: without it the calendar tool
    answers « Tool dependencies not injected »). The thread is the call's
    own, so whatever the tool saves as context is filed under the call and
    never under a conversation. The config carries the call's tracking
    callback (lot 8): a tool's own model calls travel on the runtime's
    config, and a structured door handed no config builds a fresh one the
    tracker never sees (measured 2026-09-15 on the e-mail digests).
    """
    from langchain.tools import ToolRuntime
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.orchestration.parallel_executor import NullStreamWriter

    thread_id = f"{host.surface}:{host.key}"
    context = LiaRuntimeContext(
        user_id=user_id,
        thread_id=thread_id,
        conversation_id=thread_id,
        store=await get_tool_context_store(),
        language=language,
        timezone=timezone,
        display_name=display_name,
        deps=deps,
    )
    config: RunnableConfig = enrich_config_with_node_metadata(
        {
            "configurable": {"thread_id": thread_id, "user_id": str(user_id)},
            "callbacks": callbacks,
        },
        node_name=host.spend_node,
    )
    return ToolRuntime(
        state=None,
        config=config,
        context=context,
        store=context.store,
        stream_writer=NullStreamWriter(),
        tool_call_id=None,
    )


def _validated_args(tool: Any, args: dict[str, Any]) -> dict[str, Any] | None:
    """Coerce the vendor's arguments through the tool's OWN call schema.

    The call schema is the tool's input schema minus its injected arguments
    (LangChain builds it that way), so unknown keys are dropped and scalars
    coerced exactly as a model's tool call would be.

    Args:
        tool: The registered ``StructuredTool``.
        args: What the vendor posted, minus the call id.

    Returns:
        The validated arguments, or None when they cannot be read.
    """
    schema = tool.tool_call_schema
    if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
        return None
    try:
        return schema.model_validate(args).model_dump(exclude_unset=True)
    except ValidationError:
        return None


def _native_args(spec: LiveToolSpec, args: dict[str, Any]) -> dict[str, str] | None:
    """The declared parameters of a native lookup, as strings; None if one is missing."""
    validated: dict[str, str] = {}
    for parameter in _NATIVE_PARAMETERS.get(spec.name, ()):
        value = args.get(parameter.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if parameter.required:
                return None
            continue
        validated[parameter.name] = str(value).strip()
    return validated


async def _recall_memories(user_id: UUID, args: dict[str, str]) -> str:
    """The native memories lookup: the chat's briefing lines, as plain text."""
    profile, _state, _debug = await build_psychological_profile(str(user_id), args["query"])
    return "\n".join(line for line in str(profile or "").splitlines() if line.strip())


_NATIVE_RUNNERS: Final[dict[str, Callable[[UUID, dict[str, str]], Any]]] = {
    "recall_memories": _recall_memories,
}


def _project(result: Any, tool_name: str, lines: dict[str, str]) -> str:
    """The result as the voice agent reads it: message, items, the cut stated."""
    message = str(getattr(result, "message", "") or "")
    block = extract_data_block(
        result, settings.telephony_live_tool_result_max_tokens, reshape=compact_items
    )
    if block is None:
        return message
    text = f"{message}\n\n{block.text}" if message else block.text
    if block.truncated:
        text = f"{text}\n{lines['result_cut'].format(shown=block.shown, total=block.total)}"
    return text


async def _run_registry_tool(
    spec: LiveToolSpec,
    validated: dict[str, Any],
    *,
    coroutine: Any,
    bound: float,
    user_id: UUID,
    language: str,
    timezone: str,
    display_name: str,
    host: VoiceToolHost,
    db: Any,
    callbacks: list[Any],
) -> Any:
    """Run a catalogue tool for the person on a synthetic runtime (deps closed here)."""
    # One dependency container for the run, owned here and closed here: the
    # container caches the connector clients a tool opens, and their sockets
    # must not outlive the lookup (ADR-283).
    deps = ToolDependencies(db_session=db)
    try:
        runtime = await _synthetic_runtime(
            user_id=user_id,
            language=language,
            timezone=timezone,
            display_name=display_name,
            host=host,
            deps=deps,
            callbacks=callbacks,
        )
        return await asyncio.wait_for(coroutine(runtime=runtime, **validated), timeout=bound)
    finally:
        await deps.aclose()


async def run_live_tool(
    spec: LiveToolSpec,
    args: dict[str, Any],
    *,
    user_id: UUID,
    language: str,
    timezone: str,
    display_name: str,
    host: VoiceToolHost,
) -> str:
    """Run one derived tool — or native lookup — for the person, in plain text.

    The arguments are validated through the tool's OWN call schema (unknown
    keys dropped, scalars coerced), the run is bounded under the vendor's
    timeout, and whatever happens the voice gets a sentence it can say.
    The consultation is filed on the HOST's surface like the dial path's own
    reads — under a collector THIS function opens, because a call-back runs
    in no turn and a row nobody collects is a row nobody writes (ADR-263);
    the outcome is counted per tool and surface. What the lookup SPENDS (a
    digest, an embedding search, a Maps request) is recorded under the
    host's own run id (lot 8): a tracker opened here, its callback on the
    runtime config, the ambient tracker for the clients that read it.

    Args:
        spec: The derived entry.
        args: What the voice asked, minus the host's own id.
        user_id: The person.
        language: Their backend-canonical language.
        timezone: Their IANA zone.
        display_name: What the tools may sign as.
        host: Where the lookup is filed — the owner call or the live session.

    Returns:
        The text handed back to the voice.
    """
    lines = result_lines()
    tool = None if spec.native else get_tool(spec.name)
    # ``getattr`` already answers None for a missing tool, so the extra
    # ``if tool is not None`` it used to carry tested nothing.
    coroutine = getattr(tool, "coroutine", None)
    if not spec.native and coroutine is None:
        telephony_live_tool_calls_total.labels(
            tool=spec.name, outcome="failed", surface=host.surface
        ).inc()
        logger.error("telephony_live_tool_unregistered", tool=spec.name)
        return lines["failed"].format(tool=spec.name)
    validated = _native_args(spec, args) if spec.native else _validated_args(tool, args)
    if validated is None:
        telephony_live_tool_calls_total.labels(
            tool=spec.name, outcome="failed", surface=host.surface
        ).inc()
        logger.info("telephony_live_tool_invalid_arguments", tool=spec.name)
        return lines["failed"].format(tool=spec.name)

    bound = max(
        1.0, settings.telephony_live_tool_timeout_seconds - TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS
    )
    started = time.monotonic()
    succeeded = False
    run_id = host.spend_run_id
    async with (
        get_db_context() as db,
        treatment_recorder(run_id=host.consultation_run_id),
        TrackingContext(run_id, user_id, f"{host.surface}_{host.key}", None) as tracker,
    ):
        callbacks: list[Any] = [TokenTrackingCallback(tracker, run_id)]
        try:
            if spec.native:
                text = str(
                    await asyncio.wait_for(
                        observe_read(spec.name, _NATIVE_RUNNERS[spec.name](user_id, validated)),
                        timeout=bound,
                    )
                )
                succeeded = True
            else:
                result = await _run_registry_tool(
                    spec,
                    validated,
                    coroutine=coroutine,
                    bound=bound,
                    user_id=user_id,
                    language=language,
                    timezone=timezone,
                    display_name=display_name,
                    host=host,
                    db=db,
                    callbacks=callbacks,
                )
                succeeded = explicit_success(result)
                text = _project(result, spec.name, lines)
            # ADR-303: ONE verdict for both authorities. ``succeeded`` fed the
            # consultation register while ``outcome`` stayed "ok" unless an
            # exception fired — so a tool that failed by RETURNING was « failed »
            # in the register and « ok » on the dashboard an operator watches.
            outcome = "ok" if succeeded else "failed"
        except TimeoutError:
            outcome = "timeout"
            text = lines["timeout"].format(tool=spec.name)
        except Exception:  # noqa: BLE001 — the agent must hear a sentence, never a traceback
            outcome = "failed"
            logger.exception("telephony_live_tool_failed", tool=spec.name)
            text = lines["failed"].format(tool=spec.name)
        duration_ms = int((time.monotonic() - started) * 1000)
        record_surface_consultations(
            surface=host.surface,
            user_id=user_id,
            opened=[spec.section],
            failed=[] if succeeded else [spec.section],
            duration_ms=duration_ms,
            run_id=host.consultation_run_id,
        )
    telephony_live_tool_duration_seconds.labels(tool=spec.name, surface=host.surface).observe(
        duration_ms / 1000
    )
    telephony_live_tool_calls_total.labels(
        tool=spec.name, outcome=outcome, surface=host.surface
    ).inc()
    logger.info(
        "telephony_live_tool_ran",
        tool=spec.name,
        outcome=outcome,
        duration_ms=duration_ms,
        surface=host.surface,
        host=host.key,
    )
    return text


__all__ = [
    "LIVE_SESSION_SURFACE",
    "LIVE_TOOL_DESCRIPTION_MAX_CHARS",
    "LIVE_TOOL_PROVISIONING_CONCURRENCY",
    "METADATA_HASH",
    "METADATA_IDS",
    "NATIVE_LOOKUPS",
    "SURFACE",
    "LiveToolSpec",
    "VoiceToolHost",
    "assert_live_tools_completeness",
    "available_live_tools",
    "derive_live_tool_specs",
    "domain_of",
    "ensure_vendor_live_tools",
    "function_declaration",
    "exposed_parameter_names",
    "live_tool_description",
    "live_tool_parameters",
    "live_tool_specs",
    "result_lines",
    "run_live_tool",
    "spec_for",
    "tool_descriptions",
    "vendor_bodies",
]
