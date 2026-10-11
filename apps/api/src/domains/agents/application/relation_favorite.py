"""An exact approved favorite cannot drift to another grouped display identity."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.relation_favorite_schemas import (
    RelationFavoritePatch,
    RelationFavoriteRequest,
    RelationFavoriteValues,
)
from src.domains.agents.application.relation_favorite_spec import RELATION_FAVORITE_OPERATION
from src.domains.relations.favorite_commands import (
    RelationFavoriteCompletionUnknown,
    read_relation_favorite,
    set_managed_relation_favorite,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_relation_favorite(
    db: AsyncSession,
    actor_id: UUID,
    request: RelationFavoriteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = RelationFavoriteRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    expected = await read_relation_favorite(db, actor_id, selected.name)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        RELATION_FAVORITE_OPERATION,
        RelationFavoritePatch(
            relation_favorite=RelationFavoriteValues(expected=expected, starred=selected.starred)
        ),
        {"relation_favorite": expected.public_scope()},
        {"relation_favorite": {**expected.public_scope(), "starred": selected.starred}},
        command_id=command_id,
    )


def canonical_relation_favorite(draft: ApplicationActionDraftContent) -> bool:
    selected = RelationFavoritePatch.model_validate(draft.intent).relation_favorite
    return draft.before == {
        "relation_favorite": selected.expected.public_scope()
    } and draft.after == {
        "relation_favorite": {**selected.expected.public_scope(), "starred": selected.starred}
    }


async def execute_relation_favorite(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "relation_favorite.update":
        raise CommandRejected("FORBIDDEN")
    if not canonical_relation_favorite(draft):
        raise ValueError("Favorite requires exact approved source identity and state")
    selected = RelationFavoritePatch.model_validate(draft.intent).relation_favorite

    async def check() -> None:
        await require_application_tools(db)
        await load_actor(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    try:
        await set_managed_relation_favorite(
            db, actor_id, selected.expected, selected.starred, receipt, check
        )
    except RelationFavoriteCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
