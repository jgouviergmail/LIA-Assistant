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
from dataclasses import dataclass, field

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
    """Info for a model discovered on an Ollama server.

    Capabilities are queried from the Ollama ``/api/show`` endpoint and
    reflect the model's actual support (not inferred from name/family).

    Known Ollama capability values: completion, tools, vision, thinking, embedding.
    """

    name: str
    size: str | None = None  # e.g. "8B", "70B"
    family: str | None = None  # e.g. "llama", "qwen3"
    capabilities: list[str] = field(default_factory=list)  # e.g. ["completion", "tools"]
    #: The model's maximum context, from ``model_info.<arch>.context_length``.
    #: What the server ALLOCATES may be smaller (VRAM-based default) unless
    #: LIA asks for ``num_ctx`` explicitly (``settings.ollama_num_ctx``).
    context_length: int | None = None


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


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


async def discover_ollama_models() -> list[OllamaModelInfo]:
    """Query the Ollama server for installed models with real capabilities.

    Two-phase discovery:
    1. ``GET /api/tags`` — list all installed models (names, sizes, families)
    2. ``POST /api/show`` — fetch real capabilities per model (parallel)

    Results are cached in-memory with a short TTL to avoid
    repeated HTTP calls during admin UI interactions.

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
            # Phase 1: List all models
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()

            data = response.json()
            raw_models = data.get("models", [])

            # Parse model entries (deduplicate, strip :latest)
            entries: list[tuple[str, str | None, str | None, str]] = (
                []
            )  # (name, size, family, raw_name)
            seen_names: set[str] = set()

            for entry in raw_models:
                raw_name: str = entry.get("name", "")
                if not raw_name:
                    continue

                name = raw_name
                # Strip ":latest" tag (cosmetic noise) but keep specific tags
                if name.endswith(":latest"):
                    name = name.removesuffix(":latest")

                # Deduplicate (e.g. if both "llama3.1" and "llama3.1:latest" exist)
                if name in seen_names:
                    continue
                seen_names.add(name)

                details = entry.get("details", {})
                entries.append(
                    (
                        name,
                        details.get("parameter_size"),
                        details.get("family"),
                        raw_name,  # Use original name for /api/show (Ollama needs the full tag)
                    )
                )

            # Phase 2: Fetch capabilities in parallel
            cap_tasks = [
                _fetch_model_capabilities(client, base_url, raw_name)
                for (_, _, _, raw_name) in entries
            ]
            all_capabilities = await asyncio.gather(*cap_tasks)

        # Build final model list
        models: list[OllamaModelInfo] = []
        for (name, size, family, _), (caps, context_length) in zip(
            entries, all_capabilities, strict=True
        ):
            models.append(
                OllamaModelInfo(
                    name=name,
                    size=size,
                    family=family,
                    capabilities=caps,
                    context_length=context_length,
                )
            )

        # Update cache
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


def build_discovered_profile(info: OllamaModelInfo) -> ModelProfile:
    """Turn what ``/api/show`` said about a tag into the runtime's profile.

    - ``thinking`` in the capabilities is the ONLY source of the reasoning
      ladder: the full Ollama ladder for a thinking model, ``("none",)`` for the
      others -- ``think=false`` is accepted by every model, a positive level is
      refused by a model that cannot think. An undeclared ladder would make the
      tag unknown to the reasoning resolution, so one is always declared here.
    - Structured output is native for every model (``format`` is grammar-
      constrained on the server), tools and vision are what the server says.
    - The two OpenAI penalties are not expressible through ``langchain-ollama``:
      declared unsupported so the admin UI hides the fields it cannot honour.
    - The context window is the ``num_ctx`` LIA will REQUEST on every call and
      account with (compaction threshold, ReAct budget): ``ollama_num_ctx`` when
      set, else the model's own maximum capped by ``OLLAMA_NUM_CTX_DEFAULT_CAP``.
      Requesting it is what makes the server's allocation and LIA's arithmetic
      agree; left to itself the server picks a VRAM tier (4k under 24 GiB) and
      truncates the beginning of a longer prompt in silence.

    Args:
        info: One discovered model.

    Returns:
        The profile, provenance ``discovered``, never written to the database.
    """
    caps = set(info.capabilities)
    is_embedding = "embedding" in caps and "completion" not in caps
    thinking = "thinking" in caps
    return ModelProfile(
        max_input_tokens=requested_num_ctx(info.context_length),
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
        },
    )


def requested_num_ctx(model_context_length: int | None) -> int:
    """The context window LIA requests from Ollama for a model, and accounts with.

    Args:
        model_context_length: The model's maximum, from ``/api/show`` (None when
            the server did not report one).

    Returns:
        ``settings.ollama_num_ctx`` when the operator set it; otherwise the
        model's maximum capped by ``OLLAMA_NUM_CTX_DEFAULT_CAP`` (the cap alone
        when the maximum is unknown -- the server clamps to the model's real
        limit and says so).
    """
    configured = settings.ollama_num_ctx
    if configured:
        return int(configured)
    if model_context_length and model_context_length > 0:
        return min(model_context_length, OLLAMA_NUM_CTX_DEFAULT_CAP)
    return OLLAMA_NUM_CTX_DEFAULT_CAP


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
    profiles = {info.name: build_discovered_profile(info) for info in discovered}
    ModelCapabilitiesCache.merge_discovered("ollama", profiles)
    return discovered
