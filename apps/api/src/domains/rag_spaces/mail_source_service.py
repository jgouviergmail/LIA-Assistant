"""Linking, unlinking and locking a Gmail label source (ADR-262).

The CRUD half of the mail source: what the API calls. Ownership is the
space's and hides existence; the feature flag refuses at the door; the
bounds are the published settings; the SYNCING lease is one conditional
UPDATE, exactly like the Drive source's.

The indexing half lives in ``mail_sync.py``, which imports this module (never
the other way round).
"""

from __future__ import annotations

import os
from typing import NoReturn
from uuid import UUID

from fastapi import status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.rag_spaces.consultations import SECTION_MAIL, space_read
from src.domains.rag_spaces.drive_ingest import discard_document
from src.domains.rag_spaces.jobs_repository import validate_source_worker_id
from src.domains.rag_spaces.models import RAGMailSource, RAGSourceSyncStatus
from src.domains.rag_spaces.repository import (
    RAGDocumentRepository,
    RAGMailSourceRepository,
    RAGSpaceRepository,
)
from src.domains.rag_spaces.service import raise_space_not_found
from src.domains.rag_spaces.source_link_observation import (
    SourceLinkObservation,
    observed_source_name,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import rag_mail_sources_total_count

logger = get_logger(__name__)

# Per-process worker identity for the durable sync lease (audit F001).
_MAIL_WORKER_ID = f"rag-mail-sync-{os.getpid()}"
_USER_LABEL_PREFIX = "Label_"


async def gmail_client_or_none(db: AsyncSession, user_id: UUID) -> GoogleGmailClient | None:
    """An authenticated Gmail client, or None when the connector is not active.

    The credentials are read on ``db``; the client's own writes (a refreshed
    token) run on a session of their own, never on the caller's (ADR-304).
    """
    credentials = await ConnectorService(db).get_connector_credentials(
        user_id, ConnectorType.GOOGLE_GMAIL
    )
    if credentials is None:
        return None
    return GoogleGmailClient(user_id, credentials, DetachedConnectorService())


def _raise_mail_source_not_found(source_id: UUID, space_id: UUID) -> NoReturn:
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Mail source not found",
        log_event="rag_mail_source_not_found",
        source_id=str(source_id),
        space_id=str(space_id),
    )


def _require_mail_sync_enabled() -> None:
    if not settings.rag_spaces_mail_sync_enabled:
        raise BaseAPIException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mail sync is disabled",
            log_event="rag_mail_sync_disabled",
        )


