"""What LIA finds for a contact's card (ADR-372).

From the latest messages a person sent: a value is proposed with the message that says it, and only
if that message says it, word for word, because what refuses invention here is structural: a phone
number the text does not hold never reaches the page. The whole message is read, not the reply the
assistant keeps (ADR-287), since a signature is exactly what that one leaves out.

From a photographed card: the picture is redrawn before anything reads it, so a phone's GPS stays
behind, and the vision slot reads it. From a sentence the person says or types (2026-11-07): a value
reaches the form only if every word of it was said — a number by its digits — so the model may set an
address on lines or spell a dictated e-mail, never add a word nobody said. Nothing is created either
way: the person's editor opens filled, and they save it or not.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from pydantic import BaseModel, Field

from src.core.constants import (
    TOOL_ASSIST_CARD_MAX_SIDE,
    TOOL_ASSIST_CONTACT_HTML_MAX_CHARS,
    TOOL_ASSIST_CONTACT_MESSAGE_MAX_CHARS,
    TOOL_ASSIST_CONTACT_MESSAGES_MAX,
    TOOL_ASSIST_CONTACT_VALUE_MAX_CHARS,
)
from src.core.field_names import FIELD_BODY
from src.core.i18n import get_language_name
from src.core.validators import validate_email
from src.domains.agents.prompts import load_prompt
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.connectors.clients.normalizers.html_text import html_to_text
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.shared.text_normalization import fold_name
from src.domains.tool_assists.catalogue import SECTION_CONTACTS, SECTION_MAIL
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot, ask_slot_on_image
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.contacts_photos import prepared_photo
from src.domains.workbench.contacts_service import read_contact
from src.domains.workbench.errors import ASSIST_EMPTY, ASSIST_NOT_FOUND, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.mail_projection import received_at
from src.domains.workbench.schemas.contacts import Contact

#: What a card can gain from a message; a phone can be one more, the others only fill a blank.
FIELD_PHONE: Final = "phone"
FIELD_ORGANIZATION: Final = "organization"
FIELD_JOB_TITLE: Final = "job_title"
FIELD_WEBSITE: Final = "website"
FIELD_ADDRESS: Final = "address"


class FoundValue(BaseModel):
    """One value the model read."""

    field: str = Field(description="phone, organization, job_title, website or address.")
    value: str = Field(description="The value, exactly as the message writes it.")
    message: int = Field(description="The number of the message holding it, from 1.")


class FoundValues(BaseModel):
    """What the model read."""

    values: list[FoundValue] = Field(default_factory=list, description="The values found.")


class ProposedValue(BaseModel):
    """A value for the card, with where it comes from."""

    field: str = Field(description="What it fills.")
    value: str = Field(description="The value, as the message writes it.")
    message_id: str = Field(description="The message that says it.")
    subject: str = Field(description="That message's subject.")
    received_at: datetime | None = Field(description="When it arrived.")


class CardDraft(BaseModel):
    """What the model reads on a card; empty means it does not say."""

    found: bool = Field(description="The picture shows a business card.")
    given_name: str = Field(default="", description="The first name.")
    family_name: str = Field(default="", description="The last name.")
    organization: str = Field(default="", description="The organization.")
    job_title: str = Field(default="", description="What they do.")
    website: str = Field(default="", description="The website, as written.")
    emails: list[str] = Field(default_factory=list, description="The addresses, as written.")
    phones: list[str] = Field(default_factory=list, description="The numbers, as written.")
    address: str = Field(default="", description="The postal address, its lines kept.")


class WordsDraft(CardDraft):
    """What the model reads in a person's words; empty means they do not say."""

    found: bool = Field(description="The words describe someone to save as a contact.")


class ProposedContact(BaseModel):
    """A card as the editor can take it."""

    given_name: str = Field(default="", description="The first name.")
    family_name: str = Field(default="", description="The last name.")
    organization: str = Field(default="", description="The organization.")
    job_title: str = Field(default="", description="What they do.")
    website: str = Field(default="", description="The website, as written.")
    emails: list[str] = Field(default_factory=list, description="Addresses that are addresses.")
    phones: list[str] = Field(default_factory=list, description="The numbers, as written.")
    address: str = Field(default="", description="The postal address, its lines kept.")


@dataclass(frozen=True, slots=True)
class Exchange:
    """One message of a person, as the model reads it."""

    message_id: str
    subject: str
    received: datetime | None
    words: str


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _folded(value: str) -> str:
    return " ".join(value.split()).casefold()


