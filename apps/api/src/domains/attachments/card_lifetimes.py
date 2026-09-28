"""A chat card states the lifetime its file has NOW (ADR-319).

A generated image or document is shown in the chat as a card whose metadata
was written when the file was produced: its URL and the deadline it had then
(``expires_at``). Since a person can keep a file from the gallery, or delete
it, that stored deadline can be false by the time the conversation is read
again — a kept image announced « expired », its share button disabled; a
deleted one announced « available until … » over a broken image.

The history read path therefore restates every card from the attachment row:

- the row exists and is kept (no deadline) → ``expires_at: None, kept: True``;
- the row exists → ``expires_at`` is its current deadline;
- the row is gone → ``gone: True`` (the card says it is no longer available).

A card is recognised by its SHAPE, not by the metadata key it sits under: any
object naming a stored file by its ``/api/v1/attachments/{id}`` URL and stating
an ``expires_at``. The image and document cards both have it, and a card type
added later inherits the rule without anyone remembering to add it here.

Pure functions plus one batched read — never one query per card.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.models import Attachment
from src.domains.attachments.urls import ATTACHMENT_PATH_PREFIX

__all__ = ["card_attachment_ids", "current_lifetimes", "with_current_lifetimes"]

#: How deep a card may sit in the metadata (a list of cards under a key is 2).
_MAX_DEPTH = 4

_URL = "url"
_EXPIRES_AT = "expires_at"
_KEPT = "kept"
_GONE = "gone"


def _card_id(card: Mapping[str, Any]) -> uuid.UUID | None:
    """The attachment a card names, when it is a card at all."""
    url = card.get(_URL)
    if _EXPIRES_AT not in card or not isinstance(url, str):
        return None
    if not url.startswith(ATTACHMENT_PATH_PREFIX):
        return None
    raw = url[len(ATTACHMENT_PATH_PREFIX) :].split("?", 1)[0].split("/", 1)[0]
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _walk(node: Any, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > _MAX_DEPTH:
        return
    if isinstance(node, Mapping):
        yield node
        for value in node.values():
            yield from _walk(value, depth + 1)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item, depth + 1)


def card_attachment_ids(metadata_rows: Iterable[Mapping[str, Any] | None]) -> set[uuid.UUID]:
    """Every attachment the cards of these messages name.

    Args:
        metadata_rows: The ``message_metadata`` of each message (None allowed).

    Returns:
        The ids, to be read in ONE query.
    """
    ids: set[uuid.UUID] = set()
    for metadata in metadata_rows:
        for node in _walk(metadata):
            card_id = _card_id(node)
            if card_id is not None:
                ids.add(card_id)
    return ids


async def current_lifetimes(
    db: AsyncSession, user_id: uuid.UUID, ids: set[uuid.UUID]
) -> dict[uuid.UUID, datetime | None]:
    """The current deadline of each of the person's files that still exists.

    Args:
        db: Session.
        user_id: Whose files — a card naming someone else's file reads as gone.
        ids: The ids the cards name.

    Returns:
        ``id -> deadline`` (None when kept); an absent id is gone.
    """
    if not ids:
        return {}
    rows = await db.execute(
        select(Attachment.id, Attachment.expires_at).where(
            Attachment.id.in_(ids), Attachment.user_id == user_id
        )
    )
    return {row.id: row.expires_at for row in rows}


def _restated(
    card: Mapping[str, Any], lifetimes: Mapping[uuid.UUID, datetime | None]
) -> dict[str, Any]:
    card_id = _card_id(card)
    if card_id is None:
        return dict(card)
    if card_id not in lifetimes:
        return {**card, _GONE: True, _KEPT: False}
    deadline = lifetimes[card_id]
    return {
        **card,
        _EXPIRES_AT: deadline.isoformat() if deadline else None,
        _KEPT: deadline is None,
        _GONE: False,
    }


def _rebuild(node: Any, lifetimes: Mapping[uuid.UUID, datetime | None], depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return node
    if isinstance(node, Mapping):
        base = _restated(node, lifetimes)
        return {key: _rebuild(value, lifetimes, depth + 1) for key, value in base.items()}
    if isinstance(node, list):
        return [_rebuild(item, lifetimes, depth + 1) for item in node]
    return node


def with_current_lifetimes(
    metadata: dict[str, Any] | None, lifetimes: Mapping[uuid.UUID, datetime | None]
) -> dict[str, Any] | None:
    """The message metadata with every card restated from its file, as a NEW dict.

    Never mutates the input (the caller may hold the ORM's JSONB dict), and
    returns the input itself when it names no card.

    Args:
        metadata: The persisted ``message_metadata``.
        lifetimes: From :func:`current_lifetimes`.

    Returns:
        The restated metadata.
    """
    if not metadata or not card_attachment_ids([metadata]):
        return metadata
    rebuilt: dict[str, Any] = _rebuild(metadata, lifetimes, 0)
    return rebuilt
