"""Native qualification for selected CRM rows, on the same bounded source evidence."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.core.content_classification import ContentClassification
from src.core.content_source import content_source_binding
from src.domains.shared.content_qualification import qualify_selected
from src.domains.users.models import User
from src.domains.users.preferences_cache import UserPreferencesCache
from src.infrastructure.database.session import get_db_context


@dataclass(frozen=True)
class ClassificationSource:
    provider: str
    binding: str
    container: str = ""


def capture_source(client: object, provider: object, container: str = "") -> ClassificationSource:
    name = getattr(provider, "value", provider)
    return ClassificationSource(
        name if isinstance(name, str) else "", content_source_binding(client), container
    )


async def qualify_rows(
    records: Sequence[Mapping[str, object]],
    *,
    source: ClassificationSource,
    user_id: UUID,
    kind: Literal["email", "event"],
) -> dict[str, ContentClassification]:
    if not source.binding or not source.provider or not records:
        return {}
    cached = UserPreferencesCache.get(str(user_id))
    if cached is not None:
        timezone = cached[0]
    else:
        try:
            async with get_db_context() as db:
                timezone = await db.scalar(select(User.timezone).where(User.id == user_id)) or "UTC"
        except SQLAlchemyError, TimeoutError:
            return {}
    return await qualify_selected(
        records=records,
        kind=kind,
        user_id=user_id,
        provider=source.provider,
        binding=source.binding,
        timezone=timezone,
        container=source.container,
    )
