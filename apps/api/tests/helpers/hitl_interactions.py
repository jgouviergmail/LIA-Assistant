"""Provider-free questions with the real HITL presentation contract."""

from collections.abc import AsyncGenerator
from typing import Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.services.hitl.interactions.draft_critique import DraftCritiqueInteraction


class StaticDraftInteraction(DraftCritiqueInteraction):
    """Keep metadata real; replace only the provider-bound question generation."""

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        tracker: Any | None = None,
    ) -> AsyncGenerator[str]:
        yield "May the script reach example.org?"
