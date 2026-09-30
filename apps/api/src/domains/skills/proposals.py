"""A skill written in the chat, waiting for the person's click (ADR-327).

The chat's import tool used to register a skill the moment the model called
it, from whatever the model had in hand — a web page, an e-mail, a third
party's resource included. A skill runs with the assistant's trust, so that
was an unconfirmed way in. The tool now PROPOSES: the package is validated,
kept here for a bounded time and shown to the person as a card under the
answer; only the card's own button installs it (``proposal_service``).

The HITL machinery cannot carry this question: the skill generator runs in the
response node's isolated runner, whose drafts never reach the graph. A card
the person clicks works wherever the answer is shown.

What the person approves is exactly what was proposed:

- the record keeps the files it was validated on, and nothing else can
  install under its id;
- a replacement names the version it replaces (``replaces``, a fingerprint of
  the installed text files): if the skill changed since, the install refuses
  rather than overwrite a version the card never described;
- the card states what a replacement adds, changes and removes.

A proposal lives in Redis under the conversation family: it is a question the
conversation asked, and a reset forgets it with the card. An account holds at
most ``skill_proposals_max_per_user`` live proposals — the oldest makes room.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal, TypedDict

from src.core.constants import (
    SKILL_PROPOSAL_INDEX_KEY_PREFIX,
    SKILL_PROPOSAL_KEY_PREFIX,
    SKILLS_IMPORT_TEXT_EXTENSIONS,
)
from src.domains.shared.pending_cards import PendingCards
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

ProposalStatus = Literal["pending", "installed"]
#: A stored status read back as the vocabulary (a KeyError refuses the record).
_STATUS_OF: Final[dict[str, ProposalStatus]] = {"pending": "pending", "installed": "installed"}

#: The message-metadata key the chat reads proposal cards from (done chunk and archive).
SKILL_PROPOSALS_METADATA_KEY: Final = "skill_proposals"

#: The manifest opens the card's file list; everything else follows by path.
_MANIFEST: Final = "SKILL.md"


@dataclass(frozen=True)
class ProposalChanges:
    """What a replacement does to the installed skill, file by file.

    Attributes:
        added: Paths the installed skill does not have.
        modified: Paths whose text differs.
        removed: Text files the installed skill has and the proposal drops —
            their content is lost. A binary asset is never listed: the import
            carries it over.
    """

    added: tuple[str, ...]
    modified: tuple[str, ...]
    removed: tuple[str, ...]


class ProposalFile(TypedDict):
    """One file of the card: its path and size, never its content."""

    path: str
    size: int


class ProposalChangesCard(TypedDict):
    """The card's statement of a replacement."""

    added: list[str]
    modified: list[str]
    removed: list[str]


class ProposalCard(TypedDict):
    """What the chat shows under the answer — the same shape live and after a reload."""

    id: str
    name: str
    description: str
    replaces: bool
    files: list[ProposalFile]
    changes: ProposalChangesCard | None
    expires_at: str


@dataclass(frozen=True)
class SkillProposal:
    """A validated skill package, waiting for the person's click.

    Attributes:
        id: Opaque identifier (hex), unique per proposal.
        owner_id: The account it was written for.
        name: The skill's frontmatter name.
        description: Its description, as the card shows it.
        files: Relative path → text content; emptied once installed.
        sizes: Relative path → UTF-8 size in bytes; kept after the install.
        created_at: ISO-8601 UTC instant of the proposal.
        expires_at: ISO-8601 UTC instant after which it no longer exists.
        replaces: Fingerprint of the installed skill it replaces, None for a
            new skill.
        changes: What the replacement does, None for a new skill.
        status: ``pending`` until the person installs it.
    """

    id: str
    owner_id: str
    name: str
    description: str
    files: dict[str, str]
    sizes: dict[str, int]
    created_at: str
    expires_at: str
    replaces: str | None
    changes: ProposalChanges | None
    status: ProposalStatus = "pending"

    def to_json(self) -> str:
        """The stored record (every field — ``from_json`` reads them all back)."""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> SkillProposal | None:
        """Read a stored record back; None when it is not one (never raises).

        Args:
            raw: The stored JSON.

        Returns:
            The proposal, or None for anything unreadable.
        """
        try:
            data = json.loads(raw)
            changes = data["changes"]
            proposal = cls(
                id=_str(data["id"]),
                owner_id=_str(data["owner_id"]),
                name=_str(data["name"]),
                description=_str(data["description"]),
                files={_str(k): _str(v) for k, v in dict(data["files"]).items()},
                sizes={_str(k): int(v) for k, v in dict(data["sizes"]).items()},
                created_at=_str(data["created_at"]),
                expires_at=_str(data["expires_at"]),
                replaces=None if data["replaces"] is None else _str(data["replaces"]),
                changes=None if changes is None else _changes(changes),
                status=_STATUS_OF[data["status"]],
            )
        except ValueError, TypeError, KeyError, AttributeError:
            return None
        return proposal

    def installed(self) -> SkillProposal:
        """The same proposal once installed: its contents are no longer needed."""
        return replace(self, status="installed", files={})

    def to_card(self) -> ProposalCard:
        """The card under the answer: what the person decides on, never a file's content."""
        paths = sorted(self.sizes, key=lambda path: (path != _MANIFEST, path))
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "replaces": self.replaces is not None,
            "files": [{"path": path, "size": self.sizes[path]} for path in paths],
            "changes": (
                None
                if self.changes is None
                else {
                    "added": list(self.changes.added),
                    "modified": list(self.changes.modified),
                    "removed": list(self.changes.removed),
                }
            ),
            "expires_at": self.expires_at,
        }


