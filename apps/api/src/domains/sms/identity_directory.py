"""Provider-neutral address book, read outside SMS SQL fences and best effort."""

import asyncio
from time import perf_counter
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from src.core.config import settings
from src.domains.connectors.active_client import ActiveClient, open_active_client
from src.domains.connectors.clients.contact_directory import ContactDirectory
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.relations.identity import IdentityResolver
from src.domains.relations.models import RelationAlias, RelationFavorite
from src.domains.shared.consultation_sink import collector_is_active, consultation_collector
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.domains.sms.identity import ContactIdentity, IdentityBook
from src.domains.telephony.repository import TelephonyRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
_SURFACE = "sms_identity"


class _Name(BaseModel):
    model_config = ConfigDict(extra="ignore")
    displayName: str = ""
    givenName: str = ""
    familyName: str = ""


class _Value(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: str


class _Person(BaseModel):
    model_config = ConfigDict(extra="ignore")
    names: list[_Name] = Field(default_factory=list, max_length=20)
    phoneNumbers: list[_Value] = Field(default_factory=list, max_length=100)
    emailAddresses: list[_Value] = Field(default_factory=list, max_length=100)


def project_directory(directory: ContactDirectory) -> tuple[tuple[ContactIdentity, ...], bool]:
    contacts = []
    complete = not directory.truncated
    for raw in directory.persons:
        try:
            person = _Person.model_validate(raw)
        except ValidationError:
            complete = False
            continue
        first = person.names[0] if person.names else _Name()
        name = first.displayName or " ".join(
            part for part in (first.givenName, first.familyName) if part
        )
        contacts.append(
            ContactIdentity(
                name=name,
                numbers=tuple(value.value for value in person.phoneNumbers),
                emails=tuple(value.value for value in person.emailAddresses),
            )
        )
    return tuple(contacts), complete


async def load_relation_book(owner: UUID) -> IdentityBook:
    """Build the local identity book: declared relations, aliases and known names.

    A failure is logged and yields an empty book, so a sender stays unresolved
    rather than wrongly named.

    Args:
        owner: The account.

    Returns:
        The relations' names and their resolver.
    """
    # Local metadata is the same canonical resolver the Relations view uses.
    try:
        async with get_db_context() as db:
            aliases = list(
                (
                    await db.scalars(select(RelationAlias).where(RelationAlias.user_id == owner))
                ).all()
            )
            favorites = list(
                (
                    await db.scalars(
                        select(RelationFavorite).where(RelationFavorite.user_id == owner)
                    )
                ).all()
            )
            loops = await OpenLoopRepository(db).aggregate_open_by_counterparty(owner)
            calls = await TelephonyRepository(db).aggregate_calls_by_callee(owner)
            resolver = IdentityResolver.from_pairs(
                (row.alias_key, row.canonical_key) for row in aliases
            )
            names = {resolver.key(row.raw_name): row.raw_name for row in [*loops, *calls]}
            names.update({resolver.canonical(row.name_key): row.display_name for row in favorites})
    except Exception as error:
        logger.warning("sms_relation_identity_unavailable", error_type=type(error).__name__)
        resolver, names = IdentityResolver.from_pairs([]), {}
    return IdentityBook(relations=names, resolver=resolver)


async def load_identity_book(owner: UUID) -> IdentityBook:
    """Build the full identity book: contacts first, then the local relations.

    Args:
        owner: The account.

    Returns:
        The identity book.
    """
    local = await load_relation_book(owner)
    contacts = await load_contact_book(owner)
    return IdentityBook(
        contacts=contacts.contacts,
        complete=contacts.complete,
        relations=local.relations,
        resolver=local.resolver,
    )


async def load_contact_book(owner: UUID, *, cache_scope: str | None = None) -> IdentityBook:
    """Contact-derived identities only; local alias edits never become stale snapshots."""
    directory = await _directory(owner, cache_scope=cache_scope)
    if directory is None:
        return IdentityBook()
    contacts, complete = project_directory(directory)
    return IdentityBook(contacts=contacts, complete=complete)


async def _directory(owner: UUID, *, cache_scope: str | None = None) -> ContactDirectory | None:
    started = perf_counter()
    try:
        async with asyncio.timeout(settings.sms_identity_timeout_seconds):
            async with open_active_client("contacts", owner, fresh=True) as opened:
                if not isinstance(opened, ActiveClient):
                    return None
                directory: ContactDirectory = (
                    await opened.client.list_email_directory(settings.sms_directory_max_contacts)
                    if cache_scope is None
                    else await opened.client.list_email_directory(
                        settings.sms_directory_max_contacts, cache_scope=cache_scope
                    )
                )
    except Exception as error:
        logger.warning("sms_contact_identity_unavailable", error_type=type(error).__name__)
        await _record(owner, started, failed=True)
        return None
    if not directory.from_cache:
        await _record(owner, started, failed=False)
    return directory


async def _record(owner: UUID, started: float, *, failed: bool) -> None:
    if not collector_is_active():
        async with consultation_collector(f"sms_identity_{uuid4().hex}"):
            record_surface_consultations(
                surface=_SURFACE,
                user_id=owner,
                opened=["contacts"],
                failed=["contacts"] if failed else (),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        return
    record_surface_consultations(
        surface=_SURFACE,
        user_id=owner,
        opened=["contacts"],
        failed=["contacts"] if failed else (),
        duration_ms=int((perf_counter() - started) * 1000),
    )