def said_in(field: str, value: str, words: str) -> bool:
    """Whether a message holds the value: a number by its digits, the rest word for word.

    Args:
        field: What the value fills.
        value: The value.
        words: The message.

    Returns:
        The message says it.
    """
    if field == FIELD_PHONE:
        digits = _digits(value)
        return bool(digits) and digits in _digits(words)
    return _folded(value) in _folded(words)


def _missing_from(contact: Contact, field: str, value: str) -> bool:
    """Whether the card lacks this: nothing it holds is replaced."""
    if field == FIELD_PHONE:
        digits = _digits(value)
        return not any(digits == _digits(phone.value) for phone in contact.phones)
    held = {
        FIELD_ORGANIZATION: contact.organization,
        FIELD_JOB_TITLE: contact.job_title,
        FIELD_WEBSITE: contact.website,
        FIELD_ADDRESS: contact.addresses,
    }
    return field in held and not held[field]


def proposed_values(
    draft: FoundValues, contact: Contact, exchanges: list[Exchange]
) -> list[ProposedValue]:
    """Keep what a message really says and the card really lacks, once each.

    Args:
        draft: What the model read.
        contact: The card.
        exchanges: The messages, in the order the model numbered them.

    Returns:
        The values to propose.
    """
    kept: list[ProposedValue] = []
    seen: set[tuple[str, str]] = set()
    for found in draft.values:
        value = found.value.strip()
        source = exchanges[found.message - 1] if 1 <= found.message <= len(exchanges) else None
        key = (found.field, _digits(value) if found.field == FIELD_PHONE else _folded(value))
        usable = (
            source is not None
            and 0 < len(value) <= TOOL_ASSIST_CONTACT_VALUE_MAX_CHARS
            and key not in seen
            and _missing_from(contact, found.field, value)
        )
        if not usable or source is None or not said_in(found.field, value, source.words):
            continue
        seen.add(key)
        kept.append(
            ProposedValue(
                field=found.field,
                value=value,
                message_id=source.message_id,
                subject=source.subject,
                received_at=source.received,
            )
        )
    return kept


async def _exchange(client: EmailClientProtocol, message_id: str) -> Exchange:
    """A message whole: its HTML holds the signature the assistant's own text leaves out."""
    message: dict[str, Any] = await client.get_message(message_id, use_cache=False)
    html = await client.get_message_html(message_id)
    words = str(message.get(FIELD_BODY) or "")
    if html:
        # A mailer's HTML can be large, and parsing it would hold every stream of the worker.
        words = await asyncio.to_thread(html_to_text, html[:TOOL_ASSIST_CONTACT_HTML_MAX_CHARS])
    return Exchange(
        message_id=message_id,
        subject=str(message.get("subject") or ""),
        received=received_at(message.get("internalDate")),
        words=words[:TOOL_ASSIST_CONTACT_MESSAGE_MAX_CHARS],
    )


