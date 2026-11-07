"""What the assists' routes take and answer (ADR-372).

A source is named by its id, never sent: the server reads what the model reads. Only words the
person is writing travel in the request, under the bounds the page is told (ADR-184). Every answer
is a proposal, and carries what it cost, or nothing when it was already held.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from src.core.config import settings
from src.core.constants import (
    TOOL_ASSIST_LABELS_MAX,
    TOOL_ASSIST_LANGUAGE_MAX_CHARS,
    TOOL_ASSIST_LISTS_MAX,
    TOOL_ASSIST_RECIPIENT_MAX_CHARS,
    WORKBENCH_TASK_TITLE_MAX_CHARS,
)
from src.core.llm_usage import LLMUsage
from src.domains.tool_assists.actions import ProposedEvent, ProposedTask
from src.domains.tool_assists.contact_card import ProposedContact, ProposedValue
from src.domains.tool_assists.mail_triage import TriagedMessage
from src.domains.tool_assists.mail_words import ProposedFilter, ProposedSearch
from src.domains.tool_assists.text import RewriteTone, WritingKind
from src.domains.workbench.ids import ProviderId
from src.domains.workbench.schemas.mail import AttachmentRequest

#: What the person says the answer should do, in their words. The constraint sits on
#: ``str | None``: an Annotated wrapped in a union would lose it.
OptionalInstruction = Annotated[
    str | None,
    StringConstraints(min_length=1, max_length=settings.tool_assist_instruction_max_chars),
]


class AssistAnswer(BaseModel):
    """What every answer carries."""

    model_config = ConfigDict(frozen=True)

    usage: LLMUsage | None = Field(
        default=None, description="What this answer cost; none when it was already held."
    )


class MessageAssist(BaseModel):
    """An assist on one message."""

    message_id: ProviderId = Field(description="The message, as the listing named it.")


class ReplyAssist(MessageAssist):
    """A reply to write."""

    instruction: OptionalInstruction = Field(default=None, description="What it should say.")


#: The person's own words, under the bound a writing helper publishes.
PersonWords = Annotated[
    str, StringConstraints(min_length=1, max_length=settings.tool_assist_text_max_chars)
]
Instruction = Annotated[
    str, StringConstraints(min_length=1, max_length=settings.tool_assist_instruction_max_chars)
]
OptionalWords = Annotated[
    str | None, StringConstraints(max_length=settings.tool_assist_text_max_chars)
]
#: A list as the person named it.
ListName = Annotated[str, StringConstraints(max_length=WORKBENCH_TASK_TITLE_MAX_CHARS)]


def _typed_so_far(recipient: object) -> object:
    """Who a message is for, as far as a model is told: a long list is no reason to refuse."""
    return recipient[:TOOL_ASSIST_RECIPIENT_MAX_CHARS] if isinstance(recipient, str) else recipient


#: Who a message is for, as the person typed it so far.
OptionalRecipient = Annotated[
    str | None,
    BeforeValidator(_typed_so_far),
    StringConstraints(max_length=TOOL_ASSIST_RECIPIENT_MAX_CHARS),
]
#: A language as a person names it: « espagnol », « Spanish », « pt-BR ».
LanguageName = Annotated[
    str, StringConstraints(min_length=2, max_length=TOOL_ASSIST_LANGUAGE_MAX_CHARS)
]


class RewriteAssist(BaseModel):
    """A change to words being written."""

    text: PersonWords = Field(description="The words as they stand.")
    tone: RewriteTone = Field(description="The change asked.")


class TranslateAssist(BaseModel):
    """Words being written, in another language."""

    text: PersonWords = Field(description="The words as they stand.")
    language: LanguageName = Field(description="The language asked, as the person names it.")


class WriteAssist(BaseModel):
    """A text to write from the person's words."""

    kind: WritingKind = Field(description="What the text is for.")
    instruction: Instruction = Field(description="What it should say.")


class ComposeAssist(BaseModel):
    """A new message to write."""

    instruction: Instruction = Field(description="What it should say.")
    recipient: OptionalRecipient = Field(default=None, description="Who it is for, if known.")


class SubjectAssist(BaseModel):
    """A subject for words already written."""

    body: PersonWords = Field(description="The message's words.")
    recipient: OptionalRecipient = Field(default=None, description="Who it is for, if known.")


class SentenceAssist(BaseModel):
    """What a person says in their own words."""

    sentence: Instruction = Field(description="Their words.")


