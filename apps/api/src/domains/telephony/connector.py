"""Telephony connector activation (custom multi-step wizard — spec §4.2).

Storage reuses ``ConnectorService.activate_api_key_connector``: the ElevenLabs API
key and the post-call webhook HMAC secret both live encrypted in
``credentials_encrypted`` (key → ``api_key``, webhook secret → ``api_secret``).
Only non-secret ids (``agent_id``, ``agent_phone_number_id``,
``caller_number_display``) go in ``connector_metadata`` (JSONB) — never the secret.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ExternalServiceError
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.telephony.agent_prompt import agent_config_fingerprint, build_agent_config
from src.domains.telephony.client import ElevenLabsAgentsClient, ElevenLabsAgentsError
from src.domains.telephony.schemas import KeyValidationResult, PhoneNumberInfo

logger = structlog.get_logger(__name__)

_KEY_NAME = "ElevenLabs Telephony"
ClientFactory = Callable[[str], ElevenLabsAgentsClient]


def _default_client_factory(api_key: str) -> ElevenLabsAgentsClient:
    return ElevenLabsAgentsClient(api_key)


class TelephonyConnectorService:
    """Per-user ELEVENLABS_TELEPHONY connector lifecycle (full BYO)."""

    def __init__(self, db: AsyncSession, *, client_factory: ClientFactory | None = None) -> None:
        self.db = db
        self._client_factory = client_factory or _default_client_factory

    async def get_active(self, user_id: UUID) -> Connector | None:
        """Return the user's ELEVENLABS_TELEPHONY connector iff it is active.

        The telephony capability guard: ``place_phone_call`` refuses to build a
        draft (and ``initiate_call`` refuses to dial) when this returns ``None``.
        """
        connector = await ConnectorService(self.db).repository.get_by_user_and_type(
            user_id, ConnectorType.ELEVENLABS_TELEPHONY
        )
        if connector is None or connector.status != ConnectorStatus.ACTIVE:
            return None
        return connector

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        """Ping the ElevenLabs API to confirm the key authenticates."""
        try:
            ok = await self._client_factory(api_key).validate_key()
        except Exception as exc:  # noqa: BLE001 — any failure means the key is unusable
            logger.warning("telephony_key_validation_error", error=str(exc))
            ok = False
        return KeyValidationResult(
            is_valid=ok,
            message="valid" if ok else "invalid",  # localized by the router/UI
        )

    async def list_numbers(self, api_key: str) -> list[PhoneNumberInfo]:
        """List the phone numbers imported in the user's ElevenLabs workspace."""
        try:
            return await self._client_factory(api_key).list_phone_numbers()
        except ElevenLabsAgentsError as exc:
            raise ExternalServiceError(
                service_name="elevenlabs",
                detail=f"ElevenLabs phone-number listing failed: {exc.detail}",
                status_code_upstream=exc.status_code,
            ) from exc

    async def activate(
        self,
        *,
        user_id: UUID,
        api_key: str,
        agent_phone_number_id: str,
        webhook_secret: str,
        user_language: str,
        user_name: str,
        caller_number_display: str | None = None,
    ) -> Connector:
        """Provision the LIA-controlled agent and persist the encrypted connector."""
        cfg = build_agent_config(user_language, user_name)
        try:
            agent_id = await self._client_factory(api_key).create_agent(
                name=cfg.name,
                system_prompt=cfg.system_prompt,
                first_message=cfg.first_message,
                language=cfg.language,
                # Vendor constraint: non-English agents require a turbo/flash
                # v2.5 TTS model — without it agent creation is rejected (400).
                llm_model=settings.telephony_agent_llm_model or None,
                tts_model_id=settings.telephony_agent_tts_model_id,
                voice_id=settings.telephony_agent_voice_id or None,
                audio_format=settings.telephony_agent_audio_format or None,
                max_duration_seconds=settings.telephony_max_call_duration_seconds,
                data_collection=cfg.data_collection,
            )
        except ElevenLabsAgentsError as exc:
            raise ExternalServiceError(
                service_name="elevenlabs",
                detail=f"ElevenLabs agent provisioning failed: {exc.detail}",
                status_code_upstream=exc.status_code,
            ) from exc

        metadata: dict[str, Any] = {
            "agent_id": agent_id,
            "agent_phone_number_id": agent_phone_number_id,
            "caller_number_display": caller_number_display,
            # Lazy re-sync anchor: initiate_call compares this against the
            # current config and PATCHes the agent in place on drift.
            "agent_config_hash": agent_config_fingerprint(
                cfg,
                llm_model=settings.telephony_agent_llm_model or None,
                tts_model_id=settings.telephony_agent_tts_model_id,
                voice_id=settings.telephony_agent_voice_id or None,
                audio_format=settings.telephony_agent_audio_format or None,
                max_duration_seconds=settings.telephony_max_call_duration_seconds,
            ),
        }
        connector_service = ConnectorService(self.db)
        await connector_service.activate_api_key_connector(
            user_id=user_id,
            connector_type=ConnectorType.ELEVENLABS_TELEPHONY,
            api_key=api_key,
            api_secret=webhook_secret,  # webhook HMAC secret — encrypted, never in JSONB
            key_name=_KEY_NAME,
            metadata=metadata,
        )
        connector = await connector_service.repository.get_by_user_and_type(
            user_id, ConnectorType.ELEVENLABS_TELEPHONY
        )
        if connector is None:  # pragma: no cover — just persisted above
            raise RuntimeError("telephony connector not found immediately after activation")
        logger.info("telephony_connector_activated", user_id=str(user_id), agent_id=agent_id)
        return connector

    async def deactivate(self, user_id: UUID) -> None:
        """Best-effort agent cleanup, then remove the connector row.

        Deletion goes through ``ConnectorService.delete_connector`` so the
        Redis ``user_connectors`` cache is invalidated like every other
        disconnect — a direct row delete left the cached list serving the
        connector as still connected until its TTL expired.
        """
        connector_service = ConnectorService(self.db)
        connector = await connector_service.repository.get_by_user_and_type(
            user_id, ConnectorType.ELEVENLABS_TELEPHONY
        )
        if connector is None:
            return

        agent_id = (connector.connector_metadata or {}).get("agent_id")
        creds = await connector_service.get_api_key_credentials(
            user_id, ConnectorType.ELEVENLABS_TELEPHONY
        )
        if agent_id and creds is not None:
            # The agent lives in the user's workspace — delete is best-effort.
            await self._client_factory(creds.api_key).delete_agent(agent_id)

        await connector_service.delete_connector(user_id, connector.id)
        logger.info("telephony_connector_deactivated", user_id=str(user_id))
