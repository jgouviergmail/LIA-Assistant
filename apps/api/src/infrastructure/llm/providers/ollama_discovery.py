"""
Ollama dynamic model discovery.

Queries the Ollama server's native API to list installed models and their
real capabilities (tools, vision, thinking) via ``/api/tags`` + ``/api/show``.

Includes TTL-based in-memory caching and graceful degradation.

Used by the LLM config admin endpoint to populate the model dropdown
when Ollama is selected as provider, and -- since ADR-267 -- to feed the
discovered layer of :class:`ModelCapabilitiesCache`: what the server says a tag
can do (tools, vision, thinking, context length) is what the runtime believes,
because a tag's NAME says nothing about it and the seed's static rows are
guesses. The refresh runs at boot and on every provider-key reload.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, replace
from typing import Any

import httpx

from src.core.config import settings
from src.core.constants import (
    CAPABILITY_PROVENANCE_DISCOVERED,
    OLLAMA_DISCOVERED_MAX_OUTPUT_TOKENS,
    OLLAMA_MODEL_CACHE_TTL_SECONDS,
    OLLAMA_NUM_CTX_DEFAULT_CAP,
)
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile
from src.infrastructure.llm.providers.ollama_urls import ollama_native_root, resolve_ollama_url
from src.infrastructure.llm.reasoning.profiles import ollama_declared_ladder
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OllamaModelInfo:
    """What the server said about one of its models.

    Capabilities and context length come from the server itself, never from the
    tag's NAME. Measured on 0.33.2 (2026-09-10): ``/api/tags`` carries both for
    EVERY tag, cloud ones included, while ``/api/show`` answers nothing at all
    for four of eight cloud tags — so the listing is the first source and the
    per-model call is the fallback.

    Known Ollama capability values: completion, tools, vision, thinking, embedding.

    Attributes:
        name: The tag, ``:latest`` stripped.
        size: Parameter size as the server spells it (e.g. ``"27.3B"``).
        family: Architecture family (e.g. ``"qwen35"``).
        capabilities: What the server says the model can do; empty when nothing
            could be read — which is NOT the same as "it can do nothing".
        context_length: The model's own maximum. What the server ALLOCATES may
            be smaller (a VRAM tier) unless LIA asks for ``num_ctx``.
        remote_host: Set when the model runs on Ollama's cloud rather than on
            this machine. The DISCRIMINANT for a cloud tag: a ``-cloud`` suffix
            is a naming convention, this is what the server states.
        remote_model: The upstream tag a cloud model proxies.
    """

    name: str
    size: str | None = None
    family: str | None = None
    capabilities: list[str] = field(default_factory=list)
    context_length: int | None = None
    remote_host: str | None = None
    remote_model: str | None = None

    @property
    def is_cloud(self) -> bool:
        """Whether this tag runs on somebody else's hardware.

        Returns:
            True when the server declared a remote host — never inferred from
            the tag's name.
        """
        return bool(self.remote_host)

    @property
    def is_known(self) -> bool:
        """Whether the server said anything usable about this model.

        Returns:
            True when at least the capabilities came back. A tag nobody could
            read stays UNKNOWN rather than being published as a model that can
            do nothing.
        """
        return bool(self.capabilities)


# ---------------------------------------------------------------------------
# Module-level TTL cache (simple, single-process safe)
# ---------------------------------------------------------------------------

_cached_models: list[OllamaModelInfo] = []
_cached_at: float = 0.0


def clear_ollama_model_cache() -> None:
    """Reset the discovery cache (for testing)."""
    global _cached_models, _cached_at  # noqa: PLW0603
    _cached_models = []
    _cached_at = 0.0


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


def _resolve_ollama_base_url() -> str | None:
    """Resolve the Ollama NATIVE API root from the DB cache or the environment.

    The stored value may carry the ``/v1`` suffix of the OpenAI-compatible API
    or not (both shapes have been typed by operators); the shared reader in
    ``ollama_urls`` derives the root the native API answers at. Kept as a
    module-level function so the discovery tests can patch the source of the URL.

    Returns:
        Root URL (e.g. ``http://host.docker.internal:11434``) or ``None``.
    """
    raw_url = resolve_ollama_url()
    return ollama_native_root(raw_url) if raw_url else None


# ---------------------------------------------------------------------------
# Capability fetching
# ---------------------------------------------------------------------------


async def _fetch_model_capabilities(
    client: httpx.AsyncClient,
    base_url: str,
    model_name: str,
) -> tuple[list[str], int | None]:
    """Fetch one model's capabilities and context length via ``POST /api/show``.

    The FALLBACK, not the first source: ``/api/tags`` already carries both for
    every tag it lists, and this endpoint answers nothing at all for some cloud
    tags (measured on 0.33.2, four of eight). Called only for a tag the listing
    described incompletely.

    Args:
        client: The shared HTTP client.
        base_url: The native API root.
        model_name: The tag to describe.

    Returns:
        ``(capabilities, context_length)`` -- e.g. ``(["completion", "tools",
        "thinking"], 262144)``. The context length is the architecture's
        ``<arch>.context_length`` entry of ``model_info`` when present. Both
        degrade to ``([], None)`` on error, per model (isolation).
    """
    try:
        response = await client.post(
            f"{base_url}/api/show",
            json={"name": model_name},
        )
        response.raise_for_status()
        data = response.json()
        capabilities = list(data.get("capabilities") or [])
        context_length: int | None = None
        for key, value in (data.get("model_info") or {}).items():
            if key.endswith(".context_length") and isinstance(value, int) and value > 0:
                context_length = value
                break
        return capabilities, context_length
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError) as exc:
        logger.debug(
            "ollama_show_error",
            model=model_name,
            error=str(exc),
        )
        return [], None


def _from_listing(entry: dict[str, Any]) -> OllamaModelInfo | None:
    """Read one ``/api/tags`` entry.

    Args:
        entry: One element of the listing's ``models`` array.

    Returns:
        What the listing says, or None for a nameless entry.
    """
    raw_name: str = entry.get("name") or ""
    if not raw_name:
        return None
    details = entry.get("details") or {}
    context_length = details.get("context_length")
    return OllamaModelInfo(
        name=raw_name.removesuffix(":latest"),
        size=details.get("parameter_size"),
        family=details.get("family"),
        capabilities=list(entry.get("capabilities") or []),
        context_length=(
            context_length if isinstance(context_length, int) and context_length > 0 else None
        ),
        remote_host=entry.get("remote_host"),
        remote_model=entry.get("remote_model"),
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


async def _read_listing(client: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
    """Read ``GET /api/tags``.

    Args:
        client: The shared HTTP client.
        base_url: The native API root.

    Returns:
        The decoded payload.
    """
    response = await client.get(f"{base_url}/api/tags")
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload


def _listed_models(payload: dict[str, Any]) -> list[tuple[OllamaModelInfo, str]]:
    """What the listing already says, deduplicated.

    A server may list both ``llama3.1`` and ``llama3.1:latest``; the FULL tag is
    kept beside each entry because ``/api/show`` needs it.

    Args:
        payload: The ``/api/tags`` payload.

    Returns:
        ``(info, raw_tag)`` pairs, in listing order.
    """
    listed: list[tuple[OllamaModelInfo, str]] = []
    seen: set[str] = set()
    for entry in payload.get("models", []):
        info = _from_listing(entry)
        if info is None or info.name in seen:
            continue
        seen.add(info.name)
        listed.append((info, entry.get("name", info.name)))
    return listed


async def _completed(
    client: httpx.AsyncClient,
    base_url: str,
    listed: list[tuple[OllamaModelInfo, str]],
) -> list[OllamaModelInfo]:
    """Ask ``/api/show`` about the tags the listing left incomplete, and only those.

    Args:
        client: The shared HTTP client.
        base_url: The native API root.
        listed: What the listing said.

    Returns:
        One entry per listed tag, completed where an answer came back. A tag the
        second call also fails to describe keeps what little the listing gave —
        never a value invented to fill the gap.
    """
    incomplete = [
        (index, raw_name)
        for index, (info, raw_name) in enumerate(listed)
        if not info.is_known or info.context_length is None
    ]
    answers = await asyncio.gather(
        *(_fetch_model_capabilities(client, base_url, raw_name) for (_, raw_name) in incomplete)
    )

    models = [info for (info, _) in listed]
    for (index, _raw), (caps, context_length) in zip(incomplete, answers, strict=True):
        info = models[index]
        models[index] = replace(
            info,
            capabilities=caps or info.capabilities,
            context_length=context_length or info.context_length,
        )
    return models


def _warn_undescribed(models: list[OllamaModelInfo]) -> None:
    """Name the tags nothing described, rather than publishing a guess for them.

    Args:
        models: The completed discovery.
    """
    unknown = [info.name for info in models if not info.is_known]
    if unknown:
        logger.warning(
            "ollama_models_undescribed",
            models=unknown,
            msg="neither /api/tags nor /api/show described these tags: they stay "
            "unknown to the runtime, and an administrator may declare them",
        )


async def discover_ollama_models() -> list[OllamaModelInfo]:
    """Query the Ollama server for its models and what they can do.

    ONE call in the ordinary case: ``GET /api/tags`` carries the capabilities
    AND the context length of every tag it lists (measured on 0.33.2, thirteen
    tags, cloud ones included). ``POST /api/show`` is the FALLBACK, issued only
    for a tag the listing described incompletely — and it is a fallback rather
    than the source because it answers NOTHING for some cloud tags, whose
    silence used to be published as "cannot call tools, cannot think, capped at
    the local VRAM tier" over a listing that said the opposite.

    Results are cached in-memory with a short TTL to avoid repeated HTTP calls
    during admin UI interactions.

    Returns:
        List of discovered models, or empty list on any error.
    """
    global _cached_models, _cached_at  # noqa: PLW0603

    # Check TTL cache
    if _cached_models and (time.monotonic() - _cached_at) < OLLAMA_MODEL_CACHE_TTL_SECONDS:
        logger.debug("ollama_discovery_cache_hit", count=len(_cached_models))
        return _cached_models

    base_url = _resolve_ollama_base_url()
    if not base_url:
        logger.debug("ollama_discovery_no_url")
        return []

    try:
        async with httpx.AsyncClient(timeout=settings.ollama_discovery_timeout_seconds) as client:
            listed = _listed_models(await _read_listing(client, base_url))
            models = await _completed(client, base_url, listed)

        _warn_undescribed(models)
        _cached_models = models
        _cached_at = time.monotonic()

        logger.info("ollama_discovery_success", count=len(models), base_url=base_url)
        return models

    except httpx.TimeoutException:
        logger.warning("ollama_discovery_timeout", base_url=base_url)
        return []
    except httpx.HTTPError as exc:
        logger.warning("ollama_discovery_http_error", base_url=base_url, error=str(exc))
        return []
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("ollama_discovery_parse_error", base_url=base_url, error=str(exc))
        return []


# ---------------------------------------------------------------------------
# Discovered profiles (ADR-267): the server is the authority on its own models
# ---------------------------------------------------------------------------


def build_discovered_profile(info: OllamaModelInfo) -> ModelProfile | None:
    """Turn what the server said about a tag into the runtime's profile.

    - ``thinking`` in the capabilities is the ONLY source of the reasoning
      ladder: the full Ollama ladder for a thinking model, ``("none",)`` for the
      others -- ``think=false`` is accepted by every model, a positive level is
      refused by a model that cannot think.
    - Structured output is native for every model (``format`` is grammar-
      constrained on the server), tools and vision are what the server says.
    - The two OpenAI penalties are not expressible through ``langchain-ollama``:
      declared unsupported so the admin UI hides the fields it cannot honour.
    - The context window is the ``num_ctx`` LIA will REQUEST on every call and
      account with (compaction threshold, ReAct budget). Requesting it is what
      makes the server's allocation and LIA's arithmetic agree; left to itself
      the server picks a VRAM tier (4k under 24 GiB) and truncates the beginning
      of a longer prompt in silence.

    **A tag the server did not describe gets NO profile** (ADR-278). Silence is
    not a declaration: publishing one built from an empty capability list said
    "cannot call tools, cannot think, capped at the local tier" — and that
    profile then WON over any catalogue row an administrator could edit, because
    the discovered layer is the authority on its provider. Four of eight cloud
    tags were in exactly that position (measured 2026-09-10), two of them
    declaring 262 144 tokens of context in the listing.

    Args:
        info: One discovered model.

    Returns:
        The profile, provenance ``discovered``, never written to the database;
        None when the server described nothing.
    """
    if not info.is_known:
        return None
    caps = set(info.capabilities)
    is_embedding = "embedding" in caps and "completion" not in caps
    thinking = "thinking" in caps
    return ModelProfile(
        max_input_tokens=requested_num_ctx(info.context_length, is_cloud=info.is_cloud),
        max_output_tokens=OLLAMA_DISCOVERED_MAX_OUTPUT_TOKENS,
        supports_structured_output=not is_embedding,
        supports_tool_calling="tools" in caps,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision="vision" in caps,
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
        is_reasoning_model=thinking,
        model_id=info.name,
        kind="embedding" if is_embedding else "chat",
        reasoning_enum_values=list(ollama_declared_ladder(thinking)),
        reasoning_doc_i18n_key=None,
        capability_provenance=CAPABILITY_PROVENANCE_DISCOVERED,
        metadata={
            "pricing_source": "capabilities_cache",
            "ollama_family": info.family,
            "ollama_size": info.size,
            "ollama_context_length": info.context_length,
            "ollama_is_cloud": info.is_cloud,
        },
    )


def requested_num_ctx(model_context_length: int | None, *, is_cloud: bool = False) -> int:
    """The context window LIA requests from Ollama for a model, and accounts with.

    **The cap protects VRAM, so it applies where the VRAM is.** A local tag is
    held to ``OLLAMA_NUM_CTX_DEFAULT_CAP`` (Ollama's own tier for 24-48 GiB): a
    27 B model declaring 262 144 tokens would otherwise be asked to allocate a
    window this machine has to spill to CPU. A cloud tag runs on somebody else's
    hardware and keeps its whole window.

    An operator overrides either one per LLM slot (``llm_config_overrides
    .context_window``) — that is a decision about ONE configured model, and it
    no longer travels through a single instance-wide variable that gave every
    tag the same number whatever its size (``OLLAMA_NUM_CTX``, removed).

    Args:
        model_context_length: The model's maximum, as the server reported it.
        is_cloud: Whether the tag runs on Ollama's cloud.

    Returns:
        The window to request AND account with — one number, always, because
        ADR-267's invariant is that they are the same one. A server told to
        allocate nothing picks a VRAM tier (4k under 24 GiB) and truncates the
        beginning of a longer prompt in silence, so an unreported maximum falls
        back to the cap rather than to no request at all; the server clamps that
        down to the model's real limit if it is smaller, and says so.
    """
    if not model_context_length or model_context_length <= 0:
        return OLLAMA_NUM_CTX_DEFAULT_CAP
    if is_cloud:
        return model_context_length
    return min(model_context_length, OLLAMA_NUM_CTX_DEFAULT_CAP)


async def refresh_ollama_capabilities() -> list[OllamaModelInfo]:
    """Discover the server's models and publish them to the capabilities cache.

    Best-effort by construction: no configured URL or an unreachable server
    yields an empty discovery, which CLEARS the discovered layer (a tag the
    server no longer lists must not keep a profile). The runtime then treats
    Ollama tags as unknown -- exactly the pre-ADR-267 behaviour.

    Returns:
        The discovered models, so a caller building an admin response does not
        query the server twice.
    """
    discovered = await discover_ollama_models()
    built = ((info.name, build_discovered_profile(info)) for info in discovered)
    profiles = {name: profile for name, profile in built if profile is not None}
    ModelCapabilitiesCache.merge_discovered("ollama", profiles)
    return discovered
