"""
LLM Configuration Admin API Router.

Admin-only endpoints for managing LLM provider API keys and per-type config overrides.
All changes take effect immediately via in-memory cache invalidation.

Created: 2026-03-08
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input, raise_llm_type_not_found
from src.core.session_dependencies import get_current_superuser_session
from src.domains.llm_config.schemas import (
    LLMConfigListResponse,
    LLMTypeConfig,
    LLMTypeConfigUpdate,
    OllamaModelsResponse,
    ProviderKeysResponse,
    ProviderKeyUpdate,
    ProviderModelsMetadata,
)
from src.domains.llm_config.service import LLMConfigService
from src.domains.users.models import User

router = APIRouter(
    prefix="/admin/llm-config",
    tags=["admin", "llm-config"],
)


# --- Provider Keys ---


@router.get(
    "/providers",
    response_model=ProviderKeysResponse,
    summary="List provider API key statuses",
)
async def get_providers(
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> ProviderKeysResponse:
    """List all known LLM providers with their API key configuration status."""
    service = LLMConfigService(db)
    return await service.get_all_provider_keys()


@router.put(
    "/providers/{provider}",
    status_code=204,
    summary="Update provider API key",
)
async def update_provider_key(
    provider: str,
    body: ProviderKeyUpdate,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Update or create an API key for a provider (stored encrypted)."""
    try:
        service = LLMConfigService(db)
        await service.update_provider_key(provider, body.key, current_user.id, request)
    except ValueError as e:
        raise_invalid_input(str(e))


@router.delete(
    "/providers/{provider}",
    status_code=204,
    summary="Delete provider API key",
)
async def delete_provider_key(
    provider: str,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a provider's API key. The provider will be unavailable until reconfigured."""
    try:
        service = LLMConfigService(db)
        await service.delete_provider_key(provider, current_user.id, request)
    except ValueError as e:
        raise_invalid_input(str(e))


# --- LLM Type Configs ---


@router.get(
    "/types",
    response_model=LLMConfigListResponse,
    summary="List all LLM type configs",
)
async def get_types(
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> LLMConfigListResponse:
    """List all LLM types with their effective configuration (defaults + overrides)."""
    service = LLMConfigService(db)
    configs = await service.get_all_configs()
    return LLMConfigListResponse(configs=configs)


@router.get(
    "/types/{llm_type}",
    response_model=LLMTypeConfig,
    summary="Get LLM type config",
)
async def get_type(
    llm_type: str,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> LLMTypeConfig:
    """Get a single LLM type's effective configuration."""
    try:
        service = LLMConfigService(db)
        return await service.get_config(llm_type)
    except ValueError as e:
        raise_llm_type_not_found(str(e))


@router.put(
    "/types/{llm_type}",
    response_model=LLMTypeConfig,
    summary="Update LLM type config",
)
async def update_type(
    llm_type: str,
    body: LLMTypeConfigUpdate,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> LLMTypeConfig:
    """Update an LLM type's config (full replace semantics). null = use code default."""
    try:
        service = LLMConfigService(db)
        return await service.update_config(llm_type, body, current_user.id, request)
    except ValueError as e:
        raise_invalid_input(str(e))


@router.post(
    "/types/{llm_type}/reset",
    response_model=LLMTypeConfig,
    summary="Reset LLM type to defaults",
)
async def reset_type(
    llm_type: str,
    request: Request,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> LLMTypeConfig:
    """Reset an LLM type config to proven code defaults (deletes DB override)."""
    try:
        service = LLMConfigService(db)
        return await service.reset_config(llm_type, current_user.id, request)
    except ValueError as e:
        raise_invalid_input(str(e))


# --- Metadata ---


@router.get(
    "/metadata/models",
    response_model=ProviderModelsMetadata,
    summary="Get available models by provider",
)
async def get_models_metadata(
    kinds: str | None = Query(
        default=None,
        description=(
            "Comma-separated list of model kinds to include "
            "(chat / image / audio / realtime / tts / embedding). "
            "Default: all kinds. The frontend Configuration LLM dialog "
            "passes the LLM type's required_kind."
        ),
    ),
    capability: str | None = Query(
        default=None,
        description=(
            "Optional capability filter (vision / tools / structured_output). "
            "Combined with kinds= via AND."
        ),
    ),
    current_user: User = Depends(get_current_superuser_session),
) -> ProviderModelsMetadata:
    """Get available models grouped by provider.

    Sources: ``ModelCapabilitiesCache`` (chat) +
    ``ImageOptionsCache.get_models_grouped_by_provider`` (image), both
    DB-backed and populated at boot.

    Filtering: ``?kinds=chat`` / ``?kinds=image`` / ``?kinds=chat,image`` etc.
    Plus optional ``?capability=vision`` for vision-aware chat models.
    """
    kind_list = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
    return LLMConfigService.get_provider_models(kinds=kind_list, capability=capability)


@router.get(
    "/providers/ollama/models",
    response_model=OllamaModelsResponse,
    summary="Get dynamically discovered Ollama models",
)
async def get_ollama_models(
    current_user: User = Depends(get_current_superuser_session),
) -> OllamaModelsResponse:
    """Query the Ollama server for installed models with capability profiles.

    Returns live models when Ollama is reachable, or static fallback profiles
    when the server is unavailable. The ``source`` field indicates which.
    """
    return await LLMConfigService.get_ollama_models()
