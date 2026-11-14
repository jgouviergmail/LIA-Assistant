"""A proposed skill retains its runtime and cannot be written by a stopped invocation."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.domains.skills.proposals import (
    ProposalStatus,
    ProposalStore,
    SkillProposal,
    index_key,
    proposal_key,
)
from src.infrastructure.streaming.run_admission import owned_execution

pytestmark = pytest.mark.integration


@pytest.fixture
async def scoped_store(reserved: RunAdmission, redis_client: Redis) -> AsyncIterator[ProposalStore]:
    """Retire only records owned by this committed test account."""
    yield ProposalStore(redis_client)
    keys = [
        key async for key in redis_client.scan_iter(f"skill_proposal*{reserved.target.owner_id}*")
    ]
    if keys:
        await redis_client.delete(*keys)


def proposal_from_wire(admission: RunAdmission) -> SkillProposal:
    """Decode every source coordinate as an existing stored record would be read."""
    base = SkillProposal(
        id=uuid4().hex,
        owner_id=str(admission.target.owner_id),
        name="test-skill",
        description="Test",
        files={"SKILL.md": "test"},
        sizes={"SKILL.md": 4},
        created_at="2026-11-10T00:00:00+00:00",
        expires_at="2026-11-11T00:00:00+00:00",
        replaces=None,
        changes=None,
    )
    raw = json.loads(base.to_json())
    raw["runtime_id"] = str(admission.target.runtime_id)
    result = SkillProposal.from_json(json.dumps(raw))
    assert result is not None
    return result


async def test_stored_proposal_preserves_source_runtime(reserved: RunAdmission) -> None:
    proposal = proposal_from_wire(reserved)
    assert json.loads(proposal.to_json()).get("runtime_id") == str(reserved.target.runtime_id)


async def test_revoked_graph_cannot_publish_a_late_proposal(
    reserved: RunAdmission, redis_client: Redis
) -> None:
    proposal = proposal_from_wire(reserved)
    store = ProposalStore(redis_client)
    try:
        async with owned_execution(reserved) as authority:
            authority.revoked = True
            with pytest.raises(ExecutionRevoked):
                await store.save(proposal, ttl_seconds=60, max_per_owner=2, now=time.time())
        assert await store.load(proposal.owner_id, proposal.id) is None
    finally:
        await redis_client.delete(
            proposal_key(proposal.owner_id, proposal.id), index_key(proposal.owner_id)
        )


async def test_transition_cannot_change_the_origin_of_an_existing_proposal(
    reserved: RunAdmission, redis_client: Redis
) -> None:
    original = proposal_from_wire(reserved)
    other_target = replace(reserved.target, runtime_id=uuid4())
    other = proposal_from_wire(replace(reserved, target=other_target))
    changed = replace(other, id=original.id, status="installing", attempt_id=uuid4().hex)
    store = ProposalStore(redis_client)
    try:
        async with owned_execution(reserved):
            await store.save(original, ttl_seconds=60, max_per_owner=2, now=time.time())
        with pytest.raises(ValueError):
            await store.transition(original, changed)
        assert await store.load(original.owner_id, original.id) == original
    finally:
        await redis_client.delete(
            proposal_key(original.owner_id, original.id), index_key(original.owner_id)
        )


async def test_transition_compares_the_stored_runtime_not_only_the_supplied_pair(
    reserved: RunAdmission, scoped_store: ProposalStore
) -> None:
    original = proposal_from_wire(reserved)
    async with owned_execution(reserved):
        await scoped_store.save(original, ttl_seconds=60, max_per_owner=2, now=time.time())
    stale = replace(original, runtime_id=str(uuid4()))
    assert not await scoped_store.transition(stale, replace(stale, status="installed"))
    assert not await scoped_store.mark_installed(stale)
    assert await scoped_store.load(original.owner_id, original.id) == original


async def test_full_index_keeps_installing_and_unknown_claims(
    reserved: RunAdmission, scoped_store: ProposalStore, redis_client: Redis
) -> None:
    proposals = [proposal_from_wire(reserved) for _ in range(3)]
    protected: tuple[ProposalStatus, ...] = ("installing", "unknown")
    async with owned_execution(reserved):
        for offset, status in enumerate(protected):
            original = proposals[offset]
            await scoped_store.save(original, ttl_seconds=600, max_per_owner=2, now=time.time())
            changed = replace(original, status=status, attempt_id=uuid4().hex)
            assert await scoped_store.transition(original, changed)
        with pytest.raises(RuntimeError, match="proposal capacity"):
            await scoped_store.save(proposals[2], ttl_seconds=600, max_per_owner=2, now=time.time())
    assert await redis_client.zcard(index_key(proposals[0].owner_id)) == 2
    for original in proposals[:2]:
        assert await scoped_store.load(original.owner_id, original.id) is not None
    assert await scoped_store.load(proposals[2].owner_id, proposals[2].id) is None


async def test_retiring_one_runtime_preserves_other_origins_and_install_claims(
    reserved: RunAdmission, scoped_store: ProposalStore, redis_client: Redis
) -> None:
    source = proposal_from_wire(reserved)
    states: tuple[ProposalStatus, ...] = ("pending", "installing", "unknown", "installed")
    siblings = [replace(source, id=uuid4().hex, status=status) for status in states]
    other = replace(source, id=uuid4().hex, runtime_id=str(uuid4()))
    legacy = replace(source, id=uuid4().hex, runtime_id=None)
    for item in [*siblings, other, legacy]:
        await redis_client.set(proposal_key(item.owner_id, item.id), item.to_json(), ex=600)
        await redis_client.zadd(index_key(item.owner_id), {item.id: time.time() + 600})
    assert (
        await scoped_store.retire_runtime(reserved.target.owner_id, reserved.target.runtime_id) == 1
    )
    assert await scoped_store.load(source.owner_id, siblings[0].id) is None
    for item in [*siblings[1:], other, legacy]:
        assert await scoped_store.load(item.owner_id, item.id) == item
    assert (
        await scoped_store.retire_runtime(reserved.target.owner_id, reserved.target.runtime_id) == 0
    )
    assert (
        await scoped_store.retire_runtime(reserved.target.owner_id, reserved.target.owner_id) == 1
    )
    assert await scoped_store.load(legacy.owner_id, legacy.id) is None


async def test_install_claim_and_retirement_have_one_atomic_winner(
    reserved: RunAdmission, scoped_store: ProposalStore
) -> None:
    original = proposal_from_wire(reserved)
    async with owned_execution(reserved):
        await scoped_store.save(original, ttl_seconds=600, max_per_owner=2, now=time.time())
    attempt = replace(original, status="installing", attempt_id=uuid4().hex)
    removed, claimed = await asyncio.gather(
        scoped_store.retire_runtime(reserved.target.owner_id, reserved.target.runtime_id),
        scoped_store.transition(original, attempt),
    )
    assert (removed, claimed) in {(1, False), (0, True)}
    assert await scoped_store.load(original.owner_id, original.id) == (attempt if claimed else None)


async def test_short_new_offer_does_not_shorten_the_shared_index_lifetime(
    reserved: RunAdmission, scoped_store: ProposalStore, redis_client: Redis
) -> None:
    first, second = proposal_from_wire(reserved), proposal_from_wire(reserved)
    async with owned_execution(reserved):
        await scoped_store.save(first, ttl_seconds=600, max_per_owner=2, now=time.time())
        await scoped_store.save(second, ttl_seconds=30, max_per_owner=2, now=time.time())
    assert await redis_client.ttl(index_key(first.owner_id)) > 500


async def test_unreadable_record_is_not_evicted_to_claim_capacity(
    reserved: RunAdmission, scoped_store: ProposalStore, redis_client: Redis
) -> None:
    first, second = proposal_from_wire(reserved), proposal_from_wire(reserved)
    async with owned_execution(reserved):
        await scoped_store.save(first, ttl_seconds=600, max_per_owner=1, now=time.time())
        await redis_client.set(proposal_key(first.owner_id, first.id), "3", keepttl=True)
        with pytest.raises(RuntimeError, match="proposal capacity"):
            await scoped_store.save(second, ttl_seconds=600, max_per_owner=1, now=time.time())
    assert await redis_client.get(proposal_key(first.owner_id, first.id)) == "3"
