"""Authenticated selection proposals with idle keepalives, no idle SQL session."""

import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import TOOL_ASSIST_LANGUAGE_MAX_CHARS, TOOL_ASSIST_LLM_TYPE
from src.core.exceptions import BaseAPIException
from src.core.i18n import normalize_language
from src.core.llm_config_helper import llm_call_timeout_seconds, run_bound_seconds
from src.core.llm_usage import LLMUsage
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.agents.api.sse_keepalive import KEEPALIVE, iter_with_keepalive
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.tool_assists.catalogue import ToolAssist
from src.domains.tool_assists.door import run_assist
from src.domains.tool_assists.selection import (
    SelectionAction,
    SelectionDestination,
    SelectionProposal,
    SelectionRequest,
    offered_destinations,
    propose_selection,
)
from src.domains.tool_assists.selection_research import preferred_provider, search_timeout_seconds
from src.domains.users.models import User

Person = Annotated[User, Depends(get_current_active_session_for_stream)]
router = APIRouter()


class SelectionMetadata(BaseModel):
    """Published bounds and destinations; no source content is fetched."""

    text_max_chars: int = Field(description="Maximum complete selection length.")
    question_max_chars: int = Field(description="Maximum question length.")
    language_max_chars: int = Field(description="Maximum length of a chosen language name.")
    internet_available: bool = Field(description="A configured search provider is available.")
    read_aloud_available: bool = Field(description="The read-aloud capability is enabled.")
    internet_timeout_seconds: float = Field(
        description="The query preparation and bounded search deadline."
    )
    call_timeout_seconds: float = Field(
        description="Configured model attempt timeout, informational."
    )
    heartbeat_seconds: float = Field(
        description="Maximum intended idle interval while the call runs."
    )
    destinations: list[SelectionDestination] = Field(description="Available native creation forms.")


class SelectionAnswer(BaseModel):
    proposal: SelectionProposal = Field(
        description="One complete proposal for the selected action."
    )
    usage: LLMUsage | None = Field(description="Actual captured provider usage, when present.")


@router.get("/selection", response_model=SelectionMetadata)
async def get_selection_metadata(user: Person, response: Response) -> SelectionMetadata:
    """Expose live account capabilities without reading mail, files or memories."""
    response.headers["Cache-Control"] = "no-store"
    return SelectionMetadata(
        text_max_chars=settings.tool_assist_text_max_chars,
        question_max_chars=settings.tool_assist_instruction_max_chars,
        language_max_chars=TOOL_ASSIST_LANGUAGE_MAX_CHARS,
        internet_available=await preferred_provider(user.id) is not None,
        read_aloud_available=await is_capability_enabled(PlatformCapability.TTS),
        internet_timeout_seconds=run_bound_seconds(
            0, TOOL_ASSIST_LLM_TYPE, margin_seconds=search_timeout_seconds()
        ),
        call_timeout_seconds=llm_call_timeout_seconds(TOOL_ASSIST_LLM_TYPE),
        heartbeat_seconds=settings.sse_heartbeat_interval,
        destinations=await offered_destinations(user.id),
    )


async def selection_answer(body: SelectionRequest, user: User) -> SelectionAnswer:
    """Use the common quota, billing, cancellation and decision owner exactly once."""
    done = await run_assist(
        (
            ToolAssist.SELECTION_INTERNET
            if body.action is SelectionAction.INTERNET
            else ToolAssist.SELECTION
        ),
        user.id,
        normalize_language(user.language),
        lambda run: propose_selection(run, body, user),
    )
    return SelectionAnswer(proposal=done.value, usage=done.usage)


@router.post("/text/selection", response_model=SelectionAnswer)
async def post_selection(body: SelectionRequest, user: Person) -> SelectionAnswer:
    """Whole JSON for consumers whose transport permits the configured slot."""
    return await selection_answer(body, user)


async def selection_events(body: SelectionRequest, user: User) -> AsyncGenerator[str]:
    """One terminal envelope; a disconnect cancels and awaits the common accountant."""
    try:
        answer = await selection_answer(body, user)
        yield json.dumps({"result": answer.model_dump(mode="json")}, ensure_ascii=False) + "\n"
    except BaseAPIException as error:
        yield json.dumps(
            {"error": {"status": error.status_code, "detail": error.detail}}, ensure_ascii=False
        ) + "\n"


async def selection_stream(body: SelectionRequest, user: User) -> AsyncGenerator[str]:
    """Keep proxies alive without manufacturing a partial model answer."""
    yield ": waiting\n\n"
    async for item in iter_with_keepalive(
        selection_events(body, user), settings.sse_heartbeat_interval
    ):
        if item is KEEPALIVE:
            yield ": waiting\n\n"
        elif isinstance(item, str):
            yield f"data: {item.rstrip()}\n\n"


@router.post("/text/selection/stream", response_model=None)
async def post_selection_stream(body: SelectionRequest, user: Person) -> StreamingResponse:
    """Stream only waiting pulses and one terminal result/refusal, never retry."""
    return StreamingResponse(
        selection_stream(body, user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
