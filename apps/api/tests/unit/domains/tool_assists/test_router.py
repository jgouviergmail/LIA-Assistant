"""The routes of the assists (ADR-372): what they take, what they answer, what they refuse.

The door and the assists have their own tests: here a request reaches the right assist with the
person's language and name, an id is checked before any client sees it, an instruction is held to
its published bound, and neither guard lets anything through.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.config import settings
from src.core.llm_usage import LLMUsage
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.agents.emails.digest import EmailDigest
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.tool_assists import router as assists_router
from src.domains.tool_assists.actions import AssistClock, ProposedEvent, ProposedTask
from src.domains.tool_assists.catalogue import ToolAssist
from src.domains.tool_assists.contact_card import ProposedContact, ProposedValue
from src.domains.tool_assists.door import Assisted, AssistRun
from src.domains.tool_assists.files import FileSummary
from src.domains.tool_assists.mail import (
    ComposedMessage,
    ConversationSummary,
    TranslatedMessage,
)
from src.domains.tool_assists.mail_triage import Triage, TriagedMessage
from src.domains.tool_assists.mail_words import ProposedFilter, ProposedSearch
from src.domains.tool_assists.passage import PassageAct
from src.domains.tool_assists.speech import HeardWords
from src.domains.tool_assists.text import RewriteTone, WritingKind
from src.domains.workbench.errors import ITEM_GONE, refuse
from src.domains.workbench.schemas.mail import AttachmentRequest

pytestmark = pytest.mark.unit


@dataclass
class _Person:
    """What the routes read of the account."""

    id: UUID
    language: str = "fr-FR"
    full_name: str | None = "Jean Dupont"
    email: str = "jean@example.org"
    timezone: str | None = None


PERSON = _Person(id=uuid4())
DIGEST = EmailDigest(gist="The gist", key_points=["A point"], actions=["An act"])
COST = LLMUsage(tokens_in=10, tokens_out=2, cost_eur=0.001, model_name="m")


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """What reached the door, the assist itself run on a bare run."""
    seen: list[dict[str, Any]] = []

    async def door(
        assist: ToolAssist, user_id: UUID, language: str, work: Callable[[AssistRun], Any]
    ) -> Assisted[Any]:
        seen.append({"assist": assist, "user_id": user_id, "language": language})
        return Assisted(await work(AssistRun(user_id, language, {})), COST)

    monkeypatch.setattr(assists_router, "run_assist", door)
    return seen


@pytest.fixture
def app() -> Iterator[FastAPI]:
    application = FastAPI()
    application.include_router(assists_router.router)
    application.dependency_overrides[get_current_active_session_for_stream] = lambda: PERSON
    application.dependency_overrides[assists_router.rate_limit_assist] = lambda: None
    yield application


@pytest.fixture
async def client(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    async def enabled(capability: object) -> bool:
        return True

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        yield opened


async def test_a_summary_answers_the_digest_and_what_it_cost(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def summarize(run: AssistRun, message_id: str) -> EmailDigest:
        assert message_id == "m1"
        return DIGEST

    monkeypatch.setattr(assists_router.mail, "summarize_message", summarize)

    answer = await client.post("/tool-assists/mail/summary", json={"message_id": "m1"})

    assert answer.status_code == 200
    body = answer.json()
    assert body["gist"] == "The gist"
    assert body["actions"] == ["An act"]
    assert body["usage"]["tokens_in"] == 10
    assert calls == [{"assist": ToolAssist.MAIL_SUMMARY, "user_id": PERSON.id, "language": "fr"}]


async def test_a_reply_carries_the_person_s_instruction_and_first_name(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    async def propose(
        run: AssistRun, message_id: str, instruction: str | None, sender: str | None
    ) -> str:
        seen.update(message_id=message_id, instruction=instruction, sender=sender)
        return "Dear Ana"

    monkeypatch.setattr(assists_router.mail, "propose_reply", propose)

    answer = await client.post(
        "/tool-assists/mail/reply", json={"message_id": "m1", "instruction": "Say yes"}
    )

    assert answer.json()["text"] == "Dear Ana"
    assert seen == {"message_id": "m1", "instruction": "Say yes", "sender": "Jean"}


async def test_a_reply_needs_no_instruction(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def propose(run: AssistRun, *args: object) -> str:
        assert args[1] is None
        return "Dear Ana"

    monkeypatch.setattr(assists_router.mail, "propose_reply", propose)

    answer = await client.post("/tool-assists/mail/reply", json={"message_id": "m1"})

    assert answer.status_code == 200


@pytest.mark.parametrize("message_id", ["", "with space", "x" * 1025, "line\nbreak"])
async def test_an_id_no_provider_mints_reaches_no_client(
    client: AsyncClient, calls: list[dict[str, Any]], message_id: str
) -> None:
    answer = await client.post("/tool-assists/mail/summary", json={"message_id": message_id})

    assert answer.status_code == 422
    assert calls == []


async def test_an_instruction_past_its_published_bound_is_refused(
    client: AsyncClient, calls: list[dict[str, Any]]
) -> None:
    words = "x" * (settings.tool_assist_instruction_max_chars + 1)

    answer = await client.post(
        "/tool-assists/mail/reply", json={"message_id": "m1", "instruction": words}
    )

    assert answer.status_code == 422
    assert calls == []


async def test_a_refusal_keeps_its_stable_words(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def gone(run: AssistRun, message_id: str) -> EmailDigest:
        refuse(ITEM_GONE)

    monkeypatch.setattr(assists_router.mail, "summarize_message", gone)

    answer = await client.post("/tool-assists/mail/summary", json={"message_id": "m1"})

    assert answer.status_code == 404
    assert answer.json()["detail"]["code"] == "item_gone"


async def test_a_rewrite_takes_a_known_change_and_the_person_s_words(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def rewrite(run: AssistRun, words: str, tone: RewriteTone) -> str:
        assert words == "Mine"
        assert tone is RewriteTone.SHORTER
        return "Shorter"

    monkeypatch.setattr(assists_router.text, "rewrite_text", rewrite)

    answer = await client.post(
        "/tool-assists/text/rewrite", json={"text": "Mine", "tone": "shorter"}
    )

    assert answer.json()["text"] == "Shorter"
    assert calls[0]["assist"] is ToolAssist.TEXT_REWRITE


async def test_a_change_nobody_defined_is_refused(
    client: AsyncClient, calls: list[dict[str, Any]]
) -> None:
    answer = await client.post(
        "/tool-assists/text/rewrite", json={"text": "Mine", "tone": "pirate"}
    )

    assert answer.status_code == 422
    assert calls == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/tool-assists/text/rewrite", {"tone": "fix"}),
        ("/tool-assists/text/translate", {"language": "Spanish"}),
    ],
)
async def test_words_past_their_published_bound_reach_no_model(
    client: AsyncClient, calls: list[dict[str, Any]], path: str, body: dict[str, str]
) -> None:
    words = "x" * (settings.tool_assist_text_max_chars + 1)

    answer = await client.post(path, json={**body, "text": words})

    assert answer.status_code == 422
    assert calls == []


async def test_a_translation_takes_the_language_as_the_person_names_it(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def translate(run: AssistRun, words: str, language: str) -> str:
        assert language == "brazilian portuguese"
        return "Olá"

    monkeypatch.setattr(assists_router.text, "translate_text", translate)

    answer = await client.post(
        "/tool-assists/text/translate", json={"text": "Hi", "language": "brazilian portuguese"}
    )

    assert answer.json()["text"] == "Olá"


async def test_a_passage_is_answered_by_its_own_assist(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def act(
        run: AssistRun,
        words: str,
        asked: PassageAct,
        question: str | None,
        *,
        origin: str,
    ) -> str:
        assert (words, asked, question, origin) == (
            "The fee is due.",
            PassageAct.ASK,
            "When?",
            "mail",
        )
        return "On Friday."

    monkeypatch.setattr(assists_router.passage, "act_on_passage", act)

    answer = await client.post(
        "/tool-assists/text/passage",
        json={"passage": "The fee is due.", "act": "ask", "question": "When?", "origin": "mail"},
    )

    assert answer.json()["text"] == "On Friday."
    assert calls[0]["assist"] is ToolAssist.TEXT_PASSAGE


_TOO_LONG = "x" * (settings.tool_assist_text_max_chars + 1)


@pytest.mark.parametrize(
    "body",
    [
        {"passage": _TOO_LONG, "act": "explain", "origin": "mail"},
        {"passage": "The fee is due.", "act": "ask", "origin": "mail"},
        {"passage": "The fee is due.", "act": "explain", "question": "Why?", "origin": "mail"},
        {"passage": "The fee is due.", "act": "explain", "origin": "web"},
    ],
    ids=["past_its_bound", "ask_without_question", "question_without_ask", "unknown_origin"],
)
async def test_an_odd_passage_request_reaches_no_model(
    client: AsyncClient, calls: list[dict[str, Any]], body: dict[str, str]
) -> None:
    answer = await client.post("/tool-assists/text/passage", json=body)

    assert answer.status_code == 422
    assert calls == []


async def test_a_text_is_written_for_a_known_kind(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def write(run: AssistRun, kind: WritingKind, instruction: str) -> str:
        assert kind is WritingKind.TASK_NOTES
        return "Notes"

    monkeypatch.setattr(assists_router.text, "write_text", write)

    answer = await client.post(
        "/tool-assists/text/write", json={"kind": "task_notes", "instruction": "Call Ana"}
    )

    assert answer.json()["text"] == "Notes"


async def test_a_whole_message_answers_its_subject_beside_its_words(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def compose(
        run: AssistRun, instruction: str, recipient: str | None, sender: str | None
    ) -> ComposedMessage:
        assert sender == "Jean"
        return ComposedMessage(subject="Budget", body="Dear Ana")

    monkeypatch.setattr(assists_router.mail, "compose_message", compose)

    answer = await client.post("/tool-assists/mail/compose", json={"instruction": "Ask"})

    assert answer.json()["text"] == "Dear Ana"
    assert answer.json()["subject"] == "Budget"


async def test_a_translated_message_says_when_it_was_cut(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def translate(run: AssistRun, message_id: str) -> TranslatedMessage:
        return TranslatedMessage(text="Bonjour", cut=True)

    monkeypatch.setattr(assists_router.mail, "translate_message", translate)

    answer = await client.post("/tool-assists/mail/translate", json={"message_id": "m1"})

    assert answer.json()["cut"] is True
    assert calls[0]["assist"] is ToolAssist.MAIL_TRANSLATE


async def test_a_conversation_says_its_cut(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def sum_up(run: AssistRun, message_id: str) -> ConversationSummary:
        return ConversationSummary(text="It stands", cut=True)

    monkeypatch.setattr(assists_router.mail, "summarize_conversation", sum_up)

    answer = await client.post("/tool-assists/mail/conversation", json={"message_id": "m1"})

    assert answer.status_code == 200
    assert answer.json()["text"] == "It stands"
    assert answer.json()["cut"] is True
    assert calls[0]["assist"] is ToolAssist.MAIL_CONVERSATION


async def test_a_file_and_an_attachment_each_reach_their_own_door(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    async def of_file(run: AssistRun, file_id: str) -> FileSummary:
        seen.append(file_id)
        return FileSummary(text="A plan", cut=False)

    async def of_attachment(run: AssistRun, request: AttachmentRequest) -> FileSummary:
        seen.append(request)
        return FileSummary(text="An invoice", cut=True)

    monkeypatch.setattr(assists_router.files, "summarize_file", of_file)
    monkeypatch.setattr(assists_router.files, "summarize_attachment", of_attachment)

    file = await client.post("/tool-assists/files/summary", json={"file_id": "f1"})
    attachment = await client.post(
        "/tool-assists/mail/attachment",
        json={"message_id": "m1", "attachment_id": "a1", "filename": "Bill.pdf"},
    )

    assert file.json()["text"] == "A plan"
    assert attachment.json()["cut"] is True
    assert seen == [
        "f1",
        AttachmentRequest(message_id="m1", attachment_id="a1", filename="Bill.pdf"),
    ]
    assert [call["assist"] for call in calls] == [
        ToolAssist.FILE_SUMMARY,
        ToolAssist.MAIL_ATTACHMENT,
    ]


async def test_words_are_read_aloud_with_their_cut_and_cost(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def read(run: AssistRun, words: str) -> HeardWords:
        assert words == "Hello there"
        return HeardWords(audio="SUQz", cut=True, cost_eur=0.002)

    monkeypatch.setattr(assists_router.speech, "read_aloud", read)

    answer = await client.post("/tool-assists/read-aloud", json={"text": "Hello there"})

    assert answer.status_code == 200
    assert answer.json() == {"audio": "SUQz", "cut": True, "cost_eur": 0.002, "usage": None}
    assert calls[0]["assist"] is ToolAssist.READ_ALOUD


async def test_reading_selected_words_needs_no_tools_capability(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def enabled(capability: PlatformCapability) -> bool:
        return capability is not PlatformCapability.WORKBENCH

    async def read(run: AssistRun, words: str) -> HeardWords:
        assert words == "A selection from chat"
        return HeardWords(audio="SUQz", cut=False, cost_eur=0)

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    monkeypatch.setattr(assists_router.speech, "read_aloud", read)
    response = await client.post("/tool-assists/read-aloud", json={"text": "A selection from chat"})
    assert response.status_code == 200
    assert calls[0]["assist"] is ToolAssist.READ_ALOUD


async def test_speech_switched_off_closes_the_reading_alone(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def enabled(capability: PlatformCapability) -> bool:
        return capability is not PlatformCapability.TTS

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        answer = await opened.post("/tool-assists/read-aloud", json={"text": "Hello"})

    assert answer.status_code == 403


async def test_a_sentence_reaches_the_screen_as_criteria(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def read(run: AssistRun, sentence: str, clock: object) -> ProposedSearch:
        return ProposedSearch(words="from:Ana", unread=True, attachments=False)

    monkeypatch.setattr(assists_router.mail_words, "search_from_sentence", read)

    answer = await client.post("/tool-assists/mail/search", json={"sentence": "unread from Ana"})

    assert answer.status_code == 200
    assert answer.json()["search"]["words"] == "from:Ana"
    assert calls[0]["assist"] is ToolAssist.MAIL_SEARCH


async def test_a_filter_is_read_with_the_person_s_labels(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    async def read(run: AssistRun, sentence: str, labels: list[str]) -> ProposedFilter:
        seen.append(labels)
        return ProposedFilter(sender="a@b.c", archive=True)

    monkeypatch.setattr(assists_router.mail_words, "filter_from_sentence", read)

    answer = await client.post(
        "/tool-assists/mail/filter", json={"sentence": "archive a@b.c", "labels": ["Family"]}
    )

    assert answer.status_code == 200
    assert answer.json()["filter"]["sender"] == "a@b.c"
    assert seen == [["Family"]]


async def test_a_page_is_weighed_and_says_what_stayed_in_place(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def weigh(run: AssistRun, ids: list[str]) -> Triage:
        assert ids == ["m1", "m2"]
        return Triage(
            items=[TriagedMessage(id="m1", importance="high", category="work")], skipped=1
        )

    monkeypatch.setattr(assists_router.mail_triage, "triage_messages", weigh)

    answer = await client.post("/tool-assists/mail/triage", json={"message_ids": ["m1", "m2"]})

    assert answer.status_code == 200
    assert answer.json()["skipped"] == 1
    assert answer.json()["items"][0]["importance"] == "high"
    assert calls[0]["assist"] is ToolAssist.MAIL_TRIAGE


async def test_a_page_past_its_published_size_reaches_no_provider(
    client: AsyncClient, calls: list[dict[str, Any]]
) -> None:
    ids = [f"m{index}" for index in range(settings.workbench_page_size + 1)]

    answer = await client.post("/tool-assists/mail/triage", json={"message_ids": ids})

    assert answer.status_code == 422
    assert calls == []


async def test_a_contact_s_values_answer_with_their_source(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def complete(run: AssistRun, contact_id: str) -> list[ProposedValue]:
        return [
            ProposedValue(
                field="phone", value="+33 6", message_id="m1", subject="Hi", received_at=None
            )
        ]

    monkeypatch.setattr(assists_router.contact_card, "complete_contact", complete)

    answer = await client.post("/tool-assists/contacts/complete", json={"contact_id": "c1"})

    assert answer.status_code == 200
    assert answer.json()["values"][0]["message_id"] == "m1"
    assert calls[0]["assist"] is ToolAssist.CONTACT_COMPLETE


async def test_a_card_is_read_from_its_picture(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bytes] = []

    async def read(run: AssistRun, data: bytes) -> ProposedContact:
        seen.append(data)
        return ProposedContact(family_name="Silva")

    @asynccontextmanager
    async def transfer(user_id: UUID) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(assists_router.contact_card, "contact_from_card", read)
    monkeypatch.setattr(assists_router, "one_transfer", transfer)

    answer = await client.post(
        "/tool-assists/contacts/from-card",
        files={"file": ("card.jpg", b"picture", "image/jpeg")},
    )

    assert answer.status_code == 200
    assert answer.json()["contact"]["family_name"] == "Silva"
    assert seen == [b"picture"]
    assert calls[0]["assist"] is ToolAssist.CONTACT_FROM_CARD


async def test_a_contact_said_in_a_sentence_reaches_the_editor(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The new-contact form, filled from the person's words (2026-11-07): nothing is created."""
    seen: list[str] = []

    async def read(run: AssistRun, sentence: str) -> ProposedContact:
        seen.append(sentence)
        return ProposedContact(given_name="Inès")

    monkeypatch.setattr(assists_router.contact_card, "contact_from_words", read)

    answer = await client.post(
        "/tool-assists/contacts/from-words", json={"sentence": "Inès, architecte chez Acme"}
    )

    assert answer.status_code == 200
    assert answer.json()["contact"]["given_name"] == "Inès"
    assert answer.json()["usage"]["cost_eur"] == COST.cost_eur
    assert seen == ["Inès, architecte chez Acme"]
    assert calls[0]["assist"] is ToolAssist.CONTACT_FROM_WORDS


