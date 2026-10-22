"""Resolve after releasing the read transaction, then revalidate publication."""

from typing import TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.sms.identity import IdentityBook, SenderIdentity
from src.domains.sms.identity_resolution import resolve_senders
from src.domains.sms.identity_store import validate_resolutions
from src.domains.sms.read_schemas import SmsPage, SmsQuery, SmsSenderPage, SmsSenderView, SmsView
from src.domains.sms.reads import SmsReadService, require_read

_View = TypeVar("_View", SmsView, SmsSenderView)


def resolve_view(item: _View, book: IdentityBook) -> _View:
    return resolved_view(item, book.resolve(item.sender))


def resolved_view(item: _View, identity: SenderIdentity) -> _View:
    """Return an SMS view carrying the sender identity it resolved to.

    Args:
        item: The SMS view.
        identity: The resolved sender identity.

    Returns:
        The view with its display name, identity source, state and relation key.
    """
    return item.model_copy(
        update={
            "display_name": identity.display_name,
            "identity_source": identity.source,
            "identity_state": identity.state,
            "relation_key": identity.relation_key,
        }
    )


class SmsFacade:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.reader = SmsReadService(db)

    async def _identities(
        self, owner: UUID, senders: list[str], revision: int, *, assistant: bool
    ) -> dict[str, SenderIdentity]:
        await self.db.commit()
        resolved = await resolve_senders(owner, senders, revision=revision, assistant=assistant)
        await validate_resolutions(self.db, resolved.scope, assistant=assistant)
        return resolved.identities

    async def list(
        self, owner: UUID, query: SmsQuery, *, assistant: bool, unmentioned_only: bool = False
    ) -> SmsPage:
        page = await self.reader.list(
            owner, query, assistant=assistant, unmentioned_only=unmentioned_only
        )
        if page.items:
            identities = await self._identities(
                owner, [item.sender for item in page.items], page.revision, assistant=assistant
            )
            page = page.model_copy(
                update={
                    "items": [resolved_view(item, identities[item.sender]) for item in page.items]
                }
            )
        return page

    async def get(self, owner: UUID, message_id: UUID, *, assistant: bool) -> SmsView:
        item = await self.reader.get(owner, message_id, assistant=assistant)
        actor = await require_read(self.db, owner, assistant=assistant)
        revision = actor.extraction_revision or 0
        identities = await self._identities(owner, [item.sender], revision, assistant=assistant)
        return resolved_view(item, identities[item.sender])

    async def senders(
        self, owner: UUID, *, assistant: bool, limit: int = 20, cursor: str | None = None
    ) -> SmsSenderPage:
        page = await self.reader.senders(owner, assistant=assistant, limit=limit, cursor=cursor)
        if page.items:
            identities = await self._identities(
                owner, [item.sender for item in page.items], page.revision, assistant=assistant
            )
            page = page.model_copy(
                update={
                    "items": [resolved_view(item, identities[item.sender]) for item in page.items]
                }
            )
        return page
