"""The two seams the response node needs, and nothing else.

Both of these lived inside ``response_node`` for exactly one commit, which was
long enough for the file-size and complexity ratchets to say what they always
say about that file: a logical file never grows. They were right on the merits
too — asking the model for a register and reading the register back are the
expressivity domain's job, and the node's job is to call one function each.

Everything here is a no-op when the feature is off: the tag is never requested,
so there is nothing to parse and nothing to strip.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.core.config import settings
from src.domains.agents.expressivity.annotation import (
    parse_tone_annotation,
    pop_tone_annotation,
    store_tone_annotation,
)
from src.domains.agents.prompts.prompt_loader import (
    inject_before_final_reminder,
    load_prompt,
)

logger = structlog.get_logger(__name__)


def inject_tone_instruction(base_system_prompt: str) -> str:
    """Ask the model to declare the register of the answer it is about to write.

    Independent of the psyche on purpose — one says how LIA feels over time, the
    other how THIS sentence was said, and folding them together is what made
    every turn land on the same face (ADR-253).

    Args:
        base_system_prompt: The assembled response prompt.

    Returns:
        The prompt with the instruction placed before the final reminder, or
        unchanged when the feature is off.
    """
    if not settings.expressivity_enabled:
        return base_system_prompt
    return inject_before_final_reminder(
        base_system_prompt, str(load_prompt("expressivity_tone_instruction"))
    )


def take_tone_annotation(final_content: str, run_id: str) -> str:
    """Parse, park and strip the per-turn tone tag.

    Runs beside the psyche self-report parser and for the same reason: both
    modify the content, and both must do so BEFORE relevant_ids parsing. The
    annotation is parked in the per-run registry for the SSE ``done`` chunk to
    pop; nothing downstream in the graph reads it.

    Args:
        final_content: The model's answer, tag included.
        run_id: Pipeline run the annotation belongs to.

    Returns:
        The content with the tag removed — unchanged when there was none.
    """
    if not settings.expressivity_enabled:
        return final_content
    try:
        annotation, cleaned = parse_tone_annotation(final_content)
        if annotation is not None:
            store_tone_annotation(run_id, annotation)
            logger.debug(
                "expressivity_tone_parsed",
                run_id=run_id,
                register=annotation.register,
                intensity=annotation.intensity,
                accent=annotation.accent,
            )
        return cleaned
    except Exception as e:
        # A tone the avatar will not play is never worth failing a response for.
        logger.warning(
            "expressivity_tone_parse_failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return final_content


def attach_tone_to_done(done_metadata: dict[str, Any], run_id: str) -> None:
    """Put the turn's register into the SSE ``done`` metadata, in place.

    Same per-run hand-off as the psyche summary, and the same reason: the tag
    is parsed deep in the graph, the chunk is assembled in the API layer, and
    there is no state in between.

    A failure here costs a face, never a response — the ``done`` chunk carries
    the token accounting and the generated artefacts, and none of that may be
    lost because an avatar wanted an expression.
    """
    if not settings.expressivity_enabled:
        return
    try:
        annotation = pop_tone_annotation(run_id)
        if annotation is not None:
            done_metadata["expressivity"] = annotation.to_wire()
    except Exception as e:
        logger.debug("expressivity_done_metadata_failed", run_id=run_id, error=str(e))
