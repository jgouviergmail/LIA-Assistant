"""Gmail's mailbox settings, by the person's own hand (ADR-369).

Gmail alone carries them (the descriptor's VACATION and FILTERS): elsewhere
they are refused before anything is sent. They ride the Gmail connector's own
token through Gmail's settings client, built beside the mailbox's client and
closed on every path. The vacation responder is set in the person's own days —
the first one from its midnight, the last one INCLUDED (Gmail's ``endTime`` is
exclusive: the midnight after, the assistant's tool's own rule) — and reads
back as the same days. A filter is created once per submission and never
applies a system label; nothing deletes one (the client has no such act).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.google_gmail_settings_client import (
    GoogleGmailSettingsClient,
)
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature, WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.schemas.mail_settings import (
    MailFilter,
    MailFilters,
    NewFilter,
    Vacation,
    VacationChange,
)

_TOOL = WorkbenchTool.MAIL
#: The system labels a filter's « archive » and « mark read » remove.
_INBOX, _UNREAD = "INBOX", "UNREAD"


async def read_vacation(user_id: UUID, zone: ZoneInfo) -> Vacation:
    """The vacation responder, in the person's days."""
    async with _settings(user_id, WorkbenchFeature.VACATION) as (client, _):
        async with provider_call(_TOOL, "read_vacation", act=False):
            raw = await client.get_vacation()
    return _vacation(raw, zone)


async def set_vacation(user_id: UUID, zone: ZoneInfo, change: VacationChange) -> Vacation:
    """Turn the vacation responder on (with its words and days) or off — a state SET."""
    async with _settings(user_id, WorkbenchFeature.VACATION) as (client, _):
        async with provider_call(_TOOL, "set_vacation", act=False):
            if not change.enabled:
                raw = await client.update_vacation(enable=False)
            else:
                last = change.end_date
                raw = await client.update_vacation(
                    enable=True,
                    subject=change.subject,
                    body=change.body,
                    start_time_ms=_midnight_ms(change.start_date, zone),
                    end_time_ms=_midnight_ms(last + timedelta(days=1) if last else None, zone),
                )
    return _vacation(raw, zone)


async def list_filters(user_id: UUID) -> MailFilters:
    """The mailbox's filters, each with what it matches and does."""
    async with _settings(user_id, WorkbenchFeature.FILTERS) as (client, _):
        async with provider_call(_TOOL, "list_filters", act=False):
            raw = await client.list_filters()
    return MailFilters(filters=[_filter(item) for item in raw.get("filter") or []])


async def create_filter(user_id: UUID, request: NewFilter) -> MailFilter:
    """Create a filter, once per submission; a system label is never applied."""

    async def create() -> MailFilter:
        async with _settings(user_id, WorkbenchFeature.FILTERS) as (client, mailbox):
            if request.add_label_id and mailbox.is_system_label(request.add_label_id):
                refuse(NOT_SUPPORTED_BY_PROVIDER)
            async with provider_call(_TOOL, "create_filter", act=True):
                raw = await client.create_filter(
                    criteria=_criteria(request), action=_action(request)
                )
        return _filter(raw)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"filter_id": made.id},
    )


@asynccontextmanager
async def _settings(
    user_id: UUID, feature: WorkbenchFeature
) -> AsyncIterator[tuple[GoogleGmailSettingsClient, GoogleGmailClient]]:
    """Gmail's settings client on the mailbox's token; refused unsent elsewhere."""
    async with open_tool_client(_TOOL, user_id) as opened:
        if feature not in PROVIDER_FEATURES[opened.connector_type]:
            refuse(NOT_SUPPORTED_BY_PROVIDER)
        mailbox: GoogleGmailClient = opened.client
        client = GoogleGmailSettingsClient(user_id, mailbox.credentials, DetachedConnectorService())
        try:
            yield client, mailbox
        finally:
            await client.close()


def _midnight_ms(day: date | None, zone: ZoneInfo) -> int | None:
    if day is None:
        return None
    return int(datetime.combine(day, time.min, tzinfo=zone).timestamp() * 1000)


def _day(millis: object, zone: ZoneInfo) -> date | None:
    """The person's day holding an epoch-milliseconds instant; unreadable is none."""
    try:
        return datetime.fromtimestamp(int(str(millis)) / 1000, zone).date()
    except ValueError, OverflowError, OSError:
        return None


def _vacation(raw: Mapping[str, Any], zone: ZoneInfo) -> Vacation:
    end = raw.get("endTime")
    return Vacation(
        enabled=bool(raw.get("enableAutoReply")),
        subject=str(raw.get("responseSubject") or ""),
        body=str(raw.get("responseBodyPlainText") or ""),
        start_date=_day(raw.get("startTime"), zone) if raw.get("startTime") else None,
        # Gmail's end is exclusive: the last day answered is the one before it.
        end_date=_day(int(str(end)) - 1, zone) if str(end or "").isdigit() else None,
    )


def _criteria(request: NewFilter) -> dict[str, Any]:
    named = {
        "from": request.sender,
        "to": request.recipient,
        "subject": request.subject,
        "query": request.query,
    }
    criteria: dict[str, Any] = {key: value for key, value in named.items() if value}
    if request.has_attachment:
        criteria["hasAttachment"] = True
    return criteria


def _action(request: NewFilter) -> dict[str, Any]:
    action: dict[str, Any] = {}
    if request.add_label_id:
        action["addLabelIds"] = [request.add_label_id]
    removed = [
        label for label, asked in ((_INBOX, request.archive), (_UNREAD, request.mark_read)) if asked
    ]
    if removed:
        action["removeLabelIds"] = removed
    return action


def _filter(raw: Mapping[str, Any]) -> MailFilter:
    criteria: Mapping[str, Any] = raw.get("criteria") or {}
    action: Mapping[str, Any] = raw.get("action") or {}
    removed = action.get("removeLabelIds") or []
    return MailFilter(
        id=str(raw.get("id") or ""),
        sender=criteria.get("from") or None,
        recipient=criteria.get("to") or None,
        subject=criteria.get("subject") or None,
        query=criteria.get("query") or None,
        has_attachment=bool(criteria.get("hasAttachment")),
        add_label_ids=list(action.get("addLabelIds") or []),
        archive=_INBOX in removed,
        mark_read=_UNREAD in removed,
        forward=action.get("forward") or None,
    )
