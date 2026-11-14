"""« Nothing new »: what a routine's answer declares when its owner asked for silence.

A routine whose owner ticked « only tell me when there is something new » still
runs, and its answer still lands in the chat: what is held back is the
NOTIFICATION. Whether an answer says anything new is known to the model that
wrote it and to nothing else, so that model declares it — by a machine tag
after the answer:

    <lia_nothing_new/>

The shape is the tone register's (ADR-253), for the same two reasons: the
declaration is made by the generation that wrote the answer, at no extra call,
and it is kept out of everything a person reads or hears — the token stream
(``streaming/machine_tags.py``) and the stored answer (the response node).

Three properties, each a way the option could have misfired:

- **the instruction is given only inside such a run** (:func:`quiet_run_scope`,
  published by the engine that drives the routine): an ordinary chat turn is
  never taught the tag, and its prompt does not grow by a token;
- **the declaration counts only inside such a run**: a tag written elsewhere is
  removed and declares nothing;
- **a run with something to admit is never « nothing new »**: a step that
  failed, a search cut short or a step left unrun voids the declaration
  (:func:`note_run_admission`) — the prompt says it, the code makes sure of it;
- **doubt notifies.** No tag, a tag cut short, a run that ended without its
  ``done`` chunk: the routine tells its owner, as it always did. Silence is the
  one outcome that needs a complete declaration.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Final

from src.domains.agents.prompts.prompt_loader import inject_before_final_reminder, load_prompt

#: The tag's opening: the cheap pre-test, and how the token stream recognises
#: the tag before it is complete.
NOTHING_NEW_TAG_MARKER: Final[str] = "<lia_nothing_new"

#: The complete declaration.
_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"<lia_nothing_new\s*/>", re.IGNORECASE)

#: Every occurrence, complete or cut short: from its opening to its first
#: ``>``, or to the end — the span the token stream removes too.
_SWEEP_PATTERN: Final[re.Pattern[str]] = re.compile(r"<lia_nothing_new[^>]*/?>?", re.IGNORECASE)

#: Key of the declaration in the ``done`` chunk's metadata.
DONE_KEY: Final[str] = "nothing_new"

#: True while the turn is a routine run whose owner asked to be told only of
#: something new.
_QUIET_RUN: ContextVar[bool] = ContextVar("quiet_run", default=False)

#: True once the run had something its answer must admit — a step that failed, a
#: search cut short, a step left unrun. Such a run is never « nothing new »,
#: whatever its model declares: the prompt says so, this makes sure of it.
_RUN_ADMITS: ContextVar[bool] = ContextVar("quiet_run_admits", default=False)

#: How long a declaration waits for its ``done`` chunk before it is forgotten.
_DECLARATION_TTL_SECONDS: Final[int] = 300

#: run id -> when it declared. Written by the response node deep in the graph,
#: popped where the ``done`` chunk is assembled, with no state in between —
#: the hand-off the tone annotation uses. Identifiers only, never content.
_declared: dict[str, float] = {}

_now = time.monotonic


@contextmanager
def quiet_run_scope(enabled: bool) -> Iterator[None]:
    """Publish, for the whole stream, that the run's owner wants silence when nothing is new.

    Args:
        enabled: The routine's own option; False publishes nothing new.
    """
    token = _QUIET_RUN.set(enabled)
    # Each run starts with nothing to admit: an earlier run's is not this one's.
    admits = _RUN_ADMITS.set(False)
    try:
        yield
    finally:
        _RUN_ADMITS.reset(admits)
        _QUIET_RUN.reset(token)


def is_quiet_run() -> bool:
    """Whether the current turn is a routine run told to notify only of something new."""
    return _QUIET_RUN.get()


def note_run_admission() -> None:
    """Record that this run's answer has something to admit; its « nothing new » is void.

    Called by the seam that assembles what an answer must admit about its own
    run (``runtime_failure_directive.build_run_honesty_block``), in the response
    node, before the model is asked — so the declaration read after it, in the
    same node, cannot stand for a run that failed somewhere (ADR-303).
    """
    _RUN_ADMITS.set(True)


def inject_nothing_new_instruction(base_system_prompt: str) -> str:
    """Tell the answering model how to declare that it has nothing new to say.

    Args:
        base_system_prompt: The assembled response prompt.

    Returns:
        The prompt with the instruction placed before the final reminder inside
        a quiet run; unchanged everywhere else.
    """
    if not is_quiet_run():
        return base_system_prompt
    return inject_before_final_reminder(
        base_system_prompt, str(load_prompt("routine_nothing_new_instruction"))
    )


def take_nothing_new(final_content: str, run_id: str) -> str:
    """Strip the declaration from the answer, and park it for the ``done`` chunk.

    Args:
        final_content: The model's answer, tag included.
        run_id: The run the declaration belongs to.

    Returns:
        The answer without any occurrence of the tag — unchanged when there
        was none.
    """
    if NOTHING_NEW_TAG_MARKER not in final_content.lower():
        return final_content
    declared = _TAG_PATTERN.search(final_content) is not None
    if declared and is_quiet_run() and not _RUN_ADMITS.get():
        _declared[run_id] = _now()
    return _SWEEP_PATTERN.sub("", final_content).strip()


def attach_nothing_new_to_done(done_metadata: dict[str, Any], run_id: str) -> None:
    """Put the run's declaration into the ``done`` metadata, in place, once.

    Args:
        done_metadata: The ``done`` metadata assembled so far.
        run_id: The run whose declaration is taken.
    """
    now = _now()
    for stale in [key for key, at in _declared.items() if now - at > _DECLARATION_TTL_SECONDS]:
        del _declared[stale]
    if _declared.pop(run_id, None) is not None:
        done_metadata[DONE_KEY] = True
