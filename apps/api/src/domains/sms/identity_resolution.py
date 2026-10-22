"""One sender-resolution registry for the archive, dashboard and assistant."""

import hashlib
from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.connectors.clients.contact_directory import invalidate_contacts_cache
from src.domains.relations.identity import NO_MERGES, IdentityResolver
from src.domains.sms.identity import IdentityBook, SenderIdentity
from src.domains.sms.identity_directory import (
    load_contact_book as load_identity_book,
)
from src.domains.sms.identity_directory import (
    load_relation_book,
)
from src.domains.sms.identity_store import (
    ResolutionScope,
    publish_resolutions,
    read_resolutions,
    reset_resolutions,
)
from src.infrastructure.utils.shared_flight import CLAIM_PREFIX, run_shared_flight


@dataclass(frozen=True, slots=True)
class ResolvedSenders:
    """The senders resolved for one read, under one scope and identity resolver."""

    scope: ResolutionScope
    identities: dict[str, SenderIdentity]
    resolver: IdentityResolver = NO_MERGES


async def refresh_sender_identities(db: AsyncSession, owner: UUID) -> None:
    """Forget SMS contact matches only on explicit request; keep every SMS intact."""
    await reset_resolutions(db, owner)
    await invalidate_contacts_cache(owner)


async def resolve_senders(
    owner: UUID, senders: list[str], *, revision: int, assistant: bool
) -> ResolvedSenders:
    """Reuse persisted contact matches and overlay the current local relation aliases.

    The caller must validate the returned scope in its publication transaction.
    No contact lookup occurs for a fully resolved batch, including known misses.
    """
    resolved = await _resolve_contacts(owner, senders, revision=revision, assistant=assistant)
    local = await load_relation_book(owner)
    identities = {}
    for sender, identity in resolved.identities.items():
        if identity.source == "contact":
            identity = replace(identity, relation_key=local.resolver.key(identity.display_name))
        elif identity.state in {"unresolved", "unavailable"}:
            relation = local.resolve(sender)
            if relation.source == "relation":
                identity = relation
        identities[sender] = identity
    return ResolvedSenders(resolved.scope, identities, local.resolver)


async def _resolve_contacts(
    owner: UUID, senders: list[str], *, revision: int, assistant: bool
) -> ResolvedSenders:
    requested = tuple(dict.fromkeys(senders))
    scope, cached = await read_resolutions(owner, requested, revision, assistant)
    if len(cached) == len(requested):
        return ResolvedSenders(scope, cached)

    async def published() -> ResolvedSenders | None:
        current, saved = await read_resolutions(owner, requested, revision, assistant)
        if current != scope:
            raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
        return ResolvedSenders(current, saved) if len(saved) == len(requested) else None

    async def build() -> ResolvedSenders:
        book = await load_identity_book(owner, cache_scope=f"{scope.authority}:{scope.generation}")
        book = IdentityBook(contacts=book.contacts, complete=book.complete)
        fresh = {sender: book.resolve(sender) for sender in requested if sender not in cached}
        await publish_resolutions(scope, fresh, assistant=assistant)
        return ResolvedSenders(scope, cached | fresh)

    batch = hashlib.sha256(
        "\n".join(sorted(scope.digest(sender) for sender in requested)).encode()
    ).hexdigest()
    flight = await run_shared_flight(
        f"{CLAIM_PREFIX}:sms_identity:{owner}:{scope.generation}:{scope.authority}:{batch}",
        build=build,
        read_shared=published,
        wait_budget_s=settings.sms_identity_timeout_seconds + 1,
    )
    return flight.value
