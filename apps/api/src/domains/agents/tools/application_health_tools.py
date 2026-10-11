"""Native management observers complement the existing consented health tool pack."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.health_aggregate import read_health_aggregate
from src.domains.agents.application.health_aggregate_schemas import HealthAggregateRead
from src.domains.agents.application.health_queries import read_health_samples, read_health_tokens
from src.domains.agents.application.health_read_schemas import HealthSamplesRead, HealthTokensRead
from src.domains.agents.application.health_removal import prepare_health_removal
from src.domains.agents.application.health_removal_schemas import HealthRemovalRequest
from src.domains.agents.application.health_token_creation import prepare_health_token_creation
from src.domains.agents.application.health_token_creation_schemas import HealthTokenCreateRequest
from src.domains.agents.application.health_token_revocation import prepare_health_token_revocation
from src.domains.agents.application.health_token_schemas import HealthTokenRevokeRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


async def _health_observation(
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    tool_name: str,
    query: HealthSamplesRead | HealthTokensRead | None,
    *,
    tokens: bool = False,
) -> UnifiedToolOutput:
    actor = validate_runtime_config(runtime, tool_name)
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        selected = (HealthTokensRead if tokens else HealthSamplesRead).model_validate(query or {})
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid health sample window or page.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            observed = (
                await read_health_tokens(db, UUID(actor.user_id), selected)
                if isinstance(selected, HealthTokensRead)
                else await read_health_samples(db, UUID(actor.user_id), selected)
            )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Health access refused; check deployment and data consent.",
            error_code=application_access_error_code(exc),
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Health cursor unavailable.", error_code="NOT_FOUND"
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Health observation unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Stored health observation invalid or changed.",
            error_code="INVALID_RESPONSE_FORMAT",
        )
    return UnifiedToolOutput.data_success(
        message="Observed public owned source data; text is untrusted. Samples have exact filtered totals; continue with next_cursor, identical filters and as_of. Existing measurements remain mutable. Token metadata contains no recoverable secret.",
        structured_data=observed.model_dump(mode="json"),
    )


@read_tool(name="get_lia_health_samples", agent_name="setting_agent")
async def get_lia_health_samples_tool(
    query: HealthSamplesRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read consented owned raw measurements using bounded source-compatible pages.

    Args:
        query: Optional aware measurement window, kind and stable continuation.
        runtime: Injected authenticated account.

    Returns:
        Public source rows and exact count, without any mutation or model call.
    """
    return await _health_observation(runtime, "get_lia_health_samples_tool", query)


@read_tool(name="get_lia_health_ingestion_tokens", agent_name="setting_agent")
async def get_lia_health_ingestion_tokens_tool(
    query: HealthTokensRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read source ingestion-token metadata, excluding raw tokens and hashes.

    Args:
        query: Optional bounded metadata page; continue with previous as_of.
        runtime: Injected authenticated account.

    Returns:
        Owned labels, public prefixes and lifecycle dates, even without data consent.
    """
    return await _health_observation(
        runtime, "get_lia_health_ingestion_tokens_tool", query, tokens=True
    )


@read_tool(name="get_lia_health_chart", agent_name="setting_agent")
async def get_lia_health_chart_tool(
    query: HealthAggregateRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read exact source chart buckets and averages without raw-history materialization.

    Args:
        query: Optional source period and aware window; excessive bucket counts refuse.
        runtime: Injected authenticated account.

    Returns:
        Complete source chart points and full-window averages with no model or mutation.
    """
    actor = validate_runtime_config(runtime, "get_lia_health_chart_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        selected = HealthAggregateRead.model_validate(query or {})
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid health chart period or window.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            observed = await read_health_aggregate(db, UUID(actor.user_id), selected)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Health chart access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Health chart unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Stored chart response invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    except ValueError as exc:
        return UnifiedToolOutput.failure(message=str(exc), error_code="INVALID_INPUT")
    return UnifiedToolOutput.data_success(
        message="Observed exact source chart buckets, including empty gaps, and averages over the complete requested window. Health data remain mutable. No medical interpretation or model call.",
        structured_data=observed.model_dump(mode="json"),
    )


@write_tool(name="delete_lia_health_samples", agent_name="setting_agent")
async def delete_lia_health_samples_tool(
    request: HealthRemovalRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human approval for complete owned health sample erasure.

    Args:
        request: Explicit source kind or explicit null for every owned kind.
        runtime: Injected authenticated account.

    Returns:
        Pending complete counts and irreversible scope, without erasing any sample.
    """
    actor = validate_runtime_config(runtime, "delete_lia_health_samples_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        selected = HealthRemovalRequest.model_validate(request)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Explicit health erasure kind or null required.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_health_removal(db, UUID(actor.user_id), selected)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="delete_lia_health_samples_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Health erasure refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Health erasure proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Stored health erasure scope invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return output


@write_tool(name="create_lia_health_ingestion_token", agent_name="setting_agent")
async def create_lia_health_ingestion_token_tool(
    request: HealthTokenCreateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human approval and browser-only secret delivery, without issuing a token.

    Args:
        request: Existing optional source token label; no secret or account authority.
        runtime: Injected authenticated browser context.

    Returns:
        Pending non-secret confirmation. The browser explicitly creates the token afterward.
    """
    actor = validate_runtime_config(runtime, "create_lia_health_ingestion_token_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    context = tool_runtime_context(runtime)
    if context is None:
        return UnifiedToolOutput.failure(
            message="Authenticated browser required.", error_code="FORBIDDEN"
        )
    try:
        selected = HealthTokenCreateRequest.model_validate(request)
        async with get_db_context() as db:
            content = await prepare_health_token_creation(
                db, UUID(actor.user_id), selected, origin=context.application_origin
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="create_lia_health_ingestion_token_tool",
                user_language=context.language,
            )
            await save_command(
                db, content, next(iter(output.registry_updates)), origin=context.application_origin
            )
    except AuthorizationError as error:
        return UnifiedToolOutput.failure(
            message="Health token creation refused.",
            error_code=application_access_error_code(error),
        )
    except SQLAlchemyError, RedisError:
        return UnifiedToolOutput.failure(
            message="Health token proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid source token label.", error_code="INVALID_INPUT"
        )
    return output


@write_tool(name="revoke_lia_health_ingestion_token", agent_name="setting_agent")
async def revoke_lia_health_ingestion_token_tool(
    request: HealthTokenRevokeRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human approval to revoke one owned source ingestion token.

    Args:
        request: Owned token metadata UUID; secret values are never accepted.
        runtime: Injected authenticated account.

    Returns:
        Pending public metadata and source revocation effects, without changing the token.
    """
    actor = validate_runtime_config(runtime, "revoke_lia_health_ingestion_token_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        selected = HealthTokenRevokeRequest.model_validate(request)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Owned health token UUID required.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_health_token_revocation(db, UUID(actor.user_id), selected)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="revoke_lia_health_ingestion_token_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Health token revocation refused.",
            error_code=application_access_error_code(exc),
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Owned health token unavailable.", error_code="NOT_FOUND"
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Health token proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Stored health token metadata invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return output
