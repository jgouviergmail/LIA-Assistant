"""Source-owned snapshots and exact server-enforced human confirmation."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, JsonValue, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.discussion_schemas import (
    DiscussionPreferencesIntent,
    DiscussionPurgeIntent,
    DiscussionRebuildIntent,
    DiscussionUseIntent,
)
from src.domains.agents.application.discussion_specs import DISCUSSION_SPECS
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.effects.draft_approval import valid_draft_approval
from src.domains.agents.effects.scope import current_scope
from src.domains.proactive_discussions.context_store.models import (
    ContextExclusionRecord,
    ContextItemRecord,
)
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.policy_repository import DiscussionPolicyRepository
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.proactive.discussion_rebuild import kick_context_rebuild

_JSON = TypeAdapter(dict[str, JsonValue])


async def discussion_snapshot(
    db: AsyncSession, owner: UUID, operation: str, intent: BaseModel
) -> dict[str, JsonValue]:
    """Read, from the source itself, what an action's confirmation shows and rechecks.

    A preference change shows the current policy; a context action shows the
    epoch, generation and item count, plus what it touches: the item and whether it
    is usable, or the selected items and what a purge would remove.

    Args:
        db: The session to read with.
        owner: The account.
        operation: The operation id.
        intent: The validated intent.

    Returns:
        The snapshot, keyed by the intent's field.

    Raises:
        AuthorizationError: The application tools are switched off.
        CommandRejected: An item is not the account's
            (``NOT_FOUND_OR_UNAUTHORIZED``).
    """
    await require_application_tools(db)
    policy = await DiscussionPolicyRepository(db).get_policy(owner)
    if isinstance(intent, DiscussionPreferencesIntent):
        return {"discussion_preferences": policy.model_dump(mode="json")}
    repo = ContextRepository(db)
    state = await repo.read_generation(owner, now=datetime.now(UTC), limit=1)
    value: dict[str, JsonValue] = {
        "epoch": state.context_epoch,
        "generation": state.generation,
        "count": state.total,
    }
    if isinstance(intent, DiscussionPurgeIntent):
        preview = await repo.preview_purge(
            owner,
            selection=intent.discussion_context_purge.selection,
            expected_epoch=state.context_epoch,
            expected_generation=state.generation,
            now=datetime.now(UTC),
        )
        value["affected_count"] = preview.affected_count
    if isinstance(intent, DiscussionUseIntent):
        selected = intent.discussion_context_use
        row = await db.scalar(
            select(ContextItemRecord).where(
                ContextItemRecord.user_id == owner, ContextItemRecord.id == selected.item_id
            )
        )
        marker = await db.scalar(
            select(ContextExclusionRecord.id)
            .where(
                ContextExclusionRecord.user_id == owner,
                ContextExclusionRecord.item_id == selected.item_id,
            )
            .limit(1)
        )
        if row is None and (not selected.usable or marker is None):
            raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
        value.update(
            {
                "item_id": str(selected.item_id),
                "revision": row.revision if row else None,
                "currently_usable": marker is None,
                "summary": str(row.data["summary"]) if row else None,
            }
        )
    elif (
        isinstance(intent, DiscussionPurgeIntent)
        and intent.discussion_context_purge.selection is not None
    ):
        selection = intent.discussion_context_purge.selection
        rows = (
            (
                await db.execute(
                    select(ContextItemRecord.id, ContextItemRecord.data)
                    .where(ContextItemRecord.user_id == owner, ContextItemRecord.id.in_(selection))
                    .order_by(ContextItemRecord.id)
                )
            )
            .tuples()
            .all()
        )
        if len(rows) != len(set(selection)):
            raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
        value.update(
            {
                "selection": [str(key) for key, _ in rows],
                "count": len(rows),
                "summaries": [str(data["summary"]) for _, data in rows],
            }
        )
    field = next(iter(intent.model_fields_set))
    return {field: value}


async def prepare_discussion_action(
    db: AsyncSession,
    owner: UUID,
    intent: BaseModel,
    *,
    operation: str,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    """Prepare the exact confirmation a discussion action needs before it runs.

    Args:
        db: The session to read with.
        owner: The account.
        intent: The requested action.
        operation: The operation id.
        command_id: The pending command this draft replaces, when edited.

    Returns:
        The draft: the intent, the source snapshot and their digests.

    Raises:
        ValueError: A preference change names no field.
        CommandRejected: An item is not the account's.
    """
    spec = DISCUSSION_SPECS[operation]
    desired = spec.input_model.model_validate(intent)
    if (
        isinstance(desired, DiscussionPreferencesIntent)
        and not desired.discussion_preferences.model_fields_set
    ):
        raise ValueError("explicit preference change required")
    before = await discussion_snapshot(db, owner, operation, desired)
    return build_action_content(
        owner,
        spec,
        desired,
        before,
        _JSON.validate_python(desired.model_dump(mode="json", exclude_unset=True)),
        command_id=command_id,
    )


def require_discussion_approval(owner: UUID, draft: ApplicationActionDraftContent) -> None:
    """Refuse to run a draft the person did not approve exactly as shown.

    The approval must belong to this run's scope and actor, the draft must rest on
    the current schema, be unexpired and keep its digests intact.

    Args:
        owner: The account running the action.
        draft: The approved draft.

    Raises:
        CommandRejected: ``CONFIRMATION_MISSING``, ``FORBIDDEN``, ``SCHEMA_CHANGED``,
            ``EXPIRED`` or ``INVALID_DRAFT``.
    """
    scope = current_scope()
    if scope is None or not valid_draft_approval(scope, draft.model_dump(mode="json")):
        raise CommandRejected("CONFIRMATION_MISSING")
    if draft.actor_id != owner:
        raise CommandRejected("FORBIDDEN")
    spec = DISCUSSION_SPECS.get(draft.operation_id)
    if (
        spec is None
        or draft.schema_fingerprint != payload_digest(spec.input_model.model_json_schema())
        or draft.schema_version != spec.version
    ):
        raise CommandRejected("SCHEMA_CHANGED")
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    if draft.after != draft.intent or draft.expected_digest != payload_digest(draft.before):
        raise CommandRejected("INVALID_DRAFT")


async def execute_discussion_action(
    db: AsyncSession,
    owner: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    """Run an approved discussion action exactly as it was shown.

    The source state is read again and must equal the approved snapshot; the action
    is applied, the approval checked once more, and the transaction committed
    before a requested rebuild starts in the background.

    Args:
        db: The session to write with.
        owner: The account.
        draft: The approved draft.
        receipt: Filled with the committed values.

    Raises:
        CommandRejected: The approval is invalid, or the state changed since it was
            shown (``STALE_STATE``).
    """
    require_discussion_approval(owner, draft)
    selected = DISCUSSION_SPECS[draft.operation_id].input_model.model_validate(draft.intent)
    current = await discussion_snapshot(db, owner, draft.operation_id, selected)
    if current != draft.before:
        raise CommandRejected("STALE_STATE")
    now = datetime.now(UTC)
    rebuild_epoch = None
    repo = ContextRepository(db)
    value = next(iter(current.values()))
    if not isinstance(value, dict):
        raise CommandRejected("INVALID_DRAFT")
    if isinstance(selected, DiscussionPreferencesIntent):
        await DiscussionPolicyRepository(db).update_policy(
            owner, selected.discussion_preferences, expected_revision=_integer(value["revision"])
        )
    else:
        epoch = _integer(value["epoch"])
        if isinstance(selected, DiscussionUseIntent):
            use = selected.discussion_context_use
            revision = value["revision"]
            await repo.set_usable(
                owner,
                use.item_id,
                usable=use.usable,
                expected_revision=_integer(revision) if revision is not None else None,
                expected_epoch=epoch,
                now=now,
            )
        elif isinstance(selected, DiscussionPurgeIntent):
            await repo.purge(
                owner,
                selection=selected.discussion_context_purge.selection,
                expected_epoch=epoch,
                expected_generation=_integer(value["generation"]),
                now=now,
            )
        elif isinstance(selected, DiscussionRebuildIntent):
            rebuilt = await repo.request_rebuild(owner, expected_epoch=epoch, now=now)
            rebuild_epoch = rebuilt.context_epoch
        else:
            raise CommandRejected("INVALID_DRAFT")
    require_discussion_approval(owner, draft)
    await db.commit()
    if rebuild_epoch is not None:
        kick_context_rebuild(owner, rebuild_epoch)
    receipt.committed = True
    receipt.values = draft.after


def _integer(value: JsonValue) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CommandRejected("INVALID_DRAFT")
    return value
