"""What LIA does on an open message (ADR-372, lot 2).

A summary held in the assistant's own cache opens nothing and costs nothing; otherwise the message
is read fresh and condensed once. What a digest says it could not do is told in the page's words,
never read as an empty summary. A reply is the assistant's own writer, on the person's words.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.emails.digest import DIGEST_STATUS_FIELD, EmailDigest
from src.domains.agents.emails.previous_reply import PreviousReply
from src.domains.connectors.models import ConnectorType
from src.domains.tool_assists import mail
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import assist_line
from src.domains.tool_assists.mail import (
    PROVIDER_WORDS,
    compose_message,
    propose_reply,
    propose_subject,
    summarize_conversation,
    summarize_message,
    translate_message,
)
from src.domains.tool_assists.text import WrittenText
from src.domains.workbench.features import TOOL_PROVIDERS, WorkbenchTool

pytestmark = pytest.mark.unit

MESSAGE_ID = "m1"
DIGEST = {
    "gist": "Ana asks for the budget.",
    "key_points": ["Due Friday"],
    "actions": ["Send the budget"],
    "category": "work",
    "importance": "high",
}


class _Client:
    """The provider: counts its reads."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.reads = 0

    async def get_message(self, message_id: str, *, use_cache: bool) -> dict[str, Any]:
        assert message_id == MESSAGE_ID
        assert use_cache is False
        self.reads += 1
        return self.raw


class _Opened:
    def __init__(self, client: _Client) -> None:
        self.client = client
        self.connector_type = ConnectorType.GOOGLE_GMAIL


