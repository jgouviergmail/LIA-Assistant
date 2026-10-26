"""Native SQL/session/Redis public delivery: frozen audience and one accounted batch."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.users.models import User
from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.messages import MailboxScope, MessageStatusRequest
from src.domains.world.public_models import PublicMessageRequest
from src.domains.world.public_translation import TranslatedBatch
from src.domains.world.tickets import cookie_binding
from tests.integration.world.test_messaging import MessagingFixture
from tests.integration.world.test_messaging import messaging_fixture as messaging_fixture

pytestmark = pytest.mark.integration


async def request(fixture: MessagingFixture, consent: bool = False) -> PublicMessageRequest:
    _, now = await fixture.service.world.read()
    return PublicMessageRequest(
        **fixture.scopes[0].model_dump(),
        audience="public",
        id=str(uuid4()),
        created_at=now,
        text="Bonjour à tous !",
        translation_consent=consent,
    )


async def test_public_is_frozen_idempotent_and_has_no_newcomer_history(
    messaging_fixture: MessagingFixture,
) -> None:
    f = messaging_fixture
    payload = await request(f)
    accepted = await f.service.public.send(f.cookies[0], str(f.people[0].id), payload)
    assert accepted.ack.status == "delivered" and accepted.job is None
    for i in range(3):
        view = await f.service.read(f.cookies[i], str(f.people[i].id), f.scopes[i])
        assert view.messages == [] and len(view.public_messages) == 1
        assert view.public_messages[0].text == payload.text
        assert all(str(p.id) not in view.model_dump_json() for p in f.people)
    # Re-entering the same account gets a fresh public actor, not an old broadcast subscription.
    authority = Authority(Limits())
    owner = str(f.people[2].id)

    def rejoin(state, now):
        authority.leave(state, owner, f.scopes[2].controller)
        authority.join(
            state,
            Identity(owner, "New arrival", "fr", cookie_binding(f.cookies[2])),
            "new-controller-token",
            now,
        )

    state, _ = await f.service.world.update(rejoin)
    newer = MailboxScope(epoch=state.epoch, controller=state.actors[owner].controller)
    duplicate = await f.service.public.send(f.cookies[0], str(f.people[0].id), payload)
    assert duplicate.job is None
    assert (await f.service.read(f.cookies[2], owner, newer)).public_messages == []


async def test_public_translates_once_for_a_shared_language_and_bills_only_the_sender(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine
) -> None:
    f = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        for person in f.people[1:]:
            row = await db.get(User, person.id)
            assert row is not None
            row.language = "en"
        await db.commit()
    calls = []

    async def translate(text, *, source, targets, user_id, request_id):
        calls.append((targets, user_id))
        return TranslatedBatch({"en": "Hello everyone!"}, TokenSummaryDTO(50, 20, 0, 0.001, 0))

    f.service.public.worker.translate = translate
    accepted = await f.service.public.send(
        f.cookies[0], str(f.people[0].id), await request(f, True)
    )
    assert accepted.job is not None
    before = await f.service.read(f.cookies[1], str(f.people[1].id), f.scopes[1])
    assert before.public_messages[0].text is None
    await accepted.job
    assert calls == [(("en",), f.people[0].id)]
    for i in [1, 2]:
        view = await f.service.read(f.cookies[i], str(f.people[i].id), f.scopes[i])
        assert view.public_messages[0].text == "Hello everyone!"
        assert view.public_messages[0].receipt is None
    own = await f.service.read(f.cookies[0], str(f.people[0].id), f.scopes[0])
    assert own.public_messages[0].receipt is not None
    status = await f.service.status(
        f.cookies[0],
        str(f.people[0].id),
        MessageStatusRequest(**f.scopes[0].model_dump(), id=accepted.ack.id),
    )
    assert status.status == "delivered"


async def test_corrupt_public_cache_does_not_break_private_correspondence(
    messaging_fixture: MessagingFixture,
) -> None:
    f = messaging_fixture
    await f.service.send(f.cookies[0], str(f.people[0].id), await f.request("Still private"))
    await f.service.world.redis.set(
        f.service.public.mailbox.inbox_key(str(f.people[1].id)), "malformed", ex=60
    )
    view = await f.service.read(f.cookies[1], str(f.people[1].id), f.scopes[1])
    assert view.messages[0].text == "Still private"
    assert not view.public_available and view.public_messages == []


async def test_public_blocks_and_private_studios_are_excluded_and_cannot_publish(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine
) -> None:
    from src.domains.peers.models import PeerBlock
    from src.domains.world.collision import _HOME, fits

    f = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        db.add(PeerBlock(blocker_id=f.people[1].id, blocked_id=f.people[0].id))
        await db.commit()

    # The authored private-home geometry, not an invented magic position.
    def enter_home(state, now):
        point = next(
            {"x": _HOME.x + x / 2, "y": _HOME.y + y / 2}
            for x in range(2, int(_HOME.width * 2) - 1)
            for y in range(2, int(_HOME.height * 2) - 1)
            if fits(_HOME.x + x / 2, _HOME.y + y / 2)
        )
        state.actors[str(f.people[2].id)].position = point

    await f.service.world.update(enter_home)
    await f.service.public.send(f.cookies[0], str(f.people[0].id), await request(f))
    assert (
        await f.service.read(f.cookies[1], str(f.people[1].id), f.scopes[1])
    ).public_messages == []
    assert (
        await f.service.read(f.cookies[2], str(f.people[2].id), f.scopes[2])
    ).public_messages == []
    _, now = await f.service.world.read()
    payload = PublicMessageRequest(
        **f.scopes[2].model_dump(),
        audience="public",
        id=str(uuid4()),
        created_at=now,
        text="Private studio",
    )
    with pytest.raises(ValueError):
        await f.service.public.send(f.cookies[2], str(f.people[2].id), payload)


async def test_public_erasure_finds_bodies_even_when_the_receivers_index_was_evicted(
    messaging_fixture: MessagingFixture,
) -> None:
    from src.domains.world.lifecycle import purge_world_account

    f = messaging_fixture
    payload = await request(f)
    await f.service.public.send(f.cookies[0], str(f.people[0].id), payload)
    mailbox = f.service.public.mailbox
    redis = f.service.world.redis
    await redis.delete(mailbox.inbox_key(str(f.people[1].id)))
    assert await redis.exists(mailbox.body_key(payload.id))
    await purge_world_account(redis, str(f.people[1].id))
    assert not await redis.exists(mailbox.body_key(payload.id))


async def test_public_audience_cannot_be_broadened_by_a_late_store_transition(
    messaging_fixture: MessagingFixture,
) -> None:
    f = messaging_fixture
    payload = await request(f)
    await f.service.public.send(f.cookies[0], str(f.people[0].id), payload)
    context = await f.service.access.context(f.cookies[0], str(f.people[0].id), f.scopes[0])

    def change(message, state, now):
        message.recipients.clear()

    with pytest.raises(ValueError):
        await f.service.public.mailbox.change(payload.id, context.scope, change)


async def test_foreign_audience_requires_consent_before_any_spend_or_staging(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine
) -> None:
    f = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        row = await db.get(User, f.people[1].id)
        assert row is not None
        row.language = "en"
        await db.commit()
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("no provider call permitted")

    f.service.public.worker.translate = forbidden
    payload = await request(f)
    with pytest.raises(ValueError, match="consent"):
        await f.service.public.send(f.cookies[0], str(f.people[0].id), payload)
    assert not calls
    assert not await f.service.world.redis.exists(f.service.public.mailbox.body_key(payload.id))


async def test_late_block_drops_one_receiver_without_another_provider_call(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine
) -> None:
    import asyncio

    from src.domains.peers.models import PeerBlock

    f = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        for person in f.people[1:]:
            row = await db.get(User, person.id)
            assert row is not None
            row.language = "en"
        await db.commit()
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def translate(text, *, source, targets, user_id, request_id):
        calls.append(targets)
        entered.set()
        await release.wait()
        return TranslatedBatch({"en": "Hello everyone!"}, TokenSummaryDTO(50, 20, 0, 0.001, 0))

    f.service.public.worker.translate = translate
    accepted = await f.service.public.send(
        f.cookies[0], str(f.people[0].id), await request(f, True)
    )
    assert accepted.job is not None
    task = asyncio.create_task(accepted.job)
    await asyncio.wait_for(entered.wait(), 3)
    async with async_sessionmaker(async_engine)() as db:
        db.add(PeerBlock(blocker_id=f.people[1].id, blocked_id=f.people[0].id))
        await db.commit()
    release.set()
    await task
    blocked = await f.service.read(f.cookies[1], str(f.people[1].id), f.scopes[1])
    other = await f.service.read(f.cookies[2], str(f.people[2].id), f.scopes[2])
    assert blocked.public_messages == []
    assert other.public_messages[0].text == "Hello everyone!"
    assert calls == [("en",)]


@pytest.mark.parametrize("change", ["language", "controller"])
async def test_late_identity_change_never_receives_an_old_translation(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine, change: str
) -> None:
    f = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        row = await db.get(User, f.people[1].id)
        assert row is not None
        row.language = "en"
        await db.commit()
    calls = []

    async def translate(text, *, source, targets, user_id, request_id):
        calls.append(targets)
        if change == "language":
            async with async_sessionmaker(async_engine)() as db:
                row = await db.get(User, f.people[1].id)
                assert row is not None
                row.language = "de"
                await db.commit()
        else:

            def take_over(state, now):
                state.actors[str(f.people[1].id)].controller = "replacement-controller-token"

            await f.service.world.update(take_over)
        return TranslatedBatch({"en": "Hello!"}, TokenSummaryDTO(5, 2, 0, 0.001, 0))

    f.service.public.worker.translate = translate
    accepted = await f.service.public.send(
        f.cookies[0], str(f.people[0].id), await request(f, True)
    )
    assert accepted.job is not None
    await accepted.job
    scope = (
        f.scopes[1]
        if change == "language"
        else MailboxScope(epoch=f.scopes[1].epoch, controller="replacement-controller-token")
    )
    view = await f.service.read(f.cookies[1], str(f.people[1].id), scope)
    assert view.public_messages[0].text is None
    assert view.public_messages[0].status == "unavailable"
    assert len(calls) == 1


async def test_failed_public_translation_is_not_retried_by_replaying_the_intent(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine
) -> None:
    f = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        row = await db.get(User, f.people[1].id)
        assert row is not None
        row.language = "en"
        await db.commit()
    calls = []

    async def translate(*args, **kwargs):
        calls.append(True)
        raise ValueError("malformed_provider_json")

    f.service.public.worker.translate = translate
    payload = await request(f, True)
    accepted = await f.service.public.send(f.cookies[0], str(f.people[0].id), payload)
    assert accepted.job is not None
    await accepted.job
    replay = await f.service.public.send(f.cookies[0], str(f.people[0].id), payload)
    # The shared acknowledgment intentionally uses its existing three-state contract;
    # the detailed translation failure belongs to the private mailbox projection.
    assert replay.job is None and replay.ack.status == "uncertain"
    view = await f.service.read(f.cookies[1], str(f.people[1].id), f.scopes[1])
    assert view.public_messages[0].text is None
    assert view.public_messages[0].status == "failed"
    assert len(calls) == 1
