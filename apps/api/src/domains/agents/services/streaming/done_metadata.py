"""Enrich SSE completion after accounting closes; this creates no archived row."""

from uuid import UUID

from src.core.field_names import FIELD_FOLLOWUP_SUGGESTIONS
from src.domains.agents.api.archive_metadata import (
    with_archived_message_ids,
    with_performed_effects,
)
from src.domains.agents.services.streaming.followup_metadata import with_initiative_motivation


def with_done_enrichments(
    base: dict[str, object],
    *,
    user_message_id: UUID | None,
    assistant_message_id: UUID | None,
    followup_suggestions: list[str] | None,
    effects: list[dict[str, object]] | None,
    card_metadata: dict[str, object],
    initiative_motivation: str | None,
) -> dict[str, object]:
    """Attach delivered facts to the existing consolidated accounting summary."""
    metadata = with_archived_message_ids(
        base, user_message_id=user_message_id, assistant_message_id=assistant_message_id
    )
    if followup_suggestions:
        metadata = {**metadata, FIELD_FOLLOWUP_SUGGESTIONS: followup_suggestions}
    metadata = with_performed_effects(metadata, effects)
    metadata = {**metadata, **card_metadata}
    return with_initiative_motivation(metadata, initiative_motivation)