def _run() -> AssistRun:
    return AssistRun(
        user_id=uuid4(), language="fr", config=RunnableConfig(callbacks=[]), sections=("mail",)
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> _Client:
    provider = _Client({"id": MESSAGE_ID, "subject": "Budget", "body": "Hello", "from": "Ana"})

    @asynccontextmanager
    async def open_client(tool: WorkbenchTool, user_id: object) -> AsyncIterator[_Opened]:
        assert tool is WorkbenchTool.MAIL
        yield _Opened(provider)

    monkeypatch.setattr(mail, "open_tool_client", open_client)
    return provider


def _no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    async def nothing(*args: object) -> None:
        return None

    monkeypatch.setattr(mail, "read_cached_digest", nothing)


def _digest_stamps(monkeypatch: pytest.MonkeyPatch, status: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class _Service:
        async def digest_many(self, **fields: Any) -> None:
            calls.append(fields)
            (email,) = fields["emails"]
            email[DIGEST_STATUS_FIELD] = status
            if status in ("computed", "cached"):
                email.update(DIGEST)

    monkeypatch.setattr(mail, "EmailDigestService", _Service)
    return calls


async def test_a_digest_already_held_opens_nothing(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def held(user_id: str, provider: str, message_id: str, language: str) -> EmailDigest:
        assert provider == "google"
        assert message_id == MESSAGE_ID
        assert language == "fr"
        return EmailDigest.model_validate(DIGEST)

    monkeypatch.setattr(mail, "read_cached_digest", held)
    run = _run()

    digest = await summarize_message(run, MESSAGE_ID)

    assert digest.gist == DIGEST["gist"]
    assert client.reads == 0
    assert run.opened is False


async def test_a_message_is_read_fresh_and_condensed_on_the_run(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_cache(monkeypatch)
    calls = _digest_stamps(monkeypatch, "computed")
    run = _run()

    digest = await summarize_message(run, MESSAGE_ID)

    assert digest.actions == ["Send the budget"]
    assert client.reads == 1
    assert run.opened is True
    (call,) = calls
    assert call["config"] is run.config
    assert call["language"] == "fr"
    assert call["user_id"] == str(run.user_id)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("skipped_empty", "assist_empty"),
        ("skipped_quota", "assist_quota"),
        ("failed", "assist_failed"),
        ("skipped_disabled", "assist_failed"),
    ],
)
async def test_what_a_digest_could_not_do_is_a_refusal_never_an_empty_summary(
    client: _Client, monkeypatch: pytest.MonkeyPatch, status: str, code: str
) -> None:
    _no_cache(monkeypatch)
    _digest_stamps(monkeypatch, status)

    with pytest.raises(BaseAPIException) as refused:
        await summarize_message(_run(), MESSAGE_ID)

    assert isinstance(refused.value.detail, dict)
    assert refused.value.detail["code"] == code


def test_every_mail_provider_has_the_word_the_digest_cache_is_keyed_on() -> None:
    assert set(PROVIDER_WORDS) == set(TOOL_PROVIDERS[WorkbenchTool.MAIL])


async def test_a_reply_is_written_from_the_message_read_and_the_person_s_instruction(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    async def write(original: dict[str, Any], **fields: Any) -> str:
        seen.update(fields, original=original)
        return "Hello Ana, here is the budget."

    monkeypatch.setattr(mail, "draft_reply_body", write)
    run = _run()

    words = await propose_reply(run, MESSAGE_ID, "accept", "Jean")

    assert words == "Hello Ana, here is the budget."
    assert seen["original"]["subject"] == "Budget"
    assert seen["instruction"] == "accept"
    assert seen["sender_name"] == "Jean"
    assert seen["user_language"] == "fr"
    assert seen["user_id"] == str(run.user_id)
    assert seen["config"] is run.config
    # Should the person's writing style have to be learned, the assist files that read.
    assert seen["style_reading"] == run.reading
    assert run.opened is True


async def test_an_empty_reply_is_a_failure_never_an_empty_proposal(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def write(original: dict[str, Any], **fields: Any) -> str:
        return ""

    monkeypatch.setattr(mail, "draft_reply_body", write)

    with pytest.raises(BaseAPIException) as refused:
        await propose_reply(_run(), MESSAGE_ID, None, None)

    assert isinstance(refused.value.detail, dict)
    assert refused.value.detail["code"] == "assist_failed"


async def test_a_message_that_says_nothing_is_answered_by_no_model(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def write(original: dict[str, Any], **fields: Any) -> str:
        raise AssertionError("nothing to answer: no call is paid for")

    client.raw = {"id": MESSAGE_ID, "subject": "", "body": "   "}
    monkeypatch.setattr(mail, "draft_reply_body", write)

    with pytest.raises(BaseAPIException) as refused:
        await propose_reply(_run(), MESSAGE_ID, None, None)

    assert isinstance(refused.value.detail, dict)
    assert refused.value.detail["code"] == "assist_empty"


async def test_a_whole_message_is_the_assistant_s_writer_on_the_person_s_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def write(instruction: str, recipient: str, language: str, **fields: Any) -> dict:
        seen.update(fields, instruction=instruction, recipient=recipient, language=language)
        return {"subject": " Budget ", "body": " Dear Ana "}

    monkeypatch.setattr(mail, "generate_email_content", write)
    run = _run()

    written = await compose_message(run, "Ask for the budget", "ana@example.org", "Jean")

    assert (written.subject, written.body) == ("Budget", "Dear Ana")
    assert seen["instruction"] == "Ask for the budget"
    assert seen["recipient"] == "ana@example.org"
    assert seen["language"] == "fr"
    assert seen["sender_name"] == "Jean"
    assert seen["config"] is run.config
    # The letter follows how the person writes (ADR-383), learned on this run if need be.
    assert seen["user_id"] == str(run.user_id)
    assert seen["style_reading"] == run.reading


async def test_a_message_with_no_words_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def write(*args: Any, **fields: Any) -> dict:
        return {"subject": "Budget", "body": "  "}

    monkeypatch.setattr(mail, "generate_email_content", write)

    with pytest.raises(BaseAPIException):
        await compose_message(_run(), "words", None, None)


async def test_a_subject_is_read_from_the_words_written(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def write(instruction: str, recipient: str, language: str, **fields: Any) -> dict:
        seen.update(fields)
        return {"subject": " Budget\nfor   Friday "}

    monkeypatch.setattr(mail, "generate_email_content", write)

    subject = await propose_subject(_run(), "Dear Ana, the budget.", None)

    assert subject == "Budget for Friday"
    assert seen["existing_body"] == "Dear Ana, the budget."


async def test_an_empty_subject_is_a_failure_never_an_empty_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def write(*args: Any, **fields: Any) -> dict:
        return {"subject": " \n "}

    monkeypatch.setattr(mail, "generate_email_content", write)

    with pytest.raises(BaseAPIException) as refused:
        await propose_subject(_run(), "Dear Ana, the budget.", None)

    assert isinstance(refused.value.detail, dict)
    assert refused.value.detail["code"] == "assist_failed"


async def test_a_message_is_translated_into_the_reader_s_language(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    async def translate(run: AssistRun, text: str, language: str) -> str:
        seen.update(text=text, language=language)
        return "Bonjour"

    monkeypatch.setattr(mail, "translate_text", translate)
    run = _run()

    done = await translate_message(run, MESSAGE_ID)

    assert done.text == "Bonjour"
    assert done.cut is False
    assert "Hello" in seen["text"]
    assert "external_content" in seen["text"], "a stranger's words are marked as what they are"
    assert seen["language"] == "French"
    assert run.opened is True


async def test_a_long_message_is_cut_at_the_published_bound_and_the_cut_is_said(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}

    async def translate(run: AssistRun, text: str, language: str) -> str:
        seen["text"] = text
        return "Bonjour"

    monkeypatch.setattr(mail, "translate_text", translate)
    client.raw["body"] = "§" * (settings.tool_assist_text_max_chars + 5)

    done = await translate_message(_run(), MESSAGE_ID)

    assert done.cut is True
    assert seen["text"].count("§") == settings.tool_assist_text_max_chars


async def test_a_message_with_no_text_has_nothing_to_translate(client: _Client) -> None:
    client.raw["body"] = "   "

    with pytest.raises(BaseAPIException) as refused:
        await translate_message(_run(), MESSAGE_ID)

    assert isinstance(refused.value.detail, dict)
    assert refused.value.detail["code"] == "assist_empty"


async def test_a_failed_read_stays_filed_as_failed(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def lost(message_id: str, *, use_cache: bool) -> dict[str, Any]:
        raise ConnectionError("the mailbox did not answer")

    monkeypatch.setattr(client, "get_message", lost)
    run = _run()

    with pytest.raises(BaseAPIException):
        await propose_reply(run, MESSAGE_ID, None, None)

    assert run.failed is True


class _Thread:
    """A conversation, as the three providers hand it: headers, then each message."""

    def __init__(self, bodies: list[str], *, truncated: bool = False) -> None:
        self.bodies = bodies
        self.truncated = truncated
        self.reads: list[str] = []
        self.limit = 0

    async def get_conversation(self, message_id: str, max_messages: int) -> dict[str, Any]:
        self.limit = max_messages
        return {
            "messages": [{"id": f"m{index}"} for index in range(len(self.bodies))],
            "truncated": self.truncated,
        }

    async def get_message(self, message_id: str, *, use_cache: bool) -> dict[str, Any]:
        assert use_cache is False
        self.reads.append(message_id)
        index = int(message_id[1:])
        return {
            "id": message_id,
            "from": f"Person {index} <p{index}@example.org>",
            "subject": "Budget",
            "internalDate": str(1_700_000_000_000 + index * 60_000),
            "body": self.bodies[index],
        }


@pytest.fixture
def thread_slot(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What reached the assists' slot for a conversation."""
    prompts: list[str] = []

    async def ask(run: AssistRun, prompt: str, schema: type[WrittenText]) -> WrittenText:
        prompts.append(prompt)
        return schema(text="Where it stands")

    monkeypatch.setattr(mail, "ask_slot", ask)
    return prompts


def _opened_on(monkeypatch: pytest.MonkeyPatch, thread: _Thread) -> None:
    @asynccontextmanager
    async def opened(tool: object, user_id: object) -> AsyncIterator[Any]:
        class _Open:
            client = thread
            connector_type = ConnectorType.GOOGLE_GMAIL

        yield _Open()

    monkeypatch.setattr(mail, "open_tool_client", opened)


async def test_a_conversation_is_read_whole_up_to_its_published_count(
    monkeypatch: pytest.MonkeyPatch, thread_slot: list[str]
) -> None:
    thread = _Thread(["First words", "Second words"])
    _opened_on(monkeypatch, thread)
    run = _run()

    done = await summarize_conversation(run, MESSAGE_ID)

    assert done.text == "Where it stands"
    assert done.cut is False
    assert thread.limit == settings.tool_assist_conversation_max_messages
    assert thread.reads == ["m0", "m1"]
    assert run.opened is True
    first, second = thread_slot[0].index("First words"), thread_slot[0].index("Second words")
    assert first < second
    assert "Person 1 <p1@example.org>" in thread_slot[0]
    assert "<external_content" in thread_slot[0]
    assert assist_line("conversation_cut") not in thread_slot[0]


async def test_a_conversation_longer_than_its_count_says_so(
    monkeypatch: pytest.MonkeyPatch, thread_slot: list[str]
) -> None:
    _opened_on(monkeypatch, _Thread(["Only the latest"], truncated=True))

    done = await summarize_conversation(_run(), MESSAGE_ID)

    assert done.cut is True
    assert assist_line("conversation_cut") in thread_slot[0]


async def test_what_does_not_fit_leaves_the_oldest_out_and_says_so(
    monkeypatch: pytest.MonkeyPatch, thread_slot: list[str]
) -> None:
    monkeypatch.setattr(settings, "tool_assist_document_max_chars", 300)
    _opened_on(monkeypatch, _Thread(["§" * 400, "The latest word"]))

    done = await summarize_conversation(_run(), MESSAGE_ID)

    assert done.cut is True
    assert "The latest word" in thread_slot[0]
    assert "§" not in thread_slot[0]


async def test_the_newest_message_alone_past_the_bound_is_cut_not_dropped(
    monkeypatch: pytest.MonkeyPatch, thread_slot: list[str]
) -> None:
    monkeypatch.setattr(settings, "tool_assist_document_max_chars", 120)
    _opened_on(monkeypatch, _Thread(["§" * 500]))

    done = await summarize_conversation(_run(), MESSAGE_ID)

    assert done.cut is True
    assert thread_slot[0].count("§") < 120


async def test_a_conversation_with_nothing_said_has_nothing_to_sum_up(
    monkeypatch: pytest.MonkeyPatch, thread_slot: list[str]
) -> None:
    _opened_on(monkeypatch, _Thread([]))

    with pytest.raises(BaseAPIException) as refused:
        await summarize_conversation(_run(), MESSAGE_ID)

    detail = refused.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "assist_empty"
    assert thread_slot == []


async def test_an_empty_answer_on_a_conversation_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ask(run: AssistRun, prompt: str, schema: type[WrittenText]) -> WrittenText:
        return schema(text=" ")

    monkeypatch.setattr(mail, "ask_slot", ask)
    _opened_on(monkeypatch, _Thread(["Words"]))

    with pytest.raises(BaseAPIException):
        await summarize_conversation(_run(), MESSAGE_ID)


async def test_a_proposed_reply_reads_what_the_person_already_answered(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-379: asked for a reply to a message already answered, the writer is told so."""
    seen: dict[str, Any] = {}

    async def write(original: dict[str, Any], **fields: Any) -> str:
        seen.update(fields)
        return "And Monday?"

    async def earlier(mailbox: object, original: dict[str, Any], **fields: Any) -> PreviousReply:
        seen["asked_of"] = (mailbox, original["id"], fields)
        return PreviousReply(at=None, words="Friday works for me.")

    monkeypatch.setattr(mail, "draft_reply_body", write)
    monkeypatch.setattr(mail, "previous_reply_of", earlier)

    await propose_reply(_run(), MESSAGE_ID, None, None)

    assert seen["previous_reply"].words == "Friday works for me."
    mailbox, message_id, fields = seen["asked_of"]
    assert mailbox is client and message_id == MESSAGE_ID
    assert fields["with_words"] is True
