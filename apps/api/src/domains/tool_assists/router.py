"""Routes of what LIA does from the Tools (ADR-372).

The router IS the ability, under the assist guard; source-specific routes also require the Tools. Every route
authenticates on a session of its own, closed before a provider or a model is reached (ADR-304),
and sits under a window of its own: a click spends euros, so a replayed session must not. The JSON
answer is whole or refused: nothing streams, and nothing here writes to a provider.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, status

from src.core.config import settings
from src.core.constants import WORKBENCH_CONTACT_PHOTO_MAX_BYTES
from src.core.i18n import normalize_language
from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.time_utils import resolve_user_timezone
from src.core.user_display import resolve_user_display_name
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies, require_capability
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.tool_assists import (
    actions,
    contact_card,
    files,
    keeping,
    mail,
    mail_triage,
    mail_words,
    passage,
    selection_routes,
    speech,
    text,
)
from src.domains.tool_assists.catalogue import ToolAssist
from src.domains.tool_assists.door import AssistRun, run_assist
from src.domains.tool_assists.schemas import (
    CardAnswer,
    ComposeAssist,
    ContactAssist,
    ContactValuesAnswer,
    EventAnswer,
    FileAssist,
    FilterAnswer,
    FilterSentenceAssist,
    FocusedMessageAssist,
    KeepAttachment,
    KeepFile,
    KeptDocument,
    MailSummaryAnswer,
    MailTaskAssist,
    MessageAssist,
    PassageAssist,
    ReadAloud,
    ReadAloudAnswer,
    ReplyAssist,
    RewriteAssist,
    SearchAnswer,
    SentenceAssist,
    StepsAnswer,
    StepsAssist,
    SubjectAssist,
    TaskAnswer,
    TaskSentenceAssist,
    TextAnswer,
    TranslateAssist,
    TriageAnswer,
    TriageAssist,
    WriteAssist,
)
from src.domains.users.models import User
from src.domains.workbench.downloads import one_transfer
from src.domains.workbench.errors import TOO_LARGE, refuse
from src.domains.workbench.schemas.mail import AttachmentRequest

rate_limit_assist = create_user_rate_limiter(
    "tool_assist",
    max_calls=settings.tool_assist_rate_limit_calls,
    window_seconds=settings.tool_assist_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)

Person = Annotated[User, Depends(get_current_active_session_for_stream)]

router = APIRouter(
    prefix="/tool-assists",
    tags=["Tool assists"],
    dependencies=[
        *capability_dependencies(PlatformCapability.TOOL_ASSISTS),
        Depends(rate_limit_assist),
    ],
)


source_router = APIRouter(dependencies=capability_dependencies(PlatformCapability.WORKBENCH))


def _language(user: User) -> str:
    """The language an assist answers in: the account's."""
    return normalize_language(user.language)


def _sender(user: User) -> str | None:
    """The person's first name, for a signature they asked for."""
    return resolve_user_display_name(user.full_name, user.email) or None


def _clock(user: User) -> actions.AssistClock:
    """The person's day and zone, read at the click."""
    zone = resolve_user_timezone(user)
    return actions.AssistClock(today=datetime.now(zone).date(), zone=str(zone))


@source_router.post(
    "/mail/summary",
    response_model=MailSummaryAnswer,
    summary="What a message says and asks, in a few lines",
)
async def post_mail_summary(body: MessageAssist, user: Person) -> MailSummaryAnswer:
    """Condense the message; what the assistant already holds costs nothing."""
    done = await run_assist(
        ToolAssist.MAIL_SUMMARY,
        user.id,
        _language(user),
        lambda run: mail.summarize_message(run, body.message_id),
    )
    return MailSummaryAnswer(**done.value.model_dump(), usage=done.usage)


@source_router.post(
    "/mail/reply",
    response_model=TextAnswer,
    summary="A reply to a message, proposed: nothing is sent or saved",
)
async def post_mail_reply(body: ReplyAssist, user: Person) -> TextAnswer:
    """Write the reply the person will read before sending anything."""
    sender = _sender(user)

    async def write(run: AssistRun) -> str:
        return await mail.propose_reply(run, body.message_id, body.instruction, sender)

    done = await run_assist(ToolAssist.MAIL_REPLY, user.id, _language(user), write)
    return TextAnswer(text=done.value, usage=done.usage)


