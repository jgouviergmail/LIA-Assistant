"""The refusal a name designating several people becomes — one wording, every tool.

A tool that resolves a person by name (``shared/name_resolution``) never
settles between candidates by order: it hands them back so the model asks the
user. The peer reads, the relayed message and the relationship reads say it
the same way, bounded the same way.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.shared.name_resolution import MAX_NAMED_CANDIDATES


def ambiguous_name_failure(spoken: str, candidates: Sequence[str]) -> UnifiedToolOutput:
    """Refuse a name several people carry, naming them so the user can choose.

    Args:
        spoken: The name as the person said it.
        candidates: Display names of everyone it designates, most relevant first.

    Returns:
        A ``DISAMBIGUATION_REQUIRED`` failure carrying the bounded candidates.
    """
    named = list(candidates)[:MAX_NAMED_CANDIDATES]
    return UnifiedToolOutput.failure(
        message=(
            f"Several people match '{spoken}': {', '.join(named)}. Ask the user "
            "which one they mean, then call again with that full name."
        ),
        error_code=ToolErrorCode.DISAMBIGUATION_REQUIRED,
        metadata={"candidates": named},
    )


__all__ = ["ambiguous_name_failure"]
