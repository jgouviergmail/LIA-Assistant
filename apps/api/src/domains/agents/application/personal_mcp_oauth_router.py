"""Private no-store OAuth routes, bound to the authenticated original browser."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import RATE_LIMIT_PER_MINUTE_DEFAULT
from src.core.dependencies import get_db
from src.core.exceptions import BaseAPIException
from src.core.native_client import detect_native_client
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import ApplicationCommandStatus
from src.domains.agents.application.personal_mcp_oauth_service import (
    PersonalMCPOAuthStartResponse,
    complete_application_personal_mcp_oauth,
    start_application_personal_mcp_oauth,
)
from src.domains.agents.application.private_input_route import PrivateApplicationInputRoute
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session

router = APIRouter(route_class=PrivateApplicationInputRoute)
_rate_limit = create_user_rate_limiter(
    action="application_command_resume", max_calls=RATE_LIMIT_PER_MINUTE_DEFAULT
)


@router.post(
    "/{command_id}/personal-mcp-oauth/{stage}",
    response_model=PersonalMCPOAuthStartResponse | ApplicationCommandStatus,
    dependencies=[Depends(_rate_limit), Depends(detect_native_client)],
)
async def application_personal_mcp_oauth(
    command_id: UUID,
    stage: Literal["start", "complete"],
    request: Request,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> PersonalMCPOAuthStartResponse | ApplicationCommandStatus:
    response.headers["Cache-Control"] = "no-store"
    origin = bind_browser_session(user.id, request.cookies.get(settings.session_cookie_name))
    try:
        if stage == "start":
            return await start_application_personal_mcp_oauth(db, user.id, command_id, origin)
        return await complete_application_personal_mcp_oauth(db, user.id, command_id, origin)
    except ContinuationCompletionUnknown:
        raise BaseAPIException(
            status_code=503, detail={"error_code": "COMPLETION_UNKNOWN"}
        ) from None
    except CommandRejected as error:
        raise BaseAPIException(status_code=409, detail={"error_code": error.code}) from None
    except SQLAlchemyError, RedisError:
        raise BaseAPIException(status_code=503, detail={"error_code": "DEPENDENCY_ERROR"}) from None
    except ValueError:
        raise BaseAPIException(status_code=422, detail={"error_code": "INVALID_INPUT"}) from None