class TaskSentenceAssist(SentenceAssist):
    """A task said in a sentence, which may name one of the person's lists."""

    lists: list[ListName] = Field(
        default_factory=list, max_length=TOOL_ASSIST_LISTS_MAX, description="The lists' names."
    )

    @field_validator("lists", mode="before")
    @classmethod
    def _first_lists(cls, lists: object) -> object:
        """More lists than a sentence is read against: the first ones stand for them."""
        return lists[:TOOL_ASSIST_LISTS_MAX] if isinstance(lists, list) else lists


class FilterSentenceAssist(SentenceAssist):
    """A filter said in a sentence, which may name one of the person's labels."""

    labels: list[ListName] = Field(
        default_factory=list, max_length=TOOL_ASSIST_LABELS_MAX, description="Their names."
    )

    @field_validator("labels", mode="before")
    @classmethod
    def _first_labels(cls, labels: object) -> object:
        """More labels than a sentence is read against: the first ones stand for them."""
        return labels[:TOOL_ASSIST_LABELS_MAX] if isinstance(labels, list) else labels


class TriageAssist(BaseModel):
    """The messages of a page."""

    message_ids: list[ProviderId] = Field(
        min_length=1,
        max_length=settings.workbench_page_size,
        description="The messages on screen.",
    )


class StepsAssist(BaseModel):
    """A task to break down: the person's own words, in the form open."""

    title: Instruction = Field(description="The task.")
    notes: OptionalWords = Field(default=None, description="Its notes.")


class SearchAnswer(AssistAnswer):
    """Criteria for the screen: nothing is listed until they stand on it."""

    search: ProposedSearch = Field(description="What was read, as the screen can take it.")


class FilterAnswer(AssistAnswer):
    """A filter for its form: nothing exists until the person creates it."""

    filter: ProposedFilter = Field(description="What was read, as the form can take it.")


class TriageAnswer(AssistAnswer):
    """What a page weighs: the page sorts what it already shows."""

    items: list[TriagedMessage] = Field(description="The messages read.")
    skipped: int = Field(ge=0, description="How many could not be: they keep their place.")


class ContactValuesAnswer(AssistAnswer):
    """What a card could gain, each value with its source: nothing is written."""

    values: list[ProposedValue] = Field(description="The values found.")


class CardAnswer(AssistAnswer):
    """A card read, for the editor: nothing exists until the person saves it."""

    contact: ProposedContact = Field(description="What was read, as the editor can take it.")


class EventAnswer(AssistAnswer):
    """An event for the editor: nothing exists until the person saves it."""

    event: ProposedEvent = Field(description="What was read, as a form can take it.")


class TaskAnswer(AssistAnswer):
    """A task for its form: nothing exists until the person adds it."""

    task: ProposedTask = Field(description="What was read, as a form can take it.")


class StepsAnswer(AssistAnswer):
    """Steps proposed, in order."""

    steps: list[str] = Field(description="Short concrete actions.")


class ReadAloud(BaseModel):
    """Words the person is looking at."""

    text: PersonWords = Field(description="The words, as the screen shows them.")


class ReadAloudAnswer(AssistAnswer):
    """Words heard: one file, whole or cut; a voice bills no tokens, so no usage rides it."""

    audio: str = Field(description="The MP3, base64.")
    cut: bool = Field(description="Only the beginning was read.")
    cost_eur: float = Field(description="What the voice cost; nothing on a free engine.")


class ContactAssist(BaseModel):
    """An assist on one contact."""

    contact_id: ProviderId = Field(description="The contact.")


class FileAssist(BaseModel):
    """An assist on one drive's file."""

    file_id: ProviderId = Field(description="The file.")


class KeepFile(BaseModel):
    """A drive's file to keep in a space."""

    space_id: UUID = Field(description="The space.")
    file_id: ProviderId = Field(description="The file.")


class KeepAttachment(AttachmentRequest):
    """A message's attachment to keep in a space."""

    space_id: UUID = Field(description="The space.")


class KeptDocument(BaseModel):
    """The document a space made of it: its indexing goes on from there."""

    document_id: UUID = Field(description="The document.")


class MailSummaryAnswer(AssistAnswer):
    """The digest of a message."""

    gist: str = Field(description="What it is about and what it asks, in a sentence or two.")
    key_points: list[str] = Field(description="Facts, figures, dates, names.")
    actions: list[str] = Field(description="What the reader is expected to do.")
    category: str = Field(description="What kind of message it is.")
    importance: str = Field(description="How much it matters: high, normal or low.")


class TextAnswer(AssistAnswer):
    """Words proposed: the person reads them before anything is done with them."""

    text: str = Field(description="The words proposed, plain text.")
    subject: str | None = Field(default=None, description="The subject, for a whole message.")
    cut: bool = Field(default=False, description="Only the beginning of the source was read.")
