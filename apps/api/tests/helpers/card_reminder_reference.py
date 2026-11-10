"""Fictional reminder using the list tool's schema and canonical formatters."""

from datetime import UTC, date, datetime
from uuid import UUID

from src.core.recurrence import describe, recurrence_from_parameters
from src.core.time_utils import format_datetime_for_display
from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType


def reminder_reference_domains(language: str) -> dict[str, dict[str, object]]:
    """Return a persisted reminder card without calling a tool, database or provider.

    ``list_reminders_tool`` builds its registry inline; this mirrors that exact
    payload and uses its date and recurrence formatters, then the JSON boundary.
    """
    trigger = datetime(2027, 11, 8, 8, 30, tzinfo=UTC)
    created = datetime(2027, 11, 1, 13, 15, tzinfo=UTC)
    zone = "Europe/Paris"
    schedule = recurrence_from_parameters(
        repeat="weekly", today=date(2027, 11, 1), times=["09:30"], weekdays=[1, 4]
    )
    item = RegistryItem(
        id="reminder_reference-garden",
        type=RegistryItemType.REMINDER,
        payload={
            "id": str(UUID(int=71)),
            "content": (
                "Préparer la visite du jardin : confirmer les accès, relire le plan, "
                "prévenir les bénévoles et apporter le carnet des plantations. "
                "Vérifier aussi les horaires de chacun et les clés de la verrière. "
                "REMINDER_COMPLETE_CONTENT."
            ),
            "trigger_at": trigger.isoformat(),
            "trigger_at_formatted": format_datetime_for_display(
                trigger, user_timezone=zone, locale=language
            ),
            "created_at": created.isoformat(),
            "created_at_formatted": format_datetime_for_display(
                created, user_timezone=zone, locale=language
            ),
            "schedule_human": describe(schedule, language),
            "schedule_timezone": zone,
            "status": "pending",
        },
        meta=RegistryItemMeta(
            source="reminders", domain="reminders", tool_name="list_reminders_tool"
        ),
    )
    restored = RegistryItem.model_validate_json(item.model_dump_json())
    return {"reminders": {"reminders": [card_payload(restored)]}}
