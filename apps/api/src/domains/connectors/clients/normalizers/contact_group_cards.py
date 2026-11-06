"""A contact group on iCloud is a card of its own (ADR-369, lot 9).

It says what it is (``X-ADDRESSBOOKSERVER-KIND:group``) and names each member by the UID of their
card (``X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:…``). Apple's convention, documented by the format and
written here without an account to prove it on: what was read back is the card these functions
wrote, so this is the least that could be held to it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

import vobject

KIND_LINE: Final = "x-addressbookserver-kind"
MEMBER_LINE: Final = "x-addressbookserver-member"
MEMBER_PREFIX: Final = "urn:uuid:"
GROUP_KIND: Final = "group"


def _name_card(card: Any, name: str) -> None:
    card.fn.value = name
    card.n.value = vobject.vcard.Name(family=name, given="")


def group_card(name: str, uid: str) -> str:
    """A new group's card, nobody in it."""
    card = vobject.vCard()
    card.add("fn").value = name
    card.add("n").value = vobject.vcard.Name(family=name, given="")
    card.add("uid").value = uid
    card.add(KIND_LINE).value = GROUP_KIND
    return str(card.serialize())


def renamed_group_card(card_text: str, name: str) -> str:
    """A group's card under another name, its members kept."""
    card = vobject.readOne(card_text, ignoreUnreadable=True)
    _name_card(card, name)
    return str(card.serialize())


def card_with_members(card_text: str, *, add: Sequence[str], remove: Sequence[str]) -> str:
    """A group's card with members added and taken off, by the UID of their cards."""
    card = vobject.readOne(card_text, ignoreUnreadable=True)
    gone = {f"{MEMBER_PREFIX}{uid}" for uid in remove}
    lines = [line for line in card.contents.get(MEMBER_LINE, []) if line.value not in gone]
    if lines:
        card.contents[MEMBER_LINE] = lines
    else:
        card.contents.pop(MEMBER_LINE, None)
    held = {line.value for line in lines}
    for uid in add:
        value = f"{MEMBER_PREFIX}{uid}"
        if value not in held:
            card.add(MEMBER_LINE).value = value
            held.add(value)
    return str(card.serialize())


def group_facts(card: Any) -> dict[str, Any]:
    """What a card says of groups: its UID, and its members when it is one."""
    facts: dict[str, Any] = {}
    uids = card.contents.get("uid")
    if uids:
        facts["uid"] = str(uids[0].value)
    kinds = card.contents.get(KIND_LINE)
    if kinds and str(kinds[0].value).lower() == GROUP_KIND:
        facts["isGroup"] = True
        facts["groupMembers"] = [
            str(line.value).removeprefix(MEMBER_PREFIX)
            for line in card.contents.get(MEMBER_LINE, [])
        ]
    return facts


__all__ = ["card_with_members", "group_card", "group_facts", "renamed_group_card"]
