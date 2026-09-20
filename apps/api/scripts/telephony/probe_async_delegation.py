"""Measure what an ElevenLabs ``async`` webhook tool does — before any product code relies on it.

    task telephony:probe -- --webhook-url https://<public host> [--timeout 120] [--delays 8,25]

The phone's Live mode (ADR-301) delegates every request to LIA through ONE
webhook tool the vendor's agent calls while the person is on the line. A
delegated turn takes 5 to 40 seconds, so the design hangs on four questions
the documentation cannot answer:

1. With ``execution_mode: async``, does the agent keep the conversation going
   while the webhook is pending, and is the result handed to the LLM when the
   webhook answers?
2. What does the agent do when the webhook outlives ``response_timeout_secs``?
3. What does the conversation carry for a tool call (``tool_calls`` /
   ``tool_results`` / ``tool_latency_secs``), so the closing can tell a
   delegated exchange from a voice-only one?
4. Two requests in a row while the first is pending: two webhook calls, or one?

Two instruments, because the first one lies: ``simulate-conversation`` MOCKS
every tool (measured 2026-09-20: ``tool_results`` say « Tool Called. » with a
latency of 0.0 and the webhook is never called), so it only shows the
transcript SHAPE and the LLM's behaviour around the call. The real engine is
reached through a TEXT-ONLY conversation on the conversation WebSocket (the
same engine and tools a phone line runs on, without audio): the webhook is
really called, really waited for, really answered — the delay server behind a
public URL (the rig: ``scratchpad/delay_server.py`` + a Cloudflare quick
tunnel) logs when.

Everything vendor-side is TEMPORARY — an agent and its tools — and deleted at
the end whatever happened. Nothing here touches the database, nothing imports
``src``, the only network calls are to the vendor on the operator's key
(``ELEVENLABS_API_KEY``), and every figure printed is anonymous.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

import aiohttp
import httpx

_BASE = "https://api.elevenlabs.io/v1/convai"
_TOOL = "send_to_lia_probe"
_SUBPROTOCOL = "convai"


def _client(api_key: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_BASE, headers={"xi-api-key": api_key}, timeout=httpx.Timeout(400.0)
    )


def _tool_body(name: str, url: str, timeout: int, execution_mode: str) -> dict[str, Any]:
    return {
        "tool_config": {
            "type": "webhook",
            "name": name,
            "description": (
                "Hand the person's request to LIA, in their own words. Use it for anything "
                "about their data, an action, or anything you cannot answer from the "
                "conversation alone. The result is LIA's answer."
            ),
            "response_timeout_secs": timeout,
            "execution_mode": execution_mode,
            "pre_tool_speech": "force",
            "api_schema": {
                "url": url,
                "method": "POST",
                "request_headers": {"X-LIA-Tool-Secret": "probe"},
                "request_body_schema": {
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "The person's request, in their own words.",
                        }
                    },
                    "required": ["request"],
                },
            },
        }
    }


_PROMPT = (
    "You are the voice of a personal assistant on a phone call with the account holder. "
    "Whenever the person asks anything about their own data (agenda, mail, tasks) or asks "
    "for an action, you MUST call the tool `{tool}` with the request in their own words, "
    "and you must never answer such a question from your own knowledge. First say ONE short "
    "sentence that you are on it, THEN call the tool. While the tool runs, keep the "
    "conversation going in short sentences and answer small talk yourself; do not repeat the "
    "request. When the tool result arrives, restitute it in your own words at once. If the "
    "result says the assistant is still working, say exactly that. Speak English, short "
    "sentences."
)


async def _create_agent(client: httpx.AsyncClient, tool_id: str) -> str:
    body = {
        "name": "lia-probe-async-delegation (temporary)",
        "conversation_config": {
            "agent": {
                "prompt": {
                    "prompt": _PROMPT.format(tool=_TOOL),
                    "tool_ids": [tool_id],
                    "built_in_tools": {"end_call": {"name": "end_call"}},
                },
                "first_message": "Hello, this is your assistant. What can I do for you?",
                "language": "en",
            },
            "conversation": {"text_only": True},
        },
    }
    resp = await client.post("/agents/create", json=body)
    resp.raise_for_status()
    return str(resp.json()["agent_id"])


# ---------------------------------------------------------------------------
# The real engine: a text-only conversation on the WebSocket
# ---------------------------------------------------------------------------


class _Conversation:
    """One text conversation, every frame stamped on a monotonic clock."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse, t0: float) -> None:
        self.ws = ws
        self.t0 = t0
        self.events: list[tuple[float, str, str]] = []
        self.conversation_id: str | None = None

    def stamp(self) -> float:
        return round(time.monotonic() - self.t0, 1)

    async def say(self, text: str) -> None:
        self.events.append((self.stamp(), "user", text))
        await self.ws.send_str(json.dumps({"type": "user_message", "text": text}))

    async def listen(self, seconds: float, *, until_agent: bool = False) -> None:
        """Read frames for ``seconds``; with ``until_agent`` stop at the first agent reply."""
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                message = await asyncio.wait_for(self.ws.receive(), timeout=remaining)
            except TimeoutError:
                return
            if message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                self.events.append(
                    (self.stamp(), "closed", f"{self.ws.close_code} {message.extra}")
                )
                return
            if message.type != aiohttp.WSMsgType.TEXT:
                continue
            event = json.loads(message.data)
            kind = str(event.get("type"))
            if kind == "ping":
                await self.ws.send_str(
                    json.dumps({"type": "pong", "event_id": event["ping_event"]["event_id"]})
                )
                continue
            if kind == "conversation_initiation_metadata":
                meta = event.get("conversation_initiation_metadata_event") or {}
                self.conversation_id = meta.get("conversation_id")
                self.events.append(
                    (self.stamp(), "meta", f"conversation_id={self.conversation_id}")
                )
                continue
            if kind == "agent_response":
                text = (event.get("agent_response_event") or {}).get("agent_response", "")
                self.events.append((self.stamp(), "agent", text))
                if until_agent:
                    return
                continue
            if kind == "agent_tool_response":
                ev = event.get("agent_tool_response") or {}
                self.events.append(
                    (
                        self.stamp(),
                        "tool",
                        f"{ev.get('tool_name')} type={ev.get('tool_type')} error={ev.get('is_error')}",
                    )
                )
                continue
            if kind in ("audio", "user_transcript", "internal_tentative_agent_response"):
                continue
            self.events.append((self.stamp(), kind, json.dumps(event)[:160]))


