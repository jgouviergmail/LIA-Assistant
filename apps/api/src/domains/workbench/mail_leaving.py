"""Leaving a mailing list from a message, by the person's own hand (ADR-369, lot 3).

The reader shows the ways out the message names. One-click (RFC 8058) is an act on
a stranger's server, so it reads the message again rather than taking an address
from the page, and goes out through the one validated door (ADR-326): the address
checked, the connection pinned to what was checked, no redirect followed, the one
line of the RFC and nothing of the person. Only a 2xx counts: a redirect is a new
address nobody checked, and the screen then offers the page itself. No session is
held across the wait (ADR-304): nothing here touches the database.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import httpx

from src.core.constants import WORKBENCH_UNSUBSCRIBE_TIMEOUT_SECONDS
from src.domains.connectors.clients.mail_unsubscribe import ONE_CLICK_BODY, Unsubscribe
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, PROVIDER_REFUSED, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.schemas.mail import MailUnsubscribe
from src.infrastructure.utils.url_validation import pinned_stream, validate_url

_TOOL = WorkbenchTool.MAIL
_POST_HEADERS: Final = {"Content-Type": "application/x-www-form-urlencoded"}


async def _ways_of(user_id: UUID, message_id: str) -> Unsubscribe | None:
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read_unsubscribe", act=False):
            return await client.read_unsubscribe(message_id)


async def read_ways(user_id: UUID, message_id: str) -> MailUnsubscribe:
    """The ways out a message names; none of them when it names none."""
    ways = await _ways_of(user_id, message_id)
    if ways is None:
        return MailUnsubscribe(web_url=None, mail_to=None, one_click=False)
    return MailUnsubscribe(web_url=ways.web_url, mail_to=ways.mail_to, one_click=ways.one_click)


async def leave(user_id: UUID, message_id: str) -> None:
    """Post the one-click request the message promises.

    Raises:
        BaseAPIException: ``not_supported_by_provider`` when it promises none;
            ``provider_refused`` when the address fails its check or does not answer
            with a success; ``outcome_unknown`` when the answer is lost.
    """
    ways = await _ways_of(user_id, message_id)
    if ways is None or not ways.one_click or ways.web_url is None:
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    verdict = await validate_url(ways.web_url)
    if not verdict.valid:
        refuse(PROVIDER_REFUSED)
    async with (
        provider_call(_TOOL, "unsubscribe", act=True),
        httpx.AsyncClient(follow_redirects=False) as http,
        pinned_stream(
            http,
            "POST",
            verdict,
            headers=dict(_POST_HEADERS),
            content=ONE_CLICK_BODY.encode(),
            timeout=WORKBENCH_UNSUBSCRIBE_TIMEOUT_SECONDS,
        ) as response,
    ):
        if not response.is_success:
            refuse(PROVIDER_REFUSED)
