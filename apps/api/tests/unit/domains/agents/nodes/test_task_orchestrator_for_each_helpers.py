"""FOR_EACH helpers of the task orchestrator — informed HITL and registry trim.

Two pure helpers decide what the user sees before confirming a bulk operation,
and what the response node still knows about afterwards:

* ``extract_item_previews_for_hitl`` builds the "you are about to act on these"
  list. An empty or wrong preview turns an informed confirmation into a blind
  one — the user approves a count, not a content.
* ``filter_registry_by_items`` trims the pre-executed registry down to the
  items the user KEPT. The tools iterate ``pre_executed_steps`` (already
  filtered upstream), so a bug here does not act on the wrong items — it makes
  ``response_node`` *describe* the wrong ones, which is exactly the kind of
  failure nothing raises on.

Both were entirely untested; the module sat at 16 % line coverage.
"""

from typing import Any

import pytest

from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.nodes.for_each_hitl_prep import (
    detect_domain_from_items,
    extract_item_previews_for_hitl,
    filter_registry_by_items,
)
from src.domains.agents.utils.type_domain_mapping import (
    FOR_EACH_FILTERABLE_ITEMS_KEYS,
    FOR_EACH_UNFILTERABLE_ITEMS_KEYS,
    ITEMS_KEY_TO_REGISTRY_CONFIG,
    is_items_key_for_each_filterable,
)

pytestmark = pytest.mark.unit


def _registry_item(
    item_type: RegistryItemType,
    unique_key: str,
    payload: dict[str, Any],
    domain: str,
) -> tuple[str, RegistryItem]:
    """Build a registry entry the way the tools do: ID derived from a unique key."""
    item_id = generate_registry_id(item_type, unique_key)
    return item_id, RegistryItem(
        id=item_id,
        type=item_type,
        payload=payload,
        meta=RegistryItemMeta(source="test", domain=domain, tool_name="t"),
    )


def _email_registry(*message_ids: str) -> dict[str, RegistryItem]:
    """A registry of emails, keyed exactly as ``search_emails_tool`` keys them."""
    entries = [
        _registry_item(
            RegistryItemType.EMAIL,
            message_id,
            {"id": message_id, "subject": f"Subject {message_id}"},
            "emails",
        )
        for message_id in message_ids
    ]
    return dict(entries)


class TestExtractItemPreviewsForHitl:
    """The "informed HITL" preview list."""

    def test_builds_one_preview_per_item_with_the_domain_fields(self) -> None:
        registry = _email_registry("m1", "m2")
        previews = extract_item_previews_for_hitl(
            pre_exec_registry=registry,
            for_each_steps=[{"for_each_source": "$steps.get_emails.emails"}],
            completed_steps={
                "get_emails": {
                    "emails": [
                        {"id": "m1", "subject": "Meeting tomorrow", "from": "john@example.com"},
                        {"id": "m2", "subject": "Project update", "from": "jane@example.com"},
                    ]
                }
            },
        )

        assert previews == [
            {"subject": "Meeting tomorrow", "from": "john@example.com"},
            {"subject": "Project update", "from": "jane@example.com"},
        ]

    def test_uses_the_fallback_path_when_the_primary_field_is_absent(self) -> None:
        # FOR_EACH_PREVIEW_FIELDS declares ("from", "sender") for emails.
        previews = extract_item_previews_for_hitl(
            pre_exec_registry=_email_registry("m1"),
            for_each_steps=[{"for_each_source": "$steps.get_emails.emails"}],
            completed_steps={"get_emails": {"emails": [{"subject": "S", "sender": "a@b.c"}]}},
        )

        assert previews == [{"subject": "S", "from": "a@b.c"}]

    def test_reads_a_nested_path_and_keys_the_preview_on_its_last_segment(self) -> None:
        registry = dict(
            [
                _registry_item(
                    RegistryItemType.CONTACT,
                    "people/c1",
                    {"resourceName": "people/c1"},
                    "contacts",
                )
            ]
        )
        previews = extract_item_previews_for_hitl(
            pre_exec_registry=registry,
            for_each_steps=[{"for_each_source": "$steps.get_contacts.contacts"}],
            completed_steps={
                "get_contacts": {
                    "contacts": [
                        {
                            "names": [{"displayName": "Ada Lovelace"}],
                            "emailAddresses": [{"value": "ada@example.com"}],
                        }
                    ]
                }
            },
        )

        assert previews == [{"displayName": "Ada Lovelace", "value": "ada@example.com"}]

    def test_skips_items_that_carry_none_of_the_preview_fields(self) -> None:
        previews = extract_item_previews_for_hitl(
            pre_exec_registry=_email_registry("m1"),
            for_each_steps=[{"for_each_source": "$steps.get_emails.emails"}],
            completed_steps={"get_emails": {"emails": [{"id": "m1"}, {"subject": "kept"}]}},
        )

        assert previews == [{"subject": "kept"}]

    def test_skips_non_dict_entries_rather_than_raising(self) -> None:
        previews = extract_item_previews_for_hitl(
            pre_exec_registry=_email_registry("m1"),
            for_each_steps=[{"for_each_source": "$steps.get_emails.emails"}],
            completed_steps={"get_emails": {"emails": ["not-a-dict", {"subject": "kept"}]}},
        )

        assert previews == [{"subject": "kept"}]

    @pytest.mark.parametrize(
        ("for_each_steps", "completed_steps", "reason"),
        [
            ([], {"get_emails": {"emails": [{"subject": "s"}]}}, "no for_each step"),
            (
                [{"for_each_source": "not-a-reference"}],
                {"get_emails": {"emails": [{"subject": "s"}]}},
                "unparsable reference",
            ),
            (
                [{"for_each_source": "$steps.missing.emails"}],
                {"get_emails": {"emails": [{"subject": "s"}]}},
                "provider step absent from results",
            ),
            (
                [{"for_each_source": "$steps.get_emails.emails"}],
                {"get_emails": {"emails": []}},
                "provider returned nothing",
            ),
            (
                [{"for_each_source": "$steps.get_emails.emails"}],
                {"get_emails": {"emails": {"not": "a list"}}},
                "field is not a list",
            ),
        ],
    )
    def test_returns_no_preview_when_there_is_nothing_to_show(
        self,
        for_each_steps: list[dict[str, Any]],
        completed_steps: dict[str, dict[str, Any]],
        reason: str,
    ) -> None:
        assert (
            extract_item_previews_for_hitl(
                pre_exec_registry={},
                for_each_steps=for_each_steps,
                completed_steps=completed_steps,
            )
            == []
        ), reason

    def test_an_unknown_domain_yields_empty_previews_not_an_exception(self) -> None:
        # No FOR_EACH_PREVIEW_FIELDS entry → nothing to show, but the HITL
        # confirmation must still be reachable.
        previews = extract_item_previews_for_hitl(
            pre_exec_registry={},
            for_each_steps=[{"for_each_source": "$steps.s1.widgets"}],
            completed_steps={"s1": {"widgets": [{"anything": 1}]}},
        )

        assert previews == []


