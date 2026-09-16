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
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.store import get_tool_context_store
from src.domains.agents.dependencies import ToolDependencies
from src.domains.agents.effects.treatment_labels import treatment_domain
from src.domains.agents.effects.treatment_recorder import treatment_recorder
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
from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError
from src.domains.telephony.live_tools import (
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

#: The consultation surface live lookups file under — the dial path's own.
SURFACE: Final = "phone_call"
#: The node name a lookup's model spend is filed under in ``token_usage_logs``.
_SPEND_NODE: Final = "telephony_live_tool"
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
    """The chat's own memory briefing for a question (the native lookup's reader)."""
    from src.domains.agents.middleware.memory_injection import (
        build_psychological_profile as _build,
    )

    return await _build(user_id, query=query)


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
    *, disabled_domains: frozenset[str] = frozenset()
) -> tuple[LiveToolSpec, ...]:
    """The derived list minus what the flag, the capabilities and the person hide.

    Args:
        disabled_domains: The domains the person switched off for their calls.

    Returns:
        The specs an owner call may attach right now; empty when the feature
        is off.
    """
    if not settings.telephony_live_tools_enabled:
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

    try:
        await asyncio.gather(*(_create(s, b) for s, b in zip(specs, bodies, strict=True)))
    except ElevenLabsAgentsError as exc:
        logger.warning(
            "telephony_live_tools_provisioning_failed",
            status_code=exc.status_code,
            created=len(created),
        )
        for tool_id in created.values():
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
    call_id: UUID,
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

    thread_id = f"{SURFACE}:{call_id}"
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
        node_name=_SPEND_NODE,
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
    call_id: UUID,
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
            call_id=call_id,
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
    call_id: UUID,
) -> str:
    """Run one derived tool — or native lookup — for the person, in plain text.

    The arguments are validated through the tool's OWN call schema (unknown
    keys dropped, scalars coerced), the run is bounded under the vendor's
    timeout, and whatever happens the voice agent gets a sentence it can say.
    The consultation is filed on the ``phone_call`` surface like the dial
    path's own reads — under a collector THIS function opens, because a
    call-back runs in no turn and a row nobody collects is a row nobody
    writes (ADR-263); the outcome is counted per tool. What the lookup
    SPENDS (a digest, an embedding search, a Maps request) is recorded under
    the call's own run id (lot 8): a tracker opened here, its callback on the
    runtime config, the ambient tracker for the clients that read it.

    Args:
        spec: The derived entry.
        args: What the vendor posted, minus the call id.
        user_id: The person.
        language: Their backend-canonical language.
        timezone: Their IANA zone.
        display_name: What the tools may sign as.
        call_id: The owner call.

    Returns:
        The text handed back to the vendor.
    """
    lines = result_lines()
    tool = None if spec.native else get_tool(spec.name)
    coroutine = getattr(tool, "coroutine", None) if tool is not None else None
    if not spec.native and (tool is None or coroutine is None):
        telephony_live_tool_calls_total.labels(tool=spec.name, outcome="failed").inc()
        logger.error("telephony_live_tool_unregistered", tool=spec.name)
        return lines["failed"].format(tool=spec.name)
    validated = _native_args(spec, args) if spec.native else _validated_args(tool, args)
    if validated is None:
        telephony_live_tool_calls_total.labels(tool=spec.name, outcome="failed").inc()
        logger.info("telephony_live_tool_invalid_arguments", tool=spec.name)
        return lines["failed"].format(tool=spec.name)

    bound = max(
        1.0, settings.telephony_live_tool_timeout_seconds - TELEPHONY_LIVE_TOOL_INNER_MARGIN_SECONDS
    )
    started = time.monotonic()
    outcome = "ok"
    succeeded = False
    run_id = phone_call_run_id(call_id)
    async with (
        get_db_context() as db,
        treatment_recorder(run_id=str(call_id)),
        TrackingContext(run_id, user_id, f"{SURFACE}_{call_id}", None) as tracker,
    ):
        callbacks: list[Any] = [TokenTrackingCallback(tracker, run_id)]
        try:
            if spec.native:
                text = str(
                    await asyncio.wait_for(
                        _NATIVE_RUNNERS[spec.name](user_id, validated), timeout=bound
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
                    call_id=call_id,
                    db=db,
                    callbacks=callbacks,
                )
                succeeded = bool(getattr(result, "success", True))
                text = _project(result, spec.name, lines)
        except TimeoutError:
            outcome = "timeout"
            text = lines["timeout"].format(tool=spec.name)
        except Exception:  # noqa: BLE001 — the agent must hear a sentence, never a traceback
            outcome = "failed"
            logger.exception("telephony_live_tool_failed", tool=spec.name)
            text = lines["failed"].format(tool=spec.name)
        duration_ms = int((time.monotonic() - started) * 1000)
        record_surface_consultations(
            surface=SURFACE,
            user_id=user_id,
            opened=[spec.section],
            failed=[] if succeeded else [spec.section],
            duration_ms=duration_ms,
            run_id=str(call_id),
        )
    telephony_live_tool_duration_seconds.labels(tool=spec.name).observe(duration_ms / 1000)
    telephony_live_tool_calls_total.labels(tool=spec.name, outcome=outcome).inc()
    logger.info(
        "telephony_live_tool_ran",
        tool=spec.name,
        outcome=outcome,
        duration_ms=duration_ms,
        call_id=str(call_id),
    )
    return text


__all__ = [
    "LIVE_TOOL_DESCRIPTION_MAX_CHARS",
    "LIVE_TOOL_PROVISIONING_CONCURRENCY",
    "METADATA_HASH",
    "METADATA_IDS",
    "NATIVE_LOOKUPS",
    "SURFACE",
    "LiveToolSpec",
    "assert_live_tools_completeness",
    "available_live_tools",
    "derive_live_tool_specs",
    "domain_of",
    "ensure_vendor_live_tools",
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
