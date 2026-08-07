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

        # Lend the instance's shared search key (public demonstrator only).
        # No-op elsewhere; never raises — a broken search is worth less than a
        # broken sign-up.
        from src.domains.users.demo_search_provisioning import provision_shared_search

        # No commit of its own: `db.add` only stages the row, and the next
        # step (or the caller) commits it. One round-trip less, and the
        # existing commit contract stays exactly as it was.
        await provision_shared_search(self.db, user_id)

        # Start the account with the demonstrator's own preferences (debug
        # panel on — showing the reasoning IS the demonstration). No-op
        # elsewhere; never raises, for the same reason as the step above.
        from src.domains.users import demo_account_preferences

        await demo_account_preferences.apply_demo_account_preferences(self.db, user_id)

        # Create default usage limits (feature-flagged subsystem)
        if getattr(settings, "usage_limits_enabled", False):
            from src.domains.usage_limits.service import UsageLimitService

            limit_svc = UsageLimitService(self.db)
            await limit_svc.create_default_limits(user_id)
            if commit_per_step:
                await self.db.commit()