async def test_a_picture_past_its_ceiling_is_refused_before_anything_reads_it(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assists_router, "WORKBENCH_CONTACT_PHOTO_MAX_BYTES", 3)

    answer = await client.post(
        "/tool-assists/contacts/from-card",
        files={"file": ("card.jpg", b"picture", "image/jpeg")},
    )

    assert answer.status_code == 413
    assert calls == []


async def test_a_file_is_kept_by_the_person_alone_on_their_own_space(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    space, document = uuid4(), uuid4()
    seen: dict[str, Any] = {}

    async def keep(user_id: UUID, space_id: UUID, file_id: str) -> UUID:
        seen.update(user_id=user_id, space_id=space_id, file_id=file_id)
        return document

    monkeypatch.setattr(assists_router.keeping, "keep_file", keep)

    answer = await client.post(
        "/tool-assists/spaces/keep-file", json={"space_id": str(space), "file_id": "f1"}
    )

    assert answer.status_code == 201
    assert answer.json() == {"document_id": str(document)}
    assert seen == {"user_id": PERSON.id, "space_id": space, "file_id": "f1"}
    assert calls == []


async def test_an_attachment_travels_with_its_name_and_its_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    space, document = uuid4(), uuid4()
    seen: dict[str, Any] = {}

    async def keep(user_id: UUID, space_id: UUID, request: AttachmentRequest) -> UUID:
        seen.update(space_id=space_id, request=request)
        return document

    monkeypatch.setattr(assists_router.keeping, "keep_attachment", keep)

    answer = await client.post(
        "/tool-assists/spaces/keep-attachment",
        json={
            "space_id": str(space),
            "message_id": "m1",
            "attachment_id": "a1",
            "filename": "Plan.pdf",
        },
    )

    assert answer.status_code == 201
    assert seen["space_id"] == space
    assert seen["request"] == AttachmentRequest(
        message_id="m1", attachment_id="a1", filename="Plan.pdf"
    )


async def test_a_space_that_is_no_uuid_reaches_no_provider(client: AsyncClient) -> None:
    answer = await client.post(
        "/tool-assists/spaces/keep-file", json={"space_id": "nope", "file_id": "f1"}
    )

    assert answer.status_code == 422


async def test_spaces_switched_off_close_the_keeping_alone(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def enabled(capability: PlatformCapability) -> bool:
        return capability is not PlatformCapability.RAG_SPACES

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        answer = await opened.post(
            "/tool-assists/spaces/keep-file", json={"space_id": str(uuid4()), "file_id": "f1"}
        )

    assert answer.status_code == 403


async def test_a_subject_is_proposed_for_the_words_already_written(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def propose(run: AssistRun, body: str, recipient: str | None) -> str:
        assert (body, recipient) == ("Dear Ana", "ana@example.org")
        return "The budget"

    monkeypatch.setattr(assists_router.mail, "propose_subject", propose)

    answer = await client.post(
        "/tool-assists/mail/subject", json={"body": "Dear Ana", "recipient": "ana@example.org"}
    )

    assert answer.status_code == 200
    assert answer.json()["text"] == "The budget"
    assert calls[0]["assist"] is ToolAssist.MAIL_SUBJECT


@pytest.mark.parametrize(
    ("path", "body", "reader", "assist", "source"),
    [
        (
            "/tool-assists/calendar/from-words",
            {"sentence": "Lunch on Thursday"},
            "event_from_sentence",
            ToolAssist.EVENT_FROM_WORDS,
            "Lunch on Thursday",
        ),
    ],
    ids=["from-a-sentence"],
)
async def test_an_event_reaches_the_editor_as_a_proposal(
    client: AsyncClient,
    calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, str],
    reader: str,
    assist: ToolAssist,
    source: str,
) -> None:
    seen: list[str] = []

    async def read(run: AssistRun, words: str, clock: AssistClock) -> ProposedEvent:
        seen.append(words)
        return ProposedEvent(summary="Lunch", start_date="2026-11-12")

    monkeypatch.setattr(assists_router.actions, reader, read)

    answer = await client.post(path, json=body)

    assert answer.status_code == 200
    assert answer.json()["event"]["summary"] == "Lunch"
    assert answer.json()["usage"]["cost_eur"] == COST.cost_eur
    assert seen == [source]
    assert calls[0]["assist"] is assist


async def test_an_event_from_a_message_reaches_the_editor_with_its_focus(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str | None]] = []

    async def read(
        run: AssistRun, message_id: str, clock: AssistClock, focus: str | None
    ) -> ProposedEvent:
        seen.append((message_id, focus))
        return ProposedEvent(summary="Lunch", start_date="2026-11-12", conference=True)

    monkeypatch.setattr(assists_router.actions, "event_from_message", read)

    plain = await client.post("/tool-assists/mail/event", json={"message_id": "m1"})
    focused = await client.post(
        "/tool-assists/mail/event", json={"message_id": "m1", "focus": "Lunch on Thursday"}
    )

    assert plain.status_code == focused.status_code == 200
    assert plain.json()["event"]["conference"] is True
    assert seen == [("m1", None), ("m1", "Lunch on Thursday")]
    assert calls[0]["assist"] is ToolAssist.MAIL_EVENT


async def test_a_task_from_a_message_reaches_its_form_read_against_the_lists_and_the_act_named(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, list[str], str | None]] = []

    async def read(
        run: AssistRun, message_id: str, clock: AssistClock, lists: list[str], focus: str | None
    ) -> ProposedTask:
        seen.append((message_id, lists, focus))
        return ProposedTask(title="Send the budget", due="2026-11-13", importance="high")

    monkeypatch.setattr(assists_router.actions, "task_from_message", read)

    plain = await client.post("/tool-assists/mail/task", json={"message_id": "m1"})
    focused = await client.post(
        "/tool-assists/mail/task",
        json={"message_id": "m1", "lists": ["Work", "Home"], "focus": "Send the budget"},
    )

    assert plain.status_code == focused.status_code == 200
    assert focused.json()["task"]["title"] == "Send the budget"
    assert focused.json()["task"]["importance"] == "high"
    assert seen == [("m1", [], None), ("m1", ["Work", "Home"], "Send the budget")]
    assert calls[0]["assist"] is ToolAssist.MAIL_TASK


