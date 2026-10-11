"""Confirmed stars compare the exact displayed identity under the source owner lock."""

import json
from collections.abc import Awaitable, Callable
from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.relations.identity import IdentityResolver
from src.domains.relations.preference_commands import lock_relation_owner
from src.domains.relations.repository import RelationAliasRepository, RelationFavoriteRepository
from src.domains.shared.text_normalization import fold_name
from src.domains.users.preference_cas import PreferenceWriteReceipt


class RelationFavoriteSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    canonical_key: str = Field(min_length=1, max_length=255)
    starred: StrictBool
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self) -> dict[str, JsonValue]:
        return {"name": self.name, "starred": self.starred}


class RelationFavoriteCompletionUnknown(RuntimeError):
    """The database did not acknowledge the source commit."""


async def read_relation_favorite(
    db: AsyncSession, actor_id: UUID, name: str
) -> RelationFavoriteSelection:
    folded = fold_name(name)
    if not folded or len(folded) > 255:
        raise ValueError("A bounded relationship name is required")
    aliases = await RelationAliasRepository(db).list_for_user(actor_id)
    resolver = IdentityResolver.from_pairs((row.alias_key, row.canonical_key) for row in aliases)
    canonical = resolver.canonical(folded)
    if canonical in resolver.aliases:
        raise ValueError("Stored relationship grouping is not flat; correct it in Relations first")
    keys = resolver.keys_of(canonical)
    favorites = [
        row
        for row in await RelationFavoriteRepository(db).list_for_user(actor_id)
        if row.name_key in keys
    ]
    scope = {
        "canonical": canonical,
        "aliases": [
            [str(row.id), row.alias_key, row.canonical_key, row.alias_display_name]
            for row in aliases
            if row.alias_key in keys
        ],
        "favorites": [[str(row.id), row.name_key, row.display_name] for row in favorites],
    }
    return RelationFavoriteSelection(
        name=name.strip(),
        canonical_key=canonical,
        starred=bool(favorites),
        scope_digest=sha256(
            json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
    )


async def set_managed_relation_favorite(
    db: AsyncSession,
    actor_id: UUID,
    expected: RelationFavoriteSelection,
    starred: bool,
    receipt: PreferenceWriteReceipt,
    check: Callable[[], Awaitable[None]],
) -> None:
    await lock_relation_owner(db, actor_id)
    await check()
    observed = await read_relation_favorite(db, actor_id, expected.name)
    await check()
    if observed != expected:
        raise ResourceConflictError("relation_favorite", detail={"error_code": "STALE_STATE"})
    if observed.starred == starred:
        receipt.committed = True
        receipt.no_op = True
        return
    repo = RelationFavoriteRepository(db)
    if starred:
        await repo.add(actor_id, name_key=fold_name(expected.name), display_name=expected.name)
    else:
        await repo.remove_identity(actor_id, canonical_key=expected.canonical_key)
    actual = await read_relation_favorite(db, actor_id, expected.name)
    if actual.starred != starred or actual.canonical_key != expected.canonical_key:
        raise ValueError("Source favorite write did not establish the approved identity state")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise RelationFavoriteCompletionUnknown from exc
    receipt.committed = True
