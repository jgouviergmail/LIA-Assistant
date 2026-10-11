"""Refuse oversized entire meeting consent without cutting any selected value."""

import json

import tiktoken

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_read_budget import meeting_read_token_budget


def require_meeting_action_budget(draft: ApplicationActionDraftContent) -> None:
    serialized = json.dumps(draft.model_dump(mode="json"), ensure_ascii=False, default=str)
    token_count = len(
        tiktoken.get_encoding(settings.token_encoding_name).encode(
            serialized, disallowed_special=()
        )
    )
    if len(serialized.encode("utf-8")) > 64_000 or token_count > meeting_read_token_budget():
        raise CommandRejected("CONSTRAINT_VIOLATION")
