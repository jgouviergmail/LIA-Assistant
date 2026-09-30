"""Integration: the skill proposal store against a real Redis (ADR-327).

The unit tests run the store on a double that knows nothing of Lua; this one
runs the save script itself — the cap, the eviction of the oldest, the pruning
of expired members — and the ``KEEPTTL`` of an install, where a call the double
accepts and Redis refuses cannot stay green.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.skills.proposals import ProposalStore, SkillProposal, index_key, proposal_key

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as exc:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {exc}")
    yield redis
    await redis.aclose()


@pytest.fixture
async def owner(redis_client: Redis) -> AsyncIterator[str]:
    owner_id = str(uuid.uuid4())
    yield owner_id
    keys = [key async for key in redis_client.scan_iter(f"skill_proposal*{owner_id}*")]
    if keys:
        await redis_client.delete(*keys)


def _proposal(owner_id: str, proposal_id: str) -> SkillProposal:
    return SkillProposal(
        id=proposal_id,
        owner_id=owner_id,
        name="ma-skill",
        description="Useful.",
        files={"SKILL.md": "manifest"},
        sizes={"SKILL.md": 8},
        created_at="2026-09-30T10:00:00+00:00",
        expires_at="2026-10-01T10:00:00+00:00",
        replaces=None,
        changes=None,
    )


@pytest.mark.asyncio
async def test_the_oldest_live_proposal_makes_room(redis_client: Redis, owner: str) -> None:
    store = ProposalStore(redis_client)
    now = time.time()
    ids = [uuid.uuid4().hex for _ in range(3)]

    evicted = []
    for offset, proposal_id in enumerate(ids):
        evicted.append(
            await store.save(
                _proposal(owner, proposal_id), ttl_seconds=600, max_per_owner=2, now=now + offset
            )
        )

    assert evicted == [0, 0, 1]
    assert await store.load(owner, ids[0]) is None
    assert await store.load(owner, ids[1]) is not None
    assert await store.load(owner, ids[2]) is not None
    assert await redis_client.zcard(index_key(owner)) == 2


@pytest.mark.asyncio
async def test_an_expired_member_never_costs_a_live_one_its_place(
    redis_client: Redis, owner: str
) -> None:
    store = ProposalStore(redis_client)
    now = time.time()
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    await store.save(_proposal(owner, first), ttl_seconds=60, max_per_owner=1, now=now)

    # Saved as if 61 s later: the first one's index member has expired.
    evicted = await store.save(
        _proposal(owner, second), ttl_seconds=60, max_per_owner=1, now=now + 61
    )

    assert evicted == 0, "an expired member was counted as a live proposal"
    assert await redis_client.zrange(index_key(owner), 0, -1) == [second]


@pytest.mark.asyncio
async def test_a_proposal_lives_its_ttl_and_the_install_keeps_it(
    redis_client: Redis, owner: str
) -> None:
    store = ProposalStore(redis_client)
    proposal = _proposal(owner, uuid.uuid4().hex)
    await store.save(proposal, ttl_seconds=600, max_per_owner=5, now=time.time())
    ttl_before = await redis_client.ttl(proposal_key(owner, proposal.id))

    assert await store.mark_installed(proposal) is True

    ttl_after = await redis_client.ttl(proposal_key(owner, proposal.id))
    assert 0 < ttl_after <= ttl_before <= 600
    stored = await store.load(owner, proposal.id)
    assert stored is not None and stored.status == "installed" and stored.files == {}


@pytest.mark.asyncio
async def test_an_install_on_an_expired_proposal_writes_nothing(
    redis_client: Redis, owner: str
) -> None:
    store = ProposalStore(redis_client)
    proposal = _proposal(owner, uuid.uuid4().hex)

    assert await store.mark_installed(proposal) is False
    assert await redis_client.exists(proposal_key(owner, proposal.id)) == 0


@pytest.mark.asyncio
async def test_another_account_never_reads_it(redis_client: Redis, owner: str) -> None:
    store = ProposalStore(redis_client)
    proposal = _proposal(owner, uuid.uuid4().hex)
    await store.save(proposal, ttl_seconds=600, max_per_owner=5, now=time.time())

    assert await store.load(str(uuid.uuid4()), proposal.id) is None
    assert await store.load(owner, proposal.id) == proposal
