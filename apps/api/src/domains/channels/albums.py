"""An album is ONE message (Telegram lot 11).

Telegram delivers each photo of an album as its own update, the parts sharing a
``media_group_id`` and the caption riding on one of them. Answered one by one,
an album of four photos was four turns, three of them behind a busy account
whose files cannot wait (ADR-384).

The first part to arrive owns the album: it waits
:data:`CHANNEL_ALBUM_WINDOW_SECONDS` for its siblings, which hand their files
over through Redis — the parts land on any worker — then answers them as one
message. The claim and the hand-over are two atomic scripts: a part joins an
album only while it is open, at most :data:`CHANNEL_ALBUM_MAX_PARTS` of them; a
part arriving once the owner collected, or beyond the ceiling, is answered alone.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from enum import StrEnum
from typing import Any, Protocol

from src.core.constants import (
    CHANNEL_ALBUM_MAX_PARTS,
    CHANNEL_ALBUM_REDIS_PREFIX,
    CHANNEL_ALBUM_TTL_SECONDS,
    CHANNEL_ALBUM_WINDOW_SECONDS,
)
from src.domains.channels.abstractions import ChannelFile, ChannelFileKind, ChannelInboundMessage
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: KEYS: the album's state, its parts. ARGV: this part, the TTL, the ceiling.
#: The first part opens the album; a part joins while it is open and not full.
JOIN_SCRIPT = """
local state = redis.call('GET', KEYS[1])
if not state then
  redis.call('SET', KEYS[1], 'open', 'EX', ARGV[2])
  redis.call('RPUSH', KEYS[2], ARGV[1])
  redis.call('EXPIRE', KEYS[2], ARGV[2])
  return 'own'
end
if state == 'open' and redis.call('LLEN', KEYS[2]) < tonumber(ARGV[3]) then
  redis.call('RPUSH', KEYS[2], ARGV[1])
  return 'joined'
end
return 'late'
"""

#: KEYS: the album's state, its parts. ARGV: the TTL. The owner closes the album
#: and takes its parts in one step: a part arriving after is late, never lost.
COLLECT_SCRIPT = """
redis.call('SET', KEYS[1], 'closed', 'EX', ARGV[1])
local parts = redis.call('LRANGE', KEYS[2], 0, -1)
redis.call('DEL', KEYS[2])
return parts
"""


class ScriptRunner(Protocol):
    """What an album needs of Redis: running a script."""

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        """Run ``script`` on ``numkeys`` keys then its arguments."""


class _Role(StrEnum):
    OWN = "own"
    JOINED = "joined"
    LATE = "late"


async def gather_album(
    runner: ScriptRunner, message: ChannelInboundMessage
) -> ChannelInboundMessage | None:
    """The message to answer for one part of an album, or None when another part answers it.

    Args:
        runner: The Redis client the parts meet in.
        message: One received message; one outside an album passes untouched.

    Returns:
        The message itself outside an album, when late, or when the parts could
        not meet (a part is never dropped for its album); the whole album for
        the part that owns it; None for a part handed to its owner.
    """
    if message.album_id is None:
        return message
    keys = _keys(message)
    try:
        joined = await runner.eval(
            JOIN_SCRIPT,
            2,
            *keys,
            _serialized(message),
            CHANNEL_ALBUM_TTL_SECONDS,
            CHANNEL_ALBUM_MAX_PARTS,
        )
    except Exception as exc:  # noqa: BLE001 — fail open: the part is answered alone
        logger.warning("channel_album_unjoined", error_type=type(exc).__name__)
        return message
    role = _Role(_text(joined))
    if role is _Role.JOINED:
        return None
    if role is _Role.LATE:
        logger.info("channel_album_part_late", album_parts_max=CHANNEL_ALBUM_MAX_PARTS)
        return message
    await asyncio.sleep(CHANNEL_ALBUM_WINDOW_SECONDS)
    try:
        raw_parts = await runner.eval(COLLECT_SCRIPT, 2, *keys, CHANNEL_ALBUM_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 — fail open: the owner's own part is answered
        logger.warning("channel_album_uncollected", error_type=type(exc).__name__)
        return message
    parts = [_part(_text(raw)) for raw in raw_parts]
    logger.info("channel_album_gathered", parts=len(parts))
    return _merged(message, parts)


def _keys(message: ChannelInboundMessage) -> tuple[str, str]:
    """The album's state and parts keys, one album per chat."""
    album = f"{CHANNEL_ALBUM_REDIS_PREFIX}{message.channel_user_id}:{message.album_id}"
    return album, f"{album}:parts"


def _text(raw: object) -> str:
    return raw.decode() if isinstance(raw, bytes) else str(raw)


def _serialized(message: ChannelInboundMessage) -> str:
    """What a part hands its owner: its id, its words, its files."""
    return json.dumps(
        {
            "message_id": message.message_id,
            "text": message.text,
            "quoted_text": message.quoted_text,
            "files": [
                [file.file_id, file.kind.value, file.filename, file.mime_type, file.size_bytes]
                for file in message.files
            ],
        }
    )


def _part(raw: str) -> dict[str, Any]:
    part: dict[str, Any] = json.loads(raw)
    part["files"] = [
        ChannelFile(file_id, ChannelFileKind(kind), filename, mime_type, size)
        for file_id, kind, filename, mime_type, size in part["files"]
    ]
    return part


def _order(part: dict[str, Any]) -> int:
    """A part's place in the album: Telegram numbers an album's messages in order."""
    message_id = part.get("message_id")
    return int(message_id) if isinstance(message_id, str) and message_id.isdigit() else 0


def _merged(owner: ChannelInboundMessage, parts: list[dict[str, Any]]) -> ChannelInboundMessage:
    """The album as one message: every file, every caption, in the album's order.

    The owner's own part is among ``parts``; its update stays the message's
    (the client's language is read from it).
    """
    ordered = sorted(parts, key=_order) or [_part(_serialized(owner))]
    captions = [part["text"] for part in ordered if part.get("text")]
    quoted = next((part["quoted_text"] for part in ordered if part.get("quoted_text")), None)
    return replace(
        owner,
        text="\n\n".join(captions) or None,
        quoted_text=quoted,
        files=tuple(file for part in ordered for file in part["files"]),
        message_id=ordered[0]["message_id"],
    )