@pytest.mark.parametrize("path", ["/tool-assists/mail/task", "/tool-assists/mail/event"])
async def test_a_focus_past_its_published_bound_reaches_no_model(
    client: AsyncClient, calls: list[dict[str, Any]], path: str
) -> None:
    focus = "x" * (settings.tool_assist_text_max_chars + 1)

    answer = await client.post(path, json={"message_id": "m1", "focus": focus})

    assert answer.status_code == 422
    assert calls == []


async def test_a_task_said_in_a_sentence_is_read_against_the_person_s_lists(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, list[str]]] = []

    async def read(
        run: AssistRun, sentence: str, clock: AssistClock, lists: list[str]
    ) -> ProposedTask:
        seen.append((sentence, lists))
        return ProposedTask(title="Call Ana", list_name="Work")

    monkeypatch.setattr(assists_router.actions, "task_from_sentence", read)

    answer = await client.post(
        "/tool-assists/tasks/from-words",
        json={"sentence": "Call Ana for work", "lists": ["Work", "Home"]},
    )

    assert answer.status_code == 200
    assert answer.json()["task"]["list_name"] == "Work"
    assert seen == [("Call Ana for work", ["Work", "Home"])]
    assert calls[0]["assist"] is ToolAssist.TASK_FROM_WORDS


