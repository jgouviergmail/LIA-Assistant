"""What LIA finds for a contact's card (ADR-372, lot 10).

A value reaches the page only if the message it cites says it, and only if the card lacks it: what
refuses invention is structural. The whole message is read, its signature included. A photographed
card is redrawn first, and what the model reads is held to what the editor can take.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from src.core.constants import (
    TOOL_ASSIST_CARD_MAX_SIDE,
    TOOL_ASSIST_CONTACT_HTML_MAX_CHARS,
    TOOL_ASSIST_CONTACT_MESSAGES_MAX,
    TOOL_ASSIST_CONTACT_VALUE_MAX_CHARS,
)
from src.core.exceptions import BaseAPIException
from src.domains.connectors.clients.contact_photos import ContactPhoto
from src.domains.tool_assists import contact_card
from src.domains.tool_assists.contact_card import (
    CardDraft,
    Exchange,
    FoundValue,
    FoundValues,
    complete_contact,
    contact_from_card,
    proposed_contact,
    proposed_values,
    said_in,
)
from src.domains.tool_assists.door import AssistRun
from src.domains.workbench.schemas.contacts import Contact, ContactAddress, ContactValue

pytestmark = pytest.mark.unit

SIGNED = "Hello,\n\nThanks.\n\nAna Silva\nSales lead, Acme Ltd\n+33 6 12 34 56 78\nwww.acme.example"
BARE: dict[str, Any] = {
    "id": "c1",
    "name": "Ana Silva",
    "given_name": None,
    "family_name": None,
    "email": "ana@acme.example",
    "phone": None,
    "organization": None,
    "name_key": "ana silva",
    "emails": [ContactValue(value="ana@acme.example", type=None)],
    "phones": [],
    "addresses": [],
    "notes": None,
}


def _contact(**fields: Any) -> Contact:
    return Contact(**{**BARE, **fields})


def _exchange(words: str = SIGNED, message_id: str = "m1") -> Exchange:
    return Exchange(message_id=message_id, subject="Budget", received=None, words=words)


def _found(field: str, value: str, message: int = 1) -> FoundValue:
    return FoundValue(field=field, value=value, message=message)


def _run() -> AssistRun:
    return AssistRun(
        user_id=uuid4(),
        language="fr",
        config=RunnableConfig(callbacks=[]),
        sections=("contacts", "mail"),
    )


def _code(refused: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = refused.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


@pytest.mark.parametrize(
    ("field", "value", "held"),
    [
        ("phone", "+33612345678", True),
        ("phone", "06 12 34 56 78", False),
        ("job_title", "sales LEAD,  Acme", True),
        ("organization", "Other Ltd", False),
    ],
)
def test_a_value_is_said_by_its_digits_or_word_for_word(field: str, value: str, held: bool) -> None:
    assert said_in(field, value, SIGNED) is held


def test_what_a_message_says_and_the_card_lacks_keeps_its_source() -> None:
    draft = FoundValues(
        values=[_found("phone", "+33 6 12 34 56 78"), _found("organization", "Acme Ltd")]
    )

    values = proposed_values(draft, _contact(), [_exchange()])

    assert [(value.field, value.value, value.message_id) for value in values] == [
        ("phone", "+33 6 12 34 56 78", "m1"),
        ("organization", "Acme Ltd", "m1"),
    ]
    assert values[0].subject == "Budget"


def test_a_value_no_message_says_never_reaches_the_page() -> None:
    draft = FoundValues(values=[_found("phone", "+33 1 99 99 99 99"), _found("website", "acme.ai")])

    assert proposed_values(draft, _contact(), [_exchange()]) == []


def test_a_value_citing_no_message_is_dropped() -> None:
    draft = FoundValues(
        values=[_found("organization", "Acme Ltd", 0), _found("organization", "Acme Ltd", 9)]
    )

    assert proposed_values(draft, _contact(), [_exchange()]) == []


def test_what_the_card_holds_is_never_replaced() -> None:
    contact = _contact(
        organization="Old Ltd",
        phones=[ContactValue(value="06 12 34 56 78", type=None)],
        addresses=[ContactAddress(formatted="1 rue X", type=None)],
    )
    draft = FoundValues(
        values=[
            _found("organization", "Acme Ltd"),
            _found("phone", "33612345678"),
            _found("address", "Sales lead"),
        ]
    )

    assert [
        value.value
        for value in proposed_values(draft, contact, [_exchange("Acme Ltd 33612345678 Sales lead")])
    ] == ["33612345678"]


def test_a_field_nobody_defined_is_dropped() -> None:
    draft = FoundValues(values=[_found("salary", "Acme Ltd")])

    assert proposed_values(draft, _contact(), [_exchange()]) == []


def test_the_same_value_twice_is_proposed_once() -> None:
    draft = FoundValues(
        values=[_found("phone", "+33 6 12 34 56 78"), _found("phone", "+33612345678")]
    )

    assert len(proposed_values(draft, _contact(), [_exchange()])) == 1


def test_a_value_past_its_bound_is_dropped() -> None:
    long = "x" * (TOOL_ASSIST_CONTACT_VALUE_MAX_CHARS + 1)
    draft = FoundValues(values=[_found("organization", long)])

    assert proposed_values(draft, _contact(), [_exchange(long)]) == []


class _Mailbox:
    """The provider, with an HTML body that holds the signature."""

    def __init__(self, hits: int = 2, html: str | None = "<p>Thanks</p><p>Acme Ltd</p>") -> None:
        self.hits = hits
        self.html = html
        self.query = ""
        self.size = 0

    async def search_emails(
        self, query: str, *, max_results: int, use_cache: bool, headers_only: bool
    ) -> dict[str, Any]:
        self.query, self.size = query, max_results
        return {"messages": [{"id": f"m{index}"} for index in range(self.hits)]}

    async def get_message(self, message_id: str, *, use_cache: bool) -> dict[str, Any]:
        return {
            "id": message_id,
            "subject": "Budget",
            "internalDate": "1793000000000",
            "body": "Thanks",
        }

    async def get_message_html(self, message_id: str) -> str | None:
        return self.html


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> _Mailbox:
    box = _Mailbox()

    @asynccontextmanager
    async def opened(tool: object, user_id: UUID) -> AsyncIterator[Any]:
        class _Open:
            client = box

        yield _Open()

    async def read(user_id: UUID, contact_id: str) -> Contact:
        return _contact()

    monkeypatch.setattr(contact_card, "open_tool_client", opened)
    monkeypatch.setattr(contact_card, "read_contact", read)
    return box


def _answers(monkeypatch: pytest.MonkeyPatch, answer: BaseModel) -> list[str]:
    prompts: list[str] = []

    async def ask(run: AssistRun, prompt: str, schema: type[Any]) -> BaseModel:
        prompts.append(prompt)
        return answer

    monkeypatch.setattr(contact_card, "ask_slot", ask)
    return prompts


async def test_the_latest_messages_are_read_whole_under_its_address(
    mailbox: _Mailbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = _answers(monkeypatch, FoundValues(values=[_found("organization", "Acme Ltd")]))
    run = _run()

    values = await complete_contact(run, "c1")

    assert [value.value for value in values] == ["Acme Ltd"]
    assert mailbox.query == "from:ana@acme.example"
    assert mailbox.size == TOOL_ASSIST_CONTACT_MESSAGES_MAX
    assert "Acme Ltd" in prompts[0]
    assert "Message 2:" in prompts[0]
    assert "<external_content" in prompts[0]
    assert run.read_sections == {"contacts", "mail"}


async def test_what_the_card_holds_is_not_asked_of_the_model(
    mailbox: _Mailbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def read(user_id: UUID, contact_id: str) -> Contact:
        return _contact(organization="Acme Ltd")

    monkeypatch.setattr(contact_card, "read_contact", read)
    prompts = _answers(monkeypatch, FoundValues(values=[_found("phone", "Thanks")]))

    with pytest.raises(BaseAPIException):
        await complete_contact(_run(), "c1")

    wanted = prompts[0].split("Wanted:")[-1].split("\n")[0]
    assert "organization" not in wanted
    assert "phone" in wanted


async def test_a_message_with_no_html_is_read_as_text(
    mailbox: _Mailbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    mailbox.html = None
    prompts = _answers(monkeypatch, FoundValues(values=[]))

    with pytest.raises(BaseAPIException):
        await complete_contact(_run(), "c1")

    assert "Thanks" in prompts[0]


async def test_a_vast_html_is_bounded_before_it_is_parsed(
    mailbox: _Mailbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed: list[int] = []

    def to_text(html: str) -> str:
        parsed.append(len(html))
        return "Acme Ltd"

    monkeypatch.setattr(contact_card, "html_to_text", to_text)
    mailbox.html = "x" * (TOOL_ASSIST_CONTACT_HTML_MAX_CHARS + 10)
    _answers(monkeypatch, FoundValues(values=[_found("organization", "Acme Ltd")]))

    await complete_contact(_run(), "c1")

    assert parsed == [TOOL_ASSIST_CONTACT_HTML_MAX_CHARS] * mailbox.hits


async def test_a_contact_with_no_address_has_nothing_to_look_under(
    mailbox: _Mailbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def read(user_id: UUID, contact_id: str) -> Contact:
        return _contact(emails=[])

    monkeypatch.setattr(contact_card, "read_contact", read)

    run = _run()

    with pytest.raises(BaseAPIException) as refused:
        await complete_contact(run, "c1")

    assert _code(refused) == "assist_empty"
    assert run.read_sections == {"contacts"}


async def test_nobody_wrote_or_nothing_to_add_is_a_refusal(
    mailbox: _Mailbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    mailbox.hits = 0
    prompts = _answers(monkeypatch, FoundValues(values=[]))

    with pytest.raises(BaseAPIException) as refused:
        await complete_contact(_run(), "c1")

    assert _code(refused) == "assist_not_found"
    assert prompts == []


def test_a_card_keeps_only_what_the_editor_can_take() -> None:
    proposal = proposed_contact(
        CardDraft(
            found=True,
            given_name=" Ana ",
            family_name="Silva",
            emails=["ana@acme.example", "not an address"],
            phones=["+33 6 12 34 56 78", "fax"],
        )
    )

    assert proposal.given_name == "Ana"
    assert proposal.emails == ["ana@acme.example"]
    assert proposal.phones == ["+33 6 12 34 56 78"]


@pytest.mark.parametrize(
    "draft",
    [CardDraft(found=False, given_name="Ana"), CardDraft(found=True, website="acme.example")],
)
def test_a_picture_that_is_no_card_or_names_nobody_is_a_refusal(draft: CardDraft) -> None:
    with pytest.raises(BaseAPIException) as refused:
        proposed_contact(draft)

    assert _code(refused) == "assist_not_found"


async def test_a_card_is_redrawn_before_a_model_reads_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def redraw(data: bytes, max_side: int) -> ContactPhoto:
        seen.update(data=data, side=max_side)
        return ContactPhoto(b"redrawn", "image/jpeg")

    async def ask(run: AssistRun, prompt: str, image: bytes, schema: type[Any]) -> CardDraft:
        seen.update(image=image, prompt=prompt)
        return CardDraft(found=True, family_name="Silva")

    monkeypatch.setattr(contact_card, "prepared_photo", redraw)
    monkeypatch.setattr(contact_card, "ask_slot_on_image", ask)

    proposal = await contact_from_card(_run(), b"raw photo")

    assert proposal.family_name == "Silva"
    assert seen["data"] == b"raw photo"
    assert seen["side"] == TOOL_ASSIST_CARD_MAX_SIDE
    assert seen["image"] == b"redrawn"
