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

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Delete, delete, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, raise_user_not_found
from src.domains.connectors.models import (
    Connector,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.conversations.models import Conversation
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import Base
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from fastapi import Request

logger = get_logger(__name__)


def build_purge_statements(user_id: UUID) -> list[tuple[str, Delete]]:
    """Build the ordered DELETE statements purging all user-scoped tables.

    Module-level (not a method) so the completeness guard in
    ``tests/unit/domains/users/test_user_data_map_guard.py`` can cross-check
    the purged table set against ``user_data_map.TABLE_RULES`` without
    instantiating the service.

    Statements are built against ``Base.metadata`` Table objects, not ORM
    classes: the purge is a data-lifecycle concern keyed by table name, and
    importing every domain's models here would create users<->domain runtime
    import cycles (F009 ratchet).

    FK-safe order: Group 1 (child tables referencing other user-scoped
    tables) before Group 2 (tables referencing users only).

    Args:
        user_id: Target user UUID.

    Returns:
        Ordered list of ``(count key = table name, DELETE statement)`` pairs.
    """
    import_all_models()
    tables = Base.metadata.tables

    def by_user(table_name: str, column: str = "user_id") -> tuple[str, Delete]:
        table = tables[table_name]
        return table_name, delete(table).where(table.c[column] == user_id)

    # conversation_messages has NO user_id — it cascades from conversations.
    # We delete it explicitly via subquery for accurate counting.
    conversations = tables["conversations"]
    conversation_messages = tables["conversation_messages"]
    conversation_ids_subq = select(conversations.c.id).where(conversations.c.user_id == user_id)

    def by_either_side(table_name: str, col_a: str, col_b: str) -> tuple[str, Delete]:
        """DELETE rows where the user sits on EITHER side (two-sided peers tables).

        The users row is soft-deleted, so FK CASCADEs from users never fire —
        every peers table must be purged explicitly (same trap as open_loops).
        """
        table = tables[table_name]
        return table_name, delete(table).where(
            or_(table.c[col_a] == user_id, table.c[col_b] == user_id)
        )

    # peer_domain_shares has no two-sided user columns: BOTH owners' shares on a
    # connection involving the user die with that connection — delete them via
    # the connection subquery for accurate counting (conversation_messages
    # precedent; the FK CASCADE would cover them, but silently).
    peer_connections = tables["peer_connections"]
    peer_domain_shares = tables["peer_domain_shares"]
    peer_connection_ids_subq = select(peer_connections.c.id).where(
        or_(
            peer_connections.c.user_a_id == user_id,
            peer_connections.c.user_b_id == user_id,
        )
    )

    return [
        # Group 1 — Child tables (FK to other user-scoped tables)
        by_user("interest_notifications"),
        by_user("user_broadcast_reads"),
        by_user("conversation_audit_log"),
        (
            "conversation_messages",
            delete(conversation_messages).where(
                conversation_messages.c.conversation_id.in_(conversation_ids_subq)
            ),
        ),
        # Peers (children of peer_connections first, then the pair rows).
        (
            "peer_domain_shares",
            delete(peer_domain_shares).where(
                peer_domain_shares.c.connection_id.in_(peer_connection_ids_subq)
            ),
        ),
        by_either_side("peer_messages", "sender_id", "recipient_id"),
        by_either_side("peer_access_log", "accessor_id", "owner_id"),
        by_either_side("peer_blocks", "blocker_id", "blocked_id"),
        by_either_side("peer_connections", "user_a_id", "user_b_id"),
        # BEFORE its subjects: a reference row points at a journal entry or a
        # memory, and deleting those first would leave the DELETE below with
        # nothing to remove — the CASCADE would already have fired. Purging it
        # first keeps this statement meaningful rather than incidentally empty.
        by_user("provenance_references"),
        # Group 2 — Main tables (FK directly to users)
        by_user("relation_favorites"),
        by_user("relation_aliases"),
        by_user("conversations"),
        by_user("memories"),
        by_user("journal_entries"),
        by_user("psyche_history"),
        by_user("psyche_states"),
        by_user("user_interests"),
        by_user("heartbeat_notifications"),
        by_user("reminders"),
        by_user("scheduled_actions"),
        by_user("user_skill_states"),
        by_user("skills", column="owner_id"),
        by_user("user_mcp_servers"),
        # ADR-225: after skills/user_mcp_servers (their plugin_id FK is SET
        # NULL, order-safe either way) — the plugin rows themselves are purged.
        by_user("user_plugins"),
        # ADR-083 Phase 2 cleanup: sub_agents table dropped — nothing to delete.
        by_user("rag_spaces"),
        by_user("user_fcm_tokens"),
        by_user("user_channel_bindings"),
        by_user("attachments"),
        by_user("user_usage_limits"),
        # GDPR (audit N-207.1): physiological data + ingestion tokens.
        # The user row is soft-deleted, so FK CASCADEs never fire — these
        # rows MUST be purged explicitly. Deleting the tokens also cuts
        # off any device still pushing samples (its next write is a 401).
        by_user("health_samples"),
        by_user("health_metric_tokens"),
        # Same soft-delete trap: commitments and telephony call records
        # reference users with ondelete=CASCADE that never fires.
        by_user("open_loops"),
        by_user("phone_calls"),
        # Habits (ADR-214): learned rhythm profile + discrete habits.
        by_user("user_habit_profiles"),
        by_user("user_habits"),
        by_user("user_activity_days"),
        by_user("account_export_jobs"),
        # Product analytics (ADR-178): plain user_id columns, no CASCADE.
        by_user("product_outcomes"),
        by_user("product_events"),
        # Authentication material (security program D1): passkeys must die
        # with the account — a surviving credential could otherwise still
        # complete a discoverable-credential login ceremony lookup.
        by_user("webauthn_credentials"),
        by_user("user_totp"),
        by_user("mfa_backup_codes"),
        # Google push channel registry (lot H): channel tokens are secret
        # material; live Google-side watches expire on their own TTL.
        by_user("webhook_channels"),
        by_user("connectors"),
    ]


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
        admin_user_id: UUID | None,
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
        counts["skill_files"] = self._cleanup_user_tree(
            user_id, settings.skills_users_path, "skill"
        )
        counts["plugin_files"] = self._cleanup_user_tree(
            user_id, settings.plugins_users_path, "plugin"
        )

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
                REDIS_KEY_PSYCHE_STATE_PREFIX,
                REDIS_KEY_USAGE_LIMIT_PREFIX,
            )
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            uid = str(user_id)

            # Explicit known keys (using centralized constants).
            # NOTE: SUBAGENT_DAILY_BUDGET_KEY_PREFIX was removed in ADR-083
            # Phase 2 cleanup — the bespoke executor that wrote those keys is
            # gone, so any pre-existing keys (if any) become harmless orphans
            # that Redis will expire naturally (24h TTL).
            explicit_keys = [
                f"{REDIS_KEY_USAGE_LIMIT_PREFIX}{uid}",
                f"{REDIS_KEY_CONVERSATION_ID_PREFIX}{uid}",
                f"{REDIS_KEY_GMAIL_LABELS_PREFIX}{uid}",
                f"{REDIS_KEY_GMAIL_LABELS_PREFIX}{uid}:full",
                f"{REDIS_KEY_PSYCHE_STATE_PREFIX}{uid}",
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

    def _cleanup_user_tree(self, user_id: UUID, base_path: str, label: str) -> int:
        """Delete one {base_path}/{user_id}/ tree from disk (best-effort).

        Closes the disk half of the purge for user-scoped content trees whose
        DB rows CASCADE away with the account: imported skills
        (``skills_users_path``) and installed Agent Plugins roots
        (``plugins_users_path``, ADR-225).

        Args:
            user_id: User UUID.
            base_path: Configured base directory holding per-user subtrees.
            label: Short content label for the structured log event.

        Returns:
            1 if the directory existed and was removed, 0 otherwise.
        """
        base_str = str(Path(base_path).resolve())
        # CodeQL sanitizer: normpath + startswith prevents path traversal
        user_dir_str = os.path.normpath(os.path.join(base_str, str(user_id)))
        if not user_dir_str.startswith(base_str):
            logger.warning(
                "account_deletion_path_traversal_blocked",
                user_id=str(user_id),
                resolved_path=user_dir_str,
            )
            return 0
        user_dir = Path(user_dir_str)
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
            logger.info(
                "account_deletion_user_tree_cleaned",
                user_id=str(user_id),
                content=label,
                path=user_dir_str,
            )
            return 1
        return 0

    def _cleanup_attachment_files(self, user_id: UUID) -> int:
        """Delete user's attachment directory from disk (best-effort).

        Files are organized as: {storage_path}/{user_id}/

        Args:
            user_id: User UUID.

        Returns:
            1 if directory existed and was removed, 0 if no directory found.
        """
        base_str = str(Path(settings.attachments_storage_path).resolve())
        # CodeQL sanitizer: normpath + startswith prevents path traversal
        user_dir_str = os.path.normpath(os.path.join(base_str, str(user_id)))
        if not user_dir_str.startswith(base_str):
            logger.warning(
                "account_deletion_path_traversal_blocked",
                user_id=str(user_id),
                resolved_path=user_dir_str,
            )
            return 0
        user_dir = Path(user_dir_str)
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
            logger.info(
                "account_deletion_attachment_files_cleaned",
                user_id=str(user_id),
                path=user_dir_str,
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
        base_str = str(Path(settings.rag_spaces_storage_path).resolve())
        # CodeQL sanitizer: normpath + startswith prevents path traversal
        user_dir_str = os.path.normpath(os.path.join(base_str, str(user_id)))
        if not user_dir_str.startswith(base_str):
            logger.warning(
                "account_deletion_path_traversal_blocked",
                user_id=str(user_id),
                resolved_path=user_dir_str,
            )
            return 0
        user_dir = Path(user_dir_str)
        if user_dir.exists():
            shutil.rmtree(user_dir, ignore_errors=True)
            logger.info(
                "account_deletion_rag_files_cleaned",
                user_id=str(user_id),
                path=user_dir_str,
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

        The statement list lives in the module-level ``build_purge_statements``
        so the user-data completeness guard can introspect it.

        Args:
            user_id: User UUID.

        Returns:
            Dict mapping table name → deleted row count.
        """
        counts: dict[str, int] = {}
        for table_name, stmt in build_purge_statements(user_id):
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
        # GDPR (audit N-207.2): GPS trail — scrubbed like home_location.
        user.last_known_location_encrypted = None
        user.last_known_location_updated_at = None
        # ADR-079 commit 3 — Personal Journals portrait (synthesis of user
        # description, PII by content). Source entries in `journal_entries`
        # are already purged by `_purge_user_data_tables` via FK CASCADE.
        user.journal_portrait_full = None
        user.journal_portrait_brief = None
        user.journal_portrait_compiled_at = None
        user.deleted_at = datetime.now(UTC)
        user.deleted_reason = reason

    async def _create_audit_log(
        self,
        user: User,
        admin_user_id: UUID | None,
        reason: str | None,
        counts: dict[str, int],
        request: Request | None,
    ) -> None:
        """Create admin audit log entry for the account deletion.

        Uses UserRepository.create_audit_log() for consistency with existing
        audit log creation pattern throughout the codebase.

        Skipped entirely for an automatic deletion, which has no administrator
        to credit: ``admin_audit_log.admin_user_id`` is a NOT NULL foreign key,
        so writing the line anyway raises and rolls the whole deletion back —
        the account then survives the sweep that was meant to remove it
        (measured 2026-08-06 on the demonstrator's nightly purge, where a
        fresh instance has no superuser at all). The structured log records
        the deletion either way.

        Args:
            user: User ORM instance.
            admin_user_id: Admin performing the deletion, or None when the
                deletion is automatic.
            reason: Deletion reason.
            counts: Purge counts by table.
            request: FastAPI request for IP/user-agent.
        """
        if admin_user_id is None:
            return

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
