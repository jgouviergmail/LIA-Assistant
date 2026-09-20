"""Simulate a Live owner call end to end — without a phone (ADR-301).

    docker exec lia-api-dev python -m scripts.telephony.simulate_live_call \\
        --user <uuid> [--api https://localhost:8000] [--request "..."] [--answer "..."]

What a real call does, this does with HTTP alone, against a RUNNING API:

1. a ``DIALING`` owner-call row in Live mode is inserted for the account (the
   dial's own row, minus the vendor);
2. the vendor's delegation call-back is POSTed to ``/telephony/tools/send_to_lia``
   with the call id and the derived token — the bridge runs a REAL chat turn
   on the person's conversation and answers what the voice would say; a
   second request may answer a question LIA asked (``--answer``);
3. the vendor's post-call webhook is POSTed, signed with the connector's
   secret, with a transcript carrying the delegated exchanges the way the
   vendor writes them (``tool_calls`` / ``tool_results``);
4. the books are read back: the row (no return to deliver), the voice-only
   rows and the closing card in the conversation, the calls listing's bill.

``--unanswered`` plays a Live call nobody picked up: no delegation, the
post-call webhook says ``no_answer``, and the books must show the row
settled with the fallback push « nobody answered » (``relay_outcome``
``unanswered``, a notification row) — the closing a call has whatever mode
it was dialled under (review 2026-09-20).

Only the operator's own account on a development instance: the row it
inserts is a real row, the turn a real turn. Nothing here is a test.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, text

from src.core.config import settings
from src.core.security.utils import encrypt_data
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.conversations.models import ConversationMessage
from src.domains.telephony.live_tools import LIVE_TOOL_HEADER, live_tool_token
from src.domains.telephony.models import CallKind, PhoneCall, PhoneCallStatus
from src.domains.telephony.spend import phone_call_run_id
from src.domains.telephony.webhook_handler import SIGNATURE_HEADER
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import get_db_context


async def _insert_call(user_id: UUID) -> UUID:
    """The dial's own row — or the account's active one, when a previous run
    left it open (``--skip-close``): the one-active-call guard is an invariant
    the simulation must respect, not walk around."""
    async with get_db_context() as db:
        active = (
            await db.execute(
                select(PhoneCall).where(
                    PhoneCall.user_id == user_id,
                    PhoneCall.status.in_((PhoneCallStatus.DIALING, PhoneCallStatus.IN_PROGRESS)),
                )
            )
        ).scalar_one_or_none()
        if active is not None:
            if active.call_mode != "delegated" or active.call_kind is not CallKind.SELF:
                raise SystemExit(f"an active call {active.id} is not a Live owner call")
            print(f"  reusing the active Live owner call {active.id}")
            return active.id
        now = datetime.now(UTC)
        call = PhoneCall(
            user_id=user_id,
            callee_display="simulation",
            callee_phone=encrypt_data("+33600000000"),
            objective="Simulated Live owner call (ADR-301)",
            call_kind=CallKind.SELF,
            call_mode="delegated",
            objective_window_start=now,
            objective_window_end=now + timedelta(days=1),
            status=PhoneCallStatus.DIALING,
            initiated_at=now,
            expires_at=now + timedelta(days=1),
        )
        db.add(call)
        await db.commit()
        return call.id


async def _connector(user_id: UUID) -> tuple[str, str]:
    """The connector's webhook secret and its vendor agent id.

    The post-call webhook is accepted only when its ``agent_id`` is the
    connector's (the foreign filter) and its signature the secret's: the
    rig echoes both, as the vendor does.
    """
    async with get_db_context() as db:
        service = ConnectorService(db)
        connector = await service.repository.get_by_user_and_type(
            user_id, ConnectorType.ELEVENLABS_TELEPHONY
        )
        creds = await service.get_api_key_credentials(user_id, ConnectorType.ELEVENLABS_TELEPHONY)
    if creds is None or not creds.api_secret or connector is None:
        raise SystemExit("no active telephony connector with a secret for this account")
    agent_id = str((connector.connector_metadata or {}).get("agent_id") or "")
    if not agent_id:
        raise SystemExit("the telephony connector names no agent")
    return str(creds.api_secret), agent_id


def _signature(body: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v0={digest}"


async def _delegate(api: str, call_id: UUID, token: str, request: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=api, verify=False, timeout=300.0) as client:
        started = time.monotonic()
        resp = await client.post(
            f"{settings.api_prefix}/telephony/tools/send_to_lia",
            json={"call_id": str(call_id), "request": request},
            headers={LIVE_TOOL_HEADER: token},
        )
        elapsed = round(time.monotonic() - started, 1)
    print(f"  -> {resp.status_code} in {elapsed}s: {resp.text[:400]}")
    return resp.json() if resp.status_code == 200 else {}


def _payload(call_id: UUID, agent_id: str, exchanges: list[tuple[str, str]]) -> dict[str, Any]:
    transcript: list[dict[str, Any]] = [
        {"role": "agent", "message": "Hello, is this you?", "time_in_call_secs": 0},
        {"role": "user", "message": "Yes it is.", "time_in_call_secs": 3},
    ]
    t = 5
    for request, answer in exchanges:
        transcript += [
            {"role": "user", "message": request, "time_in_call_secs": t},
            {
                "role": "agent",
                "message": "Let me check that for you.",
                "time_in_call_secs": t + 1,
                "tool_calls": [
                    {
                        "request_id": uuid4().hex,
                        "tool_name": "send_to_lia",
                        "params_as_json": json.dumps({"request": request}),
                        "type": "webhook",
                    }
                ],
            },
            {"role": "agent", "message": "Anything else meanwhile?", "time_in_call_secs": t + 3},
            {
                "role": "agent",
                "message": answer[:200],
                "time_in_call_secs": t + 12,
                "tool_results": [
                    {"tool_name": "send_to_lia", "is_error": False, "tool_latency_secs": 9.0}
                ],
            },
        ]
        t += 20
    transcript += [
        {"role": "user", "message": "Thanks, that is all. Bye.", "time_in_call_secs": t},
        {
            "role": "agent",
            "message": "Everything is in your chat. Goodbye.",
            "time_in_call_secs": t + 2,
        },
    ]
    return {
        "type": "post_call_transcription",
        "event_timestamp": int(time.time()),
        "data": {
            "agent_id": agent_id,
            "conversation_id": f"conv_sim_{call_id.hex[:8]}",
            "status": "done",
            "metadata": {"call_duration_secs": t + 4},
            "analysis": {
                "transcript_summary": "The person asked LIA for a few things and said goodbye.",
                "data_collection_results": {"owner_confirmed": {"value": True}},
            },
            "transcript": transcript,
            "conversation_initiation_client_data": {"dynamic_variables": {"call_id": str(call_id)}},
        },
    }


def _unanswered_payload(call_id: UUID, agent_id: str) -> dict[str, Any]:
    """The vendor's post-call payload of a call nobody picked up."""
    return {
        "type": "post_call_transcription",
        "event_timestamp": int(time.time()),
        "data": {
            "agent_id": agent_id,
            "conversation_id": f"conv_sim_{call_id.hex[:8]}",
            "status": "done",
            "metadata": {"call_duration_secs": 0, "termination_reason": "no_answer"},
            "analysis": {"transcript_summary": "", "data_collection_results": {}},
            "transcript": [],
            "conversation_initiation_client_data": {"dynamic_variables": {"call_id": str(call_id)}},
        },
    }


