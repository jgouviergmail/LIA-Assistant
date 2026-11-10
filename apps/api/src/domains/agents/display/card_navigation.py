"""Stamp native-card navigation from the client that produced its facts."""

from __future__ import annotations

from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from src.core.content_source import content_source_binding
from src.core.time_parsing import parse_provider_datetime
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.card_targets import (
    CARD_KIND_FIELD,
    CARD_TARGET_FIELD,
    CardTargetKind,
    CardToolTarget,
    SignedCardTarget,
    sign_card_target,
)

_KINDS: Final[dict[RegistryItemType, CardTargetKind]] = {
    RegistryItemType.EMAIL: CardTargetKind.EMAIL,
    RegistryItemType.EVENT: CardTargetKind.EVENT,
    RegistryItemType.CALENDAR: CardTargetKind.CALENDAR,
    RegistryItemType.CONTACT: CardTargetKind.CONTACT,
    RegistryItemType.TASK: CardTargetKind.TASK,
    RegistryItemType.FILE: CardTargetKind.FILE,
    RegistryItemType.HUE_LIGHT: CardTargetKind.HUE_LIGHT,
}
assert set(_KINDS.values()) == set(CardTargetKind)
_IDENTIFIERS: Final[dict[CardTargetKind, tuple[str, ...]]] = {
    CardTargetKind.EMAIL: ("message_id", "id"),
    CardTargetKind.EVENT: ("id",),
    CardTargetKind.CALENDAR: ("id",),
    CardTargetKind.CONTACT: ("resourceName", "id"),
    CardTargetKind.TASK: ("id",),
    CardTargetKind.FILE: ("id", "file_id"),
    CardTargetKind.HUE_LIGHT: ("light_id",),
}
assert set(_IDENTIFIERS) == set(CardTargetKind)


def _text(data: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _event_day(start: object, timezone: str) -> str | None:
    if not isinstance(start, dict):
        return None
    day = start.get("date")
    if isinstance(day, str):
        return day
    instant = parse_provider_datetime(start)
    if instant is None:
        return None
    try:
        return instant.astimezone(ZoneInfo(timezone)).date().isoformat()
    except ValueError, ZoneInfoNotFoundError, OverflowError:
        return None


def _target(item: RegistryItem, kind: CardTargetKind, timezone: str) -> CardToolTarget:
    data = item.payload
    container = None
    if kind == CardTargetKind.EVENT:
        container = _text(data, "calendar_id")
    elif kind == CardTargetKind.TASK:
        container = _text(data, "tasklist_id")
    elif kind == CardTargetKind.EMAIL:
        container = _text(data, "mail_folder")
    return CardToolTarget(
        kind=kind,
        item_id=_text(data, *_IDENTIFIERS[kind]) or "",
        container_id=container,
        day=_event_day(data.get("start"), timezone) if kind == CardTargetKind.EVENT else None,
        is_folder=(
            kind == CardTargetKind.FILE
            and data.get("mimeType") == "application/vnd.google-apps.folder"
        ),
    )


def stamp_card_targets(
    output: UnifiedToolOutput,
    *,
    client: object,
    provider: ConnectorType,
    user_id: UUID,
    timezone: str,
) -> UnifiedToolOutput:
    """Keep source-bound destinations outside every model-facing data payload.

    Missing scope or source proof leaves a readable historical card; no current
    provider, default container, registry-id suffix or public URL substitutes it.
    """
    binding = content_source_binding(client)
    for item in output.registry_updates.values():
        kind = _KINDS.get(item.type)
        if kind is None:
            continue
        display = {
            key: value for key, value in item.meta.display.items() if key != CARD_TARGET_FIELD
        }
        display[CARD_KIND_FIELD] = kind.value
        if binding and output.success:
            try:
                envelope = SignedCardTarget(
                    target=_target(item, kind, timezone), provider=provider, source_binding=binding
                )
                display[CARD_TARGET_FIELD] = sign_card_target(envelope, user_id)
            except ValidationError:
                # An unaddressable item remains complete, without an unsafe link.
                display.pop(CARD_TARGET_FIELD, None)
        item.meta.display = display
    return output
