"""Proposing a skill written in the chat, and installing it at the person's click (ADR-327).

Two acts, two authors:

- :func:`propose` is the chat tool's: it validates the package exactly as the
  import would (``SkillImportService.validate_files``), writes nothing, states
  what a replacement changes, keeps the package for the day and queues its
  card under the answer;
- :func:`install` is the person's, from the card's button: one install at a
  time per proposal (an owner-token claim), refused when the skill it
  replaces changed since the card described it, then the ordinary chat import
  — recorded as an action of the person's (``shared/action_sink``), claimed
  after every refusal.

No database session is held across a Redis call (ADR-304): the proposal's
validation opens its own, the install runs on the route's.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import SKILL_PROPOSAL_CLAIM_KEY_PREFIX, SKILL_PROPOSAL_CLAIM_TTL_SECONDS
from src.core.exceptions import BaseAPIException
from src.domains.shared.action_sink import SKILL_PROPOSAL_INSTALL_CAPABILITY, recorded_action
from src.domains.skills.exceptions import ImportRefusalKind, import_refusal_kind
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.proposal_errors import (
    BUSY,
    DISABLED,
    INVALID,
    NAME_TAKEN,
    NOT_FOUND,
    QUOTA_REACHED,
    STALE,
    UNAVAILABLE,
    ProposalRefusal,
)
from src.domains.skills.proposals import (
    ProposalStore,
    SkillProposal,
    describe_changes,
    package_fingerprint,
    queue_proposal_card,
    read_text_package,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.locks.redis_claim import release_claim, try_claim
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: What an import refusal becomes on the card.
_INSTALL_REFUSALS: Final[dict[ImportRefusalKind, str]] = {
    "name_taken": NAME_TAKEN,
    "quota_reached": QUOTA_REACHED,
    "invalid": INVALID,
}


def _claim_key(owner_id: str, proposal_id: str) -> str:
    """The one install of a proposal in flight."""
    return f"{SKILL_PROPOSAL_CLAIM_KEY_PREFIX}:{owner_id}:{proposal_id}"


async def _installed_package(owner_id: str, name: str) -> dict[str, str] | None:
    """The text files of the person's own skill of that name, or None when they have none."""
    from src.domains.skills.cache import SkillsCache

    own = SkillsCache.get_exact(name, owner_id)
    if own is None:
        return None
    return await asyncio.to_thread(read_text_package, Path(own["source_path"]).parent)


async def propose(
    files: dict[str, str],
    *,
    owner_id: UUID,
    conversation_id: str,
    now: datetime | None = None,
    redis: Any = None,
) -> tuple[SkillProposal, int]:
    """Validate a package, keep it for the day and show its card under the answer.

    The caller has already refused what a chat edit may not touch (a system
    skill, a managed one, a disabled one — ``tools._resolve_edit_target``).

    Args:
        files: Relative path → text content, as the model sent them.
        owner_id: The account the skill is for.
        conversation_id: The conversation the card shows in.
        now: The current instant (a test's clock).
        redis: The cache client (a test's double); the application's by default.

    Returns:
        The saved proposal, and how many older ones made room for it.

    Raises:
        BaseAPIException: The import checks refused the package — its detail
            says why, for the model to fix the files.
        Exception: The proposal could not be kept (the cache failed): nothing
            was offered.
    """
    now = now or datetime.now(UTC)
    async with get_db_context() as db:
        skill = await SkillImportService(db).validate_files(files, owner_id=owner_id)
    name = str(skill["name"])
    current = await _installed_package(str(owner_id), name)
    ttl = settings.skill_proposal_ttl_seconds
    proposal = SkillProposal(
        id=uuid.uuid4().hex,
        owner_id=str(owner_id),
        name=name,
        description=str(skill.get("description") or ""),
        files=dict(files),
        sizes={path: len(text.encode("utf-8")) for path, text in files.items()},
        created_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=ttl)).isoformat(),
        replaces=None if current is None else package_fingerprint(current),
        changes=None if current is None else describe_changes(current, files),
    )
    store = ProposalStore(redis if redis is not None else await get_redis_cache())
    evicted = await store.save(
        proposal,
        ttl_seconds=ttl,
        max_per_owner=settings.skill_proposals_max_per_user,
        now=now.timestamp(),
    )
    queue_proposal_card(conversation_id, proposal)
    logger.info(
        "skill_proposed",
        proposal_id=proposal.id,
        skill_name=name,
        replaces=proposal.replaces is not None,
        files=len(files),
        evicted=evicted,
    )
    return proposal, evicted


