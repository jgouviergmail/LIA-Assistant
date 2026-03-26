"""
API v1 routes aggregator.
Combines all domain routers into a single router for the FastAPI app.
"""

from fastapi import APIRouter

from src.core import constants
from src.core.config import settings
from src.core.field_names import FIELD_STATUS
from src.domains.agents.api.router import router as agents_router
from src.domains.auth.router import router as auth_router
from src.domains.chat.router import router as chat_router
from src.domains.connectors.router import router as connectors_router
from src.domains.conversations.router import router as conversations_router
from src.domains.google_api.router import router as google_api_admin_router
from src.domains.google_api.user_export_router import router as user_export_router
from src.domains.image_generation.router import router as image_pricing_admin_router
from src.domains.interests.router import router as interests_router
from src.domains.llm.router import router as llm_admin_router
from src.domains.llm_config.router import router as llm_config_router
from src.domains.memories.router import router as memories_router
from src.domains.notifications.router import router as notifications_router
from src.domains.personalities.router import router as personalities_router
from src.domains.scheduled_actions.router import router as scheduled_actions_router
from src.domains.system_settings.public_router import router as system_settings_public_router
from src.domains.system_settings.router import router as system_settings_router
from src.domains.users.router import router as users_router
from src.domains.voice.router import router as voice_router

# Create main API router
api_router = APIRouter()

# Include domain routers
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(connectors_router)
api_router.include_router(agents_router)
api_router.include_router(conversations_router)
api_router.include_router(chat_router)
api_router.include_router(memories_router)
api_router.include_router(interests_router)
api_router.include_router(notifications_router)
api_router.include_router(scheduled_actions_router)
if getattr(settings, "sub_agents_enabled", False):
    from src.domains.sub_agents.router import router as sub_agents_router

    api_router.include_router(sub_agents_router)
if getattr(settings, "mcp_enabled", False):
    from src.domains.user_mcp.admin_router import router as admin_mcp_router

    api_router.include_router(admin_mcp_router)
if getattr(settings, "mcp_user_enabled", False):
    from src.domains.user_mcp.router import router as user_mcp_router

    api_router.include_router(user_mcp_router)
if getattr(settings, "heartbeat_enabled", False):
    from src.domains.heartbeat.router import router as heartbeat_router

    api_router.include_router(heartbeat_router)
if getattr(settings, "channels_enabled", False):
    from src.domains.channels.router import router as channels_router

    api_router.include_router(channels_router)
if getattr(settings, "attachments_enabled", False):
    from src.domains.attachments.router import router as attachments_router

    api_router.include_router(attachments_router)
if getattr(settings, "skills_enabled", False):
    from src.domains.skills.router import router as skills_router

    api_router.include_router(skills_router)
if getattr(settings, "rag_spaces_enabled", False):
    from src.domains.rag_spaces.router import router as rag_spaces_router

    api_router.include_router(rag_spaces_router)
if getattr(settings, "journals_enabled", False):
    from src.domains.journals.router import router as journals_router

    api_router.include_router(journals_router)
if getattr(settings, "usage_limits_enabled", False):
    from src.domains.usage_limits.router import router as usage_limits_router
    from src.domains.usage_limits.websocket import router as usage_limits_ws_router

    api_router.include_router(usage_limits_router)
    api_router.include_router(usage_limits_ws_router)
api_router.include_router(voice_router)
api_router.include_router(user_export_router)
api_router.include_router(system_settings_public_router)

# Include admin routers
api_router.include_router(google_api_admin_router)
api_router.include_router(image_pricing_admin_router)
api_router.include_router(llm_admin_router)
api_router.include_router(personalities_router)
api_router.include_router(system_settings_router)
api_router.include_router(llm_config_router)


# Health check endpoint
@api_router.get(
    "/health",
    tags=["Health"],
    summary="Health check",
    description="Check API health status",
)
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        FIELD_STATUS: "healthy",
        "service": "lia-api",
        "version": constants.API_VERSION,  # PHASE 2.1: Use constant instead of hardcoded value
    }


# Root endpoint
@api_router.get(
    "/",
    tags=["Root"],
    summary="API root",
    description="API root endpoint with basic information",
)
async def root() -> dict:
    """API root endpoint."""
    return {
        "message": "Welcome to LIA API",
        "version": constants.API_VERSION,  # PHASE 2.1: Use constant instead of hardcoded value
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


# Client configuration endpoint
@api_router.get(
    "/config",
    tags=["Configuration"],
    summary="Get client configuration",
    description="Returns configuration settings that clients (web/mobile) need to know",
)
async def get_client_config() -> dict:
    """
    Get client-side configuration.

    Returns configuration values that frontend clients need for proper operation:
    - SSE (Server-Sent Events) retry configuration
    - Rate limiting information
    - i18n (internationalization) settings
    - Other client-relevant settings

    This endpoint is public and does not require authentication.
    """
    return {
        "sse": {
            "heartbeat_interval_seconds": settings.sse_heartbeat_interval,
        },
        "rate_limits": {
            "enabled": settings.rate_limit_enabled,
            "per_minute": settings.rate_limit_per_minute,
            "burst": settings.rate_limit_burst,
        },
        "i18n": {
            "supported_languages": settings.supported_languages,
            "default_language": settings.default_language,
        },
        "features": {
            "tool_approval_enabled": True,  # NOTE: Tool approval is always enabled
            "attachments_enabled": getattr(settings, "attachments_enabled", False),
            "rag_spaces_enabled": getattr(settings, "rag_spaces_enabled", False),
            "rag_spaces_embedding_model": getattr(
                settings, "rag_spaces_embedding_model", "text-embedding-3-small"
            ),
            "journals_enabled": getattr(settings, "journals_enabled", False),
        },
        "api_version": constants.API_VERSION,  # PHASE 2.1: Use constant instead of hardcoded value
    }
