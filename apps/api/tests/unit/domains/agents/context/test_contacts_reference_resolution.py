"""Referring to a contact by NAME must resolve — it never could.

The conversational resolver scores `ContextTypeDefinition.reference_fields`
against the items the ToolContextManager stored. Those items are the registry
payloads verbatim (`parallel_executor` builds `result={"data": structured_data}`,
`ToolContextManager.auto_save` reads `data["contacts"]`, `save_list` stores them
as-is plus an index) — i.e. the provider's RAW person object.

Measured 2026-08-01, before the fix: every declared reference_field resolved to
None on a real payload, so "Marie" / "Alice Vernier" NEVER matched. Only the
ordinal ("2") and keyword ("dernier") strategies worked, and the HITL
confirmation label came out empty for the same reason.

These tests run the real resolver over the real builder output.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.context.registry import ContextTypeRegistry
from src.domains.agents.context.resolver import ReferenceResolver
from src.domains.agents.tools.mixins import ToolOutputMixin

pytestmark = pytest.mark.unit


class _Builder(ToolOutputMixin):
    operation = "search"


def _stored_items(*persons: dict[str, Any]) -> list[dict[str, Any]]:
    """Exactly what `save_list` persists for a contacts search."""
    output = _Builder().build_contacts_output(contacts=[dict(p) for p in persons])
    items = []
    for item_id, item in (output.registry_updates or {}).items():
        payload = item.model_dump()["payload"] if hasattr(item, "model_dump") else item["payload"]
        items.append({**payload, "_registry_id": item_id})
    return [{**item, "index": idx} for idx, item in enumerate(items, 1)]


ALICE = {
    "resourceName": "people/c1",
    "names": [{"displayName": "Alice Vernier", "givenName": "Alice"}],
    "emailAddresses": [{"value": "alice@example.com"}],
}
MARIE = {
    "resourceName": "people/c2",
    "names": [{"displayName": "Marie Martin", "givenName": "Marie"}],
    "emailAddresses": [{"value": "marie@example.com"}],
}
NO_NAME = {"resourceName": "people/c3", "phoneNumbers": [{"value": "+33600000000"}]}


@pytest.fixture
def resolver() -> ReferenceResolver:
    return ReferenceResolver(ContextTypeRegistry.get_definition("contacts"))


class TestNameResolution:
    def test_full_name_resolves(self, resolver: ReferenceResolver) -> None:
        result = resolver.resolve("Alice Vernier", _stored_items(ALICE, MARIE))

        assert result.success is True
        assert result.item is not None
        assert result.item["resource_name"] == "people/c1"

    def test_first_name_resolves(self, resolver: ReferenceResolver) -> None:
        result = resolver.resolve("Marie", _stored_items(ALICE, MARIE))

        assert result.success is True
        assert result.item is not None
        assert result.item["resource_name"] == "people/c2"

    def test_display_name_field_is_readable(self) -> None:
        """`display_name_field` labels disambiguation AND the HITL confirmation."""
        definition = ContextTypeRegistry.get_definition("contacts")
        item = _stored_items(ALICE)[0]

        assert item.get(definition.display_name_field) == "Alice Vernier"

    def test_every_declared_reference_field_is_carried_by_the_payload(self) -> None:
        """A declared field the payload never carries cannot match anything."""
        definition = ContextTypeRegistry.get_definition("contacts")
        item = _stored_items(ALICE)[0]

        unusable = [
            field
            for field in definition.reference_fields
            if not isinstance(item.get(field), str)
            and not (
                isinstance(item.get(field), list)
                and any(isinstance(value, str) for value in item.get(field) or [])
            )
        ]

        assert not unusable, (
            f"reference_fields {unusable} are declared for the contacts domain but the "
            "stored payload carries nothing the resolver can score (it reads strings and "
            "lists of strings only)."
        )


class TestOrdinalStrategiesStillWork:
    """The strategies that already worked must keep working."""

    @pytest.mark.parametrize(
        ("reference", "expected"), [("2", "people/c2"), ("dernier", "people/c2")]
    )
    def test_index_and_keyword(
        self, resolver: ReferenceResolver, reference: str, expected: str
    ) -> None:
        result = resolver.resolve(reference, _stored_items(ALICE, MARIE))

        assert result.success is True
        assert result.item is not None
        assert result.item["resource_name"] == expected


class TestContactWithoutDisplayName:
    def test_no_fabricated_name_key(self) -> None:
        """No display name means NO `name` key — never a translated placeholder.

        A fabricated "Inconnu" would be scored by the fuzzy resolver and shown
        to the user as somebody's name.
        """
        item = _stored_items(NO_NAME)[0]

        assert "name" not in item

    def test_nameless_contact_never_matches_a_name(self, resolver: ReferenceResolver) -> None:
        result = resolver.resolve("Alice Vernier", _stored_items(NO_NAME))

        assert result.success is False