class TestDetectDomainFromItems:
    """Registry meta wins over the field path, and both are normalized."""

    def test_normalizes_the_plural_result_key_carried_by_registry_meta(self) -> None:
        registry = _email_registry("m1")

        assert detect_domain_from_items(registry, "anything") == "email"

    def test_falls_back_to_the_field_path_when_the_registry_is_empty(self) -> None:
        assert detect_domain_from_items({}, "contacts") == "contact"

    def test_reports_unknown_rather_than_guessing(self) -> None:
        assert detect_domain_from_items({}, "widgets") == "unknown"

    def test_keeps_an_unmapped_meta_domain_verbatim(self) -> None:
        _, item = _registry_item(RegistryItemType.EMAIL, "m1", {"id": "m1"}, "widgets")

        assert detect_domain_from_items({item.id: item}, "emails") == "widgets"


class TestFilterRegistryByItems:
    """Trimming the registry to what the user kept."""

    def test_keeps_only_the_registry_entries_of_the_kept_items(self) -> None:
        registry = _email_registry("m1", "m2", "m3")
        kept = [{"id": "m1"}, {"id": "m3"}]

        filtered = filter_registry_by_items(registry, kept, "emails", run_id="r1")

        assert set(filtered) == {
            generate_registry_id(RegistryItemType.EMAIL, "m1"),
            generate_registry_id(RegistryItemType.EMAIL, "m3"),
        }

    def test_uses_the_domain_specific_unique_key(self) -> None:
        # Contacts are keyed on resourceName, not on `id`.
        entries = dict(
            [
                _registry_item(
                    RegistryItemType.CONTACT, "people/c1", {"resourceName": "people/c1"}, "contacts"
                ),
                _registry_item(
                    RegistryItemType.CONTACT, "people/c2", {"resourceName": "people/c2"}, "contacts"
                ),
            ]
        )

        filtered = filter_registry_by_items(
            entries, [{"resourceName": "people/c2"}], "contacts", run_id="r1"
        )

        assert set(filtered) == {generate_registry_id(RegistryItemType.CONTACT, "people/c2")}

    def test_leaves_the_registry_untouched_when_the_domain_is_unknown(self) -> None:
        registry = _email_registry("m1", "m2")

        assert filter_registry_by_items(registry, [{"id": "m1"}], "widgets", "r1") == registry

    def test_leaves_the_registry_untouched_when_no_item_carries_the_unique_key(self) -> None:
        # Degrading OPEN is the deliberate choice: the response may mention one
        # item too many, whereas an empty registry would strip every card.
        registry = _email_registry("m1", "m2")

        assert (
            filter_registry_by_items(registry, [{"subject": "no id"}], "emails", "r1") == registry
        )

    @pytest.mark.parametrize("empty", [{}, None])
    def test_returns_the_input_when_there_is_nothing_to_filter(self, empty: Any) -> None:
        registry = _email_registry("m1")

        assert filter_registry_by_items(registry, [], "emails", "r1") == registry
        assert filter_registry_by_items(empty or {}, [{"id": "m1"}], "emails", "r1") == (
            empty or {}
        )

    def test_drops_a_kept_item_that_has_no_matching_registry_entry(self) -> None:
        # The item survives in pre_executed_steps (what the tools iterate); only
        # its card is missing.
        registry = _email_registry("m1")

        filtered = filter_registry_by_items(registry, [{"id": "unknown"}], "emails", "r1")

        assert filtered == {}


