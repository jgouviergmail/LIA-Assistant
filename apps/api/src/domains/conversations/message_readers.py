"""Every module that queries the message table outside its repository DECLARES how it reads.

Since ADR-276 a conversation holds rows a person must never be shown: the
question and the answer of a ticket LIA ran alone, archived so the record stays
whole and marked ``hidden`` so the chat stays quiet. The repository applies
that predicate to every read it owns — and a predicate a repository applies
says nothing about the modules that build their own ``select`` over the same
table. Measured 2026-09-09: nineteen modules reference the model, and the
heartbeat's « last user message » read took a run's synthetic question for the
person's last words.

Three found one at a time is not a method, so this module makes the answer a
DECLARATION over a COMPLETE list (the ``direct_client_callers`` doctrine): the
guard walks every module under ``src/``, finds each one that reads a column of
``ConversationMessage``, and refuses one that is not declared here, one that is
declared and no longer reads, and one declared ``VISIBLE_ONLY`` whose statement
carries no hidden-row exclusion.

Two scopes, and the reason is written beside each entry:

- ``VISIBLE_ONLY`` — the module interprets rows as the PERSON's: what they last
  said, when they were last active, what they mean. A run's rows must not
  reach it.
- ``WHOLE_RECORD`` — the module measures, exports, purges or joins the record
  itself, or narrows to rows a run never writes. Hiding rows from it would make
  a count wrong or a record incomplete.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class ReadScope(str, Enum):
    """How a module reads the message table."""

    VISIBLE_ONLY = "visible_only"
    WHOLE_RECORD = "whole_record"


#: Module path → (scope, reason). Every reader outside the repository, and
#: nothing else: the guard refuses an omission AND a stale entry.
MESSAGE_READERS: Final[dict[str, tuple[ReadScope, str]]] = {
    "src.domains.conversations.activity_probe": (
        ReadScope.VISIBLE_ONLY,
        "when the person was last active — a run's synthetic question is not them speaking",
    ),
    "src.domains.heartbeat.context_aggregator": (
        ReadScope.VISIBLE_ONLY,
        "the person's last message — a ticket's brief would read as their last words",
    ),
    "src.domains.heartbeat.context_sources": (
        ReadScope.WHOLE_RECORD,
        "narrowed to proactive rows by their `type`, a key a run's rows never carry",
    ),
    "src.domains.journals.consolidation_service": (
        ReadScope.VISIBLE_ONLY,
        "the person's rhythm and their exchange — a run's brief is LIA's words, not theirs",
    ),
    "src.domains.chat.service": (
        ReadScope.WHOLE_RECORD,
        "sums TTS cost per assistant row, and a run synthesises no voice",
    ),
    "src.domains.conversations.response_feedback": (
        ReadScope.WHOLE_RECORD,
        "marks the row a person voted on, by the run id the card carries — a hidden row is "
        "never shown, so it is never voted on",
    ),
    "src.domains.shared.provenance_repository": (
        ReadScope.WHOLE_RECORD,
        "reads the content of a row a provenance reference names by id",
    ),
    "src.domains.google_api.export_service": (
        ReadScope.WHOLE_RECORD,
        "an export is the record, and STT/TTS cost rows are never a run's",
    ),
    "src.infrastructure.scheduler.demo_daily_report": (
        ReadScope.WHOLE_RECORD,
        "counts the record for the demo operator, hidden rows included and said so",
    ),
    "src.infrastructure.observability.lifetime_metrics": (
        ReadScope.WHOLE_RECORD,
        "measures the record: an archived row is a row, whoever wrote it",
    ),
    "src.domains.workboard.repository": (
        ReadScope.WHOLE_RECORD,
        "the retention sweep targets the hidden rows themselves and measures their volume",
    ),
}


__all__ = ["MESSAGE_READERS", "ReadScope"]