@source_router.post(
    "/mail/compose",
    response_model=TextAnswer,
    summary="A whole message from an instruction, proposed: nothing is sent or saved",
)
async def post_mail_compose(body: ComposeAssist, user: Person) -> TextAnswer:
    """Write the message the person will read before sending anything."""
    sender = _sender(user)

    async def write(run: AssistRun) -> mail.ComposedMessage:
        return await mail.compose_message(run, body.instruction, body.recipient, sender)

    done = await run_assist(ToolAssist.MAIL_COMPOSE, user.id, _language(user), write)
    return TextAnswer(text=done.value.body, subject=done.value.subject, usage=done.usage)


@source_router.post(
    "/mail/subject",
    response_model=TextAnswer,
    summary="A subject for words already written",
)
async def post_mail_subject(body: SubjectAssist, user: Person) -> TextAnswer:
    """Propose a subject; the person's field changes only if they take it."""
    done = await run_assist(
        ToolAssist.MAIL_SUBJECT,
        user.id,
        _language(user),
        lambda run: mail.propose_subject(run, body.body, body.recipient),
    )
    return TextAnswer(text=done.value, usage=done.usage)


@source_router.post(
    "/mail/translate",
    response_model=TextAnswer,
    summary="A received message in the reader's language",
)
async def post_mail_translate(body: MessageAssist, user: Person) -> TextAnswer:
    """Translate the message; a cut is said."""
    done = await run_assist(
        ToolAssist.MAIL_TRANSLATE,
        user.id,
        _language(user),
        lambda run: mail.translate_message(run, body.message_id),
    )
    return TextAnswer(text=done.value.text, cut=done.value.cut, usage=done.usage)


@source_router.post(
    "/mail/conversation",
    response_model=TextAnswer,
    summary="Where a conversation stands, in a few lines",
)
async def post_mail_conversation(body: MessageAssist, user: Person) -> TextAnswer:
    """Sum up the latest of what was said around a message; a cut is said."""
    done = await run_assist(
        ToolAssist.MAIL_CONVERSATION,
        user.id,
        _language(user),
        lambda run: mail.summarize_conversation(run, body.message_id),
    )
    return TextAnswer(text=done.value.text, cut=done.value.cut, usage=done.usage)


@source_router.post(
    "/mail/attachment",
    response_model=TextAnswer,
    summary="What a message's attachment says, in a few lines",
)
async def post_mail_attachment(body: AttachmentRequest, user: Person) -> TextAnswer:
    """Read the attachment by what it is; a cut is said."""
    done = await run_assist(
        ToolAssist.MAIL_ATTACHMENT,
        user.id,
        _language(user),
        lambda run: files.summarize_attachment(run, body),
    )
    return TextAnswer(text=done.value.text, cut=done.value.cut, usage=done.usage)


@source_router.post(
    "/files/summary",
    response_model=TextAnswer,
    summary="What a drive's file says, in a few lines",
)
async def post_file_summary(body: FileAssist, user: Person) -> TextAnswer:
    """Read the file by what it is; a cut is said."""
    done = await run_assist(
        ToolAssist.FILE_SUMMARY,
        user.id,
        _language(user),
        lambda run: files.summarize_file(run, body.file_id),
    )
    return TextAnswer(text=done.value.text, cut=done.value.cut, usage=done.usage)


@source_router.post(
    "/mail/search",
    response_model=SearchAnswer,
    summary="Criteria read from a sentence, for the screen: nothing is listed yet",
)
async def post_mail_search(body: SentenceAssist, user: Person) -> SearchAnswer:
    """Turn the person's words into criteria they see and can change."""
    clock = _clock(user)
    done = await run_assist(
        ToolAssist.MAIL_SEARCH,
        user.id,
        _language(user),
        lambda run: mail_words.search_from_sentence(run, body.sentence, clock),
    )
    return SearchAnswer(search=done.value, usage=done.usage)


@source_router.post(
    "/mail/filter",
    response_model=FilterAnswer,
    summary="A filter read from a sentence, for its form: nothing is created",
)
async def post_mail_filter(body: FilterSentenceAssist, user: Person) -> FilterAnswer:
    """Fill the filter's form from the person's words."""
    done = await run_assist(
        ToolAssist.MAIL_FILTER,
        user.id,
        _language(user),
        lambda run: mail_words.filter_from_sentence(run, body.sentence, body.labels),
    )
    return FilterAnswer(filter=done.value, usage=done.usage)


@source_router.post(
    "/mail/triage",
    response_model=TriageAnswer,
    summary="What the messages on screen weigh: the page sorts them",
)
async def post_mail_triage(body: TriageAssist, user: Person) -> TriageAnswer:
    """Weigh a page; what is already held costs nothing."""
    done = await run_assist(
        ToolAssist.MAIL_TRIAGE,
        user.id,
        _language(user),
        lambda run: mail_triage.triage_messages(run, body.message_ids),
    )
    return TriageAnswer(items=done.value.items, skipped=done.value.skipped, usage=done.usage)


