"""Authenticated explicit map activation; no server credential is public."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.connectors.map_load_metering import (
    browser_maps_key,
    issue_load_token,
    record_map_load,
    verify_load_token,
)
from src.domains.usage_limits.enforcement import raise_for_blocked_verdict
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import User

map_load_router = APIRouter()
_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
_admission_limit = create_user_rate_limiter(
    "interactive_map_admission", 3, authenticate=get_current_active_session_for_stream
)
_report_limit = create_user_rate_limiter(
    "interactive_map_report", 30, authenticate=get_current_active_session_for_stream
)


class MapLoadReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    load_token: str = Field(min_length=1, max_length=200)


@map_load_router.post("/google-maps/load-admissions", dependencies=[Depends(_admission_limit)])
async def admit_map_load(
    user: User = Depends(get_current_active_session_for_stream),
) -> JSONResponse:
    key = browser_maps_key()
    verdict = await UsageLimitService.check_user_allowed(user.id)
    if not verdict.allowed:
        raise_for_blocked_verdict(verdict, layer="interactive_map")
    return JSONResponse({"api_key": key, "load_token": issue_load_token(user.id)}, headers=_HEADERS)


@map_load_router.post("/google-maps/load-reports", dependencies=[Depends(_report_limit)])
async def report_map_load(
    body: MapLoadReport,
    user: User = Depends(get_current_active_session_for_stream),
) -> JSONResponse:
    grant_id = verify_load_token(body.load_token, user.id)
    # A load already happened: quota expiry must never prevent its accounting.
    await record_map_load(grant_id, user.id)
    return JSONResponse({"recorded": True}, headers=_HEADERS)