async def _post_call(api: str, secret: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode()
    async with httpx.AsyncClient(base_url=api, verify=False, timeout=60.0) as client:
        resp = await client.post(
            f"{settings.api_prefix}/telephony/webhook",
            content=body,
            headers={
                SIGNATURE_HEADER: _signature(body, secret),
                "Content-Type": "application/json",
            },
        )
    print(f"  -> {resp.status_code}: {resp.text[:200]}")


async def _read_books(call_id: UUID, user_id: UUID) -> None:
    key = phone_call_run_id(call_id)
    async with get_db_context() as db:
        for _ in range(30):
            # ``populate_existing``: the identity map would otherwise hand back
            # the row as first read, DIALING for ever.
            row = (
                await db.execute(
                    select(PhoneCall)
                    .where(PhoneCall.id == call_id)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
            if row.status is not PhoneCallStatus.DIALING:
                break
            await asyncio.sleep(1)
        print(
            f"  phone_calls: status={row.status.value} outcome={row.outcome} "
            f"mode={row.call_mode} notification_status={row.notification_status} "
            f"relay_outcome={(row.notification_payload or {}).get('relay_outcome')!r} "
            f"summary={row.summary!r}"
        )
        notices = (
            await db.execute(
                text(
                    "select content from conversation_messages where message_metadata->>'target_id' = :t "
                    "order by created_at desc limit 1"
                ),
                {"t": str(call_id)},
            )
        ).all()
        print(f"  notification rows targeting the call: {[n[0][:120] for n in notices]}")
        rows = (
            await db.execute(
                select(
                    ConversationMessage.role,
                    ConversationMessage.content,
                    ConversationMessage.message_metadata,
                )
                .where(ConversationMessage.message_metadata["live_session_id"].astext == key)
                .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
            )
        ).all()
        print(f"  conversation rows stamped {key}: {len(rows)}")
        for role, content, meta in rows:
            kind = meta.get("type") or ("delegated turn" if meta.get("run_id") else "?")
            print(f"    - {role:<9} [{kind}] {content[:90]!r}")
        decisions = (
            await db.execute(
                text("select route, outcome from agent_decisions where run_id = :run"), {"run": key}
            )
        ).all()
        print(f"  agent_decisions for {key}: {decisions}")
        summaries = (
            await db.execute(
                text(
                    "select run_id, total_prompt_tokens, total_completion_tokens, total_cost_eur "
                    "from message_token_summary where user_id = :u and created_at > now() - interval '10 minutes' "
                    "order by created_at"
                ),
                {"u": str(user_id)},
            )
        ).all()
        print("  message_token_summary (last 10 min):")
        for s in summaries:
            print(f"    - {s}")
        from src.domains.telephony.router import list_calls
        from src.domains.users.models import User

        user = await db.get(User, user_id)
        if user is None:
            raise SystemExit("unknown user")
        listed = await list_calls(user=user, db=db, limit=3)
        print("  GET /telephony/calls (top 3):")
        for item in listed:
            usage = item.usage.model_dump() if item.usage else None
            print(
                f"    - {item.id} kind={item.call_kind.value} mode={item.call_mode} usage={usage}"
            )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--user", required=True)
    parser.add_argument("--api", default="https://localhost:8000")
    parser.add_argument("--request", default="What do I have on my agenda tomorrow?")
    parser.add_argument(
        "--answer", default=None, help="A second request (an answer to LIA's question)"
    )
    parser.add_argument("--skip-close", action="store_true")
    parser.add_argument(
        "--unanswered",
        action="store_true",
        help="Nobody picks up: no delegation, the fallback push",
    )
    args = parser.parse_args()
    user_id = UUID(args.user)
    import_all_models()

    print("[1] inserting a DIALING Live owner-call row")
    call_id = await _insert_call(user_id)
    print(f"  call_id={call_id}")
    secret, agent_id = await _connector(user_id)
    token = live_tool_token(secret)

    if args.unanswered:
        print("[2] nobody picks up: posting the vendor's post-call webhook (no_answer)")
        await _post_call(args.api, secret, _unanswered_payload(call_id, agent_id))
        print("[3] reading the books")
        await _read_books(call_id, user_id)
        return 0

    print(f"[2] delegating: {args.request!r}")
    exchanges: list[tuple[str, str]] = []
    first = await _delegate(args.api, call_id, token, args.request)
    exchanges.append((args.request, first.get("result", "")))
    if args.answer:
        print(f"[2b] answering: {args.answer!r}")
        second = await _delegate(args.api, call_id, token, args.answer)
        exchanges.append((args.answer, second.get("result", "")))

    if args.skip_close:
        return 0
    print("[3] posting the vendor's post-call webhook")
    await _post_call(args.api, secret, _payload(call_id, agent_id, exchanges))
    print("[4] reading the books")
    await _read_books(call_id, user_id)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
