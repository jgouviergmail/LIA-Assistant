"""Revalidate a card's original source when its reader chooses to open it."""

from uuid import UUID

from src.core.content_source import content_source_binding
from src.core.exceptions import BaseAPIException
from src.domains.workbench.card_targets import CARD_TOOLS, CardTargetResponse, read_card_target
from src.domains.workbench.clients import open_tool_client


async def open_card_target(token: str, user_id: UUID) -> CardTargetResponse:
    """Admit only the same provider account, without fetching the record itself."""
    envelope = read_card_target(token, user_id)
    if envelope is None:
        return CardTargetResponse(available=False, reason="historical")
    try:
        async with open_tool_client(
            CARD_TOOLS[envelope.target.kind], user_id, fresh=True
        ) as opened:
            if (
                opened.connector_type != envelope.provider
                or content_source_binding(opened.client) != envelope.source_binding
            ):
                return CardTargetResponse(available=False, reason="source_changed")
    except BaseAPIException, TimeoutError:
        return CardTargetResponse(available=False, reason="unavailable")
    return CardTargetResponse(available=True, target=envelope.target)
