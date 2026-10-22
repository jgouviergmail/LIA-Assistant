"""The CRM's persisted user declarations; live signals stay in their own consented sources."""

from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import literal, select, union_all
from sqlalchemy.sql.selectable import Subquery

from src.domains.relations.models import RelationAlias, RelationFavorite
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    DiscussionValue,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
)
from src.domains.shared.discussion_sql import native_discussion_page, native_page_snapshot
from src.domains.users.active_reader import require_active_owner_read
from src.infrastructure.database.session import get_db_context


class RelationDeclaration(DiscussionValue):
    """One relationship the person declared: a favourite or an explicit identity link."""

    id: UUID
    recorded_at: AwareDatetime
    display_name: str
    identity_key: str
    canonical_key: str
    declaration: str


def _declarations(owner: UUID) -> Subquery:
    favorite, alias = RelationFavorite, RelationAlias
    return union_all(
        select(
            favorite.id,
            favorite.created_at.label("recorded_at"),
            favorite.display_name,
            favorite.name_key.label("identity_key"),
            favorite.name_key.label("canonical_key"),
            literal("favorite").label("declaration"),
        ).where(favorite.user_id == owner),
        select(
            alias.id,
            alias.created_at.label("recorded_at"),
            alias.alias_display_name.label("display_name"),
            alias.alias_key.label("identity_key"),
            alias.canonical_key,
            literal("explicit_identity_link").label("declaration"),
        ).where(alias.user_id == owner),
    ).subquery()


class RelationDiscussionSource:
    """The relationships the person declared themselves, never inferred ones."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of declared relationships, searched by name or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when relationships are not consented.

        Raises:
            ValueError: The request or its reference is for another source.
        """
        if request.request.source != SourceKey.RELATIONS:
            raise ValueError("relation source mismatch")
        if SourceKey.RELATIONS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        declarations = _declarations(request.owner_id)
        statement = select(declarations)
        if request.request.query is not None:
            statement = statement.where(
                declarations.c.display_name.icontains(request.request.query, autoescape=True)
            )
        if request.request.reference is not None:
            prefix, identifier = request.request.reference.split(":", 1)
            if prefix != SourceKey.RELATIONS.value:
                raise ValueError("relation reference source mismatch")
            statement = statement.where(declarations.c.id == UUID(identifier))
        async with get_db_context() as db:
            await require_active_owner_read(db, request.owner_id)
            page = await native_discussion_page(
                db,
                request.owner_id,
                statement,
                limit=request.item_limit,
                after_id=UUID(request.cursor) if request.cursor else None,
            )
        rows = tuple(RelationDeclaration.model_validate(value) for value in page.rows)
        items = tuple(
            DiscussionEvidence(
                reference=f"relations:{row.id}",
                source=SourceKey.RELATIONS,
                object_id=str(row.id),
                version=semantic_version((row.model_dump_json(),)),
                observed_at=request.now,
                recorded_at=row.recorded_at,
                assertion="reported",
                category="explicit_relationship_declaration",
                subject_id=f"relation:{row.canonical_key}",
                excerpt=row.model_dump_json()[: request.item_max_chars],
                excerpt_truncated=len(row.model_dump_json()) > request.item_max_chars,
            )
            for row in rows[: request.item_limit]
        )
        return native_page_snapshot(request, page, items)
