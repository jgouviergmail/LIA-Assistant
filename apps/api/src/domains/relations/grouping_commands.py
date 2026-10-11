"""Exact source identity/debrief comparisons for confirmed grouping transactions."""

import json
from collections.abc import Sequence
from hashlib import sha256
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.relations.debrief.models import RelationDebrief
from src.domains.relations.identity import IdentityResolver
from src.domains.relations.models import RelationAlias
from src.domains.relations.repository import RelationAliasRepository
from src.domains.shared.text_normalization import fold_name


class RelationGroupingSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    action: Literal["merge", "split"]
    source: str = Field(min_length=1, max_length=255)
    target: str | None = None
    source_key: str
    source_canonical: str
    target_canonical: str
    affected_spellings: int = Field(ge=0)
    debriefs_to_invalidate: int = Field(ge=0)
    no_op: bool
    scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "source": self.source,
            "target": self.target,
            "action": self.action,
            "group": self.target_canonical if after and not self.no_op else self.source_canonical,
            "affected_spellings": self.affected_spellings,
            "stored_debriefs": 0 if after and not self.no_op else self.debriefs_to_invalidate,
        }


async def grouping_debriefs(
    db: AsyncSession, actor_id: UUID, keys: list[str], *, lock: bool = False
) -> list[JsonValue]:
    statement = (
        select(func.to_jsonb(RelationDebrief.__table__.table_valued()))
        .where(RelationDebrief.user_id == actor_id, RelationDebrief.name_key.in_(keys))
        .order_by(RelationDebrief.name_key)
    )
    if lock:
        statement = statement.with_for_update()
    return TypeAdapter(list[JsonValue]).validate_python(list((await db.scalars(statement)).all()))


def _affected_spellings(
    rows: Sequence[RelationAlias], source_key: str, action: str, no_op: bool
) -> int:
    if no_op:
        return 0
    if action == "split":
        return 1
    return 1 + sum(row.canonical_key == source_key and row.alias_key != source_key for row in rows)


def _grouping_alias_scope(rows: Sequence[RelationAlias], keys: set[str]) -> list[list[str]]:
    return [
        [str(row.id), row.alias_key, row.canonical_key, row.alias_display_name]
        for row in rows
        if row.alias_key in keys or row.canonical_key in keys
    ]


async def read_relation_grouping(
    db: AsyncSession,
    actor_id: UUID,
    *,
    action: Literal["merge", "split"],
    source: str,
    target: str | None,
    lock_debriefs: bool = False,
) -> RelationGroupingSelection:
    source_key = fold_name(source)
    target_key = fold_name(target or "")
    rows = await RelationAliasRepository(db).list_for_user(actor_id)
    resolver = IdentityResolver.from_pairs((row.alias_key, row.canonical_key) for row in rows)
    original = resolver.canonical(source_key)
    destination = resolver.canonical(target_key) if action == "merge" else source_key
    if action == "merge" and destination in resolver.aliases:
        raise ValueError("Target grouping is not flat; repair the source grouping first")
    existing = next((row for row in rows if row.alias_key == source_key), None)
    noop = original == destination if action == "merge" else existing is None
    invalidated = [] if noop else list(dict.fromkeys([source_key, original, destination]))
    # Whole source JSON retains payload, claim/fence and timestamps in the
    # private digest; no stored debrief body reaches the model or preview.
    debriefs = await grouping_debriefs(db, actor_id, invalidated, lock=lock_debriefs)
    relevant_keys = {source_key, target_key, original, destination}
    aliases = _grouping_alias_scope(rows, relevant_keys)
    affected = _affected_spellings(rows, source_key, action, noop)
    private = {
        "aliases": aliases,
        "debriefs": debriefs,
        "source": source_key,
        "original": original,
        "destination": destination,
    }
    return RelationGroupingSelection(
        action=action,
        source=source.strip(),
        target=target.strip() if target else None,
        source_key=source_key,
        source_canonical=original,
        target_canonical=destination,
        affected_spellings=affected,
        debriefs_to_invalidate=len(debriefs),
        no_op=noop,
        scope_digest=sha256(
            json.dumps(private, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
    )
