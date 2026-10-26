"""A paid result is delivered only after its owned Redis publication succeeds."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.users.models import User
from src.domains.world.authority import Authority, Limits
from src.domains.world.message_attempts import MessageAttempts
from src.domains.world.messages import MessageStatusRequest
from src.domains.world.public_translation import TranslatedBatch
from tests.integration.world.test_messaging import MessagingFixture
from tests.integration.world.test_messaging import messaging_fixture as messaging_fixture
from tests.integration.world.test_public_messaging import request as public_request

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("audience", ["private", "public"])
@pytest.mark.parametrize("failure", ["timeout", "controller", "unacknowledged"])
async def test_unpublished_paid_result_never_reports_delivered_or_replays_the_provider(
    messaging_fixture: MessagingFixture,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    audience: str,
    failure: str,
) -> None:
    f = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        recipient = await db.get(User, f.people[1].id)
        assert recipient is not None
        recipient.language = "en"
        await db.commit()

    calls = []

    async def translate(text, *, source, targets, user_id, request_id):
        calls.append((targets, user_id))
        return TranslatedBatch({"en": "Hello everyone!"}, TokenSummaryDTO(50, 20, 0, 0.001, 0))

    if audience == "public":
        f.service.public.worker.translate = translate
        payload = await public_request(f, True)
        send = f.service.public.send
        mailbox = f.service.public.mailbox
    else:
        payload = await f.request()
        send = f.service.send
        mailbox = f.service.mailbox
    original_change = mailbox.change
    interrupted = False

    async def interrupt_publication(message, scope, change):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            if failure == "timeout":
                raise TimeoutError("inert publication interruption")
            if failure == "unacknowledged":
                return False
            account = str(f.people[0 if audience == "public" else 1].id)
            authority = Authority(Limits())
            await f.service.world.update(
                lambda state, now: authority.takeover(
                    state, account, "replacement-controller-token", now
                )
            )
            if audience == "public":
                f.scopes[0] = f.scopes[0].model_copy(
                    update={"controller": "replacement-controller-token"}
                )
        return await original_change(message, scope, change)

    monkeypatch.setattr(mailbox, "change", interrupt_publication)
    accepted = await send(f.cookies[0], str(f.people[0].id), payload)
    assert accepted.job is not None
    await accepted.job

    status = await f.service.status(
        f.cookies[0],
        str(f.people[0].id),
        MessageStatusRequest(**f.scopes[0].model_dump(), id=payload.id),
    )
    assert status.status == "uncertain"
    own = await f.service.read(f.cookies[0], str(f.people[0].id), f.scopes[0])
    if audience == "private":
        assert own.messages[0].receipt is None
    else:
        assert own.public_messages[0].receipt is None
    if failure != "controller" or audience == "private":
        duplicate = await send(f.cookies[0], str(f.people[0].id), payload)
        assert duplicate.ack.status == "uncertain" and duplicate.job is None
    assert (len(calls) if audience == "public" else f.translator.calls) == 1


async def test_paid_completion_waits_for_owned_publication_acknowledgement(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    from tests.integration.world.test_message_attempts import accounts

    sender, recipient, _ = await accounts(async_engine, committed_user_ids)
    repo = MessageAttempts("test-" + uuid4().hex)
    now = datetime.now(UTC)
    row, _ = await repo.enqueue(uuid4(), sender, recipient, "a" * 64, translated=True, now=now)
    assert await repo.mark_ready(row.id, row.token, now=now)
    assert await repo.start(row.id, row.token, now=now)
    assert await repo.finish(row.id, row.token, "succeeded", now=now)
    assert await repo.owned_status(row.id, sender, now=now) == "uncertain"
    assert await repo.status(row.id, row.token, now=now) == "uncertain"
    assert not await repo.mark_delivered(row.id, uuid4(), now=now)
    other = MessageAttempts("other-" + uuid4().hex)
    assert not await other.mark_delivered(row.id, row.token, now=now)
    assert await repo.mark_delivered(row.id, row.token, now=now)
    assert await repo.owned_status(row.id, sender, now=now) == "delivered"
    assert not await repo.mark_delivered(row.id, row.token, now=now)
    assert not await repo.finish(row.id, row.token, "uncertain", now=now)
    assert not await repo.start(row.id, row.token, now=now)


@pytest.mark.parametrize("audience", ["private", "public"])
async def test_sql_ack_timeout_preserves_the_translation_already_published_in_redis(
    messaging_fixture: MessagingFixture,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    audience: str,
) -> None:
    f = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        recipient = await db.get(User, f.people[1].id)
        assert recipient is not None
        recipient.language = "en"
        await db.commit()
    calls = []

    async def translate(text, *, source, targets, user_id, request_id):
        calls.append((targets, user_id))
        return TranslatedBatch({"en": "Hello everyone!"}, TokenSummaryDTO(50, 20, 0, 0.001, 0))

    async def timeout_acknowledgement(*args, **kwargs):
        raise TimeoutError("inert SQL acknowledgement interruption")

    if audience == "public":
        f.service.public.worker.translate = translate
        payload = await public_request(f, True)
        send = f.service.public.send
        attempts = f.service.public.attempts
    else:
        payload = await f.request()
        send = f.service.send
        attempts = f.service.attempts
    monkeypatch.setattr(attempts, "mark_delivered", timeout_acknowledgement)
    accepted = await send(f.cookies[0], str(f.people[0].id), payload)
    assert accepted.job is not None
    await accepted.job
    own = await f.service.read(f.cookies[0], str(f.people[0].id), f.scopes[0])
    incoming = await f.service.read(f.cookies[1], str(f.people[1].id), f.scopes[1])
    if audience == "public":
        assert own.public_messages[0].status == "translated"
        assert own.public_messages[0].receipt is not None
        assert incoming.public_messages[0].text == "Hello everyone!"
    else:
        assert own.messages[0].status == "translated"
        assert own.messages[0].receipt is not None
        assert incoming.messages[0].text == "PRIVATE_TRANSLATED_FIXTURE"
    duplicate = await send(f.cookies[0], str(f.people[0].id), payload)
    assert duplicate.ack.status == "uncertain" and duplicate.job is None
    assert (len(calls) if audience == "public" else f.translator.calls) == 1