def _str(value: Any) -> str:
    """A stored string, or a refusal of the record."""
    if not isinstance(value, str):
        raise TypeError("not a string")
    return value


def _changes(data: Any) -> ProposalChanges:
    """Stored changes, read back as tuples of strings."""
    return ProposalChanges(
        added=tuple(_str(p) for p in data["added"]),
        modified=tuple(_str(p) for p in data["modified"]),
        removed=tuple(_str(p) for p in data["removed"]),
    )


def _normalised(text: str) -> str:
    """The text as compared: a package written on Windows reads back with CRLF."""
    return text.replace("\r\n", "\n")


def package_fingerprint(files: Mapping[str, str]) -> str:
    """One digest of a text package — paths and contents, in no particular order.

    Args:
        files: Relative path → text content.

    Returns:
        A SHA-256 hex digest.
    """
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(_normalised(files[path]).encode("utf-8")).digest())
    return digest.hexdigest()


def read_text_package(skill_dir: Path) -> dict[str, str]:
    """The text files of an installed skill, as a proposal would carry them.

    Blocking (disk): call through ``asyncio.to_thread``.

    Args:
        skill_dir: The installed skill's folder.

    Returns:
        Relative POSIX path → text; empty when the folder does not exist. A
        binary asset is left out: the import carries it over, it is never lost.
    """
    if not skill_dir.is_dir():
        return {}
    package: dict[str, str] = {}
    for path in sorted(skill_dir.rglob("*")):
        # A link is never followed: it could name a file outside the skill.
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in SKILLS_IMPORT_TEXT_EXTENSIONS:
            continue
        relative = path.relative_to(skill_dir).as_posix()
        package[relative] = path.read_bytes().decode("utf-8", errors="replace")
    return package


def describe_changes(current: Mapping[str, str], incoming: Mapping[str, str]) -> ProposalChanges:
    """What installing ``incoming`` over ``current`` does, file by file.

    Args:
        current: The installed skill's text files.
        incoming: The proposal's files.

    Returns:
        Added, modified and removed paths, each sorted.
    """
    shared = current.keys() & incoming.keys()
    return ProposalChanges(
        added=tuple(sorted(incoming.keys() - current.keys())),
        modified=tuple(
            sorted(p for p in shared if _normalised(current[p]) != _normalised(incoming[p]))
        ),
        removed=tuple(sorted(current.keys() - incoming.keys())),
    )


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

#: Save one proposal, keeping at most ARGV[5] live per account, atomically.
#: KEYS[1] the account's index (members scored by their expiry), KEYS[2] the
#: proposal. ARGV: id, record, ttl, now (epoch s), cap, the account's
#: proposal-key prefix. Expired members leave the index first, so a dead
#: proposal never costs a live one its place; the oldest live ones make room.
_SAVE_SCRIPT: Final = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[4])
local excess = redis.call('ZCARD', KEYS[1]) - tonumber(ARGV[5]) + 1
if excess > 0 then
  local evicted = redis.call('ZPOPMIN', KEYS[1], excess)
  for i = 1, #evicted, 2 do
    redis.call('DEL', ARGV[6] .. evicted[i])
  end