@source_router.post(
    "/mail/event",
    response_model=EventAnswer,
    summary="The event a message describes, for the editor: nothing is created",
)
async def post_mail_event(body: FocusedMessageAssist, user: Person) -> EventAnswer:
    """Read the event; the person checks it in the editor and saves it, or not."""
    clock = _clock(user)
    done = await run_assist(
        ToolAssist.MAIL_EVENT,
        user.id,
        _language(user),
        lambda run: actions.event_from_message(run, body.message_id, clock, body.focus),
    )
    return EventAnswer(event=done.value, usage=done.usage)


@source_router.post(
    "/mail/task",
    response_model=TaskAnswer,
    summary="The task a message leaves, for its form: nothing is created",
)
async def post_mail_task(body: MailTaskAssist, user: Person) -> TaskAnswer:
    """Read the task; the person checks it and adds it, or not."""
    clock = _clock(user)
    done = await run_assist(
        ToolAssist.MAIL_TASK,
        user.id,
        _language(user),
        lambda run: actions.task_from_message(run, body.message_id, clock, body.lists, body.focus),
    )
    return TaskAnswer(task=done.value, usage=done.usage)


@source_router.post(
    "/calendar/from-words",
    response_model=EventAnswer,
    summary="An event said in a sentence, for the editor: nothing is created",
)
async def post_event_from_words(body: SentenceAssist, user: Person) -> EventAnswer:
    """Fill the editor from the person's sentence."""
    clock = _clock(user)
    done = await run_assist(
        ToolAssist.EVENT_FROM_WORDS,
        user.id,
        _language(user),
        lambda run: actions.event_from_sentence(run, body.sentence, clock),
    )
    return EventAnswer(event=done.value, usage=done.usage)


@source_router.post(
    "/tasks/from-words",
    response_model=TaskAnswer,
    summary="A task said in a sentence: nothing is created until the person adds it",
)
async def post_task_from_words(body: TaskSentenceAssist, user: Person) -> TaskAnswer:
    """Read the person's sentence, its day and the list it names."""
    clock = _clock(user)
    done = await run_assist(
        ToolAssist.TASK_FROM_WORDS,
        user.id,
        _language(user),
        lambda run: actions.task_from_sentence(run, body.sentence, clock, body.lists),
    )
    return TaskAnswer(task=done.value, usage=done.usage)


@source_router.post(
    "/tasks/steps",
    response_model=StepsAnswer,
    summary="The steps of a task, proposed: nothing is added",
)
async def post_task_steps(body: StepsAssist, user: Person) -> StepsAnswer:
    """Break the task down; the person keeps what they want."""
    done = await run_assist(
        ToolAssist.TASK_STEPS,
        user.id,
        _language(user),
        lambda run: actions.steps_of_task(run, body.title, body.notes),
    )
    return StepsAnswer(steps=done.value, usage=done.usage)


@source_router.post(
    "/spaces/keep-file",
    response_model=KeptDocument,
    status_code=status.HTTP_201_CREATED,
    summary="A drive's file kept in a knowledge space",
    dependencies=[Depends(require_capability(PlatformCapability.RAG_SPACES))],
)
async def post_keep_file(body: KeepFile, user: Person) -> KeptDocument:
    """The person's own act: the space judges the file as it judges an upload."""
    return KeptDocument(document_id=await keeping.keep_file(user.id, body.space_id, body.file_id))


@source_router.post(
    "/spaces/keep-attachment",
    response_model=KeptDocument,
    status_code=status.HTTP_201_CREATED,
    summary="A message's attachment kept in a knowledge space",
    dependencies=[Depends(require_capability(PlatformCapability.RAG_SPACES))],
)
async def post_keep_attachment(body: KeepAttachment, user: Person) -> KeptDocument:
    """The person's own act: the space judges the file as it judges an upload."""
    request = AttachmentRequest(
        message_id=body.message_id, attachment_id=body.attachment_id, filename=body.filename
    )
    return KeptDocument(document_id=await keeping.keep_attachment(user.id, body.space_id, request))