class TestCompositeIdDomainsAreNeverFiltered:
    """Domains whose registry ID is composite must not be filtered at all.

    ``ITEMS_KEY_TO_REGISTRY_CONFIG`` names a single ``unique_key_field`` per
    items key, and the filter regenerates the registry ID from it. For three
    domains that ID is built from SEVERAL fields plus a timestamp:

    * ROUTE    — ``f"{origin}_{destination}_{mode}_{YYYYMMDDHHMM}"``
      (routes_tools.py::_create_route_registry_item)
    * LOCATION — ``f"{latitude}_{longitude}"`` (places_tools.py)
    * WEATHER  — ``f"current_{name}_{YYYYMMDD}"`` (weather_tools.py)

    Regenerating from one field therefore produces IDs that match NOTHING. The
    mapping's own comment called that harmless ("won't match"), but it is not:
    when the payload does carry the named field, the filter builds a non-empty
    expectation set that intersects nothing and returns an EMPTY registry —
    every card silently disappears from the answer.
    """

    def test_a_location_registry_is_not_emptied_by_filtering(self) -> None:
        # The LOCATION payload does carry `latitude`, so the filter used to
        # build IDs from it — and none of them matched the real `lat_lon` IDs.
        entries = dict(
            [
                _registry_item(
                    RegistryItemType.LOCATION,
                    "48.85_2.35",
                    {"latitude": 48.85, "longitude": 2.35, "locality": "Paris"},
                    "locations",
                ),
                _registry_item(
                    RegistryItemType.LOCATION,
                    "45.76_4.83",
                    {"latitude": 45.76, "longitude": 4.83, "locality": "Lyon"},
                    "locations",
                ),
            ]
        )

        filtered = filter_registry_by_items(
            entries, [{"latitude": 48.85, "longitude": 2.35}], "locations", "r1"
        )

        assert filtered == entries

    def test_a_weather_registry_is_not_emptied_by_filtering(self) -> None:
        entries = dict(
            [
                _registry_item(
                    RegistryItemType.WEATHER,
                    "current_Paris_20260725",
                    {"name": "Paris", "description": "sunny"},
                    "weathers",
                )
            ]
        )

        filtered = filter_registry_by_items(entries, [{"name": "Paris"}], "weathers", "r1")

        assert filtered == entries

    def test_a_route_registry_survives_filtering(self) -> None:
        entries = dict(
            [
                _registry_item(
                    RegistryItemType.ROUTE,
                    "Paris_Lyon_DRIVE_202607251200",
                    {"origin": "Paris", "destination": "Lyon"},
                    "routes",
                )
            ]
        )

        filtered = filter_registry_by_items(
            entries, [{"origin": "Paris", "destination": "Lyon"}], "routes", "r1"
        )

        assert filtered == entries


class TestForEachFilterability:
    """Every items key is explicitly classified — no silent third category."""

    def test_the_two_sets_partition_the_mapping(self) -> None:
        assert FOR_EACH_FILTERABLE_ITEMS_KEYS | FOR_EACH_UNFILTERABLE_ITEMS_KEYS == set(
            ITEMS_KEY_TO_REGISTRY_CONFIG
        )
        assert not (FOR_EACH_FILTERABLE_ITEMS_KEYS & FOR_EACH_UNFILTERABLE_ITEMS_KEYS)

    def test_the_composite_id_domains_are_the_unfilterable_ones(self) -> None:
        assert FOR_EACH_UNFILTERABLE_ITEMS_KEYS == {"routes", "locations", "weathers"}

    @pytest.mark.parametrize("items_key", ["emails", "contacts", "events", "EMAILS"])
    def test_simple_id_domains_are_filterable(self, items_key: str) -> None:
        assert is_items_key_for_each_filterable(items_key) is True

    @pytest.mark.parametrize("items_key", ["routes", "locations", "weathers", "ROUTES"])
    def test_composite_id_domains_are_not(self, items_key: str) -> None:
        assert is_items_key_for_each_filterable(items_key) is False

    def test_an_unknown_items_key_is_not_filterable(self) -> None:
        assert is_items_key_for_each_filterable("widgets") is False