else
  excess = 0
end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
redis.call('ZADD', KEYS[1], tonumber(ARGV[4]) + tonumber(ARGV[3]), ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return excess
"""


def _owner_prefix(owner_id: str) -> str:
    """The prefix of every proposal key of one account."""
    return f"{SKILL_PROPOSAL_KEY_PREFIX}:{owner_id}:"


def proposal_key(owner_id: str, proposal_id: str) -> str:
    """Where one proposal is stored — under its owner, so no other account reaches it."""
    return f"{_owner_prefix(owner_id)}{proposal_id}"


def index_key(owner_id: str) -> str:
    """The account's live proposals, scored by expiry."""
    return f"{SKILL_PROPOSAL_INDEX_KEY_PREFIX}:{owner_id}"


class ProposalStore:
    """The proposals of every account, in Redis, each with its lifetime."""

    def __init__(self, redis: Any) -> None:
        """Bind the store to a client returning strings (``decode_responses``).

        Args:
            redis: The cache client.
        """
        self._redis = redis

    async def save(
        self, proposal: SkillProposal, *, ttl_seconds: int, max_per_owner: int, now: float
    ) -> int:
        """Keep a proposal for ``ttl_seconds``, making room among its owner's.

        Args:
            proposal: The validated proposal.
            ttl_seconds: How long it may be installed.
            max_per_owner: How many live proposals an account keeps.
            now: The current epoch, in seconds.

        Returns:
            How many older proposals made room for it.

        Raises:
            Exception: Whatever the cache raised — a proposal nobody can install
                must never be announced.
        """
        evicted = await self._redis.eval(
            _SAVE_SCRIPT,
            2,
            index_key(proposal.owner_id),
            proposal_key(proposal.owner_id, proposal.id),
            proposal.id,
            proposal.to_json(),
            ttl_seconds,
            int(now),
            max_per_owner,
            _owner_prefix(proposal.owner_id),
        )
        return int(evicted or 0)

    async def load(self, owner_id: str, proposal_id: str) -> SkillProposal | None:
        """One of the account's proposals; None when it expired, never existed or is another's.

        Args:
            owner_id: The account asking.
            proposal_id: The proposal's id.

        Returns:
            The proposal, or None.
        """
        raw = await self._redis.get(proposal_key(owner_id, proposal_id))
        if raw is None:
            return None
        proposal = SkillProposal.from_json(raw)
        if proposal is None or proposal.owner_id != owner_id or proposal.id != proposal_id:
            return None
        return proposal

    async def mark_installed(self, proposal: SkillProposal) -> bool:
        """Record the install on the proposal, for what is left of its life.

        Args:
            proposal: The installed proposal.

        Returns:
            False when it expired meanwhile (the install stands; nothing to record).
        """
        stored = await self._redis.set(
            proposal_key(proposal.owner_id, proposal.id),
            proposal.installed().to_json(),
            xx=True,
            keepttl=True,
        )
        return bool(stored)


# ---------------------------------------------------------------------------
# The card under the answer
# ---------------------------------------------------------------------------

_pending_proposals: PendingCards[SkillProposal] = PendingCards(SKILL_PROPOSALS_METADATA_KEY)


def queue_proposal_card(conversation_id: str, proposal: SkillProposal) -> None:
    """Show the proposal under the answer being written for this conversation.

    Args:
        conversation_id: The conversation's thread id.
        proposal: The saved proposal.
    """
    _pending_proposals.add(conversation_id, proposal)


def attach_archived_proposals(metadata: dict[str, Any], conversation_id: str) -> None:
    """Copy the queued cards into the archived message (peek: the done chunk still needs them).

    Args:
        metadata: The assistant message metadata (mutated in place).
        conversation_id: The conversation's thread id.
    """
    pending = _pending_proposals.peek(conversation_id)
    if pending:
        metadata[SKILL_PROPOSALS_METADATA_KEY] = [p.to_card() for p in pending]


def attach_done_proposals(metadata: dict[str, Any], conversation_id: str) -> None:
    """Move the queued cards into the done chunk (take: the queue is freed).

    Args:
        metadata: The done-chunk metadata (mutated in place).
        conversation_id: The conversation's thread id.
    """
    pending = _pending_proposals.take(conversation_id)
    if pending:
        metadata[SKILL_PROPOSALS_METADATA_KEY] = [p.to_card() for p in pending]
