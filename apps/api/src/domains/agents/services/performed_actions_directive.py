"""What a ReAct turn DID, stated to the response model as its own acts (ADR-263 §23).

The sibling of ``runtime_failure_directive``: that module tells the answer what
FAILED, this one what SUCCEEDED. The response model reformulates the ReAct
loop's answer and never sees a tool result, so the loop's prose was its only
evidence that anything happened — and prose is misread: a caption under a
generated image became « I cannot generate images » (Docker dev, 2026-09-23).

The acts come from the effect REGISTER, never from the graph state: that is
what makes them facts. They are stated in a system block of their own, never
as lines of the data block — measured on the failing turn's own prompt, a bare
« Image générée : … » beside the loop's answer read as a caption somebody else
wrote (a denial the person saw) or as a second image the model then announced
(3 answers out of 100); the directive: 0 out of 100 for both.

The pipeline needs none of this — each tool's own confirmation (« Image generated
successfully and will be displayed automatically ») already reaches its summary —
except once a decision came back to the plan (``executed_drafts``, spec 2026-10-29
D7): the answer is then composed from the decided acts' accounts and the other
steps' summaries, and an MCP tool's summary is « result received », not its
confirmation. Measured 2026-10-30: beside a refused deletion, the answer told an
archive that had happened as « annulé ».
"""

from __future__ import annotations

from typing import Any

import structlog

from src.core.config import settings
from src.domains.agents.constants import STATE_KEY_EXECUTED_DRAFTS
from src.domains.agents.prompts.prompt_loader import load_prompt

logger = structlog.get_logger(__name__)


async def build_performed_actions_block(state: dict[str, Any], run_id: str, language: str) -> str:
    """The directive stating the turn's succeeded acts, or "" when there is none.

    Only a ReAct turn, or a Pipeline turn whose decision came back to the plan,
    reads the register — otherwise the pipeline's summary already carries each
    action's confirmation, and a turn with neither costs no query. The loop's result is read from the STATE, so a turn that acted
    without answering (a budget exit) still has its acts stated. Never raises:
    ``performed_effects`` swallows a register failure, and a turn whose acts
    cannot be read is answered without them rather than not at all.

    Args:
        state: The LangGraph state (``react_agent_result`` marks a ReAct turn,
            ``executed_drafts`` a decision that came back to the plan).
        run_id: The turn's TRUE run id (``run_id_of``), empty when unknown — then
            nothing is read. Never a logging placeholder: the register files
            rows under a placeholder of its own.
        language: The person's language, for the sentences.

    Returns:
        The rendered directive (braces NOT escaped: the chain escapes what it
        injects), or "".
    """
    if not state.get("react_agent_result") and not state.get(STATE_KEY_EXECUTED_DRAFTS):
        return ""
    from src.domains.agents.effects.turn_summary import (
        performed_effects,
        succeeded_effect_sentences,
    )

    sentences = succeeded_effect_sentences(await performed_effects(run_id), language)
    if not sentences:
        return ""
    logger.info("response_performed_actions_stated", run_id=run_id, count=len(sentences))
    return load_prompt(
        "response_directive_performed_actions",
        version=settings.response_prompt_version,
    ).format(performed_actions="\n".join(f"- {sentence}" for sentence in sentences))
