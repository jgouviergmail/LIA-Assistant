"""A new e-mail LIA writes for the person reads how they write (ADR-383).

Only a letter to someone does: a note to the person's own mailbox has no greeting
and no sign-off by design, and a subject alone carries no voice.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from src.domains.agents.emails import writing_style
from src.domains.agents.emails.content_generation import (
    NOTE_TO_SELF_RECIPIENT,
    generate_email_content,
)

pytestmark = pytest.mark.unit
MODULE = "src.domains.agents.emails.content_generation"
STYLE = "Writes « Salut », signs « Seb »."


async def _generate(recipient: str = "Claire", **overrides: Any) -> dict[str, Any]:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content='{"subject": "S", "body": "B"}'))
    style = AsyncMock(return_value=overrides.pop("style", STYLE))
    config = RunnableConfig(metadata={"run_id": "turn-1"})
    with (
        patch(f"{MODULE}.get_llm", return_value=llm),
        patch.object(writing_style, "writing_style_for", style),
    ):
        written = await generate_email_content(
            "propose vendredi 10h",
            recipient,
            "fr",
            config=config,
            sender_name="Seb",
            user_id="user-1",
            **overrides,
        )
    return {
        "written": written,
        "prompt": str(llm.ainvoke.await_args.args[0]),
        "style": style.await_args,
        "config": config,
    }


async def test_a_letter_reads_the_style_before_the_language_rule() -> None:
    seen = await _generate()

    prompt = seen["prompt"]
    assert prompt.index("signs « Seb »") < prompt.index("LANGUAGE:")
    assert "in place of rules 3, 4 and 5" in prompt
    assert seen["style"].args == ("user-1",)
    assert seen["style"].kwargs["config"] is seen["config"]


async def test_without_a_style_the_prompt_is_what_it_was() -> None:
    seen = await _generate(style=None)

    assert "WRITING STYLE" not in seen["prompt"]
    assert "{sender_name}\n\nLANGUAGE:".replace("{sender_name}", "Seb") in seen["prompt"]


async def test_a_note_to_self_reads_no_style() -> None:
    seen = await _generate(NOTE_TO_SELF_RECIPIENT)

    assert seen["style"] is None and "WRITING STYLE" not in seen["prompt"]


async def test_a_subject_alone_reads_no_style() -> None:
    seen = await _generate(existing_body="Salut Claire, vendredi 10h ? ++ Seb")

    assert seen["style"] is None and "WRITING STYLE" not in seen["prompt"]
    assert "Based on the instruction and the email body content" in seen["prompt"]
