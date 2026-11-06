"""What a contact group is on the three clients (ADR-369, lot 9).

Google's answer is the vocabulary: ``resourceName``, ``formattedName``, ``groupType`` and
``memberCount``. Graph and iCloud answer it too, every group theirs being the person's own, so
what reads a group never asks which provider it reads. ``memberCount`` is None where it cannot be
exact: a count shown is a claim (ADR-185).
"""

from __future__ import annotations

from typing import Any, Final

#: A group the person made, as opposed to Google's own (« starred », « myContacts »).
USER_CONTACT_GROUP: Final = "USER_CONTACT_GROUP"


def group_entry(resource_name: str, name: str, count: int | None) -> dict[str, Any]:
    """One group, in the vocabulary the three clients share."""
    return {
        "resourceName": resource_name,
        "formattedName": name,
        "groupType": USER_CONTACT_GROUP,
        "memberCount": count,
    }


__all__ = ["USER_CONTACT_GROUP", "group_entry"]
