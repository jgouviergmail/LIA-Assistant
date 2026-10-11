"""One typed native proposal boundary; source-domain preparation stays specific."""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    AuthorizationError,
    BaseAPIException,
    ResourceNotFoundError,
)
from src.core.exceptions import ValidationError as DomainValidationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.confirmation_policy import requires_confirmation
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config


async def prepare_native_tool[Request: BaseModel](
    request: Request | dict[str, object],
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    *,
    name: str,
    model: type[Request],
    prepare: Callable[[AsyncSession, UUID, Request], Awaitable[ApplicationActionDraftContent]],
    sessions: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> UnifiedToolOutput:
    actor = validate_runtime_config(runtime, name)
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        selected = model.model_validate(request)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid application proposal.", error_code="INVALID_INPUT"
        )
    try:
        async with sessions() as db:
            content = await prepare(db, UUID(actor.user_id), selected)
            if not requires_confirmation(content.operation_id, content.intent):
                # End preparation's DB lifetime before the shared domain writer runs.
                await db.commit()
                from src.domains.agents.application.reversible_execution import (
                    execute_reversible_change,
                )

                return await execute_reversible_change(content)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool=name,
                user_language=runtime.context.language,
            )
            await _save_native_proposal(db, content, output, runtime.context)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application proposal refused.",
            error_code=application_access_error_code(exc),
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Selected resource unavailable.",
            error_code="NOT_FOUND_OR_UNAUTHORIZED",
        )
    except DomainValidationError:
        return UnifiedToolOutput.failure(
            message="Source constraint refused.", error_code="CONSTRAINT_VIOLATION"
        )
    except CommandRejected as exc:
        return UnifiedToolOutput.failure(
            message="Application proposal refused.", error_code=exc.code
        )
    except BaseAPIException as exc:
        return UnifiedToolOutput.failure(
            message="Source resource unavailable or constraint refused.",
            error_code=("DEPENDENCY_ERROR" if exc.status_code >= 500 else "CONSTRAINT_VIOLATION"),
        )
    except SQLAlchemyError, RedisError, OSError:
        return UnifiedToolOutput.failure(
            message="Application proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Source state invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return output


async def _save_native_proposal(
    db: AsyncSession,
    content: ApplicationActionDraftContent,
    output: UnifiedToolOutput,
    context: LiaRuntimeContext,
) -> None:
    spec = APPLICATION_OPERATIONS.get(content.operation_id)
    await save_command(
        db,
        content,
        next(iter(output.registry_updates)),
        origin=(context.application_origin if spec.interaction_kind is not None else None),
        bind_device=spec.addressed_device,
    )
