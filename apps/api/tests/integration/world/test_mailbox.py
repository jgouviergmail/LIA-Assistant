"""Real Redis private content, expiry, bounded replay and stale-writer fencing."""

from uuid import uuid4

import pytest

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.mailbox import WorldMailbox
from src.domains.world.message_content import MessageAddress, MessageVariant, StoredMessage
from src.domains.world.messages import MESSAGE_TTL, MessageScope
from src.domains.world.store import WorldStore

pytestmark = pytest.mark.integration


async def setup_mailbox(redis_world):
    world = WorldStore(redis_world, namespace="test-" + uuid4().hex, ttl=3600)
    identity = [
        Identity(str(uuid4()), name, "fr", name) for name in ["Sender", "Recipient", "Stranger"]
    ]
    authority = Authority(Limits())

    def join(state, now):
        for item in identity:
            authority.join(state, item, item.alias + "-controller-token", now)

    state, _ = await world.update(join)
    _, now = await world.read()
    sender, recipient, _ = [state.actors[item.account_id] for item in identity]
    scope = MessageScope(
        sender.account_id,
        sender.binding,
        sender.controller,
        state.epoch,
        frozenset(state.actors),
        frozenset(),
        600,
    )
    message = StoredMessage(
        id=str(uuid4()),
        epoch=state.epoch,
        sender=MessageAddress(
            account=sender.account_id, public_id=sender.public_id, alias=sender.alias
        ),
        recipient=MessageAddress(
            account=recipient.account_id, public_id=recipient.public_id, alias=recipient.alias
        ),
        original="private inert message",
        source_language="fr",
        created_at=now,
        expires_at=now + MESSAGE_TTL,
    )
    return WorldMailbox(world), scope, message, identity


async def test_body_never_enters_world_snapshots_and_duplicate_stage_is_idempotent(redis_world):
    mailbox, scope, message, _ = await setup_mailbox(redis_world)
    assert await mailbox.stage(message, scope)
    assert not await mailbox.stage(message, scope)
    assert "private inert" not in (await mailbox.world.read())[0].model_dump_json()
    messages = await mailbox.inbox(scope)
    assert [item.id for item in messages] == [message.id]
    assert 0 < await redis_world.ttl(mailbox.body_key(message.id)) <= MESSAGE_TTL
    with pytest.raises(ValueError):
        await mailbox.stage(message.model_copy(update={"original": "changed text"}), scope)


async def test_takeover_and_epoch_change_refuse_late_content_updates(redis_world):
    mailbox, scope, message, _ = await setup_mailbox(redis_world)
    await mailbox.stage(message, scope)
    await mailbox.world.update(
        lambda state, now: setattr(
            state.actors[scope.account], "controller", "new-controller-token"
        )
    )
    with pytest.raises(ValueError, match="world_message_unavailable"):
        await mailbox.change(message.id, scope, lambda content, state, now: None)
    stored = StoredMessage.model_validate_json(await redis_world.get(mailbox.body_key(message.id)))
    assert stored.original == message.original


async def test_unrelated_actor_cannot_read_or_change_another_mailbox_message(redis_world):
    from dataclasses import replace

    mailbox, scope, message, people = await setup_mailbox(redis_world)
    await mailbox.stage(message, scope)
    state, _ = await mailbox.world.read()
    stranger = state.actors[people[2].account_id]
    outsider = replace(
        scope, account=stranger.account_id, binding=stranger.binding, controller=stranger.controller
    )
    assert await mailbox.inbox(outsider) == []
    with pytest.raises(ValueError, match="world_message_unavailable"):
        await mailbox.change(message.id, outsider, lambda content, state, now: None)


async def test_client_message_id_cannot_impersonate_an_unrelated_account_cleanup_key(redis_world):
    import fnmatch

    from src.infrastructure.cache.key_families import scan_patterns_for

    mailbox, scope, message, people = await setup_mailbox(redis_world)
    message.id = people[2].account_id
    await mailbox.stage(message, scope)
    assert not any(
        fnmatch.fnmatchcase(mailbox.body_key(message.id), pattern)
        for pattern in scan_patterns_for(people[2].account_id)
    )


async def test_corrupt_cached_body_is_unavailable_without_reflecting_private_content(redis_world):
    from src.domains.world.store import WorldUnavailable

    mailbox, scope, message, _ = await setup_mailbox(redis_world)
    await mailbox.stage(message, scope)
    await redis_world.set(mailbox.body_key(message.id), '{"original":"PRIVATE_CORRUPT"}')
    with pytest.raises(WorldUnavailable) as error:
        await mailbox.inbox(scope)
    assert "PRIVATE_CORRUPT" not in str(error.value)


async def test_mutation_is_validated_before_commit_and_preserves_the_previous_body(redis_world):
    from src.domains.world.store import WorldUnavailable

    mailbox, scope, message, _ = await setup_mailbox(redis_world)
    await mailbox.stage(message, scope)
    with pytest.raises(WorldUnavailable):
        await mailbox.change(
            message.id,
            scope,
            lambda content, state, now: setattr(content, "original", "\u202ehidden"),
        )
    assert (await mailbox.inbox(scope))[0].original == message.original


async def test_pending_translations_reserve_their_future_content_before_dispatch(redis_world):
    from src.domains.world.store import WorldUnavailable

    mailbox, scope, message, _ = await setup_mailbox(redis_world)
    for language in ("en", "de"):
        message.variants[language] = MessageVariant(
            job_id=str(uuid4()),
            payer=scope.account,
            status="pending",
            deadline=message.created_at + 60,
        )
    await mailbox.stage(message, scope)

    def third(content, state, now):
        content.variants["es"] = MessageVariant(
            job_id=str(uuid4()),
            payer=scope.account,
            status="pending",
            deadline=now + 60,
        )

    with pytest.raises(WorldUnavailable, match="world_translation_capacity"):
        await mailbox.change(message.id, scope, third)
    assert set((await mailbox.inbox(scope))[0].variants) == {"en", "de"}

    def finish(content, state, now):
        for variant in content.variants.values():
            variant.text, variant.status = "🙂" * 3000, "translated"

    assert await mailbox.change(message.id, scope, finish)
    assert all(
        variant.text == "🙂" * 3000 for variant in (await mailbox.inbox(scope))[0].variants.values()
    )


async def test_same_message_and_accounts_remain_independent_in_separate_worlds(redis_world):
    first, scope, message, _ = await setup_mailbox(redis_world)
    original, _ = await first.world.read()
    separate = WorldStore(redis_world, namespace="isolated-" + uuid4().hex, ttl=3600)

    def clone(state, now):
        # Stronger than ordinary random epochs: even an identical restored
        # snapshot must retain its configured instance boundary.
        state.epoch = original.epoch
        state.actors = {key: actor.model_copy(deep=True) for key, actor in original.actors.items()}

    await separate.update(clone)
    second = WorldMailbox(separate)
    other = message.model_copy(update={"original": "A separate private conversation"})
    assert await first.stage(message, scope)
    assert await second.stage(other, scope)
    assert [item.original for item in await first.inbox(scope)] == [message.original]
    assert [item.original for item in await second.inbox(scope)] == [other.original]
