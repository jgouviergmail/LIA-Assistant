"""
API v1 routes aggregator.
Combines all domain routers into a single router for the FastAPI app.
"""

from fastapi import APIRouter

from src.core import constants
from src.core.config import settings
from src.core.field_names import FIELD_STATUS
from src.domains.agents.api.router import router as agents_router
from src.domains.auth.checklist_router import router as checklist_router
from src.domains.auth.oauth_router import router as oauth_router
from src.domains.auth.profile_image_router import router as profile_image_router
from src.domains.auth.router import router as auth_router
from src.domains.auth.sessions_router import router as sessions_router
from src.domains.auth.step_up_router import router as step_up_router
from src.domains.briefing.router import router as briefing_router
from src.domains.capabilities.router import router as capabilities_router
from src.domains.chat.router import router as chat_router
from src.domains.connectors.router import router as connectors_router
from src.domains.conversations.router import router as conversations_router
from src.domains.feature_switches.router import router as capability_switches_router
from src.domains.google_api.router import router as google_api_admin_router
from src.domains.google_api.user_export_router import router as user_export_router
from src.domains.image_generation.options_router import router as image_options_router
from src.domains.image_generation.router import router as image_pricing_admin_router
from src.domains.interests.explainability_router import (
    router as interests_explainability_router,
)
from src.domains.interests.notifications_router import (
    router as interests_notifications_router,
)
from src.domains.interests.router import router as interests_router
from src.domains.llm.pricing_sheet_router import router as llm_pricing_sheet_router
from src.domains.llm.router import router as llm_admin_router
from src.domains.llm_config.router import router as llm_config_router
from src.domains.memories.router import router as memories_router
from src.domains.notifications.router import router as notifications_router
from src.domains.personalities.router import router as personalities_router
from src.domains.product.public_demo_link import router as public_demo_link_router
from src.domains.product.public_demo_link_admin import (
    router as public_demo_link_admin_router,
)
from src.domains.relations.router import router as relations_router
from src.domains.reminders.router import router as reminders_router
from src.domains.scheduled_actions.router import router as scheduled_actions_router
from src.domains.system_settings.public_router import router as system_settings_public_router
from src.domains.system_settings.router import router as system_settings_router
from src.domains.users.router import router as users_router
from src.domains.voice.admin_router import router as voice_admin_router
from src.domains.voice.router import router as voice_router

# Create main API router
api_router = APIRouter()

# Include domain routers
api_router.include_router(auth_router)
api_router.include_router(profile_image_router)  # Google avatar COEP proxy
api_router.include_router(oauth_router)  # Provider sign-in + native shell handoff
api_router.include_router(step_up_router)  # Step-up re-auth (works without MFA flag)
api_router.include_router(sessions_router)  # Device sessions "My devices" (D2)
api_router.include_router(users_router)
api_router.include_router(connectors_router)
api_router.include_router(agents_router)
api_router.include_router(conversations_router)
api_router.include_router(chat_router)
# Reminders expose exactly ONE action (cancel by id) — the domain has no
# management surface by design (discrete, ephemeral, chat-created).
api_router.include_router(reminders_router)
# The capability map: read-only, always mounted. Its own gate-keeping is
# per-node — a subsystem the instance disabled is absent from the payload.
api_router.include_router(capabilities_router)
api_router.include_router(memories_router)
api_router.include_router(interests_router)
# Same prefix, separate module: the history is an audit surface, and
# `interests/router.py` sits at its frozen size ceiling (ADR doctrine: extract,
# never bump the cap).
api_router.include_router(interests_notifications_router)
# Same reason, same prefix: "why does this weigh what it weighs" is a distinct
# concern from "which interests exist", and the main router is at its ceiling.
api_router.include_router(interests_explainability_router)
api_router.include_router(notifications_router)
api_router.include_router(scheduled_actions_router)
api_router.include_router(briefing_router)  # Today dashboard
api_router.include_router(relations_router)  # Personal CRM (N-09, read-only)
api_router.include_router(checklist_router)  # Starter checklist state (UXR A10)
if getattr(settings, "account_export_enabled", False):
    from src.domains.account_export.router import router as account_export_router

    api_router.include_router(account_export_router)  # GDPR portability (D3)
if getattr(settings, "mfa_enabled", False):
    from src.domains.auth.totp_router import router as totp_router
    from src.domains.auth.webauthn_router import router as webauthn_router

    api_router.include_router(webauthn_router)  # Passkeys (security program D1)
    api_router.include_router(totp_router)  # TOTP second factor (security program D1)
# ADR-083 Phase 2 cleanup: /sub-agents REST router removed (no frontend
# consumer; the planner's ephemeral delegation path runs on ReactSubAgentRunner
# and never touched the REST surface). SUB_AGENTS_ENABLED still gates the
# delegate_to_sub_agent_tool tool itself, but no router is mounted.
if getattr(settings, "open_loops_enabled", False):
    from src.domains.open_loops.router import router as open_loops_router

    api_router.include_router(open_loops_router)

if getattr(settings, "habits_enabled", False):
    from src.domains.habits.router import router as habits_router

    api_router.include_router(habits_router)  # Learned habits control surface (ADR-214)

if getattr(settings, "activity_timeline_enabled", False):
    from src.domains.activity.router import router as activity_router

    api_router.include_router(activity_router)  # Proactive activity timeline (Lot 1-A1)

if getattr(settings, "product_analytics_enabled", False):
    from src.domains.product.router import router as product_router
    from src.domains.product.showroom_telemetry import router as showroom_router

    api_router.include_router(product_router)  # Client telemetry ingestion (ADR-178 Phase 4)
    api_router.include_router(showroom_router)  # Credential-less showroom collector (P0)