class RAGMailSyncService:
    """Link, unlink, lock and inspect the Gmail label sources of a space."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.space_repo = RAGSpaceRepository(db)
        self.doc_repo = RAGDocumentRepository(db)
        self.source_repo = RAGMailSourceRepository(db)

    async def _verify_space_ownership(self, space_id: UUID, user_id: UUID) -> None:
        space = await self.space_repo.get_by_id(space_id)
        if not space or space.user_id != user_id:
            raise_space_not_found(space_id)

    async def _get_source_or_404(self, source_id: UUID, space_id: UUID) -> RAGMailSource:
        source = await self.source_repo.get_by_id_and_space(source_id, space_id)
        if not source:
            _raise_mail_source_not_found(source_id, space_id)
        return source

    async def _get_gmail_client(self, user_id: UUID) -> GoogleGmailClient:
        client = await gmail_client_or_none(self.db, user_id)
        if client is None:
            raise BaseAPIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gmail connector is not active",
                log_event="rag_mail_connector_not_active",
                user_id=str(user_id),
            )
        return client

    async def list_labels(self, space_id: UUID, user_id: UUID) -> list[dict[str, str]]:
        """The user's own labels (never the system ones), for the picker."""
        _require_mail_sync_enabled()
        await self._verify_space_ownership(space_id, user_id)
        client = await self._get_gmail_client(user_id)
        try:
            await self.db.commit()  # Ownership/credential reads end before the provider wait.
            async with space_read(user_id=user_id, section=SECTION_MAIL):
                mapping = await client.list_labels(use_cache=False)
        finally:
            await client.close()
        labels = [
            {"id": label_id, "name": name}
            for label_id, name in mapping.items()
            if label_id.startswith(_USER_LABEL_PREFIX)
        ]
        return sorted(labels, key=lambda label: label["name"].lower())

    async def link_label(
        self,
        space_id: UUID,
        user_id: UUID,
        label_id: str,
        label_name: str,
        *,
        observation: SourceLinkObservation | None = None,
        commit: bool = True,
    ) -> RAGMailSource:
        """Link a Gmail label to a space (the label must exist on the account)."""
        if not commit and observation is None:
            raise ValueError("Deferred source linking requires prior provider inspection")
        if observation is None:
            observation = await self.prepare_label_link(
                space_id, user_id, label_id, fallback_name=label_name
            )
            label_name = observation.name
        observation.require_scope("mail", space_id, user_id, label_id, label_name)
        if await self.space_repo.get_by_id_for_owner_update(space_id, user_id) is None:
            raise_space_not_found(space_id)
        await self._label_link_constraints(space_id, user_id, label_id)
        source = await self.source_repo.create(
            {
                "space_id": space_id,
                "user_id": user_id,
                "label_id": label_id,
                "label_name": label_name,
                "sync_status": RAGSourceSyncStatus.IDLE,
            }
        )
        if not commit:
            await self.db.flush()
            return source
        await self.db.commit()
        rag_mail_sources_total_count.inc()
        logger.info("rag_mail_source_linked", source_id=str(source.id), space_id=str(space_id))
        return source

    async def _label_link_constraints(self, space_id: UUID, user_id: UUID, label_id: str) -> None:
        _require_mail_sync_enabled()
        await self._verify_space_ownership(space_id, user_id)
        if (
            await self.source_repo.count_for_space(space_id)
            >= settings.rag_mail_max_sources_per_space
        ):
            raise BaseAPIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Maximum number of mail sources per space reached "
                    f"({settings.rag_mail_max_sources_per_space})"
                ),
                log_event="rag_mail_source_limit_exceeded",
                max_sources=settings.rag_mail_max_sources_per_space,
            )
        if await self.source_repo.exists_for_space_and_label(space_id, label_id):
            raise BaseAPIException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This Gmail label is already linked to this space",
                log_event="rag_mail_source_duplicate",
            )

    async def prepare_label_link(
        self, space_id: UUID, user_id: UUID, label_id: str, *, fallback_name: str | None = None
    ) -> SourceLinkObservation:
        """Inspect a real account label without writing a source or borrowing a transaction."""
        await self._label_link_constraints(space_id, user_id, label_id)
        client = await self._get_gmail_client(user_id)
        try:
            await self.db.commit()
            async with space_read(user_id=user_id, section=SECTION_MAIL):
                label = await client.get_label(label_id)
        finally:
            await client.close()
        if label is None:
            raise BaseAPIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The specified Gmail label does not exist",
                log_event="rag_mail_label_not_found",
            )
        return SourceLinkObservation(
            "mail",
            space_id,
            user_id,
            label_id,
            observed_source_name(label, label_id, fallback_name),
        )

    async def unlink_label(
        self,
        space_id: UUID,
        source_id: UUID,
        user_id: UUID,
        delete_documents: bool = False,
        *,
        commit: bool = True,
    ) -> None:
        """Unlink a label; keep its documents (unlinked) or delete them.

        Args:
            space_id: Owning space identity.
            source_id: Exact label source to remove.
            user_id: Current space owner.
            delete_documents: Whether the ordinary Source path removes documents.
            commit: False leaves a retain-only unlink in the caller's transaction.
        """
        if not commit and delete_documents:
            raise ValueError("Deferred source unlink must retain documents")
        await self._verify_space_ownership(space_id, user_id)
        source = await self._get_source_or_404(source_id, space_id)
        if delete_documents:
            for doc in await self.doc_repo.get_mail_documents_for_source(source_id):
                await discard_document(self.db, doc, user_id=user_id, space_id=space_id)
        else:
            await self.db.execute(
                text("UPDATE rag_documents SET mail_source_id = NULL WHERE mail_source_id = :sid"),
                {"sid": str(source_id)},
            )
        await self.source_repo.delete(source)
        if not commit:
            await self.db.flush()
            return
        await self.db.commit()
        rag_mail_sources_total_count.dec()
        logger.info(
            "rag_mail_source_unlinked",
            source_id=str(source_id),
            space_id=str(space_id),
            delete_documents=delete_documents,
        )

    async def get_sync_status(
        self, space_id: UUID, source_id: UUID, user_id: UUID
    ) -> RAGMailSource:
        """The source, after the ownership check."""
        await self._verify_space_ownership(space_id, user_id)
        return await self._get_source_or_404(source_id, space_id)

    async def try_acquire_sync_lock(
        self, source_id: UUID, *, commit: bool = True, worker_id: str | None = None
    ) -> bool:
        """Atomically take the SYNCING lease (a fresh run: attempts = 1)."""
        if not commit and worker_id is None:
            raise ValueError("Deferred source claims require a unique caller worker identity")
        owner = worker_id if worker_id is not None else _MAIL_WORKER_ID
        validate_source_worker_id(owner)
        clock = "clock_timestamp()" if worker_id is not None else "now()"
        result = await self.db.execute(
            text(
                "UPDATE rag_mail_sources "
                "SET sync_status = :syncing, error_message = NULL, "
                f"lease_expires_at = {clock} + (:ttl * interval '1 second'), "
                f"heartbeat_at = {clock}, attempts = 1, worker_id = :wid "
                "WHERE id = :id AND sync_status != :syncing"
            ),
            {
                "syncing": RAGSourceSyncStatus.SYNCING,
                "id": str(source_id),
                "ttl": settings.rag_job_lease_ttl_seconds,
                "wid": owner,
            },
        )
        if commit:
            await self.db.commit()
        return (getattr(result, "rowcount", 0) or 0) > 0