async def read(owner_id: UUID, proposal_id: str, *, redis: Any = None) -> SkillProposal:
    """One of the account's proposals, as the card asks for it.

    Args:
        owner_id: The account asking.
        proposal_id: The proposal's id.
        redis: The cache client (a test's double).

    Returns:
        The proposal.

    Raises:
        ProposalRefusal: ``not_found`` or ``unavailable``.
    """
    try:
        store = ProposalStore(redis if redis is not None else await get_redis_cache())
        proposal = await store.load(str(owner_id), proposal_id)
    except Exception as exc:  # noqa: BLE001 — the cache failing is a refusal the card names
        logger.warning("skill_proposal_read_failed", error_type=type(exc).__name__)
        raise ProposalRefusal(UNAVAILABLE) from exc
    if proposal is None:
        raise ProposalRefusal(NOT_FOUND)
    return proposal


async def _already_installed(proposal: SkillProposal) -> bool:
    """Whether the person's skill already IS this proposal; refuse it when it moved.

    The installed text files equal the proposal's exactly once it was installed
    — by an earlier click whose record could not be updated, say: that is done,
    never a conflict. Anything else must be the version the card described.

    Raises:
        ProposalRefusal: ``stale`` when the skill it replaces changed since, or a
            skill of that name appeared.
    """
    current = await _installed_package(proposal.owner_id, proposal.name)
    installed = None if current is None else package_fingerprint(current)
    if installed is not None and installed == package_fingerprint(proposal.files):
        return True
    if installed != proposal.replaces:
        raise ProposalRefusal(STALE)
    return False


async def install(
    db: AsyncSession, owner_id: UUID, proposal_id: str, *, redis: Any = None
) -> SkillProposal:
    """Install a proposal from its card: the person's act.

    Installing twice answers what the first install did: the proposal says it
    is installed, and nothing runs again.

    Args:
        db: The route's session (the import registers the skill on it).
        owner_id: The person clicking.
        proposal_id: The proposal's id.
        redis: The cache client (a test's double).

    Returns:
        The installed proposal.

    Raises:
        ProposalRefusal: ``disabled``, ``not_found``, ``busy``, ``stale``,
            ``name_taken``, ``quota_reached``, ``invalid`` or ``unavailable``.
    """
    if not settings.skills_chat_import_enabled:
        raise ProposalRefusal(DISABLED)
    client = redis if redis is not None else await get_redis_cache()
    proposal = await read(owner_id, proposal_id, redis=client)
    if proposal.status == "installed":
        return proposal

    owner = str(owner_id)
    token = uuid.uuid4().hex
    key = _claim_key(owner, proposal_id)
    try:
        claimed = await try_claim(client, key, token, ttl_seconds=SKILL_PROPOSAL_CLAIM_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 — no claim, no install
        raise ProposalRefusal(UNAVAILABLE) from exc
    if not claimed:
        raise ProposalRefusal(BUSY)
    try:
        # Read again under the claim: an install that finished between the
        # first read and the claim answers as done, never runs twice.
        proposal = await read(owner_id, proposal_id, redis=client)
        if proposal.status == "installed":
            return proposal
        return await _install_claimed(db, owner_id, proposal, ProposalStore(client))
    finally:
        await release_claim(client, key, token)


async def _install_claimed(
    db: AsyncSession, owner_id: UUID, proposal: SkillProposal, store: ProposalStore
) -> SkillProposal:
    """The install itself, under the proposal's claim."""
    if await _already_installed(proposal):
        await _mark(store, proposal)
        return proposal.installed()
    service = SkillImportService(db)
    try:
        # Every refusal BEFORE the act is claimed (ADR-263 amendment): the
        # register records an install that was attempted, never one refused.
        await service.validate_files(proposal.files, owner_id=owner_id)
    except BaseAPIException as exc:
        raise ProposalRefusal(_INSTALL_REFUSALS[import_refusal_kind(exc)]) from exc

    started = time.perf_counter()
    async with recorded_action(
        user_id=owner_id,
        capability=SKILL_PROPOSAL_INSTALL_CAPABILITY,
        arguments={"target": proposal.name},
    ) as act:
        try:
            await service.import_files(proposal.files, owner_id=owner_id)
        except BaseAPIException as exc:
            # Lost to a concurrent change between the check and the write.
            raise ProposalRefusal(_INSTALL_REFUSALS[import_refusal_kind(exc)]) from exc
        act.succeeded = True

    await _mark(store, proposal)
    logger.info(
        "skill_proposal_installed",
        proposal_id=proposal.id,
        skill_name=proposal.name,
        replaced=proposal.replaces is not None,
        duration_ms=round((time.perf_counter() - started) * 1000),
    )
    return proposal.installed()


async def _mark(store: ProposalStore, proposal: SkillProposal) -> None:
    """Record the install on the proposal — best effort: the skill IS installed.

    A record that could not be updated leaves the next click to find the
    installed skill equal to the proposal (``_already_installed``).
    """
    try:
        await store.mark_installed(proposal)
    except Exception as exc:  # noqa: BLE001 — see the docstring
        logger.warning("skill_proposal_mark_failed", error_type=type(exc).__name__)
