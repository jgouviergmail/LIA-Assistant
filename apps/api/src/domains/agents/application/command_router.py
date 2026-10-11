"""Authenticated browser observation; origin identity has no model-controlled input."""

from collections.abc import Awaitable, Callable
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request, Response
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_device_identity import APPLICATION_DEVICE_HEADER
from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.constants import RATE_LIMIT_PER_MINUTE_DEFAULT, SKILLS_MAX_FILE_SIZE_KB
from src.core.dependencies import get_db
from src.core.exceptions import AuthorizationError, BaseAPIException, raise_step_up_required
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.asset_download_service import serve_asset_download_command
from src.domains.agents.application.bookmark_download_service import serve_bookmark_download_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import (
    ApplicationCommandStatus,
    read_command_status,
)
from src.domains.agents.application.document_archive_service import serve_document_archive_command
from src.domains.agents.application.document_download_service import serve_document_download_command
from src.domains.agents.application.document_upload_form import parse_document_upload_form
from src.domains.agents.application.document_upload_service import serve_document_upload_command
from src.domains.agents.application.export_download_service import serve_export_download_command
from src.domains.agents.application.health_token_creation_service import serve_health_token_creation
from src.domains.agents.application.management_export_service import serve_management_export_command
from src.domains.agents.application.meeting_pdf_download import serve_meeting_pdf_command
from src.domains.agents.application.operation_spec import ApplicationEmptyRead
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    PersonalMCPConfigurationSubmit,
)
from src.domains.agents.application.personal_mcp_configuration_service import (
    serve_personal_mcp_configuration,
)
from src.domains.agents.application.personal_mcp_oauth_router import router as _oauth_router
from src.domains.agents.application.plugin_file_upload_service import (
    serve_plugin_file_upload_command,
)
from src.domains.agents.application.private_input_route import PrivateApplicationInputRoute
from src.domains.agents.application.recording_device_schemas import (
    RecordingDeviceAck,
    RecordingDeviceClaim,
)
from src.domains.agents.application.recording_device_service import (
    acknowledge_recording_device,
    claim_recording_device,
)
from src.domains.agents.application.secure_continuation import (
    ContinuationCompletionUnknown,
    resume_secure_application_command,
)
from src.domains.agents.application.skill_download_service import serve_skill_download_command
from src.domains.agents.application.skill_file_upload_service import serve_skill_file_upload_command
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.health_metrics.schemas import HealthMetricTokenCreateResponse
from src.domains.users.models import User
from src.infrastructure.account_export_downloads import ExportDownloadCompletionUnknown
from src.infrastructure.application_sessions import bind_browser_session

router = APIRouter(prefix="/application-commands", tags=["Application commands"])
_private_router = APIRouter(route_class=PrivateApplicationInputRoute)
rate_limit_commands = create_user_rate_limiter(
    action="application_command_read",
    max_calls=RATE_LIMIT_PER_MINUTE_DEFAULT,
)
rate_limit_command_resume = create_user_rate_limiter(
    action="application_command_resume",
    max_calls=RATE_LIMIT_PER_MINUTE_DEFAULT,
)


def _browser_origin(actor_id: UUID, request: Request) -> ApplicationOrigin | None:
    cookie = request.cookies.get(settings.session_cookie_name)
    address = request.headers.get(APPLICATION_DEVICE_HEADER)
    if address is None:
        return bind_browser_session(actor_id, cookie)
    return bind_browser_session(actor_id, cookie, device_id=address)


@router.post(
    "/{command_id}/device/claim",
    response_model=RecordingDeviceClaim | None,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def claim_device_command(
    command_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RecordingDeviceClaim | None:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await claim_recording_device(
            db, user.id, command_id, _browser_origin(user.id, request)
        )
    except AuthorizationError as error:
        _raise_resume_authorization(error)
    except SQLAlchemyError, RedisError, OSError:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "COMPLETION_UNKNOWN"},
            headers={"Cache-Control": "no-store"},
        ) from None


@router.post(
    "/{command_id}/device/ack",
    response_model=ApplicationCommandStatus,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def acknowledge_device_command(
    command_id: UUID,
    ack: RecordingDeviceAck,
    request: Request,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ApplicationCommandStatus:
    response.headers["Cache-Control"] = "no-store"
    origin = _browser_origin(user.id, request)
    try:
        await acknowledge_recording_device(db, user.id, command_id, ack, origin)
        return await read_command_status(db, user.id, command_id, origin)
    except AuthorizationError as error:
        _raise_resume_authorization(error)
    except SQLAlchemyError, RedisError, OSError:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "COMPLETION_UNKNOWN"},
            headers={"Cache-Control": "no-store"},
        ) from None


