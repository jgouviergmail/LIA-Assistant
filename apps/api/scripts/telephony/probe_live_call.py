"""Run the phone's Live mode on the vendor's REAL engine — without a phone (ADR-301).

    docker exec -e ELEVENLABS_API_KEY=... lia-api-dev \\
        python -m scripts.telephony.probe_live_call --user <uuid> --callback https://<public host>

Lot 4's proof. ``simulate_live_call`` plays the vendor with HTTP; this one
lets the vendor play itself: a TEMPORARY agent is created on the operator's
key with the PRODUCTION Live mandate (``build_override(SELF, mode="delegated")``)
and the PRODUCTION delegation tool body (``delegation_tool_body``, pointing at
``--callback``, a public URL that reaches THIS API — a quick tunnel on a
development machine), then a text-only conversation on the vendor's
WebSocket — the same engine and tools a phone line runs on, without audio —
plays the account holder: the identity check, a request about their data,
the wait, the restitution, the goodbye. The vendor calls the tool for real,
this API runs the bridge for real, the voice model restitutes for real; the
timeline is printed. Then the vendor's own transcript of that conversation is
handed to the post-call webhook, signed, so the closing runs on a REAL
transcript rather than a hand-written one.

Everything vendor-side is temporary and deleted at the end whatever happened;
the ``DIALING`` row the dial would have created is inserted here and closed
by the webhook. Only the operator's own account on a development instance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import aiohttp
import httpx

from scripts.telephony.probe_async_delegation import _SUBPROTOCOL, _client, _Conversation
from scripts.telephony.simulate_live_call import (
    _connector,
    _insert_call,
    _post_call,
    _read_books,
)
from src.core.config import settings
from src.core.constants import LIVE_DELEGATION_TOOL_NAME
from src.core.user_display import resolve_user_display_name
from src.domains.telephony.delegation_tool import delegation_tool_body
from src.domains.telephony.live_tools import live_tool_token
from src.domains.telephony.mandates import MandateInputs, build_override
from src.domains.telephony.models import CallKind
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import get_db_context


async def _user(user_id: UUID) -> User:
    async with get_db_context() as db:
        user = await db.get(User, user_id)
    if user is None:
        raise SystemExit("unknown user")
    return user


async def _create_agent(client: httpx.AsyncClient, tool_id: str, override: dict[str, Any]) -> str:
    agent = override["agent"]
    body = {
        "name": "lia-probe-live-call (temporary)",
        "conversation_config": {
            "agent": {
                "prompt": {
                    "prompt": agent["prompt"]["prompt"],
                    "tool_ids": [tool_id],
                    "built_in_tools": {"end_call": {"name": "end_call"}},
                },
                "first_message": agent["first_message"],
                "language": "en",
            },
            "conversation": {"text_only": True},
        },
    }
    resp = await client.post("/agents/create", json=body)
    resp.raise_for_status()
    return str(resp.json()["agent_id"])


async def _open(
    api_key: str, agent_id: str, call_id: UUID
) -> tuple[aiohttp.ClientSession, _Conversation]:
    async with _client(api_key) as client:
        resp = await client.get("/conversation/get-signed-url", params={"agent_id": agent_id})
        resp.raise_for_status()
        url = str(resp.json()["signed_url"])
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(url, protocols=(_SUBPROTOCOL,))
    conversation = _Conversation(ws, time.monotonic())
    await ws.send_str(
        json.dumps(
            {
                "type": "conversation_initiation_client_data",
                "conversation_config_override": {"conversation": {"text_only": True}},
                # The dial's own dynamic variable: the tool body binds it.
                "dynamic_variables": {"call_id": str(call_id)},
            }
        )
    )
    return session, conversation


async def _talk(
    api_key: str, agent_id: str, call_id: UUID, script: list[tuple[str, float]]
) -> str | None:
    session, conversation = await _open(api_key, agent_id, call_id)
    try:
        await conversation.listen(8, until_agent=True)
        for text, wait in script:
            await conversation.say(text)
            await conversation.listen(wait)
        await conversation.listen(6)
    finally:
        if not conversation.ws.closed:
            await conversation.ws.close(code=1000)
        await session.close()
    print("\n=== timeline (vendor engine, text-only) ===")
    for at, role, text in conversation.events:
        print(f"  [{at:>6.1f}s] {role:<6} {text[:160]!r}")
    return conversation.conversation_id


async def _vendor_transcript(client: httpx.AsyncClient, conversation_id: str) -> dict[str, Any]:
    """The vendor's own record of the conversation, once it is processed."""
    data: dict[str, Any] = {}
    for _ in range(20):
        resp = await client.get(f"/conversations/{conversation_id}")
        resp.raise_for_status()
        data = dict(resp.json())
        if data.get("status") in ("done", "processed", "failed"):
            break
        await asyncio.sleep(3)
    return data


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--user", required=True)
    parser.add_argument("--callback", required=True, help="Public base URL reaching this API")
    parser.add_argument("--api", default="https://localhost:8000")
    parser.add_argument("--request", default="What do I have on my agenda tomorrow?")
    args = parser.parse_args()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("ELEVENLABS_API_KEY is not set", file=sys.stderr)
        return 2
    import_all_models()
    user_id = UUID(args.user)
    user = await _user(user_id)
    display = resolve_user_display_name(user.full_name, user.email)
    secret, agent_id_of_connector = await _connector(user_id)
    # The production body, pointed at the public URL for this run only.
    settings.telephony_callback_base_url = args.callback
    body = delegation_tool_body(token=live_tool_token(secret), user_name=display)
    print(f"[tool] {LIVE_DELEGATION_TOOL_NAME} -> {body['tool_config']['api_schema']['url']}")
    override = build_override(
        CallKind.SELF,
        MandateInputs(
            language="en",
            user_name=display,
            objective="A catch-up call.",
            user_context="",
            availability_summary="",
            now=datetime.now(UTC),
            timezone=str(user.timezone or "UTC"),
            personality="",
            result_budget_tokens=settings.live_delegation_result_max_tokens,
        ),
        mode="delegated",
    )
    assert override is not None
    print(
        f"[mandate] {len(override['agent']['prompt']['prompt'])} chars, greeting {override['agent']['first_message']!r}"
    )

    print("[1] inserting the DIALING Live owner-call row")
    call_id = await _insert_call(user_id)
    print(f"  call_id={call_id}")

    tool_id: str | None = None
    agent_id: str | None = None
    async with _client(api_key) as client:
        try:
            resp = await client.post("/tools", json=body)
            resp.raise_for_status()
            tool_id = str(resp.json()["id"])
            agent_id = await _create_agent(client, tool_id, override)
            print(f"[2] temporary agent {agent_id} with the delegation tool")
            conversation_id = await _talk(
                api_key,
                agent_id,
                call_id,
                [
                    ("Yes, it's me.", 4),
                    (args.request, 45),
                    ("Great, thanks. That is all for today, bye.", 6),
                ],
            )
            if conversation_id:
                print("[3] fetching the vendor's own transcript")
                record = await _vendor_transcript(client, conversation_id)
                transcript = record.get("transcript") or []
                print(f"  {len(transcript)} turns, as the vendor wrote them:")
                for index, turn in enumerate(transcript):
                    calls = [c.get("tool_name") for c in turn.get("tool_calls") or []]
                    results = [
                        (r.get("tool_name"), r.get("is_error"))
                        for r in turn.get("tool_results") or []
                    ]
                    print(
                        f"    {index:>2} {turn.get('role'):<6} t={turn.get('time_in_call_secs')} "
                        f"{(turn.get('message') or '')[:70]!r} calls={calls} results={results}"
                    )
                payload = {
                    "type": "post_call_transcription",
                    "event_timestamp": int(time.time()),
                    "data": {
                        "agent_id": agent_id_of_connector,
                        "conversation_id": conversation_id,
                        "status": "done",
                        "metadata": record.get("metadata") or {},
                        "analysis": record.get("analysis") or {},
                        "transcript": transcript,
                        "conversation_initiation_client_data": {
                            "dynamic_variables": {"call_id": str(call_id)}
                        },
                    },
                }
                print("[4] posting it to the post-call webhook, signed")
                await _post_call(args.api, secret, payload)
                print("[5] reading the books")
                await _read_books(call_id, user_id)
        finally:
            if agent_id:
                await client.delete(f"/agents/{agent_id}")
                print("(temporary agent deleted)")
            if tool_id:
                await client.delete(f"/tools/{tool_id}", params={"force": "true"})
                print("(temporary tool deleted)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