if getattr(settings, "peers_enabled", False):
    from src.domains.peers.router import router as peers_router

    api_router.include_router(peers_router)  # User-to-user connections (peers program)

if getattr(settings, "diagnostics_enabled", False):
    from src.domains.diagnostics.router import router as diagnostics_admin_router
    from src.domains.diagnostics.webhook_router import router as diagnostics_webhook_router

    # Alertmanager → incident webhook (internal, shared-secret gated; the
    # handler itself 404s while the secret is unset).
    api_router.include_router(diagnostics_webhook_router)
    # Admin health/incident surface (superuser-only, read-only).
    api_router.include_router(diagnostics_admin_router)

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
if getattr(settings, "plugins_enabled", False) and getattr(settings, "skills_enabled", False):
    # ADR-225: the plugins pipeline materializes skills through the skills
    # domain (import_directory), so the feature requires skills to be on.
    from src.domains.plugins.router import router as plugins_router

    api_router.include_router(plugins_router)
if getattr(settings, "rag_spaces_enabled", False):
    from src.domains.rag_spaces.router import router as rag_spaces_router

    api_router.include_router(rag_spaces_router)
if getattr(settings, "journals_enabled", False):
    from src.domains.journals.router import router as journals_router

    api_router.include_router(journals_router)
if getattr(settings, "health_metrics_enabled", False):
    from src.domains.health_metrics.ingest_router import ingest_router as health_ingest_router
    from src.domains.health_metrics.router import router as health_metrics_router

    api_router.include_router(health_metrics_router)
    api_router.include_router(health_ingest_router)
if getattr(settings, "psyche_enabled", False):
    from src.domains.psyche.router import router as psyche_router

    api_router.include_router(psyche_router)
if getattr(settings, "usage_limits_enabled", False):
    from src.domains.usage_limits.router import router as usage_limits_router
    from src.domains.usage_limits.websocket import router as usage_limits_ws_router

    api_router.include_router(usage_limits_router)
    api_router.include_router(usage_limits_ws_router)
if getattr(settings, "telephony_enabled", False):
    from src.domains.telephony.router import router as telephony_router

    api_router.include_router(telephony_router)
if getattr(settings, "meetings_enabled", False):
    from src.domains.meetings.router import router as meetings_router

    api_router.include_router(meetings_router)  # Meeting recording & minutes (ADR-258)
# Google push webhooks (lot H): mounted when either phase is on — the Pub/Sub
# endpoint (phase 2) must exist even if phase 1 channels stay disabled.
if getattr(settings, "push_channels_enabled", False) or getattr(
    settings, "gmail_push_enabled", False
):
    from src.domains.push_channels.router import router as push_channels_router

    api_router.include_router(push_channels_router)

# The wake relay is served by exactly one deployment — the one that publishes
# the iOS app. Every other deployment CALLS a relay (push_relay_url) without
# operating one, which is why this guard reads the operator flag alone.
if getattr(settings, "push_relay_enabled", False):
    from src.domains.push_relay.router import router as push_relay_router

    api_router.include_router(push_relay_router)
api_router.include_router(voice_router)
api_router.include_router(voice_admin_router)
api_router.include_router(user_export_router)
api_router.include_router(system_settings_public_router)
# Anonymous: the landing page has no session. Deliberately NOT under the
# telemetry flag — switching analytics off would take the link down too.
api_router.include_router(public_demo_link_router)
api_router.include_router(public_demo_link_admin_router)

# Include admin routers
api_router.include_router(google_api_admin_router)
api_router.include_router(image_pricing_admin_router)
api_router.include_router(image_options_router)
api_router.include_router(llm_admin_router)
api_router.include_router(llm_pricing_sheet_router)
api_router.include_router(personalities_router)
api_router.include_router(system_settings_router)
api_router.include_router(capability_switches_router)
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
        "version": constants.API_VERSION,  # API contract version (stable for /v1)
        # Build provenance (F030): identifies the exact running artifact.
        "app_version": settings.app_version,
        "commit": settings.git_commit_sha,
        "build_date": settings.build_date,
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
                settings, "rag_spaces_embedding_model", "models/gemini-embedding-001"
            ),
            # Mail source (ADR-262): the space page offers the label section
            # only when the instance runs it.
            "rag_spaces_mail_sync_enabled": getattr(
                settings, "rag_spaces_mail_sync_enabled", False
            ),
            "journals_enabled": getattr(settings, "journals_enabled", False),
            # UXR Lot 6 (A10) — additive instance flags so the starter
            # checklist (and B5's open-loops nav) never offers a disabled
            # subsystem (gate-keeper rule, ADR-061).
            "channels_enabled": getattr(settings, "channels_enabled", False),
            "heartbeat_enabled": getattr(settings, "heartbeat_enabled", False),
            "skills_enabled": getattr(settings, "skills_enabled", False),
            "open_loops_enabled": getattr(settings, "open_loops_enabled", False),
            # Habits program (ADR-214): gates the « Habitudes » settings section.
            "habits_enabled": getattr(settings, "habits_enabled", False),
            # Peers program: gates the « Connexions » settings section.
            "peers_enabled": getattr(settings, "peers_enabled", False),
            # Activity timeline (Lot 1-A1): gates its entry links (gate-keeper
            # rule, ADR-061 — never offer a disabled subsystem).
            "activity_timeline_enabled": getattr(settings, "activity_timeline_enabled", False),
            # Meeting recording (ADR-258): gates the composer action, the
            # meetings pages and the settings section.
            "meetings_enabled": getattr(settings, "meetings_enabled", False),
        },
        "api_version": constants.API_VERSION,  # PHASE 2.1: Use constant instead of hardcoded value
    }