@router.post(
    "/{command_id}/health-token",
    response_model=HealthMetricTokenCreateResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def create_application_health_token(
    command_id: UUID,
    request: Request,
    response: Response,
    body: ApplicationEmptyRead | None = Body(default=None),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HealthMetricTokenCreateResponse:
    """Return the once-only secret to the approved browser, never an assistant result."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    origin = _browser_origin(user.id, request)
    try:
        return await serve_health_token_creation(db, user.id, command_id, origin)
    except ContinuationCompletionUnknown:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "COMPLETION_UNKNOWN"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except CommandRejected as error:
        raise BaseAPIException(
            status_code=409,
            detail={"error_code": error.code},
            headers={"Cache-Control": "no-store"},
        ) from None
    except SQLAlchemyError, RedisError:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "DEPENDENCY_ERROR"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except ValueError:
        raise BaseAPIException(
            status_code=422,
            detail={"error_code": "INVALID_INPUT"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except BaseAPIException as error:
        error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
        raise


@router.get(
    "/{command_id}",
    response_model=ApplicationCommandStatus,
    dependencies=[Depends(rate_limit_commands)],
)
async def get_application_command_status(
    command_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ApplicationCommandStatus:
    response.headers["Cache-Control"] = "no-store"
    origin = _browser_origin(user.id, request)
    try:
        return await read_command_status(db, user.id, command_id, origin)
    except SQLAlchemyError, RedisError:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "DEPENDENCY_ERROR"},
            headers={"Cache-Control": "no-store"},
        ) from None


@_private_router.post(
    "/{command_id}/personal-mcp",
    response_model=ApplicationCommandStatus,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def configure_application_personal_mcp(
    command_id: UUID,
    request: Request,
    response: Response,
    body: PersonalMCPConfigurationSubmit,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ApplicationCommandStatus:
    """Accept private values from the once-approved original live browser only."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    origin = _browser_origin(user.id, request)
    try:
        return await serve_personal_mcp_configuration(db, user.id, command_id, body.values, origin)
    except ContinuationCompletionUnknown:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "COMPLETION_UNKNOWN"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except CommandRejected as error:
        raise BaseAPIException(
            status_code=409,
            detail={"error_code": error.code},
            headers={"Cache-Control": "no-store"},
        ) from None
    except SQLAlchemyError, RedisError:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "DEPENDENCY_ERROR"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except ValueError:
        raise BaseAPIException(
            status_code=422,
            detail={"error_code": "INVALID_INPUT"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except BaseAPIException as error:
        error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
        raise


router.include_router(_private_router)

router.include_router(_oauth_router)


def _raise_resume_authorization(error: AuthorizationError) -> NoReturn:
    if isinstance(error.detail, dict) and error.detail.get("error_code") == "STEP_UP_REQUIRED":
        try:
            raise_step_up_required()
        except AuthorizationError as challenge:
            challenge.headers = {"Cache-Control": "no-store"}
            raise challenge from None
    error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
    raise error


@router.get(
    "/{command_id}/download",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def download_application_export(
    command_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await _serve_browser_download(
        serve_export_download_command, db, user, command_id, request
    )


async def _serve_browser_download(
    serve: Callable[
        [AsyncSession, UUID, UUID, ApplicationOrigin | None], Awaitable[StreamingResponse]
    ],
    db: AsyncSession,
    user: User,
    command_id: UUID,
    request: Request,
) -> StreamingResponse:
    origin = _browser_origin(user.id, request)
    try:
        return await serve(db, user.id, command_id, origin)
    except ContinuationCompletionUnknown, ExportDownloadCompletionUnknown:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "COMPLETION_UNKNOWN"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except SQLAlchemyError, RedisError, OSError:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "DEPENDENCY_ERROR"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except CommandRejected as exc:
        raise BaseAPIException(
            status_code=409, detail={"error_code": exc.code}, headers={"Cache-Control": "no-store"}
        ) from None
    except ValueError:
        raise BaseAPIException(
            status_code=422,
            detail={"error_code": "INVALID_INPUT"},
            headers={"Cache-Control": "no-store"},
        ) from None
    except BaseAPIException as exc:
        exc.headers = {**(exc.headers or {}), "Cache-Control": "no-store"}
        raise


@router.get(
    "/{command_id}/management-export",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def download_management_export(
    command_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await _serve_browser_download(
        serve_management_export_command, db, user, command_id, request
    )


@router.post(
    "/{command_id}/document-upload",
    response_model=ApplicationExecutionOutcome,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def upload_knowledge_document(
    command_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ApplicationExecutionOutcome:
    response.headers["Cache-Control"] = "no-store"
    origin = _browser_origin(user.id, request)
    try:
        return await serve_document_upload_command(
            db,
            user.id,
            command_id,
            origin,
            file_confirmed=request.headers.get("x-lia-file-confirmed") == "true",
            parse_form=lambda: parse_document_upload_form(request),
        )
    except ContinuationCompletionUnknown:
        code, http_status = "COMPLETION_UNKNOWN", 503
    except SQLAlchemyError, RedisError, OSError:
        code, http_status = "DEPENDENCY_ERROR", 503
    except CommandRejected as error:
        code, http_status = error.code, 409
    except ValueError:
        code, http_status = "INVALID_INPUT", 422
    except BaseAPIException as error:
        error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
        raise
    raise BaseAPIException(
        status_code=http_status, detail={"error_code": code}, headers={"Cache-Control": "no-store"}
    )


@router.get(
    "/{command_id}/meeting-pdf",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def download_meeting_pdf(
    command_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await _serve_browser_download(serve_meeting_pdf_command, db, user, command_id, request)


@router.get(
    "/{command_id}/asset-download",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def download_generated_asset(
    command_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await _serve_browser_download(
        serve_asset_download_command, db, user, command_id, request
    )


@router.get(
    "/{command_id}/bookmark-download",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def download_saved_answer(
    command_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await _serve_browser_download(
        serve_bookmark_download_command, db, user, command_id, request
    )


@router.get(
    "/{command_id}/skill-download",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def download_skill(
    command_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await _serve_browser_download(
        serve_skill_download_command, db, user, command_id, request
    )


@router.get(
    "/{command_id}/document-download",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def download_knowledge_document(
    command_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await _serve_browser_download(
        serve_document_download_command, db, user, command_id, request
    )


@router.get(
    "/{command_id}/document-archive",
    response_class=StreamingResponse,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def download_knowledge_archive(
    command_id: UUID,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await _serve_browser_download(
        serve_document_archive_command, db, user, command_id, request
    )


@router.post(
    "/{command_id}/resume",
    response_model=ApplicationCommandStatus,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def resume_application_command(
    command_id: UUID,
    request: Request,
    response: Response,
    body: ApplicationEmptyRead | None = Body(default=None),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ApplicationCommandStatus:
    response.headers["Cache-Control"] = "no-store"
    origin = _browser_origin(user.id, request)
    try:
        return await resume_secure_application_command(db, user.id, command_id, origin)
    except AuthorizationError as exc:
        _raise_resume_authorization(exc)
    except ContinuationCompletionUnknown:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "COMPLETION_UNKNOWN"},
            headers={"Cache-Control": "no-store"},
        ) from None

    except SQLAlchemyError, RedisError:
        raise BaseAPIException(
            status_code=503,
            detail={"error_code": "DEPENDENCY_ERROR"},
            headers={"Cache-Control": "no-store"},
        ) from None


@router.post(
    "/{command_id}/skill-upload",
    response_model=ApplicationExecutionOutcome,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def upload_personal_skill_file(
    command_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ApplicationExecutionOutcome:
    response.headers["Cache-Control"] = "no-store"
    origin = _browser_origin(user.id, request)
    try:
        return await serve_skill_file_upload_command(
            db,
            user.id,
            command_id,
            origin,
            file_confirmed=request.headers.get("x-lia-file-confirmed") == "true",
            parse_form=lambda: parse_document_upload_form(
                request, max_body_bytes=(SKILLS_MAX_FILE_SIZE_KB + 64) * 1024
            ),
        )
    except ContinuationCompletionUnknown:
        code, http_status = "COMPLETION_UNKNOWN", 503
    except SQLAlchemyError, RedisError, OSError:
        code, http_status = "DEPENDENCY_ERROR", 503
    except CommandRejected as error:
        code, http_status = error.code, 409
    except ValueError:
        code, http_status = "INVALID_INPUT", 422
    except BaseAPIException as error:
        error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
        raise
    raise BaseAPIException(
        status_code=http_status, detail={"error_code": code}, headers={"Cache-Control": "no-store"}
    )


@router.post(
    "/{command_id}/plugin-upload",
    response_model=ApplicationExecutionOutcome,
    dependencies=[Depends(rate_limit_command_resume)],
)
async def upload_personal_plugin_file(
    command_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ApplicationExecutionOutcome:
    response.headers["Cache-Control"] = "no-store"
    origin = _browser_origin(user.id, request)
    try:
        return await serve_plugin_file_upload_command(
            db,
            user.id,
            command_id,
            origin,
            file_confirmed=request.headers.get("x-lia-file-confirmed") == "true",
            parse_form=lambda: parse_document_upload_form(
                request,
                max_body_bytes=(settings.plugins_max_file_size_kb + 64) * 1024,
            ),
        )
    except ContinuationCompletionUnknown:
        code, http_status = "COMPLETION_UNKNOWN", 503
    except SQLAlchemyError, RedisError, OSError:
        code, http_status = "DEPENDENCY_ERROR", 503
    except CommandRejected as error:
        code, http_status = error.code, 409
    except ValueError:
        code, http_status = "INVALID_INPUT", 422
    except BaseAPIException as error:
        error.headers = {**(error.headers or {}), "Cache-Control": "no-store"}
        raise
    raise BaseAPIException(
        status_code=http_status,
        detail={"error_code": code},
        headers={"Cache-Control": "no-store"},
    )
