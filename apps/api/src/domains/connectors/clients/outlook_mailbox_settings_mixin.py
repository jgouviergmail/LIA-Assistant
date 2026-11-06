"""Outlook's automatic replies and rules through Microsoft Graph (ADR-369, lot 12).

The screen and the assistant speak to a mailbox's settings in one vocabulary, Gmail's settings
client's: a responder bounded in epoch milliseconds, its end excluded, and filters made of
criteria and actions. This mixin translates it, so neither carries a branch per provider.

What Outlook cannot hold is refused before anything is sent: an automatic reply has no subject,
a schedule has an end, and a rule reads no Gmail search. Both surfaces need
``MailboxSettings.ReadWrite``, which a connection made before lot 12 does not carry: Graph answers
403 and the connector stays as it was (measured), and only a reconnection asks for the right.
A write answers less than a read says, so what was written is read back. Rules sit on the inbox,
the one folder Graph holds them on.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from html import escape
from http import HTTPStatus
from typing import Any, Final, Protocol

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.mail_folders import MailFolder
from src.domains.connectors.clients.normalizers.html_text import html_to_text
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType

_REPLIES: Final = "/me/mailboxSettings/automaticRepliesSetting"
_SETTINGS: Final = "/me/mailboxSettings"
_RULES: Final = "/me/mailFolders/inbox/messageRules"
_ARCHIVE: Final = "/me/mailFolders/archive"
_NEXT_PAGE: Final = "@odata.nextLink"
#: What a responder's status says it does.
_OFF: Final = "disabled"
_SCHEDULED: Final = "scheduled"
_ALWAYS: Final = "alwaysEnabled"
#: The system labels of the vocabulary: leaving the inbox, and being read.
_INBOX: Final = "INBOX"
_UNREAD: Final = "UNREAD"
_GRAPH_TIME: Final = "%Y-%m-%dT%H:%M:%S"
#: Asked of every read, so that an instant set elsewhere reads in the one zone understood here.
_IN_UTC: Final = {"Prefer": 'outlook.timezone="UTC"'}
#: What a rule is called when nothing it matches has words: Graph requires a name.
_UNNAMED_RULE: Final = "LIA"


class MailboxSettingsNotGrantedError(Exception):
    """The connection predates ``MailboxSettings.ReadWrite``: a reconnection asks for it."""


class MailboxSettingNotHeldError(Exception):
    """Outlook has no such setting: refused unsent, never dropped in silence."""


class _OutlookSettingsHost(Protocol):
    """What the mixin needs from its host, and of itself."""

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    async def _make_request_full_url(self, method: str, url: str) -> dict[str, Any]: ...

    async def _folder_id(self, name: str) -> str: ...

    async def list_folders(self) -> tuple[list[MailFolder], bool]: ...

    async def _settings_call(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    async def _rules(self) -> list[dict[str, Any]]: ...

    async def _archive_id(self) -> str | None: ...

    async def _actions_of(self, action: Mapping[str, Any]) -> dict[str, Any]: ...

    async def get_vacation(self) -> dict[str, Any]: ...

    async def label_names(self) -> dict[str, str]: ...


def _instant(moment: Mapping[str, Any] | None) -> int | None:
    """The epoch milliseconds a Graph date in UTC names; anything else is none."""
    if not moment or moment.get("timeZone") != "UTC":
        return None
    try:
        when = datetime.fromisoformat(str(moment.get("dateTime"))[:19]).replace(tzinfo=UTC)
    except ValueError:
        return None
    return int(when.timestamp() * 1000)


def _graph_time(millis: int) -> dict[str, str]:
    moment = datetime.fromtimestamp(millis / 1000, UTC)
    return {"dateTime": moment.strftime(_GRAPH_TIME), "timeZone": "UTC"}


def _as_html(text: str) -> str:
    """The person's words, as the HTML Graph keeps a reply in."""
    return escape(text).replace("\n", "<br>")


def _first(values: list[Any] | None) -> str | None:
    return str(values[0]) if values else None


def _address(recipients: list[Mapping[str, Any]] | None) -> str | None:
    if not recipients:
        return None
    return str((recipients[0].get("emailAddress") or {}).get("address") or "") or None


