"""
Connectors router with FastAPI endpoints for external service connections.
"""

from typing import Any, cast
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    GOOGLE_STATIC_MAPS_URL_LIMIT,
    HTTP_TIMEOUT_CONNECTOR_LONG,
    HTTP_TIMEOUT_CONNECTOR_STANDARD,
    STATIC_MAP_MARKER_DEST_COLOR,
    STATIC_MAP_MARKER_ORIGIN_COLOR,
    STATIC_MAP_MAX_DIMENSION,
    STATIC_MAP_MIN_DIMENSION,
    STATIC_MAP_POLYLINE_COLOR,
    STATIC_MAP_POLYLINE_WEIGHT,
)
from src.core.dependencies import get_db
from src.core.exceptions import (
    InternalServerError,
    raise_configuration_missing,
    raise_connector_not_found,
    raise_connector_type_no_preferences,
    raise_connector_validation_errors,
    raise_external_service_connection_error,
    raise_external_service_fetch_error,
    raise_internal_error,
    raise_invalid_input,
)
from src.core.i18n import Language, _, get_language_from_header
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session, get_current_superuser_session
from src.domains.auth.models import User
from src.domains.connectors.error_handlers import handle_oauth_callback_error_redirect
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES, ConnectorType
from src.domains.connectors.preferences.schemas import PreferencesRequest
from src.domains.connectors.schemas import (
    APIKeyActivationRequest,
    APIKeyValidationRequest,
    APIKeyValidationResponse,
    AppleActivationRequest,
    AppleActivationResponse,
    AppleValidationRequest,
    AppleValidationResponse,
    CalendarListItem,
    CalendarListResponse,
    ConnectorAPIKeyInfo,
    ConnectorGlobalConfigResponse,
    ConnectorGlobalConfigUpdate,
    ConnectorHealthResponse,
    ConnectorHealthSettingsResponse,
    ConnectorListResponse,
    ConnectorOAuthInitiate,
    ConnectorPreferencesResponse,
    ConnectorPreferencesUpdateResponse,
    ConnectorResponse,
    ConnectorUpdate,
    GoogleContactsOAuthRequest,
    HueBridgeDiscoveryResponse,
    HueBridgeInfo,
    HueLocalActivationRequest,
    HuePairingRequest,
    HuePairingResponse,
    TaskListItem,
    TaskListResponse,
)
from src.domains.connectors.service import ConnectorService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/connectors", tags=["Connectors"])


