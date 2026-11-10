"""Enrich SSE completion after accounting closes; this creates no archived row."""

from typing import Any
from uuid import UUID

from src.domains.agents.api.archive_metadata import (
    with_archived_message_ids,
    with_performed_effects,
)
from src.domains.agents.services.streaming.followup_metadata import (
    TurnExtras,
    with_followup_suggestions,
    with_habit_proposal,
    with_initiative_motivation,
)


def with_done_enrichments(
    base: dict[str, Any],
    *,
    user_message_id: UUID | None,
    assistant_message_id: UUID | None,
    extras: TurnExtras,
    effects: list[dict[str, Any]] | None,
    card_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Attach delivered facts to the existing consolidated accounting summary.

    Args:
        base: The accounting summary of the turn.
        user_message_id: The archived question, when it was archived.
        assistant_message_id: The archived answer, when it was archived.
        extras: What the run handed its stream besides the answer: the same
            values the archived answer carries.
        effects: What the turn performed (ADR-263), when anything.
        card_metadata: The delivered card snapshot.

    Returns:
        The ``done`` chunk's metadata (a new dict).
    """
    metadata = with_archived_message_ids(
        base, user_message_id=user_message_id, assistant_message_id=assistant_message_id
    )
    metadata = with_followup_suggestions(metadata, extras.followups)
    metadata = with_performed_effects(metadata, effects)
    metadata = {**metadata, **card_metadata}
    metadata = with_initiative_motivation(metadata, extras.motivation)
    return with_habit_proposal(metadata, extras.habit_proposal)
