"""Live reflex owner behind the injected application-settings port."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.live.preference_commands import live_preference_snapshot, update_live_preferences
from src.domains.live.preferences import LivePreferences
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.live_preferences import LivePreferenceSnapshot, LiveReflexValues


def assert_live_preference_coverage() -> None:
    if set(LivePreferences.model_fields) != set(LiveReflexValues.model_fields) | {"provider"}:
        raise AssertionError("New live preference fields require explicit projection review")


assert_live_preference_coverage()


class SavedLivePreferences:
    async def read(self, db: AsyncSession, actor_id: UUID) -> LivePreferenceSnapshot:
        actor: User | None = await db.scalar(
            select(User).where(User.id == actor_id).execution_options(populate_existing=True)
        )
        if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        return live_preference_snapshot(actor)

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        values: LiveReflexValues,
        *,
        expected: LivePreferenceSnapshot,
        receipt: PreferenceWriteReceipt,
    ) -> None:
        await update_live_preferences(
            db, actor_id, LivePreferences(**values.model_dump()), expected=expected, receipt=receipt
        )
