"""The live providers LIA knows, by connector type (ADR-299, spec A2)."""

from __future__ import annotations

from src.domains.connectors.models import ConnectorType
from src.domains.live.providers.elevenlabs_live import ElevenLabsLiveProvider
from src.domains.live.providers.gemini import GeminiLiveProvider
from src.domains.live.providers.openai_live import OpenAiLiveProvider
from src.domains.live.providers.protocol import (
    AgentSyncing,
    LiveBilling,
    LiveCredential,
    LiveProvider,
    LiveSetupInputs,
    OfferExchanging,
    VendorBilling,
    setup_inputs_from_dict,
    setup_inputs_to_dict,
)

PROVIDERS: dict[ConnectorType, LiveProvider] = {
    ConnectorType.GEMINI_LIVE: GeminiLiveProvider(),
    ConnectorType.GPT_LIVE: OpenAiLiveProvider(),
    ConnectorType.ELEVENLABS_LIVE: ElevenLabsLiveProvider(),
}


def provider_by_id(provider_id: str) -> LiveProvider | None:
    """The provider the wire names (``gemini`` …), or None."""
    return next((p for p in PROVIDERS.values() if p.provider_id == provider_id), None)


__all__ = [
    "PROVIDERS",
    "AgentSyncing",
    "LiveBilling",
    "LiveCredential",
    "LiveProvider",
    "LiveSetupInputs",
    "OfferExchanging",
    "provider_by_id",
    "setup_inputs_from_dict",
    "VendorBilling",
    "setup_inputs_to_dict",
]
