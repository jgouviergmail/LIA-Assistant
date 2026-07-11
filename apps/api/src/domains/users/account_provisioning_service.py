"""Account provisioning service — cross-domain defaults for new users.

Counterpart of ``AccountDeletionService`` for the *creation* side of the
account lifecycle: provisions the defaults every new user needs across
domains (skill activation states, usage limits). Called by the auth domain
right after the user row is created (email/password registration and OAuth
user creation), so that auth stays an identity/session domain and the
lifecycle cascade lives in the users domain (ADR-126).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings


class AccountProvisioningService:
    """Provisions cross-domain default records for newly created accounts.

    Args:
        db: SQLAlchemy async session shared with the calling transaction.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def provision_new_user(self, user_id: UUID, *, commit_per_step: bool = False) -> None:
        """Provision default cross-domain records for a new user.

        Behavior-preserving extraction from the auth service (ADR-126): the
        two historical call sites had different transaction topologies, so
        the caller chooses it explicitly instead of this service imposing
        one.

        Args:
            user_id: Newly created user UUID.
            commit_per_step: When True, commit after each provisioning step
                (email/password registration flow). When False, leave the
                commit to the caller (OAuth creation flow, single commit at
                the end of the callback).
        """
        # Provision skill states (all admin-enabled system skills).
        # Imported lazily so tests patching the source classes keep working
        # and no cross-domain import happens at module load.
        from src.domains.skills.preference_service import SkillPreferenceService

        skill_svc = SkillPreferenceService(self.db)
        await skill_svc.ensure_user_skills(user_id)
        if commit_per_step:
            await self.db.commit()

        # Create default usage limits (feature-flagged subsystem)
        if getattr(settings, "usage_limits_enabled", False):
            from src.domains.usage_limits.service import UsageLimitService

            limit_svc = UsageLimitService(self.db)
            await limit_svc.create_default_limits(user_id)
            if commit_per_step:
                await self.db.commit()