def _criteria_of(conditions: Mapping[str, Any]) -> dict[str, Any]:
    named = {
        "from": _first(conditions.get("senderContains"))
        or _address(conditions.get("fromAddresses")),
        "to": _first(conditions.get("recipientContains"))
        or _address(conditions.get("sentToAddresses")),
        "subject": _first(conditions.get("subjectContains")),
    }
    criteria: dict[str, Any] = {key: value for key, value in named.items() if value}
    if conditions.get("hasAttachments"):
        criteria["hasAttachment"] = True
    return criteria


def _conditions_of(criteria: Mapping[str, Any]) -> dict[str, Any]:
    named = (
        ("senderContains", criteria.get("from")),
        ("recipientContains", criteria.get("to")),
        ("subjectContains", criteria.get("subject")),
    )
    conditions: dict[str, Any] = {key: [value] for key, value in named if value}
    if criteria.get("hasAttachment"):
        conditions["hasAttachments"] = True
    return conditions


def _rule_name(criteria: Mapping[str, Any]) -> str:
    named = (criteria.get(key) for key in ("from", "to", "subject"))
    return str(next((value for value in named if value), _UNNAMED_RULE))


def _filter_of(
    rule: Mapping[str, Any], names: Mapping[str, str], archive: str | None
) -> dict[str, Any]:
    """A rule as the vocabulary states a filter; a folder nobody lists keeps its id."""
    actions: Mapping[str, Any] = rule.get("actions") or {}
    folder = actions.get("moveToFolder")
    action: dict[str, Any] = {}
    removed = []
    if folder and folder == archive:
        removed.append(_INBOX)
    elif folder:
        action["addLabelIds"] = [names.get(folder, folder)]
    if actions.get("markAsRead"):
        removed.append(_UNREAD)
    if removed:
        action["removeLabelIds"] = removed
    forward = _address(actions.get("forwardTo"))
    if forward:
        action["forward"] = forward
    return {
        "id": str(rule.get("id") or ""),
        "name": str(rule.get("displayName") or ""),
        "read_only": bool(rule.get("isReadOnly")),
        "criteria": _criteria_of(rule.get("conditions") or {}),
        "action": action,
    }


