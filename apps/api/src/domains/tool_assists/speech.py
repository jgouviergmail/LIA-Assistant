"""What LIA says aloud from the Tools (ADR-372).

The words are the ones on the person's screen, so nothing is read from a provider and no model
runs: a voice reads them, on its own run, under both ceilings (``text_readout``). A cut is said.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from src.core.config import settings
from src.core.constants import TOOL_ASSIST_READOUT_MAX_SENTENCES, TOOL_ASSIST_TASK_TYPE
from src.domains.tool_assists.door import AssistRun
from src.domains.voice.text_readout import synthesize_user_text


@dataclass(frozen=True, slots=True)
class HeardWords:
    """Words read aloud.

    Attributes:
        audio: The MP3, base64.
        cut: Only the beginning was read.
        cost_eur: What the voice cost; nothing on a free engine.
    """

    audio: str
    cut: bool
    cost_eur: float


async def read_aloud(run: AssistRun, words: str) -> HeardWords:
    """Read the words up to their bound.

    Args:
        run: The assist's run.
        words: The words on the person's screen.

    Returns:
        The audio, whether it stops short, and what it cost.

    Raises:
        UsageLimitExceededError: A ceiling closed: no paid engine was asked.
    """
    bound = settings.tool_assist_readout_max_chars
    readout = await synthesize_user_text(
        user_id=run.user_id,
        user_language=run.language,
        text=words[:bound],
        max_sentences=TOOL_ASSIST_READOUT_MAX_SENTENCES,
        run_prefix=TOOL_ASSIST_TASK_TYPE,
    )
    run.served = True
    return HeardWords(
        audio=base64.b64encode(readout.audio).decode("ascii"),
        cut=len(words) > bound or readout.cut,
        cost_eur=readout.cost_eur,
    )
