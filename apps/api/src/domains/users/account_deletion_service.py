"""Account deletion service — orchestrates user data purge with billing preservation.

Implements the "Deleted" step in the account lifecycle:
    Active → Deactivated → **Deleted** → Erased (GDPR)

The service purges ALL personal data while preserving the user row (email,
full_name) and billing tables (token_usage_logs, user_statistics,
google_api_usage_logs, message_token_summary) for dispute resolution.

Preconditions:
    - User must be deactivated (is_active=False) before deletion.
    - User must not be a superuser.
    - User must not already be deleted.

Created: 2026-03-31
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, raise_user_not_found
from src.domains.attachments.models import Attachment
from src.domains.auth.models import User
from src.domains.channels.models import UserChannelBinding
from src.domains.connectors.models import (
    Connector,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.conversations.models import (
    Conversation,
    ConversationAuditLog,
    ConversationMessage,
)
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.journals.models import JournalEntry
from src.domains.memories.models import Memory
from src.domains.notifications.models import UserBroadcastRead, UserFCMToken
from src.domains.rag_spaces.models import RAGSpace
from src.domains.reminders.models import Reminder
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.skills.models import Skill, UserSkillState
from src.domains.sub_agents.models import SubAgent
from src.domains.usage_limits.models import UserUsageLimit
from src.domains.user_mcp.models import UserMCPServer
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from fastapi import Request

logger = get_logger(__name__)


class AccountDeletionService:
    """Orchestrates user account deletion with billing history preservation.

    Purges all personal data across 20+ tables, external services (OAuth, Redis,
    MCP pool, LangGraph), and physical files — while preserving billing tables
    and the user row for dispute resolution.

    Args:
        db: SQLAlchemy async session (transaction boundary).
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def delete_account(
        self,
        user_id: UUID,
        admin_user_id: UUID,
        reason: str | None = None,
        request: Request | None = None,
    ) -> tuple[User, dict[str, int]]:
        """Delete a user account: purge all personal data, preserve billing.

        This is an irreversible operation. The user row is kept (email, full_name
        preserved for billing contact) but all personal data is permanently deleted.

        Args:
            user_id: Target user UUID.
            admin_user_id: Admin performing the deletion.
            reason: Optional human-readable reason for deletion.
            request: FastAPI request for audit metadata.

        Returns:
            Tuple of (updated User with deleted_at set, dict of table → deleted row count).

        Raises:
            HTTPException 404: User not found.
            HTTPException 409: User is active (must be deactivated first),
                already deleted, or is a superuser.
        """
        counts: dict[str, int] = {}

        # =====================================================================
        # STEP 0 — Validate and lock
        # =====================================================================
        user = await self._load_and_validate_user(user_id)
        conversation = await self._load_conversation(user_id)

        # =====================================================================
        # STEP 1 — External services cleanup (best-effort, non-transactional)
        # NOTE: These operations are NOT rollbackable. If the DB commit below
        # fails, OAuth tokens are already revoked, Redis caches already cleared,
        # and files already deleted. This is acceptable because:
        # - User is already deactivated (precondition) so tokens are useless
        # - Redis caches have TTLs and self-heal
        # - File deletion is idempotent (missing files are harmless)
        # =====================================================================
        await self._revoke_all_oauth_tokens(user_id)
        await self._disconnect_mcp_pool(user_id)
        await self._invalidate_redis_sessions(user_id)
        await self._cleanup_redis_caches(user_id)

        # =====================================================================
        # STEP 1b — Physical file cleanup (before DB row deletion)
        # =====================================================================
        counts["attachment_files"] = self._cleanup_attachment_files(user_id)
        counts["rag_files"] = self._cleanup_rag_files(user_id)

        # =====================================================================
        # STEP 2 — PostgreSQL data purge (single transaction)
        # =====================================================================

        # 2a. LangGraph checkpoints
        if conversation:
            await self._purge_langgraph_checkpoints(conversation.id)

        # 2b. LangGraph Store (tool contexts, memories, heartbeat context)
        counts["store_items"] = await self._purge_langgraph_store(user_id)

        # 2c. Deactivate all connectors
        counts["connectors_deactivated"] = await self._deactivate_connectors(user_id)

        # 2d. Purge personal data tables (FK-safe order)
        table_counts = await self._purge_user_data_tables(user_id)
        counts.update(table_counts)

        # 2e. Mark user as deleted (scrub PII, keep email/name)
        await self._mark_user_deleted(user, reason)

        # 2f. Create audit log
        await self._create_audit_log(user, admin_user_id, reason, counts, request)

        # 2g. Invalidate usage limit cache
        await self._invalidate_usage_limit_cache(user_id)

        # 2h. Commit
        await self.db.commit()

        logger.warning(
            "account_deleted",
            user_id=str(user_id),
            email=user.email,
            admin_user_id=str(admin_user_id),
            reason=reason,
            counts=counts,
        )

        return user, counts

    # =========================================================================
    # STEP 0 — Validation
    # =========================================================================

    async def _load_and_validate_user(self, user_id: UUID) -> User:
        """Load user with FOR UPDATE lock and validate preconditions.

        Args:
            user_id: User UUID.

        Returns:
            Locked User instance.

        Raises:
            HTTPException 404: User not found.
            HTTPException 409: Precondition violated.
        """
        result = await self.db.execute(select(User).where(User.id == user_id).with_for_update())
        user = result.scalar_one_or_none()

        if not user:
            raise_user_not_found(user_id)
        assert user is not None  # Type narrowing after exception

        if user.is_superuser:
            raise ResourceConflictError(
                resource_type="user",
                detail="Cannot delete superuser accounts.",
            )

        if user.is_active:
            raise ResourceConflictError(
                resource_type="user",
                detail="User must be deactivated before deletion. "
                "Use PATCH /users/admin/{user_id}/activation first.",
            )

        if user.is_deleted:
            raise ResourceConflictError(
                resource_type="user",
                detail="User account is already deleted.",
            )

        return user

    async def _load_conversation(self, user_id: UUID) -> Conversation | None:
        """Load user's conversation (may not exist if user never chatted).

        Args:
            user_id: User UUID.

        Returns:
            Conversation or None.
        """
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # STEP 1 — External services cleanup
    # =========================================================================

    async def _revoke_all_oauth_tokens(self, user_id: UUID) -> None:
        """Revoke OAuth tokens grouped by provider family (best-effort).

        For account deletion, all connectors are being removed so we force
        revocation regardless of the "other active connectors" check.

        Args:
            user_id: User UUID.
        """
        try:
            import httpx

            from src.core.security.utils import decrypt_data
            from src.domains.connectors.schemas import ConnectorCredentials

            result = await self.db.execute(
                select(Connector).where(
                    Connector.user_id == user_id,
                    Connector.connector_type.in_(ConnectorType.get_oauth_types()),
                    Connector.credentials_encrypted.isnot(None),
                )
            )
            connectors = list(result.scalars().all())

            if not connectors:
                return

            # Revoke Google OAuth grant once (all Google connectors share the same grant).
            # Apple uses app-specific passwords (no revocation endpoint).
            # Microsoft has no revocation endpoint.
            google_connector = next((c for c in connectors if c.connector_type.is_google), None)
            if google_connector:
                try:
                    decrypted_json = decrypt_data(google_connector.credentials_encrypted)
                    credentials = ConnectorCredentials.model_validate_json(decrypted_json)
                    async with httpx.AsyncClient(follow_redirects=False) as client:
                        await client.post(
                            "https://oauth2.googleapis.com/revoke",
                            params={"token": credentials.access_token},
                        )
                    logger.info(
                        "account_deletion_google_oauth_revoked",
                        user_id=str(user_id),
                        connector_id=str(google_connector.id),
                    )
                except Exception as e:
                    logger.warning(
                        "account_deletion_google_oauth_revoke_failed",
                        user_id=str(user_id),
                        error=str(e),
                    )
        except Exception as e:
            logger.warning(
                "account_deletion_oauth_revoke_error",
                user_id=str(user_id),
                error=str(e),
            )

    async def _disconnect_mcp_pool(self, user_id: UUID) -> None:
        """Disconnect all MCP server connections for the user (best-effort).

        Args:
            user_id: User UUID.
        """
        try:
            from src.infrastructure.mcp.user_pool import get_user_mcp_pool

            pool = get_user_mcp_pool()
            if pool:
                await pool.disconnect_user(user_id)
                logger.info(
                    "account_deletion_mcp_disconnected",
                    user_id=str(user_id),
                )
        except Exception as e:
            logger.warning(
                "account_deletion_mcp_disconnect_failed",
                user_id=str(user_id),
                error=str(e),
            )

    async def _invalidate_redis_sessions(self, user_id: UUID) -> None:
        """Invalidate all Redis sessions for the user (best-effort).

        Reuses the UserService pattern: SCAN session:* keys, filter by user_id,
        batch delete via pipeline.

        Args:
            user_id: User UUID.
        """
        try:
            from src.domains.users.service import UserService

            user_service = UserService(self.db)
            await user_service._invalidate_all_user_sessions(user_id)
        except Exception as e:
            logger.warning(
                "account_deletion_session_invalidation_failed",
                user_id=str(user_id),
                error=str(e),
            )

    async def _cleanup_redis_caches(self, user_id: UUID) -> None:
        """Delete all user-specific Redis cache keys (best-effort).

        Covers: usage limits, conversation ID cache, Gmail labels cache,
        sub-agent budget, rate limit keys for all connector types and channels.

        Args:
            user_id: User UUID.
        """
        try:
            from src.core.constants import (
                REDIS_KEY_CONVERSATION_ID_PREFIX,
                REDIS_KEY_GMAIL_LABELS_PREFIX,
                REDIS_KEY_USAGE_LIMIT_PREFIX,
            )
            from src.domains.sub_agents.constants import SUBAGENT_DAILY_BUDGET_KEY_PREFIX
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            uid = str(user_id)

            # Explicit known keys (using centralized constants)
            explicit_keys = [
                f"{REDIS_KEY_USAGE_LIMIT_PREFIX}{uid}",
                f"{REDIS_KEY_CONVERSATION_ID_PREFIX}{uid}",
                f"{REDIS_KEY_GMAIL_LABELS_PREFIX}{uid}",
                f"{REDIS_KEY_GMAIL_LABELS_PREFIX}{uid}:full",
                f"{SUBAGENT_DAILY_BUDGET_KEY_PREFIX}{uid}",
            ]
            for key in explicit_keys:
                await redis.delete(key)

            # Wildcard patterns (rate limits, channel caches)
            patterns = [
                f"apikey:user:{uid}:*",
                f"user:{uid}:*",
                f"apple_rate_limit:*:{uid}",
                f"channel:*:{uid}",
            ]
            for pattern in patterns:
                cursor = 0
                while True:
                    cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await redis.delete(*keys)
                    if cursor == 0:
                        break

            logger.info(
                "account_deletion_redis_caches_cleaned",
                user_id=uid,
            )
        except Exception as e:
            logger.warning(
                "account_deletion_redis_cleanup_failed",
                user_id=str(user_id),
                error=str(e),
            )

    # =========================================================================
    # STEP 1b — Physical file cleanup
    # =========================================================================

    def _cleanup_attachment_files(self, user_id: UUID) -> int:
        """Delete user's attachment directory from disk (best-effort).

        Files are organized as: {storage_path}/{user_id}/

        Args:
            user_id: User UUID.

        Returns:
            1 if directory existed and was removed, 0 if no directory found.
        """
        user_dir = Path(settings.attachments_storage_path) / str(user_id)
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
            logger.info(
                "account_deletion_attachment_files_cleaned",
                user_id=str(user_id),
                path=str(user_dir),
            )
            return 1
        return 0

    def _cleanup_rag_files(self, user_id: UUID) -> int:
        """Delete user's RAG upload directory from disk (best-effort).

        Files are organized as: {storage_path}/{user_id}/{space_id}/

        Args:
            user_id: User UUID.

        Returns:
            1 if directory existed and was deleted, 0 otherwise.
        """
        user_dir = Path(settings.rag_spaces_storage_path) / str(user_id)
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
            logger.info(
                "account_deletion_rag_files_cleaned",
                user_id=str(user_id),
                path=str(user_dir),
            )
            return 1
        return 0

    # =========================================================================
    # STEP 2 — PostgreSQL data purge
    # =========================================================================

    async def _purge_langgraph_checkpoints(self, conversation_id: UUID) -> None:
        """Purge LangGraph checkpoints for the user's conversation thread.

        Uses the checkpointer's adelete_thread() to properly handle all 3 tables
        (checkpoints, checkpoint_writes, checkpoint_blobs) and internal caches.

        Args:
            conversation_id: Conversation UUID (= LangGraph thread_id).
        """
        try:
            from src.domains.conversations.checkpointer import get_checkpointer

            checkpointer = await get_checkpointer()
            await checkpointer.adelete_thread(str(conversation_id))
            logger.info(
                "account_deletion_checkpoints_purged",
                conversation_id=str(conversation_id),
            )
        except Exception as e:
            logger.warning(
                "account_deletion_checkpoint_purge_failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )

    async def _purge_langgraph_store(self, user_id: UUID) -> int:
        """Purge all LangGraph Store entries for the user.

        Store namespaces start with '{user_id}.' — covers tool contexts,
        memories, heartbeat context. The store_vectors table cascades from store.

        Args:
            user_id: User UUID.

        Returns:
            Number of store items deleted.
        """
        uid = str(user_id)
        cursor_result = await self.db.execute(
            text("DELETE FROM store WHERE prefix LIKE :pattern"),
            {"pattern": f"{uid}.%"},
        )
        count: int = cursor_result.rowcount  # type: ignore[attr-defined]
        if count > 0:
            logger.info(
                "account_deletion_store_purged",
                user_id=uid,
                items_deleted=count,
            )
        return count

    async def _deactivate_connectors(self, user_id: UUID) -> int:
        """Deactivate all connectors: OAuth → REVOKED, non-OAuth → INACTIVE.

        Args:
            user_id: User UUID.

        Returns:
            Number of connectors deactivated.
        """
        # OAuth connectors → REVOKED
        oauth_result = await self.db.execute(
            update(Connector)
            .where(
                Connector.user_id == user_id,
                Connector.connector_type.in_(ConnectorType.get_oauth_types()),
            )
            .values(status=ConnectorStatus.REVOKED)
        )

        # Non-OAuth connectors → INACTIVE
        non_oauth_result = await self.db.execute(
            update(Connector)
            .where(
                Connector.user_id == user_id,
                Connector.connector_type.notin_(ConnectorType.get_oauth_types()),
            )
            .values(status=ConnectorStatus.INACTIVE)
        )

        return (oauth_result.rowcount or 0) + (non_oauth_result.rowcount or 0)  # type: ignore[attr-defined]

    async def _purge_user_data_tables(self, user_id: UUID) -> dict[str, int]:
        """Delete personal data from all user-scoped tables in FK-safe order.

        Group 1: child tables (FK to other user-scoped tables).
        Group 2: main tables (FK directly to users only).

        Args:
            user_id: User UUID.

        Returns:
            Dict mapping table name → deleted row count.
        """
        counts: dict[str, int] = {}

        # Group 1 — Child tables (FK to other user-scoped tables)
        # Note: ConversationMessage has NO user_id — it cascades from Conversation.
        # We delete it explicitly via subquery for accurate counting.
        conversation_ids_subq = select(Conversation.id).where(Conversation.user_id == user_id)
        group1: list[tuple[str, Any]] = [
            (
                "interest_notifications",
                delete(InterestNotification).where(InterestNotification.user_id == user_id),
            ),
            (
                "broadcast_read_receipts",
                delete(UserBroadcastRead).where(UserBroadcastRead.user_id == user_id),
            ),
            (
                "conversation_audit_log",
                delete(ConversationAuditLog).where(ConversationAuditLog.user_id == user_id),
            ),
            (
                "conversation_messages",
                delete(ConversationMessage).where(
                    ConversationMessage.conversation_id.in_(conversation_ids_subq)
                ),
            ),
        ]

        # Group 2 — Main tables (FK directly to users)
        group2: list[tuple[str, Any]] = [
            ("conversations", delete(Conversation).where(Conversation.user_id == user_id)),
            ("memories", delete(Memory).where(Memory.user_id == user_id)),
            ("journal_entries", delete(JournalEntry).where(JournalEntry.user_id == user_id)),
            ("user_interests", delete(UserInterest).where(UserInterest.user_id == user_id)),
            (
                "heartbeat_notifications",
                delete(HeartbeatNotification).where(HeartbeatNotification.user_id == user_id),
            ),
            ("reminders", delete(Reminder).where(Reminder.user_id == user_id)),
            (
                "scheduled_actions",
                delete(ScheduledAction).where(ScheduledAction.user_id == user_id),
            ),
            ("user_skill_states", delete(UserSkillState).where(UserSkillState.user_id == user_id)),
            ("skills", delete(Skill).where(Skill.owner_id == user_id)),
            ("user_mcp_servers", delete(UserMCPServer).where(UserMCPServer.user_id == user_id)),
            ("sub_agents", delete(SubAgent).where(SubAgent.user_id == user_id)),
            ("rag_spaces", delete(RAGSpace).where(RAGSpace.user_id == user_id)),
            ("user_fcm_tokens", delete(UserFCMToken).where(UserFCMToken.user_id == user_id)),
            ("channels", delete(UserChannelBinding).where(UserChannelBinding.user_id == user_id)),
            ("attachments", delete(Attachment).where(Attachment.user_id == user_id)),
            ("user_usage_limits", delete(UserUsageLimit).where(UserUsageLimit.user_id == user_id)),
            ("connectors", delete(Connector).where(Connector.user_id == user_id)),
        ]

        for table_name, stmt in group1 + group2:
            result = await self.db.execute(stmt)
            counts[table_name] = result.rowcount  # type: ignore[attr-defined]

        return counts

    async def _mark_user_deleted(self, user: User, reason: str | None) -> None:
        """Mark user as deleted: scrub sensitive PII, set deleted_at timestamp.

        Preserves email and full_name for billing contact purposes.

        Args:
            user: User ORM instance (already locked).
            reason: Deletion reason.
        """
        user.hashed_password = None
        user.oauth_provider = None
        user.oauth_provider_id = None
        user.picture_url = None
        user.home_location_encrypted = None
        user.deleted_at = datetime.now(UTC)
        user.deleted_reason = reason

    async def _create_audit_log(
        self,
        user: User,
        admin_user_id: UUID,
        reason: str | None,
        counts: dict[str, int],
        request: Request | None,
    ) -> None:
        """Create admin audit log entry for the account deletion.

        Uses UserRepository.create_audit_log() for consistency with existing
        audit log creation pattern throughout the codebase.

        Args:
            user: User ORM instance.
            admin_user_id: Admin performing the deletion.
            reason: Deletion reason.
            counts: Purge counts by table.
            request: FastAPI request for IP/user-agent.
        """
        from src.domains.users.repository import UserRepository

        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        repo = UserRepository(self.db)
        await repo.create_audit_log(
            admin_user_id=admin_user_id,
            action="account_deleted",
            resource_type="user",
            resource_id=user.id,
            details={
                "user_email": user.email,
                "user_name": user.full_name,
                "reason": reason,
                "purge_counts": counts,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def _invalidate_usage_limit_cache(self, user_id: UUID) -> None:
        """Invalidate usage limit Redis cache for the user.

        Args:
            user_id: User UUID.
        """
        try:
            from src.domains.usage_limits.service import UsageLimitService

            await UsageLimitService.invalidate_cache_static(user_id)
        except Exception as e:
            logger.warning(
                "account_deletion_usage_limit_cache_invalidation_failed",
                user_id=str(user_id),
                error=str(e),
            )