async def _open(api_key: str, agent_id: str) -> tuple[aiohttp.ClientSession, _Conversation]:
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
            }
        )
    )
    return session, conversation


async def _run_scenario(
    api_key: str, agent_id: str, name: str, script: list[tuple[str, float]], *, tail: float
) -> None:
    """Say each line, listen for its wait, then listen a tail; print the timeline."""
    session, conversation = await _open(api_key, agent_id)
    try:
        await conversation.listen(6, until_agent=True)
        for text, wait in script:
            await conversation.say(text)
            await conversation.listen(wait)
        await conversation.listen(tail)
    finally:
        if not conversation.ws.closed:
            await conversation.ws.close(code=1000)
        await session.close()
    print(f"\n=== {name} ===")
    for at, role, text in conversation.events:
        print(f"  [{at:>6.1f}s] {role:<6} {text[:120]!r}")
    return None


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--webhook-url", required=True, help="Public base URL of the delay server")
    parser.add_argument(
        "--timeout", type=int, default=120, help="response_timeout_secs of the tool"
    )
    parser.add_argument("--delays", default="8,25", help="Delays (s) the webhook answers after")
    parser.add_argument("--execution-mode", default="async", choices=["async", "immediate"])
    parser.add_argument(
        "--over-timeout", type=int, default=0, help="A delay past the timeout (0 = skip)"
    )
    args = parser.parse_args()
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("ELEVENLABS_API_KEY is not set", file=sys.stderr)
        return 2
    delays = [int(d) for d in args.delays.split(",") if d.strip()]
    if args.over_timeout:
        delays.append(args.over_timeout)

    created_tools: list[str] = []
    agent_id: str | None = None
    async with _client(api_key) as client:
        try:
            for index, delay in enumerate(delays):
                url = f"{args.webhook_url.rstrip('/')}/d{delay}"
                resp = await client.post(
                    "/tools", json=_tool_body(_TOOL, url, args.timeout, args.execution_mode)
                )
                resp.raise_for_status()
                tool_id = str(resp.json()["id"])
                created_tools.append(tool_id)
                if agent_id is None:
                    agent_id = await _create_agent(client, tool_id)
                else:
                    resp = await client.patch(
                        f"/agents/{agent_id}",
                        json={
                            "conversation_config": {"agent": {"prompt": {"tool_ids": [tool_id]}}}
                        },
                    )
                    resp.raise_for_status()
                past = delay > args.timeout
                print(
                    f"\n##### webhook answers after {delay} s "
                    f"(timeout {args.timeout} s, {args.execution_mode}{', PAST the timeout' if past else ''})"
                )
                # Q1/Q2: one request, small talk while it runs, then silence long
                # enough for the webhook to answer.
                await _run_scenario(
                    api_key,
                    agent_id,
                    f"single request, delay {delay}s",
                    [
                        ("What is on my agenda tomorrow afternoon?", 4),
                        ("Nice. How is the weather looking for the weekend?", 4),
                    ],
                    tail=delay + 12,
                )
                if index == 0:
                    # Q4: a second request while the first is pending.
                    await _run_scenario(
                        api_key,
                        agent_id,
                        f"two requests in a row, delay {delay}s",
                        [
                            ("What is on my agenda tomorrow afternoon?", 3),
                            ("Actually, also tell me if I have unread mail from Anna.", 4),
                        ],
                        tail=delay + 12,
                    )
        finally:
            if agent_id:
                await client.delete(f"/agents/{agent_id}")
                print("\n(temporary agent deleted)")
            for tool_id in created_tools:
                await client.delete(f"/tools/{tool_id}", params={"force": "true"})
            print(f"({len(created_tools)} temporary tool(s) deleted)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
