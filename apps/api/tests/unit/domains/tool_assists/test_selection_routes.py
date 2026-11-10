"""Cross-app availability is independent of Tools; streaming keeps one terminal outcome."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.config import settings
from src.core.constants import TOOL_ASSIST_LANGUAGE_MAX_CHARS
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.tool_assists import passage, selection_routes
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.passage import PassageAct, PassageOrigin
from src.domains.tool_assists.selection import SelectionRequest, TextProposal
from src.domains.tool_assists.selection_routes import SelectionAnswer
from src.domains.users.models import User
from src.domains.workbench.errors import ASSIST_QUOTA, refuse
from tests.unit.domains.tool_assists.test_router import app as app
from tests.unit.domains.tool_assists.test_router import calls as calls
from tests.unit.domains.tool_assists.test_router import client as client

pytestmark = pytest.mark.unit


async def test_metadata_is_personal_and_never_cached(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def offered(user_id: object) -> list[Literal["task", "event", "memory"]]:
        return ["memory"]

    async def provider(user_id: object) -> Literal["brave"]:
        return "brave"

    monkeypatch.setattr(selection_routes, "offered_destinations", offered)
    monkeypatch.setattr(selection_routes, "preferred_provider", provider)
    answer = await client.get("/tool-assists/selection")
    assert answer.status_code == 200
    assert answer.headers["cache-control"] == "no-store"
    assert answer.json()["destinations"] == ["memory"]
    assert answer.json()["text_max_chars"] == settings.tool_assist_text_max_chars
    assert answer.json()["internet_available"] is True
    assert answer.json()["language_max_chars"] == TOOL_ASSIST_LANGUAGE_MAX_CHARS
    assert answer.json()["internet_timeout_seconds"] > answer.json()["call_timeout_seconds"]


async def test_stream_has_the_unbuffered_sse_contract_and_one_terminal_result(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def answer(body: SelectionRequest, user: User) -> SelectionAnswer:
        return SelectionAnswer(proposal=TextProposal(text="A complete answer"), usage=None)

    monkeypatch.setattr(selection_routes, "selection_answer", answer)
    response = await client.post(
        "/tool-assists/text/selection/stream",
        json={"mode": "read", "action": "explain", "text": "字"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["cache-control"] == "no-store"
    assert response.text.count("data: ") == 1
    invalid = await client.post(
        "/tool-assists/text/selection/stream",
        json={"mode": "read", "action": "fix", "text": "Text"},
    )
    assert invalid.status_code == 422


async def test_text_works_with_tools_off_but_source_routes_stay_closed(
    client: AsyncClient, calls: list[object], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def enabled(capability: PlatformCapability) -> bool:
        return capability is not PlatformCapability.WORKBENCH

    async def answer(
        run: AssistRun,
        passage: str,
        act: PassageAct,
        question: str | None,
        *,
        origin: PassageOrigin,
    ) -> str:
        assert origin == "chat"
        return "An explanation"

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    monkeypatch.setattr(passage, "act_on_passage", answer)
    response = await client.post(
        "/tool-assists/text/passage", json={"passage": "字", "act": "explain", "origin": "chat"}
    )
    assert response.status_code == 200 and response.json()["text"] == "An explanation"
    denied = await client.post("/tool-assists/mail/summary", json={"message_id": "m1"})
    assert denied.status_code == 403


async def test_assist_switch_closes_generic_stream_before_headers(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def disabled(capability: PlatformCapability) -> bool:
        return capability is not PlatformCapability.TOOL_ASSISTS

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", disabled)
    response = await client.post(
        "/tool-assists/text/selection/stream",
        json={"mode": "read", "action": "explain", "text": "Text"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("failure", [False, True])
async def test_waiting_pulses_preserve_one_complete_answer_or_typed_refusal(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    invoked = 0

    async def answer(body: SelectionRequest, user: User) -> SelectionAnswer:
        nonlocal invoked
        invoked += 1
        await asyncio.sleep(0.015)
        if failure:
            refuse(ASSIST_QUOTA)
        return SelectionAnswer(proposal=TextProposal(text="Complete answer"), usage=None)

    monkeypatch.setattr(selection_routes, "selection_answer", answer)
    monkeypatch.setattr(settings, "sse_heartbeat_interval", 0.002)
    body = SelectionRequest(mode="read", action="explain", text="Text")
    user = User(id=uuid4(), email="reader@example.test")
    frames = [frame async for frame in selection_routes.selection_stream(body, user)]
    assert invoked == 1 and len(frames) > 2
    terminal = [
        json.loads(frame.removeprefix("data: ")) for frame in frames if frame.startswith("data: ")
    ]
    assert len(terminal) == 1
    if failure:
        assert terminal[0]["error"]["detail"]["code"] == ASSIST_QUOTA
    else:
        assert terminal[0]["result"]["proposal"]["text"] == "Complete answer"


@pytest.mark.parametrize("repeated", [False, True])
async def test_disconnect_awaits_model_accountant_cleanup(
    monkeypatch: pytest.MonkeyPatch, repeated: bool
) -> None:
    started, closed, cleaning, release = (asyncio.Event() for _ in range(4))

    async def events(body: SelectionRequest, user: User) -> AsyncIterator[str]:
        started.set()
        try:
            await asyncio.Event().wait()
            yield "unreachable"
        finally:
            cleaning.set()
            await release.wait()
            closed.set()

    monkeypatch.setattr(selection_routes, "selection_events", events)
    stream = selection_routes.selection_stream(
        SelectionRequest(mode="read", action="explain", text="Text"), User(id=uuid4())
    )
    await anext(stream)
    pending = asyncio.ensure_future(anext(stream))
    await started.wait()
    pending.cancel()
    await cleaning.wait()
    if repeated:
        pending.cancel()
        await asyncio.sleep(0.01)
    still_owned = not pending.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await stream.aclose()
    assert still_owned and closed.is_set()