@source_router.post(
    "/contacts/complete",
    response_model=ContactValuesAnswer,
    summary="What a contact's latest messages say that the card lacks: nothing is written",
)
async def post_contact_complete(body: ContactAssist, user: Person) -> ContactValuesAnswer:
    """Propose values, each with the message that says it."""
    done = await run_assist(
        ToolAssist.CONTACT_COMPLETE,
        user.id,
        _language(user),
        lambda run: contact_card.complete_contact(run, body.contact_id),
    )
    return ContactValuesAnswer(values=done.value, usage=done.usage)


@source_router.post(
    "/contacts/from-card",
    response_model=CardAnswer,
    summary="A photographed business card, for the editor: nothing is created",
)
async def post_contact_from_card(file: UploadFile, user: Person) -> CardAnswer:
    """Read the card: read here, under the account's one transfer."""
    if file.size is None or file.size > WORKBENCH_CONTACT_PHOTO_MAX_BYTES:
        refuse(TOO_LARGE, max_bytes=WORKBENCH_CONTACT_PHOTO_MAX_BYTES)
    async with one_transfer(user.id):
        data = await file.read()
    done = await run_assist(
        ToolAssist.CONTACT_FROM_CARD,
        user.id,
        _language(user),
        lambda run: contact_card.contact_from_card(run, data),
    )
    return CardAnswer(contact=done.value, usage=done.usage)


@source_router.post(
    "/contacts/from-words",
    response_model=CardAnswer,
    summary="A contact said in a sentence, for the editor: nothing is created",
)
async def post_contact_from_words(body: SentenceAssist, user: Person) -> CardAnswer:
    """Fill the new-contact form from the person's words, held to what they say."""
    done = await run_assist(
        ToolAssist.CONTACT_FROM_WORDS,
        user.id,
        _language(user),
        lambda run: contact_card.contact_from_words(run, body.sentence),
    )
    return CardAnswer(contact=done.value, usage=done.usage)


@router.post(
    "/read-aloud",
    response_model=ReadAloudAnswer,
    summary="Words on the screen, read aloud",
    dependencies=[Depends(require_capability(PlatformCapability.TTS))],
)
async def post_read_aloud(body: ReadAloud, user: Person) -> ReadAloudAnswer:
    """Read what the person is looking at: no model, a voice, billed on its own run."""
    done = await run_assist(
        ToolAssist.READ_ALOUD,
        user.id,
        _language(user),
        lambda run: speech.read_aloud(run, body.text),
    )
    heard = done.value
    return ReadAloudAnswer(audio=heard.audio, cut=heard.cut, cost_eur=heard.cost_eur)


@router.post(
    "/text/rewrite",
    response_model=TextAnswer,
    summary="Words being written, with one change",
)
async def post_text_rewrite(body: RewriteAssist, user: Person) -> TextAnswer:
    """Rewrite the person's words; what they wrote stays theirs until they choose."""
    done = await run_assist(
        ToolAssist.TEXT_REWRITE,
        user.id,
        _language(user),
        lambda run: text.rewrite_text(run, body.text, body.tone),
    )
    return TextAnswer(text=done.value, usage=done.usage)


@router.post(
    "/text/translate",
    response_model=TextAnswer,
    summary="Words being written, in another language",
)
async def post_text_translate(body: TranslateAssist, user: Person) -> TextAnswer:
    """Translate the person's words into the language they name."""
    done = await run_assist(
        ToolAssist.TEXT_TRANSLATE,
        user.id,
        _language(user),
        lambda run: text.translate_text(run, body.text, body.language),
    )
    return TextAnswer(text=done.value, usage=done.usage)


@router.post(
    "/text/passage",
    response_model=TextAnswer,
    summary="A passage the person selected, explained, translated, simplified or questioned",
)
async def post_text_passage(body: PassageAssist, user: Person) -> TextAnswer:
    """Answer beside the passage, in the reader's language; it is read, never obeyed."""
    done = await run_assist(
        ToolAssist.TEXT_PASSAGE,
        user.id,
        _language(user),
        lambda run: passage.act_on_passage(
            run, body.passage, body.act, body.question, origin=body.origin
        ),
    )
    return TextAnswer(text=done.value, usage=done.usage)


@router.post(
    "/text/write",
    response_model=TextAnswer,
    summary="A short text written from an instruction",
)
async def post_text_write(body: WriteAssist, user: Person) -> TextAnswer:
    """Write what a field is for, from the person's words."""
    done = await run_assist(
        ToolAssist.TEXT_WRITE,
        user.id,
        _language(user),
        lambda run: text.write_text(run, body.kind, body.instruction),
    )
    return TextAnswer(text=done.value, usage=done.usage)


router.include_router(source_router)
router.include_router(selection_routes.router)