async def test_the_steps_of_a_task_are_proposed_from_the_words_of_its_form(
    client: AsyncClient, calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def steps(run: AssistRun, title: str, notes: str | None) -> list[str]:
        assert (title, notes) == ("Move house", "In March")
        return ["Find boxes", "Book a van"]

    monkeypatch.setattr(assists_router.actions, "steps_of_task", steps)

    answer = await client.post(
        "/tool-assists/tasks/steps", json={"title": "Move house", "notes": "In March"}
    )

    assert answer.status_code == 200
    assert answer.json()["steps"] == ["Find boxes", "Book a van"]
    assert calls[0]["assist"] is ToolAssist.TASK_STEPS


@pytest.mark.parametrize(
    ("zone", "day"),
    [("Asia/Tokyo", date(2026, 11, 8)), ("America/New_York", date(2026, 11, 7))],
)
async def test_thursday_is_counted_from_the_person_s_day_never_the_server_s(
    app: FastAPI,
    client: AsyncClient,
    calls: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    zone: str,
    day: date,
) -> None:
    class _Instant:
        """23:30 UTC: already tomorrow in Tokyo, still today in New York."""

        @staticmethod
        def now(tz: ZoneInfo) -> datetime:
            return datetime(2026, 11, 7, 23, 30, tzinfo=UTC).astimezone(tz)

    seen: list[AssistClock] = []

    async def read(run: AssistRun, sentence: str, clock: AssistClock) -> ProposedEvent:
        seen.append(clock)
        return ProposedEvent(summary="Lunch")

    monkeypatch.setattr(assists_router, "datetime", _Instant)
    monkeypatch.setattr(assists_router.actions, "event_from_sentence", read)
    person = _Person(id=uuid4(), timezone=zone)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: person

    answer = await client.post(
        "/tool-assists/calendar/from-words", json={"sentence": "Lunch on Thursday"}
    )

    assert answer.status_code == 200
    assert seen == [AssistClock(today=day, zone=zone)]


@pytest.mark.parametrize("off", ["workbench", "tool_assists"])
async def test_either_switch_off_closes_every_route(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, off: str
) -> None:
    async def switched(capability: Any) -> bool:
        return capability.value != off

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", switched)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        answer = await opened.post("/tool-assists/mail/summary", json={"message_id": "m1"})

    assert answer.status_code == 403
