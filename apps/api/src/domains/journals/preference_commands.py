"""Source UI and confirmed native journal preferences share one owner settlement."""

from collections.abc import Awaitable, Callable, Mapping
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError, raise_user_not_found
from src.domains.journals.lifecycle import mark_journal_changed
from src.domains.journals.management_projection import build_journal_settings
from src.domains.journals.schemas import JournalSettingsResponse, JournalSettingsUpdate
from src.domains.journals.service import JournalService
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.models import User
from src.domains.users.preference_cas import (
    PreferenceWriteReceipt,
    check_expected_preferences,
    verified_preference_noop,
)
from src.domains.users.repository import UserRepository

JOURNAL_SETTING_FIELDS = frozenset(JournalSettingsUpdate.model_fields)
JOURNAL_PORTRAIT_SETTING_FIELDS = frozenset(
    {
        "journals_enabled",
        "journal_consolidation_with_history",
        "journal_max_total_chars",
        "journal_max_entry_chars",
    }
)


class JournalSettingsCompletionUnknown(RuntimeError):
    """No acknowledgement means no assertion of completion."""


async def _observe_noop(
    actor: User,
    service: JournalService,
    current: dict[str, JsonValue],
    receipt: PreferenceWriteReceipt | None,
    check: Callable[[], Awaitable[None]] | None,
) -> JournalSettingsResponse:
    observed = await build_journal_settings(actor, service, portrait_invalidated=False)
    if check is not None:
        await check()
    if receipt is not None:
        receipt.committed = True
        receipt.no_op = True
        receipt.values = current
    return observed


def _record_committed_settings(
    receipt: PreferenceWriteReceipt | None,
    observed: JournalSettingsResponse,
    patch: JournalSettingsUpdate,
) -> None:
    if receipt is not None:
        receipt.committed = True
        receipt.values = {name: getattr(observed, name) for name in patch.model_fields_set}


async def _validate_storage_budget(
    service: JournalService, actor_id: UUID, changed: dict[str, JsonValue]
) -> None:
    if "journal_max_total_chars" not in changed:
        return
    maximum = changed["journal_max_total_chars"]
    if not isinstance(maximum, int) or isinstance(maximum, bool):
        raise ValueError("Journal storage budget must be an explicit integer")
    if maximum < await service.repo.get_total_chars(actor_id):
        raise ValidationError(
            detail="Cannot set max_total_chars below current usage; delete entries first."
        )


async def update_journal_preferences(
    db: AsyncSession,
    actor_id: UUID,
    data: JournalSettingsUpdate,
    *,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> JournalSettingsResponse:
    # Preserve the management route's legacy empty/null-as-omitted convention.
    patch = JournalSettingsUpdate.model_validate(
        data.model_dump(exclude_unset=True, exclude_none=True)
    )
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise_user_not_found(actor_id)
    assert actor is not None
    if check is not None:
        await check()
    if expected is not None:
        check_expected_preferences(actor, patch, expected)
    current = {name: getattr(actor, name) for name in patch.model_fields_set}
    service = JournalService(db)
    if verified_preference_noop(patch, current, None):
        return await _observe_noop(actor, service, current, receipt, check)
    changed = {
        name: value
        for name, value in patch.model_dump(exclude_unset=True).items()
        if getattr(actor, name) != value
    }
    await _validate_storage_budget(service, actor_id, changed)
    invalidated = bool(changed.keys() & JOURNAL_PORTRAIT_SETTING_FIELDS)
    invalidate_extractions(actor)
    for name, value in changed.items():
        setattr(actor, name, value)
    await db.flush()
    if invalidated:
        await mark_journal_changed(db, actor_id)
    await db.refresh(actor)
    observed = await build_journal_settings(actor, service, portrait_invalidated=invalidated)
    if check is not None:
        await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise JournalSettingsCompletionUnknown from exc
    _record_committed_settings(receipt, observed, patch)
    return observed
