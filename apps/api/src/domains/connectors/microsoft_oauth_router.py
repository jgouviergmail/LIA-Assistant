"""The OAuth doors of the Microsoft 365 connectors.

Moved out of ``connectors/router.py`` (file-size ratchet) as one cohesive sub-router: each
connector has its ``authorize`` and its ``callback``, paths and demo guard unchanged, which
the main router includes.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.connectors.error_handlers import handle_oauth_callback_error_redirect
from src.domains.connectors.oauth_return import connector_success_return, oauth_return_is_native
from src.domains.connectors.schemas import ConnectorOAuthInitiate
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

microsoft_oauth_router = APIRouter()


@microsoft_oauth_router.get(
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


@microsoft_oauth_router.get(
    "/microsoft-outlook/callback",
    summary="Microsoft Outlook OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_outlook_oauth_callback(
    code: str,
    state: str,
    is_native: bool = Depends(oauth_return_is_native),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Microsoft Outlook OAuth callback."""

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_outlook_callback_stateless(code, state)
        logger.info(
            "microsoft_outlook_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return connector_success_return(
            is_native=is_native,
            connector_type="microsoft_outlook",
            connector_id=connector.id,
        )
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_outlook", is_native=is_native)


@microsoft_oauth_router.get(
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


@microsoft_oauth_router.get(
    "/microsoft-calendar/callback",
    summary="Microsoft Calendar OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_calendar_oauth_callback(
    code: str,
    state: str,
    is_native: bool = Depends(oauth_return_is_native),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Microsoft Calendar OAuth callback."""

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_calendar_callback_stateless(code, state)
        logger.info(
            "microsoft_calendar_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return connector_success_return(
            is_native=is_native,
            connector_type="microsoft_calendar",
            connector_id=connector.id,
        )
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_calendar", is_native=is_native)


@microsoft_oauth_router.get(
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


@microsoft_oauth_router.get(
    "/microsoft-contacts/callback",
    summary="Microsoft Contacts OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_contacts_oauth_callback(
    code: str,
    state: str,
    is_native: bool = Depends(oauth_return_is_native),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Microsoft Contacts OAuth callback."""

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_contacts_callback_stateless(code, state)
        logger.info(
            "microsoft_contacts_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return connector_success_return(
            is_native=is_native,
            connector_type="microsoft_contacts",
            connector_id=connector.id,
        )
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_contacts", is_native=is_native)


@microsoft_oauth_router.get(
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


@microsoft_oauth_router.get(
    "/microsoft-tasks/callback",
    summary="Microsoft To Do OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_tasks_oauth_callback(
    code: str,
    state: str,
    is_native: bool = Depends(oauth_return_is_native),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Microsoft To Do OAuth callback."""

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_tasks_callback_stateless(code, state)
        logger.info(
            "microsoft_tasks_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return connector_success_return(
            is_native=is_native,
            connector_type="microsoft_tasks",
            connector_id=connector.id,
        )
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_tasks", is_native=is_native)


@microsoft_oauth_router.get(
    "/microsoft-onedrive/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Initiate OneDrive OAuth",
    description="Initiate OneDrive OAuth flow. Returns authorization URL.",
)
async def initiate_microsoft_onedrive_oauth(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Initiate OneDrive OAuth flow."""
    service = ConnectorService(db)
    return await service.initiate_microsoft_onedrive_oauth(current_user.id)


@microsoft_oauth_router.get(
    "/microsoft-onedrive/callback",
    summary="OneDrive OAuth callback",
    description="Handle OAuth callback from Microsoft and redirect to frontend.",
    include_in_schema=False,
)
async def microsoft_onedrive_oauth_callback(
    code: str,
    state: str,
    is_native: bool = Depends(oauth_return_is_native),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle OneDrive OAuth callback."""

    service = ConnectorService(db)
    try:
        connector = await service.handle_microsoft_onedrive_callback_stateless(code, state)
        logger.info(
            "microsoft_onedrive_oauth_callback_success",
            connector_id=str(connector.id),
            user_id=str(connector.user_id),
        )
        return connector_success_return(
            is_native=is_native,
            connector_type="microsoft_onedrive",
            connector_id=connector.id,
        )
    except Exception as e:
        return handle_oauth_callback_error_redirect(e, "microsoft_onedrive", is_native=is_native)
