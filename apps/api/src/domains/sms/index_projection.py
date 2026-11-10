"""One storage accounting rule for ingestion and atomic index rebuilds."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from src.core.config import settings
from src.domains.sms.display_index import display_projection
from src.domains.sms.search import blind_terms


@dataclass(frozen=True, slots=True)
class SmsIndexProjection:
    """Both opaque projections, completeness and their charged logical bytes."""

    terms: tuple[bytes, ...]
    complete: bool
    display_terms: tuple[bytes, ...]
    display_complete: bool
    logical_bytes: int


async def prepare_index_projection(
    owner: UUID, sender: str, body: str, *, key: bytes
) -> SmsIndexProjection:
    """Run bounded but CPU-heavy hashing away from the API event loop.

    Only immutable content/key inputs cross the thread boundary; no session or
    side effect does. Cancelling the caller cannot publish the computed result.
    """
    return await asyncio.to_thread(build_index_projection, owner, sender, body, key=key)


def build_index_projection(
    owner: UUID, sender: str, body: str, *, key: bytes
) -> SmsIndexProjection:
    """Build both indexes and count exactly the binary terms actually stored.

    Args:
        owner: Tenant owning this message.
        sender: Original sender, kept encrypted elsewhere.
        body: Original body, kept encrypted elsewhere.
        key: Tenant HMAC key.

    Returns:
        Immutable storage projection and complete logical storage charge.
    """
    lexical = blind_terms(owner, body, key=key)
    terms = tuple(bytes.fromhex(value) for value in lexical[: settings.sms_max_index_terms])
    display, complete = display_projection(owner, body, key=key)
    return SmsIndexProjection(
        terms,
        len(lexical) <= settings.sms_max_index_terms,
        tuple(display),
        complete,
        len(sender.encode()) + len(body.encode()) + sum(map(len, terms)) + sum(map(len, display)),
    )
