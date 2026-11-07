"""What LIA can do from the Tools, declared once (ADR-372).

An assist names the slot that writes it and the source it reads, so the door bills the right row
and files the right read without either being typed at a call site. A slot is the assistant's own
wherever the assistant already writes the same thing: the same words, the same cache, the same
administrator's choice. The registry is checked complete at boot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from src.core.constants import TOOL_ASSIST_LLM_TYPE, TOOL_ASSIST_VISION_LLM_TYPE
from src.domains.agents.emails.digest import LLM_TYPE as DIGEST_SLOT
from src.domains.agents.emails.reply_drafting import LLM_TYPE as MAIL_WRITING_SLOT

#: The sections an assist reads, as the surface of its consultations names them.
SECTION_MAIL: Final = "mail"
SECTION_FILES: Final = "files"
SECTION_CONTACTS: Final = "contacts"


class ToolAssist(str, Enum):
    """One thing a click can ask of LIA."""

    MAIL_SUMMARY = "mail_summary"
    MAIL_REPLY = "mail_reply"
    MAIL_COMPOSE = "mail_compose"
    MAIL_SUBJECT = "mail_subject"
    MAIL_TRANSLATE = "mail_translate"
    MAIL_EVENT = "mail_event"
    MAIL_TASK = "mail_task"
    MAIL_CONVERSATION = "mail_conversation"
    MAIL_ATTACHMENT = "mail_attachment"
    FILE_SUMMARY = "file_summary"
    MAIL_SEARCH = "mail_search"
    MAIL_FILTER = "mail_filter"
    MAIL_TRIAGE = "mail_triage"
    CONTACT_COMPLETE = "contact_complete"
    CONTACT_FROM_CARD = "contact_from_card"
    EVENT_FROM_WORDS = "event_from_words"
    TASK_FROM_WORDS = "task_from_words"
    TASK_STEPS = "task_steps"
    TEXT_REWRITE = "text_rewrite"
    TEXT_TRANSLATE = "text_translate"
    TEXT_WRITE = "text_write"
    READ_ALOUD = "read_aloud"


@dataclass(frozen=True, slots=True)
class AssistSpec:
    """How one assist runs.

    Attributes:
        slot: The LLM slot that answers it; a file read by sight moves to the vision slot.
        sections: The sources it opens; none for words the person is writing.
        asks_a_model: A model answers it; a voice asks the ceilings itself, and a free
            engine answers to none.
    """

    slot: str
    sections: tuple[str, ...] = ()
    asks_a_model: bool = True


ASSISTS: Final[dict[ToolAssist, AssistSpec]] = {
    ToolAssist.MAIL_SUMMARY: AssistSpec(slot=DIGEST_SLOT, sections=(SECTION_MAIL,)),
    ToolAssist.MAIL_REPLY: AssistSpec(slot=MAIL_WRITING_SLOT, sections=(SECTION_MAIL,)),
    ToolAssist.MAIL_COMPOSE: AssistSpec(slot=MAIL_WRITING_SLOT),
    ToolAssist.MAIL_SUBJECT: AssistSpec(slot=MAIL_WRITING_SLOT),
    ToolAssist.MAIL_TRANSLATE: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE, sections=(SECTION_MAIL,)),
    ToolAssist.MAIL_EVENT: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE, sections=(SECTION_MAIL,)),
    ToolAssist.MAIL_TASK: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE, sections=(SECTION_MAIL,)),
    ToolAssist.MAIL_CONVERSATION: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE, sections=(SECTION_MAIL,)),
    ToolAssist.MAIL_ATTACHMENT: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE, sections=(SECTION_MAIL,)),
    ToolAssist.FILE_SUMMARY: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE, sections=(SECTION_FILES,)),
    ToolAssist.MAIL_SEARCH: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE),
    ToolAssist.MAIL_FILTER: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE),
    ToolAssist.MAIL_TRIAGE: AssistSpec(slot=DIGEST_SLOT, sections=(SECTION_MAIL,)),
    ToolAssist.CONTACT_COMPLETE: AssistSpec(
        slot=TOOL_ASSIST_LLM_TYPE, sections=(SECTION_CONTACTS, SECTION_MAIL)
    ),
    ToolAssist.CONTACT_FROM_CARD: AssistSpec(slot=TOOL_ASSIST_VISION_LLM_TYPE),
    ToolAssist.EVENT_FROM_WORDS: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE),
    ToolAssist.TASK_FROM_WORDS: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE),
    ToolAssist.TASK_STEPS: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE),
    ToolAssist.TEXT_REWRITE: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE),
    ToolAssist.TEXT_TRANSLATE: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE),
    ToolAssist.TEXT_WRITE: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE),
    # No model: the voice bills on its own run, and the slot here prices nothing.
    ToolAssist.READ_ALOUD: AssistSpec(slot=TOOL_ASSIST_LLM_TYPE, asks_a_model=False),
}


def assert_assist_registry_completeness() -> None:
    """Refuse to boot on an assist nobody declared.

    Raises:
        AssertionError: A member of :class:`ToolAssist` has no entry.
    """
    missing = [assist.value for assist in ToolAssist if assist not in ASSISTS]
    assert not missing, f"tool assists without a spec: {missing}"
