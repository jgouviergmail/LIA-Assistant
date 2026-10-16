"""A typed port for the voice domain to authorize a TTS configuration write.

The API composition root installs the implementation. This domain cannot
import voice (voice already reads its configuration), and a missing guard
refuses the write rather than silently omitting library safety.
"""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BaseAPIException
from src.core.llm_agent_config import LLMAgentConfig
from src.domains.llm.models import LLMModelKindEnum
from src.domains.llm_config.constants import LLM_TYPES_REGISTRY


@dataclass(frozen=True, slots=True)
class VoiceSelection:
    revision: UUID | None
    voices: frozenset[str]
    credential_fingerprint: str | None = field(repr=False)


class SpeechSelectionGuard(Protocol):
    async def prepare(
        self, db: AsyncSession, slot: str, effective: LLMAgentConfig
    ) -> VoiceSelection | None: ...

    async def fence(
        self, db: AsyncSession, slot: str, selection: VoiceSelection | None
    ) -> None: ...


# Only a stateless implementation lives here, never a request's selection.
_guard: SpeechSelectionGuard | None = None


def install_speech_guard(guard: SpeechSelectionGuard) -> None:
    """Wire the port once at API composition, also for disabled voice surfaces."""
    global _guard
    _guard = guard


async def authorize_speech(
    db: AsyncSession,
    slot: str,
    effective: LLMAgentConfig,
    guard: SpeechSelectionGuard | None = None,
) -> None:
    """Prepare without a held SQL connection, then fence the final TTS write."""
    if LLM_TYPES_REGISTRY[slot].required_kind is not LLMModelKindEnum.tts:
        return
    implementation = guard or _guard
    if implementation is None:
        raise BaseAPIException(
            status_code=503,
            detail={"code": "service_unavailable"},
            log_level="error",
            log_event="llm_speech_guard_missing",
        )
    selection = await implementation.prepare(db, slot, effective)
    await implementation.fence(db, slot, selection)
