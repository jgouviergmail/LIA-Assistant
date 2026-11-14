"""What the answering model declares after its answer, behind one call per seam.

Two declarations follow an answer today, each owned by its own module: the
tone register (``expressivity``, ADR-253) and « nothing new » (a routine told
to notify only of something new, ``nothing_new``). The response node and the
stream that assembles the ``done`` chunk are both frozen at their size: each
calls ONE function here, and a third declaration will not make either grow.

The order is free — every declaration is removed by its own pattern wherever
it stands — and each one is a no-op when its feature does not apply.
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.expressivity.turn import (
    attach_tone_to_done,
    inject_tone_instruction,
    take_tone_annotation,
)
from src.domains.agents.services.nothing_new import (
    attach_nothing_new_to_done,
    inject_nothing_new_instruction,
    take_nothing_new,
)


def inject_answer_annotations(base_system_prompt: str) -> str:
    """Ask the answering model for the declarations this turn reads.

    Args:
        base_system_prompt: The assembled response prompt.

    Returns:
        The prompt with each applicable instruction before the final reminder.
    """
    return inject_nothing_new_instruction(inject_tone_instruction(base_system_prompt))


def take_answer_annotations(final_content: str, run_id: str) -> str:
    """Parse, park and strip every declaration the model appended to its answer.

    Runs BEFORE the relevant-ids parsing, like the psyche self-report: all of
    them modify the content.

    Args:
        final_content: The model's answer, tags included.
        run_id: The run the declarations belong to.

    Returns:
        The answer with every declaration removed.
    """
    return take_nothing_new(take_tone_annotation(final_content, run_id), run_id)


def attach_answer_annotations_to_done(done_metadata: dict[str, Any], run_id: str) -> None:
    """Put the run's declarations into the ``done`` metadata, in place.

    Args:
        done_metadata: The ``done`` metadata assembled so far.
        run_id: The run whose declarations are taken.
    """
    attach_tone_to_done(done_metadata, run_id)
    attach_nothing_new_to_done(done_metadata, run_id)
