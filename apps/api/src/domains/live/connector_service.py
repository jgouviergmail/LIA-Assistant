"""The live connectors, server side (ADR-299, ADR-300): the catalogue, the choice, the samples.

Everything that exists BEFORE a session: the connector of each provider
(key verified by the listing, voice checked against the vendored list,
thinking level against the model's ladder, model probed by the provider),
the account's choice among its active providers, the union of the models
their keys discover, the voices of one provider, a voice sample on the
person's key, the four conversation reflexes. `LiveService` (the session
lifecycle) composes this service and never re-implements it.
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    REDIS_KEY_LIVE_SAMPLE_PREFIX,
)
from src.core.i18n_live import get_live_phrases
from src.core.user_display import resolve_user_display_name
from src.domains.connectors.models import (
    CONNECTOR_FUNCTIONAL_CATEGORIES,
    Connector,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.connectors.service import ConnectorService
from src.domains.live.errors import (
    raise_live_connector_missing,
    raise_live_mint_rate_limited,
    raise_live_model_unpriced,
    raise_live_provider_refused,
    raise_live_thinking_level_unknown,
    raise_live_voice_unknown,
)
from src.domains.live.mandate import MandateInputs, delegation_tool_declaration, render_live_mandate
from src.domains.live.model_settings import (
    LiveModelSettings,
    default_durations,
    read_models,
    read_session_budget,
    write_models,
    write_session_budget,
)
from src.domains.live.preferences import LivePreferences, read_live_preferences
from src.domains.live.pricing import is_priced, split_priced
from src.domains.live.providers import (
    PROVIDERS,
    LiveProvider,
    LiveSetupInputs,
    provider_by_id,
)
from src.domains.live.schemas import (
    LiveConnectorActivateRequest,
    LiveConnectorResponse,
    LiveConnectorSettings,
    LiveConnectorsResponse,
    LiveModel,
    LiveModelCapabilitiesResponse,
    LiveModelsResponse,
    LiveVoiceSampleRequest,
    LiveVoiceSampleResponse,
    LiveVoicesResponse,
)
from src.domains.users.models import User
from src.infrastructure.media.wav import wav_bytes
from src.infrastructure.observability.metrics_live import (
    live_voice_samples_total,
)
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

if TYPE_CHECKING:
    from src.domains.live.providers.protocol import LiveModelCapabilities

logger = structlog.get_logger(__name__)


def _declared_only(models: list[LiveModel], *, default_model: str) -> LiveModelsResponse:
    """Offer the models the tariff table declares; name the rest (owner rule 2026-09-19).

    Args:
        models: What the keys discovered.
        default_model: The provider's preselection.

    Returns:
        The listing, its ``unpriced`` naming every discovered model with no tariff.
    """
    # A tariff-billed provider's model is priced under its own name; a
    # VENDOR-billed provider's models (an ElevenLabs agent) are offered
    # whatever the tariff table holds — the platform prices nothing of them.
    tariffed = [model for model in models if not _vendor_billed(model.provider)]
    priced, unpriced = split_priced(model.name for model in tariffed)
    priced_set = set(priced)
    offered = [
        model for model in models if _vendor_billed(model.provider) or model.name in priced_set
    ]
    return LiveModelsResponse(models=offered, default_model=default_model, unpriced=unpriced)


def _vendor_billed(provider_id: str) -> bool:
    provider = provider_by_id(provider_id)
    return provider is not None and provider.billing == "vendor"


class LiveConnectorService:
    """The live connectors of an account: activation, catalogue, voices, samples, reflexes."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- thin doors the tests replace ------------------------------------------------

    async def _limiter(self) -> Any:
        return await get_rate_limiter()

    async def api_key_of(self, user_id: uuid.UUID, connector_type: ConnectorType) -> str:
        credentials = await ConnectorService(self.db).get_api_key_credentials(
            user_id, connector_type
        )
        return credentials.api_key if credentials else ""

    async def active_connectors(self, user_id: uuid.UUID) -> list[Connector]:
        """Every ACTIVE connector of the ``live`` category, in the providers' order."""
        repository = ConnectorService(self.db).repository
        found: list[Connector] = []
        for connector_type in PROVIDERS:
            if connector_type not in CONNECTOR_FUNCTIONAL_CATEGORIES["live"]:
                continue
            connector = await repository.get_by_user_and_type(user_id, connector_type)
            if connector is not None and connector.status == ConnectorStatus.ACTIVE:
                found.append(connector)
        return found

    async def chosen_connector(self, user: User) -> Connector | None:
        """The connector the sessions open on: the account's choice, else the first active.

        The choice survives its connector's removal by falling back, never by
        refusing: a person who disconnected one of two keys still has a live
        mode.
        """
        connectors = await self.active_connectors(user.id)
        if not connectors:
            return None
        wanted = self.preferences(user).provider
        for connector in connectors:
            if PROVIDERS[ConnectorType(connector.connector_type)].provider_id == wanted:
                return connector
        return connectors[0]

    async def connector_of(self, user: User, provider_id: str, *, language: str) -> Connector:
        """The account's active connector of ONE provider, or the coded refusal."""
        for connector in await self.active_connectors(user.id):
            if PROVIDERS[ConnectorType(connector.connector_type)].provider_id == provider_id:
                return connector
        raise_live_connector_missing(language)

    def _set_active_provider(self, user: User, provider_id: str) -> None:
        """The connector the person last saved is the one the sessions open on (a NEW dict)."""
        user.live_preferences = {**(user.live_preferences or {}), "provider": provider_id}
        self.db.add(user)

    @staticmethod
    def connector_settings(connector: Connector) -> LiveConnectorSettings:
        """The current model and its own settings, as the connector metadata holds them."""
        metadata = connector.connector_metadata or {}
        provider = PROVIDERS[ConnectorType(connector.connector_type)]
        model = str(metadata.get("model") or provider.default_model)
        remembered = read_models(metadata).get(model)
        if remembered is None:
            # Never reached after an activation (it refuses a voice off the list);
            # a metadata nobody can read runs under the defaults with no voice.
            remembered = LiveModelSettings(voice="-", **default_durations())
        return LiveConnectorSettings(
            model=model,
            session_budget_eur=read_session_budget(metadata),
            **remembered.model_dump(),
        )

    @staticmethod
    def model_settings(connector: Connector) -> dict[str, LiveModelSettings]:
        """Every model the connector remembers (the settings form reads the one switched to)."""
        return read_models(connector.connector_metadata)

    def connector_response(self, connector: Connector, *, active: bool) -> LiveConnectorResponse:
        """The connector as the settings show it."""
        provider = PROVIDERS[ConnectorType(connector.connector_type)]
        metadata = connector.connector_metadata or {}
        chosen = self.connector_settings(connector)
        return LiveConnectorResponse(
            provider=provider.provider_id,
            connector_type=ConnectorType(connector.connector_type).value,
            status=ConnectorStatus(connector.status).value,
            settings=chosen,
            model_settings=self.model_settings(connector),
            functionally_verified=bool(metadata.get("functionally_verified")),
            capabilities=LiveModelCapabilitiesResponse(
                **asdict(provider.capabilities_of(chosen.model))
            ),
            active=active,
        )

    async def connectors_response(self, user: User) -> LiveConnectorsResponse:
        """Every active connector, the chosen one flagged."""
        chosen = await self.chosen_connector(user)
        connectors = await self.active_connectors(user.id)
        active_provider = (
            PROVIDERS[ConnectorType(chosen.connector_type)].provider_id if chosen else None
        )
        return LiveConnectorsResponse(
            connectors=[self.connector_response(c, active=c is chosen) for c in connectors],
            active_provider=active_provider,
        )

    def setup_inputs(
        self,
        provider: LiveProvider,
        user: User,
        chosen: LiveConnectorSettings,
        *,
        language: str,
        timezone: str,
        display_name: str,
        now: datetime,
        personality: str,
        psyche_block: str = "",
    ) -> LiveSetupInputs:
        """The ONE rendering of a session setup — what the session opens with and what the probe replays.

        The probe renders it without the personality and without the inner
        state (colour, never a gate); a session start hands both.
        """
        capabilities: LiveModelCapabilities = provider.capabilities_of(chosen.model)
        return LiveSetupInputs(
            model=chosen.model,
            voice=chosen.voice,
            thinking_level=chosen.thinking_level,
            system_instruction=render_live_mandate(
                MandateInputs(
                    language=language,
                    user_name=display_name,
                    personality=personality,
                    now=now,
                    timezone=timezone,
                    result_budget_tokens=settings.live_delegation_result_max_tokens,
                    async_delegation=capabilities.async_delegation,
                    native_delegation=provider.delegation_wire == "native",
                    psyche_block=psyche_block,
                    tone_notes=settings.expressivity_enabled,
                )
            ),
            tool_declaration=delegation_tool_declaration(display_name),
            direct_tools=(),
            preferences=self.preferences(user),
            trigger_tokens=settings.live_context_trigger_tokens,
            target_tokens=settings.live_context_target_tokens,
        )

    async def _check_choice(
        self,
        provider: LiveProvider,
        api_key: str,
        user: User,
        chosen: LiveConnectorSettings,
        *,
        language: str,
    ) -> None:
        """Refuse a voice or a level the provider does not offer, then let it judge the setup.

        Measured 2026-09-18: the provider never refuses a wrong voice name (it
        falls back in silence), so the list is the only place to catch it;
        the model and its level, it does refuse — the probe opens a session on
        the REAL setup (the personality left out: colour, never a gate).
        """
        if not provider.knows_voice(chosen.voice):
            raise_live_voice_unknown(language, chosen.voice)
        # A tariff-billed model needs its row; a vendor-billed one (an agent)
        # is priced by the vendor alone and needs none.
        if provider.billing == "tariff" and not is_priced(chosen.model):
            raise_live_model_unpriced(language, chosen.model)
        ladder = provider.thinking_levels_of(chosen.model)
        if chosen.thinking_level and chosen.thinking_level not in ladder:
            raise_live_thinking_level_unknown(language, chosen.thinking_level)
        if ladder and not chosen.thinking_level:
            # A model whose ladder is non-empty REQUIRES a level: refused here,
            # in the person's language, rather than by the provider's 1007.
            raise_live_thinking_level_unknown(language, "none")
        inputs = self.setup_inputs(
            provider,
            user,
            chosen,
            language=language,
            timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
            display_name=resolve_user_display_name(user.full_name, user.email),
            now=datetime.now(UTC),
            personality="",
        )
        accepted, detail = await provider.probe(
            api_key, inputs, timeout=settings.live_probe_timeout_seconds
        )
        if not accepted:
            raise_live_provider_refused(language, detail)

    async def activate_connector(
        self, user: User, payload: LiveConnectorActivateRequest, *, language: str
    ) -> LiveConnectorResponse:
        """Verify the key, check the choice, store — one door (spec A10)."""
        from src.core.exceptions import raise_invalid_input

        provider = provider_by_id(payload.provider)
        if provider is None:
            raise_invalid_input("unknown live provider", field="provider")
        connector_type = provider.connector_type
        service = ConnectorService(self.db)
        ok, message = await service.validate_api_key(connector_type, payload.api_key, None)
        if not ok:
            raise_invalid_input(message, field="api_key")
        chosen = LiveConnectorSettings(
            model=payload.model,
            voice=payload.voice,
            thinking_level=payload.thinking_level,
            **default_durations(),
        )
        await self._check_choice(provider, payload.api_key, user, chosen, language=language)
        response = await service.activate_api_key_connector(
            user_id=user.id,
            connector_type=connector_type,
            api_key=payload.api_key,
            metadata=write_models(
                None, chosen.model, LiveModelSettings(**chosen.model_dump(exclude={"model"}))
            ),
        )
        # The newly set-up provider is the one the sessions open on (a NEW dict).
        self._set_active_provider(user, provider.provider_id)
        await self.db.commit()
        connector = await service.repository.get_by_user_and_type(user.id, connector_type)
        if connector is None:  # pragma: no cover - just written
            raise_live_connector_missing(language)
        logger.info("live_connector_activated", user_id=str(user.id), connector_id=str(response.id))
        return self.connector_response(connector, active=True)

    async def update_connector_settings(
        self, user: User, provider_id: str, new_settings: LiveConnectorSettings, *, language: str
    ) -> LiveConnectorResponse:
        """Change model, voice or thinking level — the provider judges the model again.

        The connector saved becomes the one the sessions open on: choosing a
        model IS choosing a provider.
        """
        connector = await self.connector_of(user, provider_id, language=language)
        connector_type = ConnectorType(connector.connector_type)
        provider = PROVIDERS[connector_type]
        api_key = await self.api_key_of(user.id, connector_type)
        await self._check_choice(provider, api_key, user, new_settings, language=language)
        # A NEW dict (the JSONB rule): the model named becomes current, its settings
        # are remembered beside the other models' — a switch never forgets a voice.
        # The budget is the connector's, written beside the models.
        connector.connector_metadata = write_session_budget(
            write_models(
                connector.connector_metadata,
                new_settings.model,
                LiveModelSettings(**new_settings.model_dump(exclude={"model"})),
            ),
            new_settings.session_budget_eur,
        )
        self._set_active_provider(user, provider.provider_id)
        await self.db.commit()
        return self.connector_response(connector, active=True)

    async def list_models(self, user: User, *, language: str) -> LiveModelsResponse:
        """The declared models EVERY active connector's key discovers, each naming its provider."""
        connectors = await self.active_connectors(user.id)
        if not connectors:
            raise_live_connector_missing(language)
        models = []
        for connector in connectors:
            connector_type = ConnectorType(connector.connector_type)
            models.extend(
                await PROVIDERS[connector_type].list_models(
                    await self.api_key_of(user.id, connector_type)
                )
            )
        first = PROVIDERS[ConnectorType(connectors[0].connector_type)]
        return _declared_only(models, default_model=first.default_model)

    async def discover_models(
        self, api_key: str, *, provider_id: str, language: str
    ) -> LiveModelsResponse:
        """The models a key discovers BEFORE the connector exists (the form's first step)."""
        from src.core.exceptions import raise_invalid_input

        provider = provider_by_id(provider_id)
        if provider is None:
            raise_invalid_input("unknown live provider", field="provider")
        ok, message = await ConnectorService(self.db).validate_api_key(
            provider.connector_type, api_key, None
        )
        if not ok:
            raise_invalid_input(message, field="api_key")
        models = await provider.list_models(api_key)
        return _declared_only(models, default_model=provider.default_model)

    async def list_voices(
        self, user: User, *, provider_id: str | None, language: str
    ) -> LiveVoicesResponse:
        """The voices of ONE provider (the chosen one by default), with their provenance."""
        connector = (
            await self.connector_of(user, provider_id, language=language)
            if provider_id
            else await self.chosen_connector(user)
        )
        if connector is None:
            raise_live_connector_missing(language)
        connector_type = ConnectorType(connector.connector_type)
        provider = PROVIDERS[connector_type]
        return await provider.list_voices(await self.api_key_of(user.id, connector_type))

    @staticmethod
    async def published_voices(provider_id: str) -> LiveVoicesResponse:
        """The published voices of a provider, BEFORE the connector exists."""
        from src.core.exceptions import raise_invalid_input

        provider = provider_by_id(provider_id)
        if provider is None:
            raise_invalid_input("unknown live provider", field="provider")
        return await provider.list_voices("")

    async def sample_voice(
        self, user: User, payload: LiveVoiceSampleRequest, *, language: str
    ) -> LiveVoiceSampleResponse:
        """One sentence in the chosen voice, on the person's key — the form's or the stored one.

        Never counted (the key is the person's, ADR-299); bounded by its own
        limiter under the mint's published bounds; refused for a voice off
        the list before any call is made.
        """
        provider = next((p for p in PROVIDERS.values() if p.provider_id == payload.provider), None)
        if provider is None or not provider.knows_voice(payload.voice):
            live_voice_samples_total.labels(
                provider=payload.provider, outcome="voice_unknown"
            ).inc()
            raise_live_voice_unknown(language, payload.voice)
        api_key = payload.api_key or await self.api_key_of(user.id, provider.connector_type)
        if not api_key:
            live_voice_samples_total.labels(
                provider=provider.provider_id, outcome="connector_missing"
            ).inc()
            raise_live_connector_missing(language)
        limiter = await self._limiter()
        allowed = await limiter.acquire(
            key=f"{REDIS_KEY_LIVE_SAMPLE_PREFIX}{user.id}",
            max_calls=settings.live_mint_rate_limit_max_calls,
            window_seconds=settings.live_mint_rate_limit_window_seconds,
        )
        if not allowed:
            live_voice_samples_total.labels(
                provider=provider.provider_id, outcome="rate_limited"
            ).inc()
            raise_live_mint_rate_limited(language)
        try:
            pcm = await provider.sample_voice(
                api_key, payload.voice, get_live_phrases(language)["voice_sample"]
            )
        except Exception as exc:
            live_voice_samples_total.labels(
                provider=provider.provider_id, outcome="provider_error"
            ).inc()
            # The SDK's message carries the provider's status and reason, never the key.
            logger.warning(
                "live_voice_sample_failed", error_type=type(exc).__name__, detail=str(exc)[:200]
            )
            raise_live_provider_refused(language, type(exc).__name__)
        live_voice_samples_total.labels(provider=provider.provider_id, outcome="ok").inc()
        return LiveVoiceSampleResponse(
            audio_base64=base64.b64encode(wav_bytes(pcm, provider.sample_rate)).decode("ascii"),
            sample_rate=provider.sample_rate,
        )

    # -- preferences -----------------------------------------------------------------

    @staticmethod
    def preferences(user: User) -> LivePreferences:
        """The person's reflexes, tolerant of what the column holds."""
        return read_live_preferences(user.live_preferences)

    async def update_preferences(self, user: User, prefs: LivePreferences) -> LivePreferences:
        """Full replace of the reflexes (a NEW dict — the JSONB rule).

        The provider choice lives in the same column but belongs to the
        connector settings: a PUT of the reflexes that carries none keeps it.
        """
        kept = prefs.provider or self.preferences(user).provider
        merged = prefs.model_copy(update={"provider": kept})
        user.live_preferences = merged.model_dump()
        self.db.add(user)
        await self.db.commit()
        return merged


__all__ = ["LiveConnectorService"]
