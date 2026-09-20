"""Measure what the Live API does — before any product code relies on it.

    task live:probe -- --model gemini-3.8-live [--extended]

Seven questions the design cannot answer from documentation alone (spec §9 of
``docs/superpowers/specs/2026-09-18-live-llm-connector-design.md``):

1. Are ``system_instruction`` and ``tools`` accepted inside
   ``live_connect_constraints`` — and does a session opened with a DIFFERENT
   instruction get refused?
2. Does a ``NON_BLOCKING`` function call keep the model talking, and how does
   ``scheduling`` (``INTERRUPT`` vs ``WHEN_IDLE``) behave when the result
   arrives 8 s later?
3. Can a session opened with a ``uses: 1`` token be RESUMED with the same
   token and the last ``new_handle``?
4. Does a setup + immediate close (no audio) report zero tokens?
5. In which order do ``input_transcription`` / ``output_transcription`` /
   ``turn_complete`` arrive?
6. Which fields of ``models.list()`` say a model is live-capable?
7. Can a late text be pushed as client content after a tool call was cancelled?

Nothing here touches the database, and nothing imports ``src``. The only
network call is to the provider, on the operator's TEST key, and every figure
printed is anonymous (no token, no transcript of a real person).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import struct
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from google import genai
from google.genai import types

INSTRUCTION = "You are a voice assistant. Answer in one short sentence."
OTHER_INSTRUCTION = "You are a pirate. Always say ARR."
TOOL = types.FunctionDeclaration(
    name="send_to_lia",
    description="Hand the request to the backend. Say you are checking, then wait.",
    parameters={
        "type": "object",
        "properties": {"request": {"type": "string", "description": "The request."}},
        "required": ["request"],
    },
    behavior=types.Behavior.NON_BLOCKING,
)
#: How long one probe session listens before giving up (seconds).
SESSION_BUDGET_S = 40
#: How long the fake backend "works" before answering the tool call.
BACKEND_DELAY_S = 8


def _tone(seconds: float, hz: float = 440.0, rate: int = 16000) -> bytes:
    """A sine tone as 16-bit PCM — a stand-in for speech, enough to open a turn."""
    frames = int(seconds * rate)
    return b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / rate))) for i in range(frames)
    )


def _config(instruction: str, extended: bool) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=instruction,
        tools=[types.Tool(function_declarations=[TOOL])],
        session_resumption=types.SessionResumptionConfig(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=25000, sliding_window=types.SlidingWindow(target_tokens=8000)
        ),
        thinking_config=(types.ThinkingConfig(thinking_level="low") if extended else None),
    )


async def mint(client: genai.Client, model: str, extended: bool) -> types.AuthToken:
    """Question 1: a token constrained to the model AND the instruction AND the tool."""
    now = datetime.now(UTC)
    return await client.aio.auth_tokens.create(
        config=types.CreateAuthTokenConfig(
            uses=1,
            expire_time=now + timedelta(minutes=30),
            new_session_expire_time=now + timedelta(minutes=1),
            live_connect_constraints=types.LiveConnectConstraints(
                model=model, config=_config(INSTRUCTION, extended)
            ),
            lock_additional_fields=[],
            http_options=types.HttpOptions(api_version="v1alpha"),
        )
    )


async def session_events(
    token: str,
    model: str,
    config: types.LiveConnectConfig,
    *,
    scheduling: str,
    handle: str | None,
    push_late_text: bool = False,
    api_version: str = "v1beta",
) -> dict[str, Any]:
    """Open a session with the ephemeral token; play a tone; answer the tool LATE.

    The tool is answered from a background task so the receive loop keeps
    observing what the model says DURING the wait (``receive()`` yields one
    turn and ends on ``turn_complete``; the loop re-enters it until the budget
    is spent).
    """
    client = genai.Client(api_key=token, http_options=types.HttpOptions(api_version=api_version))
    if handle:
        config = config.model_copy(
            update={"session_resumption": types.SessionResumptionConfig(handle=handle)}
        )
    report: dict[str, Any] = {
        "events": [],
        "handles": [],
        "usage": [],
        "tool_calls": [],
        "turns": 0,
    }
    started = time.monotonic()
    pending: list[asyncio.Task[None]] = []

    async def answer_later(session: Any, call: Any) -> None:
        await asyncio.sleep(BACKEND_DELAY_S)
        stamp = round(time.monotonic() - started, 2)
        if push_late_text:
            await session.send_client_content(
                turns=types.Content(
                    role="user", parts=[types.Part(text="LIA's answer is ready: two meetings.")]
                ),
                turn_complete=True,
            )
            report["events"].append({"t": stamp, "late_text_pushed": True})
            return
        await session.send_tool_response(
            function_responses=[
                types.FunctionResponse(
                    id=call.id,
                    name=call.name,
                    response={"result": "Tomorrow: two meetings, 9 and 14."},
                    scheduling=scheduling,
                )
            ]
        )
        report["events"].append({"t": stamp, "tool_answered": True})

    async with client.aio.live.connect(model=model, config=config) as session:
        await session.send_realtime_input(
            audio=types.Blob(data=_tone(1.5), mime_type="audio/pcm;rate=16000")
        )
        await session.send_realtime_input(
            text="Ask the backend what is on my calendar tomorrow, then keep talking."
        )
        deadline = time.monotonic() + SESSION_BUDGET_S
        while time.monotonic() < deadline:
            try:
                await asyncio.wait_for(
                    _drain_turn(session, report, started, deadline, pending, answer_later),
                    timeout=max(1.0, deadline - time.monotonic()),
                )
            except TimeoutError:
                report["events"].append({"t": round(time.monotonic() - started, 2), "budget": True})
                break
            except Exception as exc:  # noqa: BLE001 — a provider close IS a measurement
                report["events"].append(
                    {
                        "t": round(time.monotonic() - started, 2),
                        "error": f"{type(exc).__name__}: {exc}"[:200],
                    }
                )
                break
            report["turns"] += 1
            answered = any(
                "tool_answered" in e or "late_text_pushed" in e for e in report["events"]
            )
            # Past the tool answer and a full extra turn, the question is answered.
            if answered and report["turns"] >= 3:
                break
        for task in pending:
            if not task.done():
                task.cancel()
    report["duration_s"] = round(time.monotonic() - started, 2)
    return report


async def _drain_turn(
    session: Any,
    report: dict[str, Any],
    started: float,
    deadline: float,
    pending: list[asyncio.Task[None]],
    answer_later: Any,
) -> None:
    """One ``receive()`` pass: ends on ``turn_complete`` or the budget."""
    async for message in session.receive():
        stamp = round(time.monotonic() - started, 2)
        update = message.session_resumption_update
        if update and update.new_handle:
            report["handles"].append(update.new_handle)
        if message.usage_metadata:
            report["usage"].append(message.usage_metadata.total_token_count)
        if message.tool_call:
            for call in message.tool_call.function_calls or []:
                report["tool_calls"].append({"t": stamp, "name": call.name, "args": call.args})
                pending.append(asyncio.create_task(answer_later(session, call)))
        if message.tool_call_cancellation:
            report["events"].append(
                {"t": stamp, "cancelled": list(message.tool_call_cancellation.ids or [])}
            )
        content = message.server_content
        if content:
            if content.input_transcription and content.input_transcription.text:
                report["events"].append(
                    {"t": stamp, "input": len(content.input_transcription.text)}
                )
            if content.output_transcription and content.output_transcription.text:
                report["events"].append({"t": stamp, "output": content.output_transcription.text})
            if content.model_turn and content.model_turn.parts:
                report["events"].append({"t": stamp, "audio_parts": len(content.model_turn.parts)})
            if content.interrupted:
                report["events"].append({"t": stamp, "interrupted": True})
            if content.turn_complete:
                report["events"].append({"t": stamp, "turn_complete": True})
            if content.generation_complete:
                report["events"].append({"t": stamp, "generation_complete": True})
        if message.go_away:
            report["events"].append({"t": stamp, "go_away": str(message.go_away.time_left)})
        if time.monotonic() > deadline:
            break


async def raw_websocket_check(token: str, model: str) -> dict[str, Any]:
    """The browser transport's exact contract: raw JSON over ``wss://…?access_token=``.

    Measured 2026-09-18: the plain ``BidiGenerateContent`` method refuses an
    ephemeral token (1008 « unregistered callers »); the SDK reaches
    ``BidiGenerateContentConstrained`` with the token, and that method accepts
    ``access_token`` in the query — on ``v1beta`` as well as ``v1alpha``.
    """
    import websockets

    url = (
        "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage."
        f"v1beta.GenerativeService.BidiGenerateContentConstrained?access_token={token}"
    )
    setup = {
        "setup": {
            "model": f"models/{model}",
            "generationConfig": {"responseModalities": ["AUDIO"]},
            "outputAudioTranscription": {},
        }
    }
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps(setup))
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            return {"ok": "setupComplete" in first, "first_keys": sorted(first)}
    except Exception as exc:  # noqa: BLE001 — the refusal is the measurement
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


async def probe_activation(client: genai.Client, model: str, voice: str) -> dict[str, Any]:
    """Question 4: setup + close with no audio — what does it cost, what is refused?"""
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
    )
    started = time.monotonic()
    try:
        async with client.aio.live.connect(model=model, config=config):
            return {"ok": True, "seconds": round(time.monotonic() - started, 2)}
    except Exception as exc:  # noqa: BLE001 — the refusal IS the measurement
        return {
            "ok": False,
            "seconds": round(time.monotonic() - started, 2),
            "error": f"{type(exc).__name__}: {exc}"[:300],
        }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemini-3.8-live")
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--voice", default="Kore")
    parser.add_argument(
        "--skip-sessions", action="store_true", help="listing + activation probes only"
    )
    args = parser.parse_args()
    api_key = os.environ.get("LIVE_PROBE_API_KEY")
    if not api_key:
        print("LIVE_PROBE_API_KEY is not set", file=sys.stderr)
        return 2
    client = genai.Client(api_key=api_key)
    report: dict[str, Any] = {"model": args.model, "measured_at": datetime.now(UTC).isoformat()}

    models = [
        {"name": m.name, "actions": list(m.supported_actions or [])}
        async for m in await client.aio.models.list()
    ]
    report["live_models"] = sorted(
        m["name"] for m in models if "bidiGenerateContent" in m["actions"]
    )
    report["activation_probe"] = await probe_activation(client, args.model, args.voice)
    report["activation_probe_bad_voice"] = await probe_activation(client, args.model, "not-a-voice")
    if args.skip_sessions:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    token = await mint(client, args.model, args.extended)
    report["token_minted"] = bool(token.name)
    report["interrupt"] = await session_events(
        token.name,
        args.model,
        _config(INSTRUCTION, args.extended),
        scheduling="INTERRUPT",
        handle=None,
    )
    handles = report["interrupt"]["handles"]
    if handles:
        try:
            report["resumed_with_same_token"] = await session_events(
                token.name,
                args.model,
                _config(INSTRUCTION, args.extended),
                scheduling="WHEN_IDLE",
                handle=handles[-1],
            )
        except Exception as exc:  # noqa: BLE001 — a refusal is a measurement too
            report["resumed_with_same_token"] = f"refused: {type(exc).__name__}: {exc}"[:300]
        fresh = await mint(client, args.model, args.extended)
        try:
            report["resumed_with_fresh_token"] = await session_events(
                fresh.name,
                args.model,
                _config(INSTRUCTION, args.extended),
                scheduling="WHEN_IDLE",
                handle=handles[-1],
            )
        except Exception as exc:  # noqa: BLE001
            report["resumed_with_fresh_token"] = f"refused: {type(exc).__name__}: {exc}"[:300]
    else:
        report["resumed_with_same_token"] = "no handle received"
    raw_token = await mint(client, args.model, args.extended)
    report["raw_websocket_v1beta"] = await raw_websocket_check(raw_token.name, args.model)
    other_token = await mint(client, args.model, args.extended)
    try:
        await session_events(
            other_token.name,
            args.model,
            _config(OTHER_INSTRUCTION, args.extended),
            scheduling="INTERRUPT",
            handle=None,
        )
        report["other_instruction_accepted"] = True
    except Exception as exc:  # noqa: BLE001 — a refusal is the hoped-for answer
        report["other_instruction_accepted"] = f"refused: {type(exc).__name__}: {exc}"[:300]
    late_token = await mint(client, args.model, args.extended)
    try:
        report["late_text_after_tool_call"] = await session_events(
            late_token.name,
            args.model,
            _config(INSTRUCTION, args.extended),
            scheduling="INTERRUPT",
            handle=None,
            push_late_text=True,
        )
    except Exception as exc:  # noqa: BLE001
        report["late_text_after_tool_call"] = f"failed: {type(exc).__name__}: {exc}"[:300]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
