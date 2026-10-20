"""Shortcuts writes with a scoped bearer credential, independently of sessions."""

from contextlib import suppress
from typing import Never

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import (
    ExternalServiceError,
    raise_bearer_auth_failed,
    raise_invalid_input,
    raise_payload_too_large,
)
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.ingestion.limits import require_admission
from src.domains.ingestion.parser import IngestionBodyError, parse_body, read_bounded_body
from src.domains.ingestion.registry import IngestionResource, policy_for
from src.domains.ingestion.token_auth import extract_token
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.schemas import SmsIngestResponse

router = APIRouter(
    prefix="/ingest",
    tags=["Phone Ingestion"],
    dependencies=capability_dependencies(PlatformCapability.SMS),
)


@router.post("/message", response_model=SmsIngestResponse)
async def ingest_message(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> SmsIngestResponse:
    raw = extract_token(authorization, prefix=policy_for(IngestionResource.SMS).token_prefix)
    if raw is None:
        raise_bearer_auth_failed("Missing or malformed ingestion token")
    service = SmsIngestionService(db)
    try:
        principal = await service.authenticate(raw)
        # Release this read transaction before network admission. Authority is
        # checked again under the owner fence before the atomic write.
        await db.rollback()
    except SQLAlchemyError, OSError, TimeoutError:
        await _storage_unavailable(db)
    await require_admission(principal)
    try:
        body = await read_bounded_body(
            request.stream(), max_bytes=settings.ingestion_max_body_bytes
        )
        parsed = parse_body(body, max_bytes=settings.ingestion_max_body_bytes)
    except IngestionBodyError as exc:
        if exc.code == "body_too_large":
            raise_payload_too_large("ingestion_body_too_large")
        raise_invalid_input(str(exc))
    try:
        result = await service.ingest(principal, list(parsed.items))
    except SQLAlchemyError, OSError, TimeoutError:
        await _storage_unavailable(db)
    response.headers["Cache-Control"] = "no-store"
    if parsed.single:
        response.status_code = _single_status(result)
    return result


def _single_status(result: SmsIngestResponse) -> int:
    if result.inserted:
        return 201
    if result.conflict:
        return 409
    return 422 if result.rejected else 200


async def _storage_unavailable(db: AsyncSession) -> Never:
    with suppress(SQLAlchemyError, OSError, TimeoutError):
        await db.rollback()
    raise ExternalServiceError(
        "ingestion", detail="ingestion_commit_unacknowledged", headers={"Retry-After": "60"}
    ) from None
