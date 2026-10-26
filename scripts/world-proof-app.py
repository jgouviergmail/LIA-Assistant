"""Disposable native-world qualification host; NEVER imported by the application.

Only inert accounts in the exact isolated Docker database are accepted. Native
UI namespaces expose their authenticated application routes and response security
policy, without the production lifespan, provider keys or schedulers.
Created by scripts/world-proof.py as /app/world_proof.py after native migrations.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import Depends, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.v1.routes import api_router
from src.core.config import settings
from src.core.constants import SESSION_COOKIE_NAME
from src.core.exceptions import AuthorizationError
from src.core.middleware import SecurityHeadersMiddleware
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.memories.models import Memory
from src.domains.users.models import User
from src.domains.world.router import router
from src.domains.world.configuration import configured_store
from src.domains.world.transport import origin_allowed
from src.infrastructure.cache.redis import close_redis, get_redis_session, get_redis_cache
from src.infrastructure.cache.session_store import SessionStore
from src.infrastructure.cache.user_channel import publish_to_user, user_notifications_channel
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import engine, get_db_context

PROOF_NAMESPACES = frozenset(
    f"world-{stage}-proof"
    for stage in (
        "v1",
        "home",
        "functions",
        "social",
        "polish",
        "final",
        "qualification",
        "art",
    )
)
NATIVE_UI_PROOFS = frozenset(
    f"world-{stage}-proof"
    for stage in ("functions", "social", "polish", "final", "qualification", "art")
)
TRANSLATION_PROOFS = frozenset(
    f"world-{stage}-proof" for stage in ("social", "polish", "final", "qualification", "art")
)
DECORATED_PROOFS = frozenset(
    {
        "world-polish-proof",
        "world-final-proof",
        "world-qualification-proof",
        "world-art-proof",
    }
)

if (
    settings.environment != "development"
    or settings.world_namespace not in PROOF_NAMESPACES
    or settings.database_url.hosts()[0]["host"] != "world-proof-postgres"
    or settings.database_url.path
    != {
        "world-final-proof": "/world_final",
        "world-art-proof": "/world_art_g19",
        "world-qualification-proof": "/world_qualification",
    }.get(settings.world_namespace, "/world")
    or settings.redis_url.host != "world-proof-redis"
):
    raise RuntimeError("world_proof_requires_its_disposable_infrastructure")

LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN", "fr", "en")


async def seed_polish_fixture(db: AsyncSession) -> None:
    """Inert accepted people and cached observations in the exact guarded database."""
    from src.domains.peers.models import PeerConnection, canonical_pair

    zones = (
        "Europe/Paris",
        "America/New_York",
        "Asia/Tokyo",
        "Europe/Madrid",
        "Europe/Rome",
        "Asia/Shanghai",
    )
    for index, zone in enumerate(zones, 1):
        user = await db.get(User, UUID(account(index)))
        if user is None:
            raise RuntimeError("missing_inert_proof_user")
        user.timezone = zone
    for index in (2, 3, *range(11, 28)):
        target = UUID(account(index))
        if await db.get(User, target) is None:
            db.add(
                User(
                    id=target,
                    email=f"{settings.world_namespace}-extra-{index}@example.com",
                    full_name=f"Atelier {index - 10:02}",
                    is_active=True,
                    is_verified=True,
                    language="fr",
                )
            )
            await db.flush()
        connection = uuid5(NAMESPACE_URL, f"{settings.world_namespace}/connection/{index}")
        if await db.get(PeerConnection, connection) is None:
            a, b = canonical_pair(UUID(account(1)), target)
            db.add(
                PeerConnection(
                    id=connection,
                    user_a_id=a,
                    user_b_id=b,
                    requested_by_id=UUID(account(1)),
                    status="accepted",
                    responded_at=datetime.now(UTC),
                )
            )
    await db.commit()
    for index in (1, 2, 3):
        user = await db.get(User, UUID(account(index)))
        if user is None:
            raise RuntimeError("missing_inert_proof_user")
        await seed_weather_fixture(user, index)


async def seed_weather_fixture(user: User, index: int) -> None:
    """Refresh only authored weather at proof login; production freshness stays intact."""
    from src.domains.briefing.constants import SECTION_WEATHER
    from src.domains.briefing.schemas import CardSection, CardStatus, WeatherData
    from src.domains.briefing.service import BriefingService

    condition = {1: "Rain", 2: "Clear", 3: "Snow"}.get(index)
    if condition is None:
        return
    service = BriefingService(user)
    section = CardSection(
        status=CardStatus.OK,
        generated_at=datetime.now(UTC),
        data=WeatherData(
            temperature_c=3.0 if condition == "Snow" else 16.0,
            condition_code=condition,
            description="INERT WEATHER FIXTURE",
            icon_emoji="☁",
            location_city="PRIVATE_FIXTURE_LOCATION",
            wind_speed_kmh=8.0,
        ),
    )
    # Fixture-only use of the native cache serialization; no provider path.
    await service._write_cache(service._cache_key(SECTION_WEATHER), section, 1800)


def account(index: int) -> str:
    prefix = (
        "lia-world-native-proof"
        if settings.world_namespace == "world-v1-proof"
        else f"lia-{settings.world_namespace}"
    )
    return str(uuid5(NAMESPACE_URL, f"{prefix}/{index}"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import_all_models()
    async with get_db_context() as db:
        for index, language in enumerate(LANGUAGES, 1):
            prefix = (
                "world-proof"
                if settings.world_namespace == "world-v1-proof"
                else settings.world_namespace
            )
            domain = (
                "example.com" if settings.world_namespace in NATIVE_UI_PROOFS else "example.invalid"
            )
            email = f"{prefix}-{index}@{domain}"
            existing = await db.get(User, UUID(account(index)))
            if existing is None:
                db.add(
                    User(
                        id=UUID(account(index)),
                        email=email,
                        language=language,
                        full_name=f"Proof {index}",
                        is_active=True,
                        is_verified=True,
                        onboarding_completed=True,
                    )
                )
            elif settings.world_namespace in NATIVE_UI_PROOFS:
                existing.email = email
                existing.onboarding_completed = True
        await db.commit()
        if settings.world_namespace in PROOF_NAMESPACES - {"world-v1-proof"}:
            for index, text in enumerate(
                (
                    "J'adore la musique",
                    "I love reading books",
                    "Ich liebe Natur",
                    "Me encanta viajar",
                    "Mi piace la scienza",
                    "我喜欢艺术",
                ),
                1,
            ):
                identifier = uuid5(NAMESPACE_URL, f"lia-{settings.world_namespace}/memory/{index}")
                if await db.get(Memory, identifier) is None:
                    db.add(
                        Memory(
                            id=identifier,
                            user_id=UUID(account(index)),
                            content=text,
                            category="preference",
                            char_count=len(text),
                        )
                    )
            await db.commit()
        if settings.world_namespace in DECORATED_PROOFS:
            await seed_polish_fixture(db)
    try:
        yield
    finally:
        await close_redis()
        await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(
    api_router if settings.world_namespace in NATIVE_UI_PROOFS else router,
    prefix="/api/v1",
)

# An explicitly isolated proof port, never a production provider or a claim of
# linguistic fidelity. Only this authored phrase has an inert translation.
if settings.world_namespace in TRANSLATION_PROOFS:
    from src.core.i18n_types import Language
    from src.domains.chat.schemas import TokenSummaryDTO
    from src.domains.world.message_router import get_messaging
    from src.domains.world.public_translation import TranslatedBatch
    from src.domains.world.messaging import WorldMessaging
    from src.domains.world.store import WorldStore
    from src.domains.world.translation import TranslatedMessage, TranslationText

    PHRASES: dict[Language, str] = {
        "fr": "Bonjour, ravi de te rencontrer.",
        "en": "Hello, pleased to meet you.",
        "de": "Hallo, schön, dich kennenzulernen.",
        "es": "Hola, encantado de conocerte.",
        "it": "Ciao, piacere di conoscerti.",
        "zh-CN": "你好，很高兴认识你。",
    }

    async def inert_translation(
        text: str,
        *,
        source: Language,
        target: Language,
        user_id: UUID,
        request_id: UUID,
    ) -> TranslatedMessage:
        if text != PHRASES[source]:
            raise ValueError("proof_phrase_only")
        return TranslatedMessage(
            TranslationText(language=target, text=PHRASES[target]),
            TokenSummaryDTO(0, 0, 0, 0, 0),
        )

    async def inert_public_translation(
        text: str,
        *,
        source: Language,
        targets: tuple[Language, ...],
        user_id: UUID,
        request_id: UUID,
    ) -> TranslatedBatch:
        if text != PHRASES[source]:
            raise ValueError("proof_phrase_only")
        return TranslatedBatch(
            {target: PHRASES[target] for target in targets},
            TokenSummaryDTO(0, 0, 0, 0, 0),
        )

    async def proof_messaging() -> WorldMessaging:
        return WorldMessaging(
            WorldStore(
                await get_redis_cache(),
                namespace=settings.world_namespace,
                ttl=settings.world_state_seconds,
                timeout=settings.world_authority_timeout,
            ),
            translate=inert_translation,
            translate_public=inert_public_translation,
        )

    app.dependency_overrides[get_messaging] = proof_messaging


@app.get("/api/v1/world-proof/me")
async def proof_identity(
    user: User = Depends(get_current_active_session_for_stream),
) -> dict[str, str]:
    return {"owner_id": str(user.id), "language": user.language.replace("zh-CN", "zh")}


@app.post("/api/v1/world-proof/reset", status_code=204)
async def reset_world_fixture(request: Request) -> Response:
    """Start a fresh authority epoch between tests on this exact inert proof host.

    Native SQL preferences and weather fixtures remain available. Old controller
    scopes and message epochs cannot enter the new authority; real application
    entry points never mount this fixture-only route.
    """
    if not origin_allowed(request.headers.get("origin"), settings.cors_origins):
        raise AuthorizationError(detail={"error_code": "PROOF_ORIGIN"})
    async with asyncio.timeout(settings.world_authority_timeout):
        redis = await get_redis_cache()
        await redis.delete(configured_store(redis).key)
    return Response(status_code=204)


@app.post("/api/v1/world-proof/proactive", status_code=204)
async def publish_proof_opening(
    request: Request,
    user: User = Depends(get_current_active_session_for_stream),
) -> Response:
    """Publish one fixed opening to the authenticated inert account, without Docker access."""
    if not origin_allowed(request.headers.get("origin"), settings.cors_origins):
        raise AuthorizationError(detail={"error_code": "PROOF_ORIGIN"})
    if str(user.id) not in {account(index) for index in range(1, len(LANGUAGES) + 1)}:
        raise AuthorizationError(detail={"error_code": "PROOF_ACCOUNT"})
    if request.query_params or await request.body():
        raise AuthorizationError(detail={"error_code": "PROOF_INPUT"})
    async with asyncio.timeout(settings.world_authority_timeout):
        redis = await get_redis_cache()
        subscribers = await redis.pubsub_numsub(user_notifications_channel(user.id))
        if sum(count for _, count in subscribers) < 1:
            raise RuntimeError("proof_notification_subscriber_required")
        published = await publish_to_user(
            user.id,
            {
                "type": "proactive_discussion",
                "content": "Une idée pour ta promenade dans le jardin.",
                "target_id": str(uuid4()),
                "metadata": {"message_id": str(uuid4())},
            },
        )
        if not published:
            raise RuntimeError("proof_notification_not_published")
    return Response(status_code=204)


class ProofChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    index: int = Field(ge=1, le=len(LANGUAGES))


@app.post("/api/v1/world-proof/session")
async def choose_proof_account(
    choice: ProofChoice, request: Request, response: Response
) -> dict[str, str]:
    if not origin_allowed(request.headers.get("origin"), settings.cors_origins):
        raise AuthorizationError(detail={"error_code": "PROOF_ORIGIN"})
    owner = account(choice.index)
    if settings.world_namespace in DECORATED_PROOFS:
        async with get_db_context() as db:
            user = await db.get(User, UUID(owner))
            if user is None:
                raise RuntimeError("missing_inert_proof_user")
            await seed_weather_fixture(user, choice.index)
    session = await SessionStore(await get_redis_session()).create_session(owner)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session.session_id,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
        max_age=3600,
    )
    return {
        "owner_id": owner,
        "language": LANGUAGES[choice.index - 1].replace("zh-CN", "zh"),
    }
