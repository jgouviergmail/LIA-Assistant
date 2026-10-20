"""One bounded address-book projection; ambiguous identities stay literal."""

from dataclasses import dataclass, field
from typing import Literal

from src.domains.relations.identity import NO_MERGES, IdentityResolver
from src.domains.shared.text_normalization import fold_name
from src.domains.sms.sender_policy import normalize_sender
from src.domains.telephony.phone_numbers import same_line


@dataclass(frozen=True, slots=True)
class ContactIdentity:
    name: str
    numbers: tuple[str, ...] = ()
    emails: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SenderIdentity:
    display_name: str
    source: Literal["contact", "relation", "raw"]
    state: Literal["resolved", "ambiguous", "incomplete", "unavailable", "unresolved"]
    relation_key: str | None = None


@dataclass(frozen=True, slots=True)
class IdentityBook:
    contacts: tuple[ContactIdentity, ...] = ()
    complete: bool = False
    relations: dict[str, str] = field(default_factory=dict)
    resolver: IdentityResolver = NO_MERGES

    def resolve(self, sender: str) -> SenderIdentity:
        matches = [contact for contact in self.contacts if _matches(sender, contact)]
        if len(matches) > 1:
            return SenderIdentity(sender, "raw", "ambiguous")
        if matches:
            if not self.complete:
                return SenderIdentity(sender, "raw", "incomplete")
            contact = matches[0]
            if contact.name:
                return SenderIdentity(
                    contact.name, "contact", "resolved", self.resolver.key(contact.name)
                )
        relation_key = self.resolver.key(sender)
        if relation_key in self.relations:
            return SenderIdentity(
                self.relations[relation_key], "relation", "resolved", relation_key
            )
        return SenderIdentity(sender, "raw", "unresolved" if self.complete else "unavailable")


def _matches(sender: str, contact: ContactIdentity) -> bool:
    if fold_name(sender) == fold_name(contact.name):
        return True
    if any(normalize_sender(sender) == normalize_sender(email) for email in contact.emails):
        return True
    if not normalize_sender(sender).startswith("phone:"):
        return False
    return any(same_line(sender, number, infer_country=False) for number in contact.numbers)
