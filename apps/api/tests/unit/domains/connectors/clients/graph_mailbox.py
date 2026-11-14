"""Microsoft Graph's mail endpoints over an in-memory inbox, for the real Outlook client.

No Outlook mailbox can be measured any more (no live proof on a consumer mailbox since
2026-11-11), so the client is exercised against what the Graph reference documents,
served through ``httpx.MockTransport``: the client builds its own requests, its own hooks
run (the read budget claims one call per request), its own normaliser reads the answers.

What is modelled, and where the reference says it:

- « List messages » (``GET /me/mailFolders/{id}/messages``): ``$select`` answers the
  named properties alone, beside ``id`` and ``@odata.etag``; ``$filter`` on
  ``receivedDateTime``; ``$orderby=receivedDateTime desc``; ``$top`` pages, a further
  page being named by ``@odata.nextLink``.
- « Get message » (``GET /me/messages/{id}``): ``$select``, and the ONE relationship a
  request expands — ``attachments``, or ``singleValueExtendedProperties($filter=id eq
  '…' or id eq '…')`` (« Get singleValueLegacyExtendedProperty »): each entry is
  ``{"id", "value"}``, the value a string. An item holding none of the properties
  named is answered here WITHOUT the property; the reference does not say whether Graph
  answers an empty list instead, and the client's own tests read that shape too. An
  unknown id answers 404 ``ErrorItemNotFound``.
- What a reply does to the message it answers: Exchange stamps on it
  ``PidTagLastVerbExecuted`` (0x1081 — 102 reply to sender, 103 reply to all, 104 forward)
  and ``PidTagLastVerbExecutionTime`` (0x1082) ([MS-OXOMSG] 2.2.1.14).

What is not modelled answers 400: a gap in the script fails loudly, never silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from urllib.parse import unquote

import httpx

_LAST_VERB: Final = "Integer 0x1081"
_LAST_VERB_AT: Final = "SystemTime 0x1082"
_BOUND: Final = re.compile(r"receivedDateTime (ge|gt|le|lt) (\S+)")
_NAMED_PROPERTY: Final = re.compile(r"id eq '([^']+)'")
_TAGS: Final = re.compile(r"<[^>]+>")
#: « bodyPreview: the first 255 characters of the message body, in text format ».
_PREVIEW_CHARS: Final = 255


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _holds(received: datetime, operator: str, bound: datetime) -> bool:
    return {
        "ge": received >= bound,
        "gt": received > bound,
        "le": received <= bound,
        "lt": received < bound,
    }[operator]


@dataclass
class GraphMailbox:
    """One Outlook mailbox — its inbox — as Microsoft Graph serves it.

    Attributes:
        requests: Every request received, in order.
    """

    requests: list[httpx.Request] = field(default_factory=list)
    _messages: dict[str, dict[str, Any]] = field(default_factory=dict)
    _properties: dict[str, dict[str, str]] = field(default_factory=dict)

    def receive(
        self, message_id: str, *, subject: str, sender: tuple[str, str], received: str, html: str
    ) -> None:
        """File a received message in the inbox, as the message resource describes it."""
        name, address = sender
        self._messages[message_id] = {
            "@odata.etag": f'W/"{message_id}"',
            "id": message_id,
            "conversationId": f"conversation-of-{message_id}",
            "subject": subject,
            "from": {"emailAddress": {"name": name, "address": address}},
            "toRecipients": [{"emailAddress": {"name": "Jane Doe", "address": "jane@outlook.com"}}],
            "ccRecipients": [],
            "bccRecipients": [],
            "replyTo": [],
            "body": {"contentType": "html", "content": html},
            "bodyPreview": _TAGS.sub("", html)[:_PREVIEW_CHARS],
            "receivedDateTime": received,
            "isRead": True,
            "isDraft": False,
            "hasAttachments": False,
            "flag": {"flagStatus": "notFlagged"},
            "importance": "normal",
            "webLink": f"https://outlook.live.com/owa/?ItemID={message_id}",
            "parentFolderId": "inbox-folder-id",
        }

    def stamp_last_verb(self, message_id: str, verb: int, at: str) -> None:
        """What Exchange stamps on a message once something was done with it."""
        self._properties[message_id] = {_LAST_VERB: str(verb), _LAST_VERB_AT: at}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._answer)

    def paths(self) -> list[str]:
        """The path of every request received, without the API version."""
        return [request.url.path.removeprefix("/v1.0") for request in self.requests]

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v1.0")
        if request.method == "GET" and path == "/me/mailFolders/inbox/messages":
            return self._listed(request)
        if request.method == "GET" and (one := re.fullmatch(r"/me/messages/([^/]+)", path)):
            return self._one(unquote(one.group(1)), request)
        return self._refusal(400, "BadRequest", f"{request.method} {path} is not scripted here")

    @staticmethod
    def _refusal(status: int, code: str, message: str) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": code, "message": message}})

    @staticmethod
    def _selected(message: dict[str, Any], request: httpx.Request) -> dict[str, Any]:
        """The properties ``$select`` names, beside what Graph always answers."""
        names = request.url.params.get("$select")
        if names is None:
            return dict(message)
        kept = {"@odata.etag", "id", *names.split(",")}
        return {name: value for name, value in message.items() if name in kept}

    def _listed(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        unknown = set(params) - {"$top", "$skip", "$select", "$filter", "$orderby"}
        if unknown or params.get("$orderby") != "receivedDateTime desc":
            return self._refusal(400, "BadRequest", "this listing is not scripted here")
        bounds = [
            (operator, _instant(value))
            for operator, value in _BOUND.findall(params.get("$filter", ""))
        ]
        found = sorted(
            (
                message
                for message in self._messages.values()
                if all(
                    _holds(_instant(message["receivedDateTime"]), operator, bound)
                    for operator, bound in bounds
                )
            ),
            key=lambda message: _instant(message["receivedDateTime"]),
            reverse=True,
        )
        top, skip = int(params["$top"]), int(params.get("$skip", 0))
        page: dict[str, Any] = {
            "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('me')/mailFolders('inbox')/messages",
            "value": [self._selected(message, request) for message in found[skip : skip + top]],
        }
        if len(found) > skip + top:
            page["@odata.nextLink"] = str(request.url.copy_set_param("$skip", str(skip + top)))
        return httpx.Response(200, json=page)

    def _one(self, message_id: str, request: httpx.Request) -> httpx.Response:
        message = self._messages.get(message_id)
        if message is None:
            return self._refusal(404, "ErrorItemNotFound", "The specified object was not found.")
        answer = self._selected(message, request)
        expand = request.url.params.get("$expand", "")
        if expand.startswith("attachments"):
            answer["attachments"] = []
        elif expand.startswith("singleValueExtendedProperties"):
            held = self._properties.get(message_id, {})
            named = [name for name in _NAMED_PROPERTY.findall(expand) if name in held]
            if named:
                answer["singleValueExtendedProperties"] = [
                    {"id": name, "value": held[name]} for name in named
                ]
        elif expand:
            return self._refusal(400, "BadRequest", "this expansion is not scripted here")
        return httpx.Response(200, json=answer)
