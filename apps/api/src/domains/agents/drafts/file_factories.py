"""The drafts of a file's sharing (ADR-369, lot 6): beside ``service.py``, at its size cap."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.agents.drafts.models import DraftType, FileShareDraftInput
from src.domains.agents.drafts.service import DraftService

if TYPE_CHECKING:
    from src.domains.agents.tools.output import UnifiedToolOutput


def create_file_share_draft(
    draft_input: FileShareDraftInput,
    source_tool: str = "share_file_tool",
) -> UnifiedToolOutput:
    """Create the draft of a file's sharing: nobody is told before it is confirmed.

    Args:
        draft_input: The item, the person, what they may do.
        source_tool: Tool creating this draft.

    Returns:
        UnifiedToolOutput with the draft.
    """
    return DraftService().create_draft(
        draft_type=DraftType.FILE_SHARE,
        content=draft_input.model_dump(),
        related_registry_ids=draft_input.related_registry_ids,
        source_tool=source_tool,
        source_step_id=None,
        user_language=draft_input.user_language,
    )


__all__ = ["create_file_share_draft"]