@router.get(
    "",
    response_model=ConnectorListResponse,
    summary="Get user connectors",
    description="Get all connectors for the authenticated user.",
)
async def get_connectors(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorListResponse:
    """Get all connectors for the current user."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.get_user_connectors(user_id)


# Connector types endpoint (MUST be before /{connector_id} to avoid path matching conflict)
@router.get(
    "/types",
    response_model=list[str],
    summary="List supported connector types",
    description="Get list of all supported connector types.",
)
async def list_connector_types() -> list[str]:
    """List all supported connector types."""
    from src.domains.connectors.models import ConnectorType

    return [connector_type.value for connector_type in ConnectorType]


# Google Routes Static Map proxy (MUST be before /{connector_id} to avoid path matching conflict)
# Note: This endpoint is public (no auth) because browser <img> tags don't send session cookies.
# The API key is still protected server-side. The polyline is already visible in the HTML.
@router.get(
    "/google-routes/static-map",
    summary="Proxy Google Routes static map",
    description="Proxy endpoint to generate static map images for routes using API key.",
    responses={
        200: {"content": {"image/png": {}}, "description": "Static map image"},
        400: {"description": "Invalid parameters"},
    },
)
async def proxy_routes_static_map(
    polyline: str,
    width: int = 600,
    height: int = 300,
    origin: str | None = None,
    dest: str | None = None,
) -> StreamingResponse:
    """
    Proxy Google Static Maps API with encoded polyline and optional markers.

    This endpoint generates a static map image showing a route polyline,
    using the server's API key to avoid exposing it to the frontend.
    Optional origin/destination markers ensure accurate visual representation
    even when the polyline is simplified for long routes.

    Note: This endpoint is intentionally public (no authentication) because
    browser <img> tags do not send session cookies reliably. The polyline
    data is already visible in the HTML sent to the client, so there's no
    additional data exposure. The Google API key remains protected server-side.

    Args:
        polyline: URL-encoded polyline string from Routes API
        width: Map width in pixels (50-2048, default 600)
        height: Map height in pixels (50-2048, default 300)
        origin: Optional origin coordinates as "lat,lng" for green marker
        dest: Optional destination coordinates as "lat,lng" for red marker

    Returns:
        StreamingResponse with the map image
    """
    import re
    from urllib.parse import quote

    import httpx

    from src.core.config import settings

    try:
        api_key = settings.google_api_key
        if not api_key:
            logger.warning("google_api_key_not_configured_for_static_map")
            raise_configuration_missing("google_routes", "api_key")

        # Validate coordinate format for origin/dest to prevent parameter injection
        _coord_pattern = re.compile(r"^-?\d{1,3}(\.\d+)?,-?\d{1,3}(\.\d+)?$")
        if origin and not _coord_pattern.match(origin):
            raise_invalid_input("origin must be 'lat,lng' format", field="origin")
        if dest and not _coord_pattern.match(dest):
            raise_invalid_input("dest must be 'lat,lng' format", field="dest")

        # Validate dimensions (Google limits from constants)
        width = max(STATIC_MAP_MIN_DIMENSION, min(STATIC_MAP_MAX_DIMENSION, width))
        height = max(STATIC_MAP_MIN_DIMENSION, min(STATIC_MAP_MAX_DIMENSION, height))

        # FastAPI auto-decodes query params, so polyline arrives decoded here
        # We must re-encode it for the Google Static Maps URL
        # Google polyline chars (ASCII 63-126) include URL-unsafe chars like \ | ?
        encoded_polyline = quote(polyline, safe="")

        # Build Static Maps URL with polyline path (colors from constants)
        static_map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap?"
            f"size={width}x{height}"
            f"&path=color:{STATIC_MAP_POLYLINE_COLOR}|weight:{STATIC_MAP_POLYLINE_WEIGHT}|enc:{encoded_polyline}"
        )

        # Add origin marker (label A) - ensures accurate starting point
        if origin:
            static_map_url += f"&markers=color:{STATIC_MAP_MARKER_ORIGIN_COLOR}|label:A|{origin}"

        # Add destination marker (label B) - ensures accurate ending point
        if dest:
            static_map_url += f"&markers=color:{STATIC_MAP_MARKER_DEST_COLOR}|label:B|{dest}"

        # Add API key last
        static_map_url += f"&key={api_key}"

        # Note: Polyline is pre-simplified in routes_tools.py to fit URL limits
        # Google Static Maps URL limit from GOOGLE_STATIC_MAPS_URL_LIMIT
        url_length = len(static_map_url)
        if url_length > GOOGLE_STATIC_MAPS_URL_LIMIT:
            logger.warning(
                "static_map_url_too_long_fallback",
                url_length=url_length,
                polyline_length=len(polyline),
                limit=GOOGLE_STATIC_MAPS_URL_LIMIT,
            )
            raise_external_service_fetch_error("google_routes", "static_map (URL too long)", 414)

        logger.debug(
            "static_map_proxy_request",
            width=width,
            height=height,
            polyline_length=len(polyline),
            url_length=url_length,
            has_origin_marker=bool(origin),
            has_dest_marker=bool(dest),
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                static_map_url,
                follow_redirects=True,
                timeout=HTTP_TIMEOUT_CONNECTOR_STANDARD,
            )

            if response.status_code != 200:
                logger.warning(
                    "static_map_proxy_error",
                    status_code=response.status_code,
                    response_text=response.text[:200] if response.text else None,
                )
                raise_external_service_fetch_error(
                    "google_routes", "static_map", response.status_code
                )

            content_type = response.headers.get("content-type", "image/png")

            logger.debug(
                "static_map_proxy_success",
                content_length=len(response.content),
            )

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                },
            )
    except httpx.RequestError as e:
        logger.error(
            "static_map_proxy_request_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_external_service_connection_error("google_routes")
    except InternalServerError:
        # Re-raise API exceptions as-is
        raise
    except Exception as e:
        # Catch any other unexpected errors for debugging
        logger.exception(
            "static_map_proxy_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_internal_error(
            detail=f"Static map proxy error: {type(e).__name__}",
            error_type=type(e).__name__,
        )


# ========== GMAIL ATTACHMENT PROXY ==========
# Authenticated proxy to download Gmail attachments via the Gmail API.
# Opens in a new browser tab (Content-Disposition: inline).
# MUST be before /{connector_id} to avoid path matching conflict.


@router.get(
    "/gmail/attachment/{message_id}/{attachment_id}",
    summary="Proxy Gmail attachment",
    description="Download a Gmail attachment via the server. Opens inline in a new tab.",
    responses={
        200: {"description": "Attachment content (inline)"},
        404: {"description": "Attachment not found"},
    },
)
async def proxy_gmail_attachment(
    message_id: str,
    attachment_id: str,
    filename: str = "attachment",
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Proxy a Gmail attachment for inline display in the browser.

    The frontend opens this URL in a new tab when the user clicks
    an attachment chip in the email card. Authentication is via
    session cookie (BFF pattern).

    Args:
        message_id: Gmail message ID
        attachment_id: Gmail attachment ID
        filename: Original filename (for Content-Disposition header)
    """
    import mimetypes
    import re

    from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

    user_id = current_user.id
    service = ConnectorService(db)

    try:
        credentials = await service.get_connector_credentials(user_id, ConnectorType.GOOGLE_GMAIL)

        if not credentials:
            raise_connector_not_found(user_id)

        client = GoogleGmailClient(user_id, credentials, service)
        data = await client.get_attachment(message_id, attachment_id)

        # Determine MIME type from filename
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/octet-stream"

        # Sanitize filename for Content-Disposition header (prevent header injection)
        safe_filename = re.sub(r'[\r\n\x00-\x1f\\"]', "", filename)

        logger.debug(
            "gmail_attachment_proxy_success",
            user_id=str(user_id),
            message_id=message_id,
            filename=filename,
            content_type=content_type,
            content_length=len(data),
        )

        return StreamingResponse(
            iter([data]),
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{safe_filename}"',
                "Cache-Control": "private, max-age=3600",
            },
        )

    except InternalServerError:
        raise
    except Exception as e:
        logger.error(
            "gmail_attachment_proxy_error",
            user_id=str(user_id),
            message_id=message_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_external_service_fetch_error("google_gmail", "attachment", 404)


# ========== CONNECTOR HEALTH CHECK ==========
# OAuth token health monitoring endpoints (MUST be before /{connector_id} to avoid path matching conflict)


@router.get(
    "/health/settings",
    response_model=ConnectorHealthSettingsResponse,
    summary="Get connector health settings",
    description=(
        "Get the configuration settings for connector health monitoring. "
        "Frontend uses these values for polling intervals and cooldowns. "
        "Single source of truth - avoids duplicating config in frontend."
    ),
)
async def get_health_settings() -> ConnectorHealthSettingsResponse:
    """
    Get health monitoring settings from backend configuration.

    SIMPLIFIED: Only critical cooldown (modal deduplication).
    No warning settings since we only alert on status=ERROR.

    Returns:
        ConnectorHealthSettingsResponse with polling and cooldown values in milliseconds.
    """
    from src.core.config import settings

    return ConnectorHealthSettingsResponse(
        polling_interval_ms=settings.oauth_health_check_interval_minutes * 60 * 1000,
        critical_cooldown_ms=settings.oauth_health_critical_cooldown_hours * 60 * 60 * 1000,
    )


@router.get(
    "/health",
    response_model=ConnectorHealthResponse,
    summary="Check connector health",
    description=(
        "Check the health status of all OAuth connectors for the authenticated user. "
        "Returns health status (healthy, expiring_soon, expired, error) for each connector. "
        "Use this endpoint to detect token expiration before it causes issues."
    ),
)
async def check_connector_health(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorHealthResponse:
    """
    Check health of all OAuth connectors for the current user.

    Returns:
        ConnectorHealthResponse with health status for each OAuth connector,
        including critical and warning counts.
    """
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.check_connector_health(user_id)


@router.get(
    "/{connector_id}",
    response_model=ConnectorResponse,
    summary="Get connector by ID",
    description="Get a specific connector by ID. Must belong to the authenticated user.",
)
async def get_connector(
    connector_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    """Get connector by ID."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.get_connector_by_id(user_id, connector_id)


@router.patch(
    "/{connector_id}",
    response_model=ConnectorResponse,
    summary="Update connector",
    description="Update a connector's status or metadata.",
)
async def update_connector(
    connector_id: UUID,
    update_data: ConnectorUpdate,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    """Update a connector."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.update_connector(user_id, connector_id, update_data)


@router.delete(
    "/{connector_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete connector",
    description="Delete a connector and revoke OAuth access.",
)
async def delete_connector(
    connector_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a connector."""
    user_id = current_user.id
    service = ConnectorService(db)
    await service.delete_connector(user_id, connector_id)
    # 204 No Content - no response body


@router.post(
    "/{connector_id}/refresh",
    response_model=ConnectorResponse,
    summary="Refresh connector credentials",
    description="Refresh OAuth credentials for a connector using refresh token.",
)
async def refresh_connector_credentials(
    connector_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    """Refresh connector OAuth credentials."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.refresh_connector_credentials(user_id, connector_id)


# ========== CONNECTOR PREFERENCES ==========


@router.get(
    "/{connector_id}/preferences",
    response_model=ConnectorPreferencesResponse,
    summary="Get connector preferences",
    description=(
        "Get user preferences for a connector (e.g., default calendar name). "
        "Returns decrypted preferences. Only connectors with preferences schema are supported."
    ),
)
async def get_connector_preferences(
    connector_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorPreferencesResponse:
    """Get preferences for a connector (decrypted)."""
    from src.domains.connectors.preferences import (
        ConnectorPreferencesService,
        has_preferences,
    )

    user_id = current_user.id
    service = ConnectorService(db)

    # Verify ownership and get connector
    connector_response = await service.get_connector_by_id(user_id, connector_id)

    # Check if this connector type supports preferences
    connector_type_value = connector_response.connector_type.value
    if not has_preferences(connector_type_value):
        raise_connector_type_no_preferences(connector_type_value)

    # Get connector for preferences_encrypted field
    connector = await service.repository.get_by_id(connector_id)
    if not connector:
        raise_connector_not_found(connector_id)

    # Decrypt preferences
    prefs = ConnectorPreferencesService.decrypt_and_get(
        connector_type_value,
        connector.preferences_encrypted,
    )

    return ConnectorPreferencesResponse(
        connector_id=connector_id,
        connector_type=connector_type_value,
        preferences=prefs.model_dump() if prefs else {},
    )


@router.patch(
    "/{connector_id}/preferences",
    response_model=ConnectorPreferencesUpdateResponse,
    summary="Update connector preferences",
    description=(
        "Update user preferences for a connector. "
        "Values are validated, sanitized (anti-injection), and encrypted before storage."
    ),
)
async def update_connector_preferences(
    connector_id: UUID,
    preferences_data: PreferencesRequest,
    request: Request,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorPreferencesUpdateResponse:
    """Update preferences for a connector (encrypted storage)."""
    from src.domains.connectors.preferences import (
        ConnectorPreferencesService,
        has_preferences,
    )

    user_id = current_user.id
    service = ConnectorService(db)

    # Verify ownership and get connector
    connector_response = await service.get_connector_by_id(user_id, connector_id)

    # Check if this connector type supports preferences
    connector_type_value = connector_response.connector_type.value
    if not has_preferences(connector_type_value):
        raise_connector_type_no_preferences(connector_type_value)

    # For Google Calendar: empty/null default_calendar_name is allowed
    # The tool will fallback to user's primary Google calendar if not set
    # (see calendar_tools.py resolve_calendar_name with fallback="primary")

    # Validate, sanitize, and encrypt (convert schema to dict, excluding None values)
    prefs_dict = preferences_data.model_dump(exclude_none=True)
    success, encrypted, errors = ConnectorPreferencesService.validate_and_encrypt(
        connector_type_value,
        prefs_dict,
    )

    if not success:
        # Convert string errors to structured format
        structured_errors = [{"field": "preferences", "message": err} for err in errors]
        raise_connector_validation_errors(
            errors=structured_errors,
            connector_type=connector_type_value,
        )

    # Get connector and update
    connector = await service.repository.get_by_id(connector_id)
    if not connector:
        raise_connector_not_found(connector_id)

    connector.preferences_encrypted = encrypted
    await db.commit()

    logger.info(
        "connector_preferences_updated",
        connector_id=str(connector_id),
        connector_type=connector_type_value,
        user_id=str(user_id),
    )

    user_lang = (
        cast("Language", current_user.language)
        if current_user.language
        else get_language_from_header(request.headers.get("accept-language"))
    )
    return ConnectorPreferencesUpdateResponse(
        message=_("Preferences updated", user_lang),
        connector_id=connector_id,
    )


# ========== CALENDAR & TASK LIST DISCOVERY ==========


async def _get_client_for_connector(
    service: ConnectorService,
    user_id: UUID,
    connector_id: UUID,
    connector_type: ConnectorType,
) -> Any:
    """Instantiate the appropriate API client for a connector.

    Pattern follows resolve_client_for_category() in provider_resolver.py.

    Args:
        service: ConnectorService instance.
        user_id: User UUID.
        connector_id: Connector UUID (for error messages).
        connector_type: Type of connector.

    Returns:
        Instantiated API client.
    """
    from src.domains.connectors.clients.registry import ClientRegistry

    credentials: Any = None
    if connector_type.is_apple:
        credentials = await service.get_apple_credentials(user_id, connector_type)
    else:
        credentials = await service.get_connector_credentials(user_id, connector_type)

    if not credentials:
        raise_connector_not_found(connector_id)

    client_class = ClientRegistry.get_client_class(connector_type)
    if client_class is None:
        raise_connector_not_found(connector_id)

    return client_class(user_id, credentials, service)


@router.get(
    "/{connector_id}/calendars",
    response_model=CalendarListResponse,
    summary="List calendars from connected provider",
    description=(
        "Fetch available calendars from the connected calendar provider "
        "(Google, Apple, or Microsoft). Used for default calendar selection."
    ),
)
async def list_connector_calendars(
    connector_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> CalendarListResponse:
    """List calendars from a connected calendar provider."""
    user_id = current_user.id
    service = ConnectorService(db)

    # Verify ownership and get connector
    connector_response = await service.get_connector_by_id(user_id, connector_id)
    connector_type = connector_response.connector_type

    # Validate connector is a calendar type
    if connector_type not in CONNECTOR_FUNCTIONAL_CATEGORIES["calendar"]:
        raise_invalid_input(
            "This connector does not support calendar listing",
            connector_type=connector_type.value,
        )

    # Instantiate client (may raise HTTPException — let it propagate)
    client = await _get_client_for_connector(service, user_id, connector_id, connector_type)

    # Fetch calendars from external provider
    try:
        result = await client.list_calendars()
    except Exception as e:
        logger.error(
            "calendar_list_fetch_failed",
            connector_id=str(connector_id),
            connector_type=connector_type.value,
            error=str(e),
        )
        raise_external_service_connection_error(connector_type.value)

    raw_items = result.get("items", [])
    items = [
        CalendarListItem(
            name=item.get("summary", ""),
            is_default=bool(item.get("primary", False)),
            access_role=item.get("accessRole", "owner"),
        )
        for item in raw_items
        if item.get("summary")
    ]

    return CalendarListResponse(items=items)


@router.get(
    "/{connector_id}/task-lists",
    response_model=TaskListResponse,
    summary="List task lists from connected provider",
    description=(
        "Fetch available task lists from the connected tasks provider "
        "(Google Tasks or Microsoft To Do). Used for default task list selection."
    ),
)
async def list_connector_task_lists(
    connector_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TaskListResponse:
    """List task lists from a connected tasks provider."""
    user_id = current_user.id
    service = ConnectorService(db)

    # Verify ownership and get connector
    connector_response = await service.get_connector_by_id(user_id, connector_id)
    connector_type = connector_response.connector_type

    # Validate connector is a tasks type
    if connector_type not in CONNECTOR_FUNCTIONAL_CATEGORIES["tasks"]:
        raise_invalid_input(
            "This connector does not support task list listing",
            connector_type=connector_type.value,
        )

    # Instantiate client (may raise HTTPException — let it propagate)
    client = await _get_client_for_connector(service, user_id, connector_id, connector_type)

    # Fetch task lists from external provider
    try:
        result = await client.list_task_lists()
    except Exception as e:
        logger.error(
            "task_list_fetch_failed",
            connector_id=str(connector_id),
            connector_type=connector_type.value,
            error=str(e),
        )
        raise_external_service_connection_error(connector_type.value)

    # Filter items with valid titles first, then enumerate for is_default
    valid_items = [item for item in result.get("items", []) if item.get("title")]
    items = [
        TaskListItem(
            name=item.get("title", ""),
            # Neither Google Tasks nor Microsoft To Do have a primary flag;
            # first item is conventionally the default list
            is_default=(i == 0),
        )
        for i, item in enumerate(valid_items)
    ]

    return TaskListResponse(items=items)


# ========== GMAIL CONNECTOR ==========


@router.get(
    "/gmail/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Gmail OAuth",
    description="Initiate Gmail OAuth flow. Returns authorization URL to redirect user to.",
)
async def initiate_gmail_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Gmail OAuth flow."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.initiate_gmail_oauth(user_id)


@router.get(
    "/gmail/callback",
    summary="Gmail OAuth callback",
    description=(
        "Handle OAuth callback from Google and redirect to frontend. "
        "This endpoint does NOT require authentication as it validates "
        "user_id from OAuth state."
    ),
    include_in_schema=False,  # Hidden from docs (internal redirect)
)
async def gmail_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Handle Gmail OAuth callback.

    Security Model: Same as Google Contacts callback.
    See google_contacts_oauth_callback() for detailed documentation.
    """
    from src.core.config import settings

    service = ConnectorService(db)

    try:
        connector = await service.handle_gmail_callback_stateless(code, state)

        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=gmail"
        )

        logger.info(
            "gmail_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )

        return RedirectResponse(url=redirect_url, status_code=302)

    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "gmail")


# ========== GOOGLE CONTACTS CONNECTOR ==========


@router.get(
    "/google-contacts/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Google Contacts OAuth",
    description="Initiate Google Contacts OAuth flow with PKCE. Returns authorization URL.",
)
async def initiate_google_contacts_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Google Contacts OAuth flow with PKCE."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.initiate_google_contacts_oauth(user_id)


@router.get(
    "/google-contacts/callback",
    summary="Google Contacts OAuth callback",
    description=(
        "Handle OAuth callback from Google and redirect to frontend. "
        "This endpoint does NOT require authentication as it validates "
        "user_id from OAuth state."
    ),
    include_in_schema=False,  # Hidden from docs (internal redirect)
)
async def google_contacts_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Handle Google Contacts OAuth callback.

    Security Model:
    - Does NOT require session authentication (user not logged in via cookie during OAuth redirect)
    - Validates user_id from OAuth state metadata (stored during initiation)
    - OAuth state provides CSRF protection and user identity validation
    - Single-use state token prevents replay attacks

    Flow:
    1. Validate OAuth state and extract user_id from metadata
    2. Verify user exists and is active
    3. Exchange code for tokens
    4. Create connector linked to user
    5. Redirect to frontend with success/error params
    """
    from src.core.config import settings

    service = ConnectorService(db)

    try:
        connector = await service.handle_google_contacts_callback_stateless(code, state)

        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=google_contacts"
        )

        logger.info(
            "google_contacts_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )

        return RedirectResponse(url=redirect_url, status_code=302)

    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "google_contacts")


@router.post(
    "/google-contacts/activate",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Activate Google Contacts connector",
    description="Handle Google Contacts OAuth callback and activate connector.",
)
async def activate_google_contacts_connector(
    data: GoogleContactsOAuthRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    """Activate Google Contacts connector with OAuth callback data."""
    service = ConnectorService(db)
    return await service.handle_google_contacts_callback_stateless(data.code, data.state)


# ========== GOOGLE CALENDAR CONNECTOR ==========


@router.get(
    "/google-calendar/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Google Calendar OAuth",
    description="Initiate Google Calendar OAuth flow. Returns authorization URL.",
)
async def initiate_google_calendar_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Google Calendar OAuth flow."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.initiate_google_calendar_oauth(user_id)


@router.get(
    "/google-calendar/callback",
    summary="Google Calendar OAuth callback",
    description=(
        "Handle OAuth callback from Google and redirect to frontend. "
        "This endpoint does NOT require authentication."
    ),
    include_in_schema=False,
)
async def google_calendar_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Google Calendar OAuth callback."""
    from src.core.config import settings

    service = ConnectorService(db)

    try:
        connector = await service.handle_google_calendar_callback_stateless(code, state)

        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=google_calendar"
        )

        logger.info(
            "google_calendar_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )

        return RedirectResponse(url=redirect_url, status_code=302)

    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "google_calendar")


# ========== GOOGLE DRIVE CONNECTOR ==========


@router.get(
    "/google-drive/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Google Drive OAuth",
    description="Initiate Google Drive OAuth flow. Returns authorization URL.",
)
async def initiate_google_drive_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Google Drive OAuth flow."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.initiate_google_drive_oauth(user_id)


@router.get(
    "/google-drive/callback",
    summary="Google Drive OAuth callback",
    description=(
        "Handle OAuth callback from Google and redirect to frontend. "
        "This endpoint does NOT require authentication."
    ),
    include_in_schema=False,
)
async def google_drive_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Google Drive OAuth callback."""
    from src.core.config import settings

    service = ConnectorService(db)

    try:
        connector = await service.handle_google_drive_callback_stateless(code, state)

        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=google_drive"
        )

        logger.info(
            "google_drive_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )

        return RedirectResponse(url=redirect_url, status_code=302)

    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "google_drive")


# ========== GOOGLE TASKS CONNECTOR ==========


@router.get(
    "/google-tasks/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Google Tasks OAuth",
    description="Initiate Google Tasks OAuth flow. Returns authorization URL.",
)
async def initiate_google_tasks_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Google Tasks OAuth flow."""
    user_id = current_user.id
    service = ConnectorService(db)
    return await service.initiate_google_tasks_oauth(user_id)


@router.get(
    "/google-tasks/callback",
    summary="Google Tasks OAuth callback",
    description=(
        "Handle OAuth callback from Google and redirect to frontend. "
        "This endpoint does NOT require authentication."
    ),
    include_in_schema=False,
)
async def google_tasks_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Google Tasks OAuth callback."""
    from src.core.config import settings

    service = ConnectorService(db)

    try:
        connector = await service.handle_google_tasks_callback_stateless(code, state)

        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=google_tasks"
        )

        logger.info(
            "google_tasks_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )

        return RedirectResponse(url=redirect_url, status_code=302)

    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "google_tasks")


# ========== MICROSOFT 365 CONNECTORS (OAuth) ==========


@router.get(
    "/microsoft-outlook/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Microsoft Outlook OAuth",
    description="Initiate Microsoft Outlook OAuth flow. Returns authorization URL.",
)
async def initiate_microsoft_outlook_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Microsoft Outlook OAuth flow."""
    service = ConnectorService(db)
    return await service.initiate_microsoft_outlook_oauth(current_user.id)


@router.get(
    "/microsoft-outlook/callback",
    summary="Microsoft Outlook OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_outlook_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Microsoft Outlook OAuth callback."""
    from src.core.config import settings

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_outlook_callback_stateless(code, state)
        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=microsoft_outlook"
        )
        logger.info(
            "microsoft_outlook_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return RedirectResponse(url=redirect_url, status_code=302)
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_outlook")


@router.get(
    "/microsoft-calendar/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Microsoft Calendar OAuth",
    description="Initiate Microsoft Calendar OAuth flow. Returns authorization URL.",
)
async def initiate_microsoft_calendar_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Microsoft Calendar OAuth flow."""
    service = ConnectorService(db)
    return await service.initiate_microsoft_calendar_oauth(current_user.id)


@router.get(
    "/microsoft-calendar/callback",
    summary="Microsoft Calendar OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_calendar_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Microsoft Calendar OAuth callback."""
    from src.core.config import settings

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_calendar_callback_stateless(code, state)
        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=microsoft_calendar"
        )
        logger.info(
            "microsoft_calendar_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return RedirectResponse(url=redirect_url, status_code=302)
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_calendar")


@router.get(
    "/microsoft-contacts/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Microsoft Contacts OAuth",
    description="Initiate Microsoft Contacts OAuth flow. Returns authorization URL.",
)
async def initiate_microsoft_contacts_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Microsoft Contacts OAuth flow."""
    service = ConnectorService(db)
    return await service.initiate_microsoft_contacts_oauth(current_user.id)


@router.get(
    "/microsoft-contacts/callback",
    summary="Microsoft Contacts OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_contacts_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Microsoft Contacts OAuth callback."""
    from src.core.config import settings

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_contacts_callback_stateless(code, state)
        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=microsoft_contacts"
        )
        logger.info(
            "microsoft_contacts_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return RedirectResponse(url=redirect_url, status_code=302)
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_contacts")


@router.get(
    "/microsoft-tasks/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Microsoft To Do OAuth",
    description="Initiate Microsoft To Do OAuth flow. Returns authorization URL.",
)
async def initiate_microsoft_tasks_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate Microsoft To Do OAuth flow."""
    service = ConnectorService(db)
    return await service.initiate_microsoft_tasks_oauth(current_user.id)


@router.get(
    "/microsoft-tasks/callback",
    summary="Microsoft To Do OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_tasks_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Microsoft To Do OAuth callback."""
    from src.core.config import settings

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_tasks_callback_stateless(code, state)
        redirect_url = (
            f"{settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=microsoft_tasks"
        )
        logger.info(
            "microsoft_tasks_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return RedirectResponse(url=redirect_url, status_code=302)
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_tasks")


# ========== GOOGLE PLACES CONNECTOR (API Key based) ==========


@router.post(
    "/google-places/activate",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Activate Google Places connector",
    description=(
        "Enable Google Places connector for the user. "
        "Places uses a global API key, no user credentials needed. "
        "The user simply activates the connector to enable Places features."
    ),
)
async def activate_google_places_connector(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    """Activate Google Places connector (toggle-based, uses global API key)."""
    service = ConnectorService(db)
    return await service.activate_places_connector(current_user.id)


# ========== GOOGLE DRIVE THUMBNAIL PROXY ==========


@router.get(
    "/google-drive/thumbnail/{file_id}",
    summary="Proxy Google Drive thumbnail",
    description="Proxy endpoint to fetch Google Drive file thumbnails using API key.",
    responses={
        200: {"content": {"image/png": {}}, "description": "Thumbnail image"},
        404: {"description": "Thumbnail not found"},
    },
)
async def proxy_drive_thumbnail(
    file_id: str,
    sz: int = 220,
    current_user: User = Depends(get_current_active_session),
) -> StreamingResponse:
    """
    Proxy Google Drive thumbnail with API key authentication.

    This endpoint fetches thumbnails from Google Drive using the server's
    API key, allowing the frontend to display thumbnails without OAuth.

    Args:
        file_id: Google Drive file ID
        sz: Thumbnail size in pixels (default 220)

    Returns:
        StreamingResponse with the thumbnail image
    """
    import httpx

    from src.core.config import settings

    api_key = settings.google_api_key
    if not api_key:
        logger.warning("google_api_key_not_configured")
        raise_configuration_missing("google_drive", "api_key")

    # Google Drive thumbnail URL with API key
    thumbnail_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w{sz}"

    logger.debug(
        "drive_thumbnail_proxy_request",
        user_id=str(current_user.id),
        file_id=file_id,
        size=sz,
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                thumbnail_url,
                follow_redirects=True,
                timeout=HTTP_TIMEOUT_CONNECTOR_STANDARD,
            )

            if response.status_code != 200:
                logger.warning(
                    "drive_thumbnail_proxy_error",
                    user_id=str(current_user.id),
                    status_code=response.status_code,
                    file_id=file_id,
                )
                raise_external_service_fetch_error(
                    "google_drive", "thumbnail", response.status_code
                )

            content_type = response.headers.get("content-type", "image/png")

            logger.info(
                "drive_thumbnail_proxy_success",
                user_id=str(current_user.id),
                file_id=file_id,
                content_length=len(response.content),
            )

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                },
            )
    except httpx.RequestError as e:
        logger.error(
            "drive_thumbnail_proxy_request_error",
            user_id=str(current_user.id),
            file_id=file_id,
            error=str(e),
        )
        raise_external_service_connection_error("google_drive")


# ========== GOOGLE PLACES PHOTO PROXY ==========


@router.get(
    "/google-places/photo/{photo_name:path}",
    summary="Proxy Google Places photo",
    description="Proxy endpoint to fetch Google Places photos using global API key.",
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Photo image"},
        403: {"description": "Places connector not enabled for user"},
        404: {"description": "Photo not found"},
    },
)
async def proxy_places_photo(
    photo_name: str,
    max_height: int = 400,
    max_width: int = 400,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Proxy Google Places photo with global API key.

    Requires the user to have the Places connector enabled.
    Uses the global GOOGLE_API_KEY for authentication.

    Args:
        photo_name: Full photo resource name (e.g., "places/ChIJ.../photos/AWYs...")
        max_height: Maximum height in pixels (default 400)
        max_width: Maximum width in pixels (default 400)

    Returns:
        StreamingResponse with the image data
    """
    import re

    import httpx
    from fastapi import HTTPException

    from src.core.config import settings
    from src.core.exceptions import raise_configuration_missing, raise_permission_denied

    # Validate photo_name format to prevent path manipulation on Google API
    places_photo_pattern = re.compile(r"^places/[^/]+/photos/[^/]+$")
    if not places_photo_pattern.match(photo_name):
        logger.warning(
            "places_photo_invalid_name",
            photo_name=photo_name[:80],
        )
        raise HTTPException(status_code=400, detail="Invalid photo resource name format")

    user_id = current_user.id
    service = ConnectorService(db)

    try:
        # Verify user has Places connector enabled
        if not await service.is_places_enabled(user_id):
            logger.warning(
                "places_photo_proxy_not_enabled",
                user_id=str(user_id),
            )
            raise_permission_denied(
                action="access",
                resource_type="google_places_photo",
                details="Google Places connector must be enabled",
            )

        # Verify global API key is configured
        api_key = settings.google_api_key
        if not api_key:
            logger.error("places_photo_proxy_no_api_key")
            raise_configuration_missing("google_places", "GOOGLE_API_KEY")

        # Construct photo URL with API key
        photo_url = (
            f"https://places.googleapis.com/v1/{photo_name}/media"
            f"?maxHeightPx={max_height}&maxWidthPx={max_width}&key={api_key}"
        )

        logger.info(
            "places_photo_proxy_request",
            user_id=str(user_id),
            photo_name=photo_name[:50] + "..." if len(photo_name) > 50 else photo_name,
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                photo_url,
                follow_redirects=True,
                timeout=HTTP_TIMEOUT_CONNECTOR_LONG,
            )

            if response.status_code != 200:
                logger.warning(
                    "places_photo_proxy_error",
                    user_id=str(user_id),
                    status_code=response.status_code,
                    photo_name=photo_name[:50],
                )
                raise_external_service_fetch_error("google_places", "photo", response.status_code)

            # Get content type from response
            content_type = response.headers.get("content-type", "image/jpeg")

            # NOTE: Photo API calls are tracked in places_tools.py when photo_url is generated
            # This ensures the cost is associated with the correct message (run_id).
            # The proxy endpoint just fetches the image, it doesn't track separately
            # to avoid double-counting.

            logger.info(
                "places_photo_proxy_success",
                user_id=str(user_id),
                content_length=len(response.content),
            )

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                },
            )
    except httpx.RequestError as e:
        logger.error(
            "places_photo_proxy_request_error",
            user_id=str(user_id),
            error=str(e),
        )
        raise_external_service_connection_error("google_places")
    except (HTTPException, InternalServerError):
        # Re-raise HTTP/API exceptions as-is
        raise
    except Exception as e:
        # Catch any other unexpected errors
        logger.exception(
            "places_photo_proxy_unexpected_error",
            user_id=str(user_id),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_internal_error(
            detail=APIMessages.internal_error(type(e).__name__),
            error_type=type(e).__name__,
        )


# ========== API KEY CONNECTORS ==========


@router.post(
    "/api-key/activate",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Activate API Key connector",
    description=(
        "Activate a connector using API key authentication. "
        "The API key is encrypted before storage. "
        "Use this for services that use API keys instead of OAuth."
    ),
)
async def activate_api_key_connector(
    data: APIKeyActivationRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    """
    Activate a connector with API key.

    Security:
    - API key is encrypted with Fernet before storage
    - Key is never logged in full (only masked version)
    - Key validation is performed before activation
    """
    user_id = current_user.id
    service = ConnectorService(db)

    # Validate key format first
    is_valid, message = await service.validate_api_key(
        data.connector_type,
        data.api_key,
        data.api_secret,
    )

    if not is_valid:
        from src.core.exceptions import raise_invalid_input

        raise_invalid_input(message, field="api_key")

    return await service.activate_api_key_connector(
        user_id=user_id,
        connector_type=data.connector_type,
        api_key=data.api_key,
        api_secret=data.api_secret,
        key_name=data.key_name,
    )


@router.post(
    "/api-key/validate",
    response_model=APIKeyValidationResponse,
    summary="Validate API key",
    description=(
        "Validate an API key before activation. "
        "Checks key format and optionally tests connectivity."
    ),
)
async def validate_api_key(
    data: APIKeyValidationRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> APIKeyValidationResponse:
    """Validate API key format and connectivity."""
    service = ConnectorService(db)

    is_valid, message = await service.validate_api_key(
        data.connector_type,
        data.api_key,
        data.api_secret,
    )

    # Mask the key for response (show first 4 and last 4 chars)
    masked_key = f"{data.api_key[:4]}...{data.api_key[-4:]}" if len(data.api_key) > 8 else "****"

    return APIKeyValidationResponse(
        is_valid=is_valid,
        message=message,
        masked_key=masked_key,
        expires_at=None,  # Could be detected for some services
    )


@router.get(
    "/api-key/{connector_id}/info",
    response_model=ConnectorAPIKeyInfo,
    summary="Get API key info",
    description=(
        "Get information about an API key connector. "
        "Returns masked key and metadata, NOT the actual key."
    ),
)
async def get_api_key_info(
    connector_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorAPIKeyInfo:
    """Get API key connector info (masked key, metadata)."""
    from src.core.security import decrypt_data
    from src.domains.connectors.schemas import APIKeyCredentials

    user_id = current_user.id
    service = ConnectorService(db)

    # Get connector and verify ownership
    await service.get_connector_by_id(user_id, connector_id)

    # Get the actual connector for decryption
    connector = await service.repository.get_by_id(connector_id)
    if not connector:
        from src.core.exceptions import raise_connector_not_found

        raise_connector_not_found(connector_id)

    # Decrypt to get masked key
    try:
        decrypted_json = decrypt_data(connector.credentials_encrypted)
        credentials = APIKeyCredentials.model_validate_json(decrypted_json)
    except Exception:
        from src.core.exceptions import raise_invalid_input

        raise_invalid_input("Failed to decrypt credentials", connector_id=str(connector_id))

    metadata = connector.connector_metadata or {}

    # Mask the key for response (show first 4 and last 4 chars)
    masked_key = (
        f"{credentials.api_key[:4]}...{credentials.api_key[-4:]}"
        if len(credentials.api_key) > 8
        else "****"
    )

    return ConnectorAPIKeyInfo(
        key_name=credentials.key_name,
        masked_key=masked_key,
        has_secret=bool(credentials.api_secret),
        expires_at=credentials.expires_at,
        created_at=connector.created_at,
        last_used_at=metadata.get("last_used_at"),
    )


@router.put(
    "/api-key/{connector_id}/rotate",
    response_model=ConnectorResponse,
    summary="Rotate API key",
    description=(
        "Replace the API key for a connector. Old key is discarded and new key is encrypted."
    ),
)
async def rotate_api_key(
    connector_id: UUID,
    data: APIKeyActivationRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    """Rotate (replace) an API key."""
    user_id = current_user.id
    service = ConnectorService(db)

    # Verify ownership first
    await service.get_connector_by_id(user_id, connector_id)

    # Validate new key
    is_valid, message = await service.validate_api_key(
        data.connector_type,
        data.api_key,
        data.api_secret,
    )

    if not is_valid:
        from src.core.exceptions import raise_invalid_input

        raise_invalid_input(message, field="api_key")

    # Activate with new key (this will update the existing connector)
    return await service.activate_api_key_connector(
        user_id=user_id,
        connector_type=data.connector_type,
        api_key=data.api_key,
        api_secret=data.api_secret,
        key_name=data.key_name,
        metadata={"rotated_at": "auto"},
    )


# ========== ADMIN ENDPOINTS ==========


@router.get(
    "/admin/global-config",
    response_model=list[ConnectorGlobalConfigResponse],
    summary="Get all connector global configurations (Admin)",
    description="Get all connector global configurations. **Requires superuser role.**",
)
async def get_all_connector_configs(
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectorGlobalConfigResponse]:
    """Get all connector global configurations (admin only)."""
    service = ConnectorService(db)
    return await service.get_global_config_all()


@router.put(
    "/admin/global-config/{connector_type}",
    response_model=ConnectorGlobalConfigResponse,
    summary="Update connector global configuration (Admin)",
    description=(
        "Update or create global configuration for connector type. "
        "Allows admins to enable/disable connector types globally. "
        "When disabling, all active connectors of this type are revoked. "
        "**Requires superuser role.**"
    ),
)
async def update_connector_config(
    connector_type: ConnectorType,
    update_data: ConnectorGlobalConfigUpdate,
    current_user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorGlobalConfigResponse:
    """Update or create global configuration for connector type (admin only)."""
    service = ConnectorService(db)
    return await service.update_global_config(connector_type, update_data, current_user.id)


# ============================================================================
# APPLE iCLOUD ENDPOINTS
# ============================================================================


@router.post(
    "/apple/validate",
    response_model=AppleValidationResponse,
    summary="Validate Apple iCloud credentials",
    description=(
        "Test Apple ID + app-specific password without activating any service. "
        "Used to verify credentials before activation."
    ),
)
async def validate_apple_connection(
    data: AppleValidationRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> AppleValidationResponse:
    """Validate Apple iCloud credentials."""
    service = ConnectorService(db)
    # Test all Apple protocols to verify credentials
    all_apple_services = [
        ConnectorType.APPLE_EMAIL,
        ConnectorType.APPLE_CALENDAR,
        ConnectorType.APPLE_CONTACTS,
    ]
    success, message = await service.test_apple_connection(
        data.apple_id, data.app_password, all_apple_services
    )
    return AppleValidationResponse(
        is_valid=success,
        message=message,
    )


@router.post(
    "/apple/activate",
    response_model=AppleActivationResponse,
    summary="Activate Apple iCloud connectors",
    description=(
        "Activate one or more Apple iCloud services (Email, Calendar, Contacts). "
        "Tests credentials, then creates connectors with mutual exclusivity "
        "(deactivates conflicting Google connectors)."
    ),
)
async def activate_apple_connectors(
    data: AppleActivationRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> AppleActivationResponse:
    """Activate Apple iCloud connectors."""
    service = ConnectorService(db)
    return await service.activate_apple_connectors(
        user_id=current_user.id,
        apple_id=data.apple_id,
        app_password=data.app_password,
        services=data.services,
    )


# ============================================================================
# PHILIPS HUE SMART HOME
# ============================================================================


@router.post(
    "/philips-hue/discover",
    response_model=HueBridgeDiscoveryResponse,
    summary="Discover Philips Hue bridges on local network",
    description=(
        "Discover Hue bridges via discovery.meethue.com. "
        "Returns a list of bridges found on the local network."
    ),
)
async def discover_hue_bridges(
    current_user: User = Depends(get_current_active_session),
) -> HueBridgeDiscoveryResponse:
    """Discover Hue bridges via Philips discovery service."""
    from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient

    try:
        bridges_raw = await PhilipsHueClient.discover_bridges()
        bridges = [HueBridgeInfo(**b) for b in bridges_raw]
    except Exception as e:
        logger.error("hue_discovery_failed", error=str(e))
        bridges = []

    return HueBridgeDiscoveryResponse(bridges=bridges)


@router.post(
    "/philips-hue/pair",
    response_model=HuePairingResponse,
    summary="Pair with Hue Bridge via press-link",
    description=(
        "Initiate press-link pairing with a Hue Bridge. "
        "The user must press the physical button on the bridge within "
        "30 seconds before calling this endpoint."
    ),
)
async def pair_hue_bridge(
    data: HuePairingRequest,
    current_user: User = Depends(get_current_active_session),
) -> HuePairingResponse:
    """Pair with Hue Bridge via press-link authentication."""
    from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient

    try:
        result = await PhilipsHueClient.pair_bridge(data.bridge_ip)

        # Parse Hue API response
        if isinstance(result, list) and result:
            first = result[0]
            if "success" in first:
                return HuePairingResponse(
                    success=True,
                    application_key=first["success"].get("username"),
                    client_key=first["success"].get("clientkey"),
                )
            elif "error" in first:
                return HuePairingResponse(
                    success=False,
                    error=first["error"].get("description", "Pairing failed"),
                )

        return HuePairingResponse(
            success=False,
            error="Unexpected response from Hue Bridge",
        )
    except Exception as e:
        logger.error(
            "hue_pairing_failed",
            bridge_ip=data.bridge_ip,
            error=str(e),
        )
        return HuePairingResponse(
            success=False,
            error=f"Cannot reach bridge at {data.bridge_ip}: {e}",
        )


@router.post(
    "/philips-hue/activate/local",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Activate Hue connector in local mode",
    description=(
        "Activate Philips Hue connector after successful press-link pairing. "
        "Validates connectivity to the bridge before activation."
    ),
)
async def activate_hue_local(
    data: HueLocalActivationRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    """Activate Hue connector with local bridge credentials."""
    service = ConnectorService(db)
    return await service.activate_hue_local(
        user_id=current_user.id,
        bridge_ip=data.bridge_ip,
        application_key=data.application_key,
        client_key=data.client_key,
        bridge_id=data.bridge_id,
    )


@router.get(
    "/philips-hue/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate Hue Remote API OAuth2 flow",
    description=(
        "Generate OAuth2 authorization URL for remote Hue Bridge access. "
        "Used when the LIA server is not on the same network as the bridge."
    ),
)
async def initiate_hue_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Generate OAuth2 authorization URL for Hue Remote API."""
    service = ConnectorService(db)
    return await service.initiate_hue_oauth(user_id=current_user.id)


@router.get(
    "/philips-hue/callback",
    summary="Hue Remote API OAuth2 callback",
    description="Handle OAuth2 callback from meethue.com after user authorization.",
)
async def hue_oauth_callback(
    code: str = Query(..., description="Authorization code from Hue"),
    state: str = Query(..., description="CSRF state token"),
    error: str | None = Query(None, description="Error from OAuth provider"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Hue Remote API OAuth2 callback."""
    from src.core.config import settings as app_settings

    if error:
        logger.warning("hue_oauth_callback_error", error=error)
        return handle_oauth_callback_error_redirect(
            ValueError(f"OAuth provider error: {error}"),
            "philips_hue",
        )

    service = ConnectorService(db)
    try:
        connector = await service.handle_hue_oauth_callback(code=code, state=state)

        redirect_url = (
            f"{app_settings.frontend_url}/dashboard/settings?"
            f"connector_added=true&connector_id={connector.id}"
            f"&connector_type=philips_hue"
        )

        logger.info(
            "hue_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )

        return RedirectResponse(url=redirect_url, status_code=302)
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "philips_hue")


@router.post(
    "/philips-hue/test",
    response_model=dict[str, Any],
    summary="Test Hue Bridge connectivity",
    description="Test connection to the configured Hue Bridge.",
)
async def test_hue_connection(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Test connection to configured Hue Bridge."""
    from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient

    service = ConnectorService(db)
    credentials = await service.get_hue_credentials(current_user.id)
    if not credentials:
        raise_connector_not_found(connector_id=current_user.id)

    client = PhilipsHueClient(current_user.id, credentials, service)
    bridge_info = await client.test_connection()
    data = bridge_info.get("data", [{}])
    return {"success": True, "bridge": data[0] if data else {}}