async def _latest_from(run: AssistRun, address: str) -> list[Exchange]:
    """The latest messages this address sent."""
    async with open_tool_client(WorkbenchTool.MAIL, run.user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with run.reading(SECTION_MAIL), provider_call(WorkbenchTool.MAIL, "read", act=False):
            page = await client.search_emails(
                f"from:{address}",
                max_results=TOOL_ASSIST_CONTACT_MESSAGES_MAX,
                use_cache=False,
                headers_only=True,
            )
            hits = (page.get("messages") or [])[:TOOL_ASSIST_CONTACT_MESSAGES_MAX]
            return [await _exchange(client, str(hit["id"])) for hit in hits]


def _lacks(contact: Contact) -> list[str]:
    """What the model is asked for."""
    held = {
        FIELD_ORGANIZATION: contact.organization,
        FIELD_JOB_TITLE: contact.job_title,
        FIELD_WEBSITE: contact.website,
        FIELD_ADDRESS: contact.addresses,
    }
    return [FIELD_PHONE, *(field for field, value in held.items() if not value)]


def _numbered(exchanges: list[Exchange], source_id: str) -> str:
    said = "\n\n".join(
        f"Message {number}:\n{exchange.words}" for number, exchange in enumerate(exchanges, 1)
    )
    return wrap_external_content(said, source_url=source_id, source_type="email")


async def complete_contact(run: AssistRun, contact_id: str) -> list[ProposedValue]:
    """What the latest messages of a contact say that their card lacks.

    Args:
        run: The assist's run.
        contact_id: The contact.

    Returns:
        The values, each with its source: nothing is written.

    Raises:
        BaseAPIException: No address to look under, or nothing to add.
    """
    async with run.reading(SECTION_CONTACTS):
        contact = await read_contact(run.user_id, contact_id)
    if not contact.emails:
        refuse(ASSIST_EMPTY)
    exchanges = await _latest_from(run, contact.emails[0].value)
    if not exchanges:
        refuse(ASSIST_NOT_FOUND)
    prompt = load_prompt("tool_assist_contact_prompt").format(
        wanted=", ".join(_lacks(contact)),
        messages=_numbered(exchanges, contact_id),
    )
    values = proposed_values(await ask_slot(run, prompt, FoundValues), contact, exchanges)
    if not values:
        refuse(ASSIST_NOT_FOUND)
    return values


def _address_of(value: str) -> str | None:
    """A written address that is one; anything else stays off the form."""
    written = value.strip()
    return written if validate_email(written) else None


def proposed_contact(draft: CardDraft) -> ProposedContact:
    """What the editor can take of a card; a picture that is none is a refusal.

    Args:
        draft: What the model read.

    Returns:
        The filled form.

    Raises:
        BaseAPIException: It is no card, or it names nobody.
    """
    bound = TOOL_ASSIST_CONTACT_VALUE_MAX_CHARS
    proposal = ProposedContact(
        given_name=draft.given_name.strip()[:bound],
        family_name=draft.family_name.strip()[:bound],
        organization=draft.organization.strip()[:bound],
        job_title=draft.job_title.strip()[:bound],
        website=draft.website.strip()[:bound],
        emails=[address for value in draft.emails if (address := _address_of(value))],
        phones=[phone.strip()[:bound] for phone in draft.phones if _digits(phone)],
        address=draft.address.strip()[:bound],
    )
    named = proposal.given_name or proposal.family_name or proposal.organization
    if not (draft.found and named):
        refuse(ASSIST_NOT_FOUND)
    return proposal


def _words(text: str) -> list[str]:
    """A text's words, case and accents aside."""
    return [fold_name(word) for word in re.findall(r"\w+", text)]


def said_in_words(value: str, words: str, *, number: bool = False) -> bool:
    """Whether a person's words hold a value: a number by its digits, the rest by its words.

    Every word of the value must be said, in any order and case, accents aside: the model may set
    an address on lines or write « ines arobase acme point fr » as an address, never add a word.

    Args:
        value: What the model read.
        words: What the person said.
        number: The value is a phone number.

    Returns:
        The words hold it.
    """
    if number:
        digits = _digits(value)
        return bool(digits) and digits in _digits(words)
    said = set(_words(words))
    wanted = _words(value)
    return bool(wanted) and all(word in said for word in wanted)


def proposed_contact_from_words(draft: WordsDraft, words: str) -> ProposedContact:
    """What the editor can take of a sentence: only what it says.

    Args:
        draft: What the model read.
        words: What the person said.

    Returns:
        The filled form.

    Raises:
        BaseAPIException: The words describe nobody, or name nobody they say.
    """

    def kept(value: str) -> str:
        return value if said_in_words(value, words) else ""

    return proposed_contact(
        CardDraft(
            found=draft.found,
            given_name=kept(draft.given_name),
            family_name=kept(draft.family_name),
            organization=kept(draft.organization),
            job_title=kept(draft.job_title),
            website=kept(draft.website),
            emails=[address for address in draft.emails if said_in_words(address, words)],
            phones=[phone for phone in draft.phones if said_in_words(phone, words, number=True)],
            address=kept(draft.address),
        )
    )


async def contact_from_words(run: AssistRun, sentence: str) -> ProposedContact:
    """Fill a new contact from what the person says: nothing is created.

    Args:
        run: The assist's run.
        sentence: Their words, typed or dictated.

    Returns:
        The filled form.

    Raises:
        BaseAPIException: The words describe nobody, or no usable answer came.
    """
    prompt = load_prompt("tool_assist_contact_words_prompt").format(sentence=sentence)
    return proposed_contact_from_words(await ask_slot(run, prompt, WordsDraft), sentence)


async def contact_from_card(run: AssistRun, data: bytes) -> ProposedContact:
    """Read a photographed card: nothing is created.

    Args:
        run: The assist's run.
        data: The picture, as the person took it.

    Returns:
        The filled form.

    Raises:
        BaseAPIException: It is no image, no card, or no usable answer came.
    """
    picture = await asyncio.to_thread(prepared_photo, data, TOOL_ASSIST_CARD_MAX_SIDE)
    prompt = load_prompt("tool_assist_card_prompt").format(
        language_name=get_language_name(run.language)
    )
    return proposed_contact(await ask_slot_on_image(run, prompt, picture.data, CardDraft))
