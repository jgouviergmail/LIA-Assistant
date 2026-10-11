"""Typed manual-management mappings reuse the source repository's business defaults."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.interests.management_schemas import InterestConfiguration
from src.domains.interests.models import InterestCategory, UserInterest
from src.domains.interests.repository import InterestRepository
from src.domains.interests.schemas import InterestCreate, InterestUpdate
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.models import User
from src.domains.users.repository import UserRepository


async def lock_interest_actor(db: AsyncSession, actor_id: UUID) -> User:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise ResourceNotFoundError("user", actor_id)
    return actor


async def get_managed_interest(
    db: AsyncSession, actor_id: UUID, interest_id: UUID, *, lock: bool = False
) -> UserInterest:
    query = (
        select(UserInterest)
        .where(UserInterest.user_id == actor_id, UserInterest.id == interest_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        await lock_interest_actor(db, actor_id)
        query = query.with_for_update()
    row = await db.scalar(query)
    if row is None:
        raise ResourceNotFoundError("interest", interest_id)
    return row


def preview_interest_update(row: UserInterest, data: InterestUpdate) -> InterestConfiguration:
    """One source mapping owns UI and native sparse edits; UI null means omitted."""
    configuration = InterestConfiguration(
        topic=row.topic,
        category=InterestCategory(row.category),
        positive_signals=row.positive_signals,
        negative_signals=row.negative_signals,
    ).model_dump()
    changes = InterestUpdate.model_validate(data.model_dump(exclude_unset=True)).model_dump(
        exclude_unset=True, exclude_none=True
    )
    return InterestConfiguration.model_validate({**configuration, **changes})


def require_interest_snapshot(
    row: UserInterest, expected: InterestConfiguration, status: str, subject: str | None
) -> None:
    if (
        preview_interest_update(row, InterestUpdate()) != expected
        or row.status != status
        or row.subject != subject
    ):
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})


async def delete_managed_interest(
    db: AsyncSession,
    actor_id: UUID,
    interest_id: UUID,
    *,
    expected: InterestConfiguration | None = None,
    expected_status: str | None = None,
    expected_subject: str | None = None,
) -> None:
    row = await get_managed_interest(db, actor_id, interest_id, lock=True)
    if expected is not None:
        assert expected_status is not None
        require_interest_snapshot(row, expected, expected_status, expected_subject)
    actor = await lock_interest_actor(db, actor_id)
    invalidate_extractions(actor)
    await InterestRepository(db).delete(row)
    await db.flush()


async def delete_all_managed_interests(db: AsyncSession, actor_id: UUID) -> int:
    actor = await lock_interest_actor(db, actor_id)
    removed = await InterestRepository(db).delete_all_for_user(actor_id)
    if removed:
        invalidate_extractions(actor)
        await db.flush()
    return removed


async def require_available_interest_configuration(
    db: AsyncSession, row: UserInterest, configuration: InterestConfiguration
) -> None:
    assert configuration.topic is not None and configuration.category is not None
    other = await InterestRepository(db).get_by_user_topic_category(
        row.user_id, configuration.topic, configuration.category.value
    )
    if other is not None and other.id != row.id:
        raise ResourceConflictError("interest", detail={"error_code": "STALE_STATE"})


async def update_managed_interest(
    db: AsyncSession,
    actor_id: UUID,
    row: UserInterest,
    data: InterestUpdate,
    *,
    embedding: list[float] | None,
    expected: InterestConfiguration,
    expected_status: str,
    expected_subject: str | None,
) -> tuple[UserInterest, bool]:
    """The caller supplies precomputed vectors; account then interest locks fence writes."""
    current = await get_managed_interest(db, actor_id, row.id, lock=True)
    previous = preview_interest_update(current, InterestUpdate())
    require_interest_snapshot(current, expected, expected_status, expected_subject)
    configuration = preview_interest_update(current, data)
    if configuration == previous:
        return current, True
    await require_available_interest_configuration(db, current, configuration)
    actor = await lock_interest_actor(db, actor_id)
    invalidate_extractions(actor)
    if configuration.topic != previous.topic:
        # Failed best-effort regeneration must not retain a vector for the former topic.
        current.embedding = embedding
    assert configuration.category is not None
    await InterestRepository(db).update(
        current,
        topic=configuration.topic,
        category=configuration.category.value,
        positive_signals=configuration.positive_signals,
        negative_signals=configuration.negative_signals,
    )
    return current, False


async def create_managed_interest(
    db: AsyncSession,
    user_id: UUID,
    data: InterestCreate,
    *,
    embedding: list[float] | None,
    interest_id: UUID | None = None,
) -> UserInterest:
    configuration = InterestCreate.model_validate(data.model_dump())
    actor = await lock_interest_actor(db, user_id)
    invalidate_extractions(actor)
    return await InterestRepository(db).create(
        user_id=user_id,
        topic=configuration.topic,
        category=configuration.category.value,
        embedding=embedding,
        interest_id=interest_id,
    )
