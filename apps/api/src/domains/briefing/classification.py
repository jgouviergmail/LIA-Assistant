"""Enrich only the selected briefing entities; no additional provider read."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from src.domains.agents.services.qualification.publication import classify_selected
from src.domains.briefing.schemas import AgendaData, CardSection, MailsData


async def classify_briefing_items(
    records: Sequence[Mapping[str, object]],
    *,
    kind: Literal["email", "event"],
    user_id: UUID,
    provider: str,
    binding: str,
    timezone: str,
    container: str = "",
) -> list[dict[str, object]]:
    annotations = await classify_selected(
        records=records,
        kind=kind,
        user_id=user_id,
        provider=provider,
        binding=binding,
        timezone=timezone,
        container=container,
    )
    result = []
    for index, record in enumerate(records):
        item = {key: value for key, value in record.items() if key != "classification"}
        if annotation := annotations.get(str(index)):
            item["classification"] = annotation.model_dump(mode="json")
        result.append(item)
    return result


def expire_cached_annotations(section: CardSection) -> CardSection:
    """The stale-data fallback may keep source facts, never an expired urgency."""
    now = datetime.now(UTC)
    data = section.data
    if isinstance(data, AgendaData):
        data = data.model_copy(
            update={
                "events": [
                    (
                        item.model_copy(update={"classification": None})
                        if item.classification is not None
                        and item.classification.valid_until <= now
                        else item
                    )
                    for item in data.events
                ]
            }
        )
    elif isinstance(data, MailsData):
        data = data.model_copy(
            update={
                "items": [
                    (
                        item.model_copy(update={"classification": None})
                        if item.classification is not None
                        and item.classification.valid_until <= now
                        else item
                    )
                    for item in data.items
                ]
            }
        )
    return section.model_copy(update={"data": data})
