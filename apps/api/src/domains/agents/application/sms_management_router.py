"""Session-only exact approval for the finite SMS settings operations."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.constants import RATE_LIMIT_PER_MINUTE_DEFAULT
from src.core.dependencies import get_db
from src.core.exceptions import AuthorizationError, BaseAPIException, raise_invalid_input
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.operation_spec import ApplicationEmptyRead
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.agents.application.sms_token_creation_service import serve_sms_token_creation
from src.domains.agents.application.sms_ui_commands import (
    SmsUiCompletion,
    SmsUiProposal,
    cancel_sms_ui,
    confirm_sms_ui,
    propose_sms_ui,
)
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.ingestion.schemas import IngestionTokenSecret
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session

router = APIRouter(route_class=PrivateApplicationInputRoute)
rate_limit = create_user_rate_limiter("sms_commands", RATE_LIMIT_PER_MINUTE_DEFAULT)


class SmsUiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: Literal[
        "sms_token.create",
        "sms_token.revoke",
        "sms_preferences.update",
        "sms_sender_block.update",
        "sms_messages.delete",
    ]
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class SmsUiConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def browser_origin(actor: User, request: Request) -> ApplicationOrigin:
    origin = bind_browser_session(actor.id, request.cookies.get(settings.session_cookie_name))
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    return origin


def unavailable() -> BaseAPIException:
    return BaseAPIException(
        status_code=503,
        detail={"error_code": "COMPLETION_UNKNOWN"},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/commands", response_model=SmsUiProposal, dependencies=[Depends(rate_limit)])
async def propose(
    selected: SmsUiRequest,
    request: Request,
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsUiProposal:
    try:
        return await propose_sms_ui(
            db, actor.id, selected.operation_id, selected.payload, browser_origin(actor, request)
        )
    except CommandRejected, ValueError:
        raise_invalid_input("Invalid SMS operation")
    except SQLAlchemyError, RedisError, OSError, TimeoutError:
        raise unavailable() from None


@router.post(
    "/commands/{command_id}/confirm",
    response_model=SmsUiCompletion,
    dependencies=[Depends(rate_limit)],
)
async def confirm(
    command_id: UUID,
    selected: SmsUiConfirmation,
    request: Request,
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsUiCompletion:
    try:
        return await confirm_sms_ui(
            db, actor.id, command_id, selected.content_digest, browser_origin(actor, request)
        )
    except CommandRejected:
        raise unavailable() from None
    except SQLAlchemyError, RedisError, OSError, TimeoutError:
        raise unavailable() from None


@router.post("/commands/{command_id}/cancel", status_code=204, dependencies=[Depends(rate_limit)])
async def cancel(
    command_id: UUID,
    request: Request,
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await cancel_sms_ui(db, actor.id, command_id, browser_origin(actor, request))
    except SQLAlchemyError, RedisError, OSError, TimeoutError:
        raise unavailable() from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post(
    "/commands/{command_id}/token",
    response_model=IngestionTokenSecret,
    dependencies=[Depends(rate_limit)],
)
async def create_approved_token(
    command_id: UUID,
    selected: ApplicationEmptyRead,
    request: Request,
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> IngestionTokenSecret:
    try:
        return await serve_sms_token_creation(
            db, actor.id, command_id, browser_origin(actor, request)
        )
    except CommandRejected as error:
        raise BaseAPIException(
            status_code=409,
            detail={"error_code": error.code},
            headers={"Cache-Control": "no-store"},
        ) from None
    except ContinuationCompletionUnknown, SQLAlchemyError, RedisError, OSError, TimeoutError:
        raise unavailable() from None
