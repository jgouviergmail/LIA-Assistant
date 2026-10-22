"""Session-only personal archive; external credentials can only ingest."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.sms.facade import SmsFacade
from src.domains.sms.identity_resolution import refresh_sender_identities
from src.domains.sms.management_commands import set_sms_preference
from src.domains.sms.management_read_schemas import (
    SmsManagementPageQuery,
    SmsSenderBlockPage,
    SmsSettingsView,
    SmsTokenPage,
)
from src.domains.sms.management_reads import SmsManagementReader
from src.domains.sms.preferences import SmsPreferences, SmsPreferenceUpdate
from src.domains.sms.read_schemas import SmsPage, SmsQuery, SmsSenderPage, SmsView
from src.domains.users.models import User

router = APIRouter(
    prefix="/sms",
    tags=["SMS"],
    dependencies=capability_dependencies(PlatformCapability.SMS),
    route_class=PrivateApplicationInputRoute,
)


@router.post("/search", response_model=SmsPage)
async def search_sms(
    query: SmsQuery,
    response: Response,
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsPage:
    response.headers["Cache-Control"] = "no-store"
    return await SmsFacade(db).list(actor.id, query, assistant=False)


@router.get("/senders", response_model=SmsSenderPage)
async def sender_groups(
    response: Response,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=4096),
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsSenderPage:
    response.headers["Cache-Control"] = "no-store"
    return await SmsFacade(db).senders(actor.id, limit=limit, cursor=cursor, assistant=False)


def management_page_query(
    limit: int = Query(default=20, ge=1, le=100),
    after_id: UUID | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
) -> SmsManagementPageQuery:
    # HTTP query strings are parsed once; domain snapshots stay strictly typed.
    try:
        return SmsManagementPageQuery(limit=limit, after_id=after_id, as_of=as_of)
    except ValidationError:
        raise_invalid_input("Invalid SMS metadata page")


@router.get("/settings", response_model=SmsSettingsView)
async def sms_settings(
    response: Response,
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsSettingsView:
    response.headers["Cache-Control"] = "no-store"
    return await SmsManagementReader(db).settings(actor.id)


@router.get("/tokens", response_model=SmsTokenPage)
async def sms_tokens(
    response: Response,
    query: SmsManagementPageQuery = Depends(management_page_query),
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsTokenPage:
    response.headers["Cache-Control"] = "no-store"
    return await SmsManagementReader(db).tokens(actor.id, query)


@router.patch("/preferences", response_model=SmsPreferences)
async def update_sms_setting(
    change: SmsPreferenceUpdate,
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsPreferences:
    """Change one SMS setting; the person's own click is the confirmation."""
    return await set_sms_preference(db, actor.id, change)


@router.get("/blocked-senders", response_model=SmsSenderBlockPage)
async def sms_blocked_senders(
    response: Response,
    query: SmsManagementPageQuery = Depends(management_page_query),
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsSenderBlockPage:
    response.headers["Cache-Control"] = "no-store"
    return await SmsManagementReader(db).blocks(actor.id, query)


@router.post("/identities/refresh", status_code=204, response_class=Response)
async def refresh_sms_identities(
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Forget the senders' contact matches so they resolve again; no SMS is touched."""
    await refresh_sender_identities(db, actor.id)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/{message_id}", response_model=SmsView)
async def sms_detail(
    message_id: UUID,
    response: Response,
    actor: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SmsView:
    response.headers["Cache-Control"] = "no-store"
    return await SmsFacade(db).get(actor.id, message_id, assistant=False)
