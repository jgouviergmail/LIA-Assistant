"""Grouped Google/Microsoft authorization endpoints for selected connectors."""

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input
from src.core.session_dependencies import get_current_active_session
from src.domains.connectors.error_handlers import handle_oauth_callback_error_redirect
from src.domains.connectors.oauth_bulk_service import BulkOAuthService, OAuthAccountMismatchError
from src.domains.connectors.oauth_return import (
    bulk_connector_success_return,
    connector_error_return,
    oauth_return_is_native,
)
from src.domains.connectors.schemas import (
    BulkConnectAllRequest,
    BulkReconnectRequest,
    ConnectorOAuthInitiate,
)
from src.domains.users.models import User

bulk_oauth_router = APIRouter()


@bulk_oauth_router.post(
    "/oauth-bulk/{provider}/connect-all/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Connect available provider services with one OAuth authorization",
)
async def initiate_bulk_oauth_connection(
    provider: Literal["google", "microsoft"],
    request: BulkConnectAllRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Server derives available services and scopes; caller may select one owned grant."""
    try:
        return await BulkOAuthService(db).initiate_connect_all(
            current_user.id, provider, request.grant_id
        )
    except ValueError as error:
        raise_invalid_input(str(error))


@bulk_oauth_router.post(
    "/oauth-bulk/{provider}/authorize",
    response_model=ConnectorOAuthInitiate,
    summary="Reconnect selected provider services with one OAuth authorization",
)
async def initiate_bulk_oauth_reconnection(
    provider: Literal["google", "microsoft"],
    request: BulkReconnectRequest,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConnectorOAuthInitiate:
    """Only the server decides which configured services and scopes are eligible."""
    try:
        return await BulkOAuthService(db).initiate_reconnection(
            current_user.id, provider, request.connector_types
        )
    except ValueError as error:
        raise_invalid_input(str(error))


@bulk_oauth_router.get("/oauth-bulk/{provider}/callback", include_in_schema=False)
async def bulk_oauth_callback(
    provider: Literal["google", "microsoft"],
    state: str,
    code: str | None = None,
    error: str | None = None,
    is_native: bool = Depends(oauth_return_is_native),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Close the server-side PKCE flow and report partial consent honestly."""
    if error or not code:
        return connector_error_return(is_native=is_native, error_code="oauth_failed")
    try:
        result = await BulkOAuthService(db).complete_callback(provider, code, state)
        return bulk_connector_success_return(
            is_native=is_native,
            provider=provider,
            activated=len(result.activated),
            denied=len(result.denied),
            mode=result.mode,
        )
    except OAuthAccountMismatchError:
        await db.rollback()
        return connector_error_return(is_native=is_native, error_code="account_mismatch")
    except Exception as callback_error:
        await db.rollback()
        return handle_oauth_callback_error_redirect(
            callback_error, f"{provider}_bulk", is_native=is_native
        )
