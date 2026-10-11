"""Bounded discovery pages are invalidated when their source catalogue changes."""

import asyncio
import hashlib
import json
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.i18n import normalize_language
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.live_options_schemas import LiveOptionsRead
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.live_connector_preferences import (
    LiveOptionsProjection,
    get_live_connector_preferences,
)


def page_live_options(
    catalogue: LiveOptionsProjection, request: LiveOptionsRead
) -> dict[str, JsonValue]:
    items = catalogue.choices
    identities = [(item.get("provider", request.provider), item.get("name")) for item in items]
    if any(not isinstance(name, str) or not name for _, name in identities):
        raise ValueError("Invalid Live choice identity")
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate Live choice identity")
    digest = hashlib.sha256(
        json.dumps(
            {
                "section": request.section,
                "provider": request.provider,
                **catalogue.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    offset = request.offset
    if request.cursor is not None:
        previous, index = request.cursor.split(":")
        if previous != digest:
            raise ValueError("Live catalogue changed; restart at the first page")
        offset = int(index)
    if offset > len(items):
        raise ValueError("Live choice offset outside catalogue")
    page = items[offset : offset + request.limit]
    next_offset = offset + len(page)
    visible: list[JsonValue] = list(page)
    return {
        "choices": visible,
        "details": catalogue.details,
        "total": len(items),
        "page_offset": offset,
        "catalogue_digest": digest,
        "next_cursor": f"{digest}:{next_offset}" if next_offset < len(items) else None,
    }


async def read_live_options(
    db: AsyncSession, actor_id: UUID, request: LiveOptionsRead
) -> dict[str, JsonValue]:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.LIVE)
    actor = await load_actor(db, actor_id)
    async with asyncio.timeout(settings.live_probe_timeout_seconds):
        catalogue = await get_live_connector_preferences().options(
            db,
            actor_id,
            request.section,
            request.provider,
            language=normalize_language(actor.language),
        )
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.LIVE)
    await load_actor(db, actor_id)
    return page_live_options(catalogue, request)