class OutlookMailboxSettingsMixin:
    """Automatic replies and rules, under the names Gmail's settings client gives them."""

    async def _settings_call(
        self: _OutlookSettingsHost,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            return await self._make_request(
                method, endpoint, None, json_data, extra_headers=extra_headers
            )
        except ConnectorAPIError as refused:
            if refused.upstream_status_code == HTTPStatus.FORBIDDEN:
                raise MailboxSettingsNotGrantedError from refused
            raise

    async def get_vacation(self: _OutlookSettingsHost) -> dict[str, Any]:
        """The automatic replies, as the vocabulary states a responder."""
        raw = await self._settings_call("GET", _REPLIES, extra_headers=_IN_UTC)
        status = raw.get("status", _OFF)
        words = raw.get("externalReplyMessage") or raw.get("internalReplyMessage") or ""
        vacation: dict[str, Any] = {
            "enableAutoReply": status != _OFF,
            "responseSubject": "",
            "responseBodyPlainText": html_to_text(str(words)),
        }
        if status == _SCHEDULED:
            start = _instant(raw.get("scheduledStartDateTime"))
            end = _instant(raw.get("scheduledEndDateTime"))
            if start is not None:
                vacation["startTime"] = start
            if end is not None:
                vacation["endTime"] = end
        return vacation

    async def update_vacation(
        self: _OutlookSettingsHost,
        enable: bool,
        subject: str | None = None,
        body: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> dict[str, Any]:
        """Set the automatic replies, and read back what Graph kept.

        Args:
            enable: Turn them on or off.
            subject: Refused when given: an automatic reply has none.
            body: Their words, sent inside and outside the organisation alike.
            start_time_ms: The first instant (epoch milliseconds); now when left out.
            end_time_ms: The instant they stop (exclusive); a schedule has one.

        Returns:
            The responder as it stands.

        Raises:
            MailboxSettingNotHeldError: A subject, or a first day with no last.
        """
        setting: dict[str, Any] = {"status": _OFF}
        if enable:
            if subject or (start_time_ms is not None and end_time_ms is None):
                raise MailboxSettingNotHeldError
            message = _as_html(body or "")
            setting = {
                "status": _ALWAYS,
                "externalAudience": "all",
                "internalReplyMessage": message,
                "externalReplyMessage": message,
            }
            if end_time_ms is not None:
                start = start_time_ms or int(datetime.now(UTC).timestamp() * 1000)
                setting["status"] = _SCHEDULED
                setting["scheduledStartDateTime"] = _graph_time(start)
                setting["scheduledEndDateTime"] = _graph_time(end_time_ms)
        await self._settings_call("PATCH", _SETTINGS, {"automaticRepliesSetting": setting})
        return await self.get_vacation()

    async def _rules(self: _OutlookSettingsHost) -> list[dict[str, Any]]:
        page = await self._settings_call("GET", _RULES)
        rules = list(page.get("value") or [])
        while next_page := page.get(_NEXT_PAGE):
            page = await self._make_request_full_url("GET", str(next_page))
            rules.extend(page.get("value") or [])
        return rules

    async def _archive_id(self: _OutlookSettingsHost) -> str | None:
        """The Archive's id; a mailbox that never made one answers 404."""
        try:
            folder = await self._make_request("GET", _ARCHIVE, {"$select": "id"})
        except ConnectorAPIError as refused:
            if refused.upstream_status_code == HTTPStatus.NOT_FOUND:
                return None
            raise
        return str(folder.get("id") or "") or None

    async def label_names(self: _OutlookSettingsHost) -> dict[str, str]:
        """Each folder's path by its Graph id: a rule names its folder by id alone."""
        folders, _ = await self.list_folders()
        return {folder.folder_id: folder.path for folder in folders}

    async def list_filters(self: _OutlookSettingsHost) -> dict[str, Any]:
        """The inbox's rules, as the vocabulary states filters."""
        rules = await self._rules()
        if not any((rule.get("actions") or {}).get("moveToFolder") for rule in rules):
            return {"filter": [_filter_of(rule, {}, None) for rule in rules]}
        names = await self.label_names()
        archive = await self._archive_id()
        return {"filter": [_filter_of(rule, names, archive) for rule in rules]}

    async def create_filter(
        self: _OutlookSettingsHost, criteria: dict[str, Any], action: dict[str, Any]
    ) -> dict[str, Any]:
        """Add a rule after the others.

        Args:
            criteria: What it matches (from, to, subject, hasAttachment).
            action: What it does (addLabelIds, removeLabelIds).

        Returns:
            The rule, as the vocabulary states a filter.

        Raises:
            MailboxSettingNotHeldError: A Gmail search, which no rule can read.
        """
        if criteria.get("query"):
            raise MailboxSettingNotHeldError
        actions = await self._actions_of(action)
        rules = await self._rules()
        last = max((int(rule.get("sequence") or 0) for rule in rules), default=0)
        made = await self._settings_call(
            "POST",
            _RULES,
            {
                "displayName": _rule_name(criteria),
                "sequence": last + 1,
                "isEnabled": True,
                "conditions": _conditions_of(criteria),
                "actions": actions,
            },
        )
        return _filter_of(made, await self.label_names(), await self._archive_id())

    async def _actions_of(self: _OutlookSettingsHost, action: Mapping[str, Any]) -> dict[str, Any]:
        removed = action.get("removeLabelIds") or []
        added = action.get("addLabelIds") or []
        actions: dict[str, Any] = {}
        if added:
            folder = str(added[0])
            held = folder in await self.label_names()
            actions["moveToFolder"] = folder if held else await self._folder_id(folder)
        elif _INBOX in removed:
            archive = await self._archive_id()
            if archive is None:
                raise MailboxSettingNotHeldError
            actions["moveToFolder"] = archive
        if _UNREAD in removed:
            actions["markAsRead"] = True
        return actions

    async def delete_filter(self: _OutlookSettingsHost, filter_id: str) -> None:
        """Delete a rule; what it already sorted stays where it is."""
        segment = path_segment(filter_id, connector_type=ConnectorType.MICROSOFT_OUTLOOK)
        await self._settings_call("DELETE", f"{_RULES}/{segment}")

    async def list_send_as(self) -> dict[str, Any]:
        """Outlook sends from the mailbox alone."""
        return {"sendAs": []}

    def is_system_label(self, name: str) -> bool:
        """A folder of the person's own is all a rule is offered here."""
        return False
