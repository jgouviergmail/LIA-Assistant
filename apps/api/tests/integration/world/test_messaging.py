"""Native sessions/SQL/Redis and an inert translator exercise the whole private flow."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.i18n_types import Language
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.peers.models import PeerBlock
from src.domains.users.models import User
from src.domains.world import policy
from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.messages import MailboxScope, MessageRequest, MessageStatusRequest
from src.domains.world.messaging import WorldMessaging
from src.domains.world.store import WorldStore
from src.domains.world.tickets import cookie_binding
from src.domains.world.translation import TranslatedMessage, TranslationText
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@dataclass
class InertTranslator:
    calls: int = 0
    release: asyncio.Event | None = None
    entered: asyncio.Event | None = None
    payer: UUID | None = None

    async def __call__(
        self, text: str, *, source: Language, target: Language, user_id: UUID, request_id: UUID
    ) -> TranslatedMessage:
        self.calls += 1
        self.payer = user_id
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            await self.release.wait()
        return TranslatedMessage(
            TranslationText(language=target, text="PRIVATE_TRANSLATED_FIXTURE"),
            TokenSummaryDTO(40, 12, 0, 0.001, 0),
        )


@dataclass
class MessagingFixture:
    service: WorldMessaging
    people: list[User]
    cookies: list[str]
    scopes: list[MailboxScope]
    translator: InertTranslator

    async def request(self, text: str = "Bonjour") -> MessageRequest:
        state, now = await self.service.world.read()
        return MessageRequest(
            **self.scopes[0].model_dump(),
            id=str(uuid4()),
            recipient=state.actors[str(self.people[1].id)].public_id,
            created_at=now,
            text=text,
            translation_consent=True,
        )


@pytest.fixture
async def messaging_fixture(
    async_engine: AsyncEngine,
    redis_world: Redis,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[MessagingFixture]:
    monkeypatch.setattr(settings, "world_enabled", True)

    async def session_redis() -> Redis:
        return redis_world

    monkeypatch.setattr(policy, "get_redis_session", session_redis)
    async with async_sessionmaker(async_engine, expire_on_commit=False)() as db:
        people = [
            User(email=f"messages-{uuid4().hex}@example.invalid", is_active=True, language="fr")
            for _ in range(3)
        ]
        db.add_all(people)
        await db.flush()
        committed_user_ids.extend(person.id for person in people)
        await db.commit()
    sessions = SessionStore(redis_world)
    cookies = [(await sessions.create_session(str(person.id))).session_id for person in people]
    world = WorldStore(redis_world, namespace="test-" + uuid4().hex, ttl=3600)
    authority = Authority(Limits())

    def join(state, now):
        for index, person in enumerate(people):
            authority.join(
                state,
                Identity(str(person.id), f"Visitor {index}", "fr", cookie_binding(cookies[index])),
                f"controller-token-{index}",
                now,
            )

    state, _ = await world.update(join)
    scopes = [
        MailboxScope(epoch=state.epoch, controller=state.actors[str(person.id)].controller)
        for person in people
    ]
    translator = InertTranslator()
    try:
        yield MessagingFixture(
            WorldMessaging(world, translate=translator), people, cookies, scopes, translator
        )
    finally:
        for cookie in cookies:
            await sessions.delete_session(cookie)


async def test_same_language_delivery_has_zero_model_calls_and_no_third_party_projection(
    messaging_fixture: MessagingFixture,
) -> None:
    fixture = messaging_fixture
    payload = await fixture.request("<img src=x> literal")
    accepted = await fixture.service.send(fixture.cookies[0], str(fixture.people[0].id), payload)
    assert accepted.ack.status == "delivered" and accepted.job is None
    duplicate = await fixture.service.send(fixture.cookies[0], str(fixture.people[0].id), payload)
    assert duplicate.job is None
    incoming = await fixture.service.read(
        fixture.cookies[1], str(fixture.people[1].id), fixture.scopes[1]
    )
    assert len(incoming.messages) == 1
    assert incoming.messages[0].text == "<img src=x> literal"
    assert incoming.messages[0].receipt is None
    assert fixture.translator.calls == 0
    outsider = await fixture.service.read(
        fixture.cookies[2], str(fixture.people[2].id), fixture.scopes[2]
    )
    assert outsider.messages == []
    assert all(str(person.id) not in incoming.model_dump_json() for person in fixture.people)


async def test_translation_bills_only_its_initiator_and_is_visible_only_in_the_current_native_language(
    messaging_fixture: MessagingFixture,
    async_engine: AsyncEngine,
) -> None:
    fixture = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        recipient = await db.get(User, fixture.people[1].id)
        assert recipient is not None
        recipient.language = "en"
        await db.commit()
    accepted = await fixture.service.send(
        fixture.cookies[0], str(fixture.people[0].id), await fixture.request()
    )
    assert accepted.job is not None
    before = await fixture.service.read(
        fixture.cookies[1], str(fixture.people[1].id), fixture.scopes[1]
    )
    assert before.messages[0].text is None and before.messages[0].status == "pending"
    await accepted.job
    after = await fixture.service.read(
        fixture.cookies[1], str(fixture.people[1].id), fixture.scopes[1]
    )
    assert (
        after.messages[0].text == "PRIVATE_TRANSLATED_FIXTURE" and after.messages[0].receipt is None
    )
    sender = await fixture.service.read(
        fixture.cookies[0], str(fixture.people[0].id), fixture.scopes[0]
    )
    assert sender.messages[0].receipt is not None
    status = await fixture.service.status(
        fixture.cookies[0],
        str(fixture.people[0].id),
        MessageStatusRequest(**fixture.scopes[0].model_dump(), id=accepted.ack.id),
    )
    assert status.status == "delivered"
    assert fixture.translator.calls == 1 and fixture.translator.payer == fixture.people[0].id
    async with async_sessionmaker(async_engine)() as db:
        recipient = await db.get(User, fixture.people[1].id)
        assert recipient is not None
        recipient.language = "de"
        await db.commit()
    changed = await fixture.service.read(
        fixture.cookies[1], str(fixture.people[1].id), fixture.scopes[1]
    )
    assert changed.messages[0].text is None and changed.messages[0].status == "unavailable"
    assert fixture.translator.calls == 1


async def test_private_peer_gallery_is_bounded_by_native_connection_and_live_visibility(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.peers.models import PeerConnection, canonical_pair
    from src.domains.world.peer_views import PeerPage, PeerPageRequest, read_peer_page

    fixture = messaging_fixture
    monkeypatch.setattr(settings, "peers_enabled", True)
    async with async_sessionmaker(async_engine)() as db:
        peer = await db.get(User, fixture.people[1].id)
        assert peer is not None
        peer.full_name = "PRIVATE_ACCEPTED_PEER"
        a, b = canonical_pair(fixture.people[0].id, fixture.people[1].id)
        db.add(PeerConnection(user_a_id=a, user_b_id=b, requested_by_id=a, status="accepted"))
        await db.commit()
    payload = PeerPageRequest(**fixture.scopes[0].model_dump())

    async def read() -> PeerPage:
        return await read_peer_page(
            fixture.service.access, fixture.cookies[0], str(fixture.people[0].id), payload
        )

    page = await read()
    assert len(page.peers) == 1 and page.peers[0].presence == "online"

    def enter_home(state, now):
        from src.domains.world.collision import WORLD
        from src.domains.world.presence import track_actor_presence

        account = str(fixture.people[1].id)
        home = next(zone for zone in WORLD.zones if zone.id == "home")
        state.actors[account].position = {"x": home.x + 1, "y": home.y + 1}
        track_actor_presence(state, account, fixture.scopes[1].controller, now)

    await fixture.service.world.update(enter_home)
    assert (await read()).peers[0].presence == "home"

    def idle(state, now):
        state.actors[str(fixture.people[1].id)].activity_at = now - 601
        Authority(Limits()).prune(state, now)

    await fixture.service.world.update(idle)
    assert (await read()).peers[0].presence == "away"
    await fixture.service.world.update(
        lambda state, now: Authority(Limits()).leave(
            state, str(fixture.people[1].id), fixture.scopes[1].controller
        )
    )
    page = await read()
    assert len(page.peers) == 1 and page.peers[0].name == "PRIVATE_ACCEPTED_PEER"
    assert page.peers[0].presence == "offline"
    assert str(fixture.people[1].id) not in page.model_dump_json()
    assert "@" not in page.model_dump_json()
    async with async_sessionmaker(async_engine)() as db:
        db.add(PeerBlock(blocker_id=fixture.people[1].id, blocked_id=fixture.people[0].id))
        await db.commit()
    assert (await read()).peers == []


async def test_environment_borrows_only_its_owners_cached_observation_without_location(
    messaging_fixture: MessagingFixture,
) -> None:
    from datetime import UTC, datetime

    from src.domains.briefing.constants import SECTION_WEATHER
    from src.domains.briefing.schemas import CardSection, CardStatus, WeatherData
    from src.domains.briefing.service import BriefingService
    from src.domains.world.environment import read_environment

    owner, other = messaging_fixture.people[:2]
    owner.timezone = "Asia/Tokyo"
    service = BriefingService(owner)
    cached = CardSection(
        status=CardStatus.OK,
        generated_at=datetime.now(UTC),
        data=WeatherData(
            temperature_c=14.0,
            condition_code="Rain",
            description="PRIVATE_WEATHER_TEXT",
            icon_emoji="☁",
            location_city="PRIVATE_LOCATION",
        ),
    )
    await service._write_cache(service._cache_key(SECTION_WEATHER), cached, 1800)
    result = await read_environment(owner)
    assert result.timezone == "Asia/Tokyo" and result.weather is not None
    assert result.weather.condition_code == "Rain"
    assert result.server_time > 0
    assert "PRIVATE_" not in result.model_dump_json()
    assert (await read_environment(other)).weather is None


async def test_a_reverse_block_during_provider_work_discards_the_late_translation(
    messaging_fixture: MessagingFixture,
    async_engine: AsyncEngine,
) -> None:
    fixture = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        recipient = await db.get(User, fixture.people[1].id)
        assert recipient is not None
        recipient.language = "en"
        await db.commit()
    fixture.translator.entered, fixture.translator.release = asyncio.Event(), asyncio.Event()
    accepted = await fixture.service.send(
        fixture.cookies[0], str(fixture.people[0].id), await fixture.request()
    )
    assert accepted.job is not None
    task = asyncio.create_task(accepted.job)
    await asyncio.wait_for(fixture.translator.entered.wait(), 3)
    async with async_sessionmaker(async_engine)() as db:
        db.add(PeerBlock(blocker_id=fixture.people[1].id, blocked_id=fixture.people[0].id))
        await db.commit()
    fixture.translator.release.set()
    await task
    result = await fixture.service.read(
        fixture.cookies[1], str(fixture.people[1].id), fixture.scopes[1]
    )
    assert result.messages == [] and fixture.translator.calls == 1
    raw = await fixture.service.world.redis.get(fixture.service.mailbox.body_key(accepted.ack.id))
    assert "PRIVATE_TRANSLATED_FIXTURE" not in str(raw)


@pytest.mark.parametrize("reply_language", ["en", "de"])
async def test_native_token_callback_records_the_exact_owner_once_even_when_output_is_refused(
    messaging_fixture: MessagingFixture,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    reply_language: Language,
) -> None:
    import json

    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from sqlalchemy import select

    from src.domains.agents.effects.models import AgentDecision
    from src.domains.chat.models import TokenUsageLog
    from src.domains.llm_config.constants import LLM_DEFAULTS
    from src.domains.world import translation

    request_id = uuid4()
    configuration = LLM_DEFAULTS[translation.SLOT]
    client = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content=json.dumps({"language": reply_language, "text": "Hello"}),
                    usage_metadata={"input_tokens": 31, "output_tokens": 4, "total_tokens": 35},
                    response_metadata={"model_name": configuration.model},
                )
            ]
        ),
        metadata={"llm_type": translation.SLOT, "llm_provider": configuration.provider},
    )
    monkeypatch.setattr(translation, "get_llm", lambda *args, **kwargs: client)
    # The separate real-SDK test proves transport retry fencing. This probe owns
    # the native callback/SQL seam and has no provider transport at all.
    monkeypatch.setattr(translation, "single_async_attempt", nullcontext)
    user_id = messaging_fixture.people[0].id
    if reply_language == "en":
        result = await translation.translate_message(
            "PRIVATE_DIRECT_FIXTURE_TEXT",
            source="fr",
            target="en",
            user_id=user_id,
            request_id=request_id,
        )
        assert result.usage.tokens_in == 31 and result.usage.tokens_out == 4
    else:
        with pytest.raises(ValueError, match="world_translation_language"):
            await translation.translate_message(
                "PRIVATE_DIRECT_FIXTURE_TEXT",
                source="fr",
                target="en",
                user_id=user_id,
                request_id=request_id,
            )
    async with async_sessionmaker(async_engine)() as db:
        rows = list(
            (
                await db.scalars(
                    select(TokenUsageLog).where(
                        TokenUsageLog.run_id == "world_message_" + request_id.hex
                    )
                )
            ).all()
        )
        assert len(rows) == 1
        assert rows[0].user_id == user_id and rows[0].node_name == translation.SLOT
        assert (rows[0].prompt_tokens, rows[0].completion_tokens) == (31, 4)
        assert "PRIVATE_DIRECT_FIXTURE_TEXT" not in str(rows[0].dict())
        decisions = list(
            (
                await db.scalars(
                    select(AgentDecision).where(
                        AgentDecision.run_id == "world_message_" + request_id.hex
                    )
                )
            ).all()
        )
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.user_id == user_id and decision.route == "world_translation"
        assert decision.source == "user" and decision.execution_mode == "direct"
        assert decision.outcome == ("answered" if reply_language == "en" else "failed")
        assert decision.request_message_id is None and decision.response_message_id is None
        assert "PRIVATE_DIRECT_FIXTURE_TEXT" not in str(decision.__dict__)


@pytest.mark.parametrize("inbox_failure", ["none", "missing", "corrupt"])
async def test_account_cleanup_removes_both_sides_of_its_messages_and_preserves_unrelated_text(
    messaging_fixture: MessagingFixture,
    async_engine: AsyncEngine,
    inbox_failure: str,
) -> None:
    from src.domains.world.lifecycle import purge_world_account

    fixture = messaging_fixture
    first = await fixture.service.send(
        fixture.cookies[0], str(fixture.people[0].id), await fixture.request()
    )
    state, now = await fixture.service.world.read()
    unrelated = MessageRequest(
        **fixture.scopes[2].model_dump(),
        id=str(uuid4()),
        recipient=state.actors[str(fixture.people[1].id)].public_id,
        created_at=now,
        text="Unrelated",
    )
    second = await fixture.service.send(fixture.cookies[2], str(fixture.people[2].id), unrelated)
    async with async_sessionmaker(async_engine)() as db:
        owner = await db.get(User, fixture.people[0].id)
        assert owner is not None
        owner.is_active = False
        await db.commit()
    inbox_key = fixture.service.mailbox.inbox_key(str(fixture.people[0].id))
    if inbox_failure == "missing":
        await fixture.service.world.redis.delete(inbox_key)
    elif inbox_failure == "corrupt":
        await fixture.service.world.redis.set(inbox_key, '{"ids":["PRIVATE_BAD_INDEX"]}')
    await purge_world_account(fixture.service.world.redis, str(fixture.people[0].id))
    assert (
        await fixture.service.world.redis.get(fixture.service.mailbox.body_key(first.ack.id))
        is None
    )
    assert (
        await fixture.service.world.redis.get(fixture.service.mailbox.body_key(second.ack.id))
        is not None
    )
    result = await fixture.service.read(
        fixture.cookies[1], str(fixture.people[1].id), fixture.scopes[1]
    )
    assert [message.text for message in result.messages] == ["Unrelated"]


async def test_owned_ephemeral_history_survives_a_new_admission_without_exposing_it_to_others(
    messaging_fixture: MessagingFixture,
) -> None:
    fixture = messaging_fixture
    await fixture.service.send(
        fixture.cookies[0], str(fixture.people[0].id), await fixture.request()
    )
    recipient = str(fixture.people[1].id)
    authority = Authority(Limits())

    def rejoin(state, now):
        authority.leave(state, recipient, fixture.scopes[1].controller)
        authority.join(
            state,
            Identity(recipient, "New alias", "fr", cookie_binding(fixture.cookies[1])),
            "replacement-controller",
            now,
        )

    state, _ = await fixture.service.world.update(rejoin)
    new_scope = MailboxScope(epoch=state.epoch, controller="replacement-controller")
    result = await fixture.service.read(fixture.cookies[1], recipient, new_scope)
    assert [message.text for message in result.messages] == ["Bonjour"]
    outsider = await fixture.service.read(
        fixture.cookies[2], str(fixture.people[2].id), fixture.scopes[2]
    )
    assert outsider.messages == []


async def test_explicit_retranslation_is_recipient_owned_and_reuses_a_completed_variant(
    messaging_fixture: MessagingFixture,
    async_engine: AsyncEngine,
) -> None:
    from src.domains.world.messages import RetranslateRequest

    fixture = messaging_fixture
    initial = await fixture.service.send(
        fixture.cookies[0], str(fixture.people[0].id), await fixture.request()
    )
    async with async_sessionmaker(async_engine)() as db:
        recipient = await db.get(User, fixture.people[1].id)
        assert recipient is not None
        recipient.language = "en"
        await db.commit()
    _, now = await fixture.service.world.read()
    payload = RetranslateRequest(
        **fixture.scopes[1].model_dump(),
        id=str(uuid4()),
        message_id=initial.ack.id,
        created_at=now,
        translation_consent=True,
    )
    translated = await fixture.service.retranslate(
        fixture.cookies[1], str(fixture.people[1].id), payload
    )
    assert translated.job is not None
    await translated.job
    assert fixture.translator.calls == 1 and fixture.translator.payer == fixture.people[1].id
    view = await fixture.service.read(
        fixture.cookies[1], str(fixture.people[1].id), fixture.scopes[1]
    )
    assert len(view.messages) == 1 and view.messages[0].text == "PRIVATE_TRANSLATED_FIXTURE"
    assert view.messages[0].receipt is not None
    replay = await fixture.service.retranslate(
        fixture.cookies[1], str(fixture.people[1].id), payload
    )
    assert replay.job is None and fixture.translator.calls == 1
    another = payload.model_copy(update={"id": str(uuid4())})
    reused = await fixture.service.retranslate(
        fixture.cookies[1], str(fixture.people[1].id), another
    )
    assert reused.job is None and fixture.translator.calls == 1
    with pytest.raises(ValueError):
        await fixture.service.retranslate(
            fixture.cookies[2],
            str(fixture.people[2].id),
            payload.model_copy(update={**fixture.scopes[2].model_dump(), "id": str(uuid4())}),
        )


@pytest.mark.parametrize("revocation", ["cancel", "controller", "language", "session"])
async def test_inflight_revocation_never_publishes_a_late_private_translation(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine, revocation: str
) -> None:
    fixture = messaging_fixture
    async with async_sessionmaker(async_engine)() as db:
        recipient = await db.get(User, fixture.people[1].id)
        assert recipient is not None
        recipient.language = "en"
        await db.commit()
    fixture.translator.entered, fixture.translator.release = asyncio.Event(), asyncio.Event()
    accepted = await fixture.service.send(
        fixture.cookies[0], str(fixture.people[0].id), await fixture.request()
    )
    assert accepted.job is not None
    task = asyncio.create_task(accepted.job)
    await asyncio.wait_for(fixture.translator.entered.wait(), 3)
    if revocation == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        if revocation == "controller":
            await fixture.service.world.update(
                lambda state, now: setattr(
                    state.actors[str(fixture.people[1].id)], "controller", "new-controller-token"
                )
            )
        elif revocation == "language":
            async with async_sessionmaker(async_engine)() as db:
                recipient = await db.get(User, fixture.people[1].id)
                assert recipient is not None
                recipient.language = "de"
                await db.commit()
        else:
            await SessionStore(fixture.service.world.redis).delete_session(fixture.cookies[0])
        fixture.translator.release.set()
        await asyncio.wait_for(task, 3)
    raw = await fixture.service.world.redis.get(fixture.service.mailbox.body_key(accepted.ack.id))
    assert raw is not None and "PRIVATE_TRANSLATED_FIXTURE" not in raw
    assert fixture.translator.calls == 1


async def test_full_message_refuses_a_new_translation_before_reserving_or_spending(
    messaging_fixture: MessagingFixture, async_engine: AsyncEngine
) -> None:
    from src.domains.world.message_content import MessageVariant, StoredMessage
    from src.domains.world.message_models import WorldMessageAttempt
    from src.domains.world.messages import RetranslateRequest
    from src.domains.world.schemas import WorldState
    from src.domains.world.store import WorldUnavailable

    fixture = messaging_fixture
    sender = str(fixture.people[0].id)
    initial = await fixture.service.send(fixture.cookies[0], sender, await fixture.request())
    context = await fixture.service.access.context(fixture.cookies[0], sender, fixture.scopes[0])

    def fill(content: StoredMessage, state: WorldState, now: float) -> None:
        for language in ("en", "de"):
            content.variants[language] = MessageVariant(
                job_id=str(uuid4()),
                payer=sender,
                status="translated",
                deadline=now,
                text="🙂" * 3000,
            )

    await fixture.service.mailbox.change(initial.ack.id, context.scope, fill)
    async with async_sessionmaker(async_engine)() as db:
        recipient = await db.get(User, fixture.people[1].id)
        assert recipient is not None
        recipient.language = "es"
        await db.commit()
    request_id = uuid4()
    payload = RetranslateRequest(
        **fixture.scopes[1].model_dump(),
        id=str(request_id),
        message_id=initial.ack.id,
        created_at=context.now,
        translation_consent=True,
    )
    with pytest.raises(WorldUnavailable, match="world_translation_capacity"):
        await fixture.service.retranslate(fixture.cookies[1], str(fixture.people[1].id), payload)
    assert fixture.translator.calls == 0
    async with async_sessionmaker(async_engine)() as db:
        assert await db.get(WorldMessageAttempt, request_id) is None
