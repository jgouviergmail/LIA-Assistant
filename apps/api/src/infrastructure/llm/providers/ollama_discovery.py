"""
Ollama dynamic model discovery.

Queries the Ollama server's native API to list installed models and their
real capabilities (tools, vision, thinking) via ``/api/tags`` + ``/api/show``.

Includes TTL-based in-memory caching and graceful degradation.

Used by the LLM config admin endpoint to populate the model dropdown
when Ollama is selected as provider.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

import httpx

from src.core.constants import (
    OLLAMA_DISCOVERY_TIMEOUT_SECONDS,
    OLLAMA_MODEL_CACHE_TTL_SECONDS,
)
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
    """Resolve the Ollama root URL from DB cache or environment.

    The stored URL typically ends with ``/v1`` (OpenAI-compat format).
    This function strips that suffix to reach the native Ollama API.

    Returns:
        Root URL (e.g. ``http://host.docker.internal:11434``) or ``None``.
    """
    from src.domains.llm_config.cache import LLMConfigOverrideCache

    raw_url = LLMConfigOverrideCache.get_api_key("ollama")
    if not raw_url:
        raw_url = os.environ.get("OLLAMA_BASE_URL")
    if not raw_url:
        return None

    # Strip trailing /v1 (OpenAI-compat suffix) to get native API root
    return raw_url.rstrip("/").removesuffix("/v1")


# ---------------------------------------------------------------------------
# Capability fetching
# ---------------------------------------------------------------------------


async def _fetch_model_capabilities(
    client: httpx.AsyncClient,
    base_url: str,
    model_name: str,
) -> list[str]:
    """Fetch capabilities for a single model via ``POST /api/show``.

    Returns:
        List of capability strings (e.g. ["completion", "tools", "vision"]),
        or empty list on error.
    """
    try:
        response = await client.post(
            f"{base_url}/api/show",
            json={"name": model_name},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("capabilities", [])
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        logger.debug(
            "ollama_show_error",
            model=model_name,
            error=str(exc),
        )
        return []


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
        async with httpx.AsyncClient(timeout=OLLAMA_DISCOVERY_TIMEOUT_SECONDS) as client:
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
        for (name, size, family, _), caps in zip(entries, all_capabilities, strict=True):
            models.append(
                OllamaModelInfo(
                    name=name,
                    size=size,
                    family=family,
                    capabilities=caps,
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
