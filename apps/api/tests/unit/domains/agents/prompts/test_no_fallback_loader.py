"""A prompt has one text, and it is the versioned file (prompt audit 2026-09-12, lot B/D).

``load_prompt_with_fallback`` was a « temporary migration helper » with two production
callers, each carrying an inline copy of its file — and one copy had already lost a
rule the file states (« an interruption still has to earn itself »), which is the
2026-09-06 trap again: a fallback that contradicts the versioned text and that no
prompt guard can read. The Literal sync test guarantees every file exists at CI time
and the image ships the store, so a missing file is a broken deployment that must fail
loudly, not degrade into a different prompt.
"""

from __future__ import annotations

import inspect

from src.domains.agents import prompts
from src.domains.agents.prompts import prompt_loader
from src.domains.heartbeat import wake_context
from src.infrastructure.scheduler import reminder_notification


def test_the_fallback_door_is_gone() -> None:
    assert not hasattr(prompt_loader, "load_prompt_with_fallback")
    assert "load_prompt_with_fallback" not in getattr(prompts, "__all__", ())


def test_no_caller_keeps_an_inline_copy_of_a_prompt() -> None:
    assert "fallback_content" not in inspect.getsource(wake_context)
    assert "FALLBACK_REMINDER_PROMPT" not in inspect.getsource(reminder_notification)


def test_the_wake_block_carries_the_files_rule() -> None:
    rendered = wake_context.build_fresh_block("a new mail from Alice")
    assert rendered.startswith("FRESH: a new mail from Alice.")
    assert "an interruption still has to earn itself" in rendered
