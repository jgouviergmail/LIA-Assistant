"""
Test GROUP → Jinja → get_details pattern.

This test validates the critical flow for queries like "contacts qui habitent ensemble":
1. search_contacts → populates registry with contacts
2. local_query_engine (GROUP) → groups contacts by address
3. get_contact_details with Jinja → extracts resource_names from groups with count > 1

The key issue fixed: Jinja templates accessing `item.resource_name` on RegistryItem objects
was failing because resource_name is inside payload, not at top level.
Fix: parallel_executor now extracts payloads from group.members.
"""

import pytest

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.orchestration.jinja_evaluator import JinjaTemplateEvaluator


class TestGroupJinjaPattern:
    """Test the GROUP → Jinja extraction pattern."""

    @pytest.fixture
    def jinja_evaluator(self):
        """Create a JinjaTemplateEvaluator instance."""
        return JinjaTemplateEvaluator()

    @pytest.fixture
    def sample_contacts_payload(self):
        """Sample contact payloads (as they appear after extraction in parallel_executor)."""
        return [
            {
                "resource_name": "people/c123",
                "names": "Jean dupond",
                "emailAddresses": [{"value": "jean@example.com"}],
                "addresses": [{"formatted": "10 rue de Paris"}],
                "_registry_id": "contact_abc123",
            },
            {
                "resource_name": "people/c456",
                "names": "Marie dupond",
                "emailAddresses": [{"value": "marie@example.com"}],
                "addresses": [{"formatted": "10 rue de Paris"}],  # Same address
                "_registry_id": "contact_def456",
            },
            {
                "resource_name": "people/c789",
                "names": "Pierre dupond",
                "emailAddresses": [{"value": "pierre@example.com"}],
                "addresses": [{"formatted": "20 rue de Lyon"}],  # Different address
                "_registry_id": "contact_ghi789",
            },
        ]

    @pytest.fixture
    def groups_structured_data(self, sample_contacts_payload):
        """
        Simulated GROUP operation output (as it appears in structured_data after fix).

        The fix ensures members contain payload dicts (with resource_name at top level),
        not RegistryItem objects.
        """
        return {
            "groups": [
                {
                    "key": "10 rue de Paris",
                    "members": [
                        sample_contacts_payload[0],  # Jean
                        sample_contacts_payload[1],  # Marie
                    ],
                    "count": 2,
                },
                {
                    "key": "20 rue de Lyon",
                    "members": [
                        sample_contacts_payload[2],  # Pierre
                    ],
                    "count": 1,
                },
            ],
            "result": "Grouped items by payload.addresses[0].formatted: 2 groups",
        }

    def test_jinja_extracts_resource_names_from_groups(
        self, jinja_evaluator, groups_structured_data
    ):
        """
        Test that Jinja template correctly extracts resource_names from groups.

        This is the critical pattern: iterate over groups where count > 1,
        extract resource_name from each member.
        """
        # Arrange: Template as used by planner for "contacts qui habitent ensemble"
        template = (
            "{% for g in steps.group_by_address.groups %}"
            "{% if g.count > 1 %}"
            "{% for item in g.members %}"
            "{{ item.resource_name }}"
            "{% if not loop.last %},{% endif %}"
            "{% endfor %}"
            "{% endif %}"
            "{% endfor %}"
        )

        context = {"steps": {"group_by_address": groups_structured_data}}

        # Act
        result = jinja_evaluator.evaluate(
            template_str=template,
            context=context,
            step_id="get_details",
            parameter_name="resource_names",
            is_required=False,
        )

        # Assert: Should get Jean and Marie (same address), not Pierre (alone)
        assert result is not None
        assert "people/c123" in result  # Jean
        assert "people/c456" in result  # Marie
        assert "people/c789" not in result  # Pierre (count=1, not included)

        # Verify format: comma-separated
        resource_names = [r.strip() for r in result.split(",") if r.strip()]
        assert len(resource_names) == 2

    def test_jinja_handles_no_groups_with_count_gt_1(
        self, jinja_evaluator, sample_contacts_payload
    ):
        """
        Test that Jinja returns empty string when no groups have count > 1.

        This is expected behavior - if everyone lives alone, there are no
        "contacts qui habitent ensemble".
        """
        # Arrange: Each contact has unique address (all count=1)
        groups_data = {
            "groups": [
                {"key": "addr1", "members": [sample_contacts_payload[0]], "count": 1},
                {"key": "addr2", "members": [sample_contacts_payload[1]], "count": 1},
                {"key": "addr3", "members": [sample_contacts_payload[2]], "count": 1},
            ],
            "result": "Grouped: 3 groups",
        }

        template = (
            "{% for g in steps.group.groups %}"
            "{% if g.count > 1 %}"
            "{% for item in g.members %}{{ item.resource_name }}{% if not loop.last %},{% endif %}{% endfor %}"
            "{% endif %}"
            "{% endfor %}"
        )

        context = {"steps": {"group": groups_data}}

        # Act
        result = jinja_evaluator.evaluate(
            template_str=template,
            context=context,
            step_id="get_details",
            parameter_name="resource_names",
            is_required=False,
        )

        # Assert: Empty string (no groups with count > 1)
        assert result is not None
        assert result.strip() == ""

    def test_jinja_handles_empty_groups(self, jinja_evaluator):
        """Test that Jinja handles empty groups gracefully."""
        groups_data = {"groups": [], "result": "Grouped: 0 groups"}

        template = (
            "{% for g in steps.group.groups %}"
            "{% for item in g.members %}{{ item.resource_name }}{% endfor %}"
            "{% endfor %}"
        )

        context = {"steps": {"group": groups_data}}

        # Act
        result = jinja_evaluator.evaluate(
            template_str=template,
            context=context,
            step_id="get_details",
            parameter_name="resource_names",
        )

        # Assert: Empty string, no error
        assert result is not None
        assert result.strip() == ""

    def test_jinja_handles_missing_step(self, jinja_evaluator):
        """Test that Jinja handles missing step gracefully.

        With LoggingUndefined, missing steps return empty string (more resilient)
        instead of raising UndefinedError. The warning is logged for debugging.
        """
        template = "{% for g in steps.nonexistent.groups %}{{ g.key }}{% endfor %}"

        context = {"steps": {}}  # No steps

        # Act
        result = jinja_evaluator.evaluate(
            template_str=template,
            context=context,
            step_id="get_details",
            parameter_name="resource_names",
        )

        # Assert: Returns empty string (LoggingUndefined handles gracefully)
        # Warning is logged for debugging (jinja_undefined_access event)
        assert result is not None
        assert result.strip() == ""


class TestGroupPayloadExtraction:
    """
    Test that parallel_executor correctly extracts payloads from RegistryItem objects.

    This validates the fix: group.members should contain payload dicts
    (with resource_name at top level), not RegistryItem objects.
    """

    def test_registry_item_structure(self):
        """Verify RegistryItem has expected structure."""
        item = RegistryItem(
            id="contact_abc123",
            type=RegistryItemType.CONTACT,
            payload={
                "resource_name": "people/c123",
                "names": "Jean dupond",
            },
            meta=RegistryItemMeta(source="google_contacts", domain="contacts"),
        )

        # resource_name is inside payload, not at top level
        assert not hasattr(item, "resource_name")
        assert "resource_name" in item.payload
        assert item.payload["resource_name"] == "people/c123"

    def test_payload_extraction_for_jinja(self):
        """
        Simulate the payload extraction that parallel_executor should do.

        This is what the fix in parallel_executor does for GROUP results.
        """
        # Original RegistryItem objects (as stored in registry)
        items = [
            RegistryItem(
                id="contact_abc",
                type=RegistryItemType.CONTACT,
                payload={"resource_name": "people/c123", "names": "Jean"},
                meta=RegistryItemMeta(source="google_contacts"),
            ),
            RegistryItem(
                id="contact_def",
                type=RegistryItemType.CONTACT,
                payload={"resource_name": "people/c456", "names": "Marie"},
                meta=RegistryItemMeta(source="google_contacts"),
            ),
        ]

        # Simulated extraction (as done by parallel_executor fix)
        transformed_members = []
        for item in items:
            if hasattr(item, "payload"):
                payload = item.payload
                item_id = item.id
            elif isinstance(item, dict) and "payload" in item:
                payload = item["payload"]
                item_id = item.get("id", "")
            else:
                payload = item
                item_id = ""

            if payload:
                enriched_payload = {**payload, "_registry_id": item_id}
                transformed_members.append(enriched_payload)

        # After extraction: resource_name is at top level
        assert len(transformed_members) == 2
        assert transformed_members[0]["resource_name"] == "people/c123"
        assert transformed_members[0]["_registry_id"] == "contact_abc"
        assert transformed_members[1]["resource_name"] == "people/c456"


class TestEscapedJinjaSyntax:
    """Test handling of escaped Jinja syntax from planner output."""

    @pytest.fixture
    def jinja_evaluator(self):
        return JinjaTemplateEvaluator()

    def test_double_brace_unescaping(self, jinja_evaluator):
        """Test that {{{{ }}}} is correctly unescaped to {{ }}."""
        # This is how planner generates templates (escaped to avoid premature eval)
        template = "{{{{ steps.search.contacts[0].resource_name }}}}"

        context = {"steps": {"search": {"contacts": [{"resource_name": "people/c123"}]}}}

        result = jinja_evaluator.evaluate(
            template_str=template,
            context=context,
            step_id="test",
        )

        assert result == "people/c123"

    def test_double_percent_unescaping(self, jinja_evaluator):
        """Test that {{% %}} is correctly unescaped to {% %}."""
        template = "{{% if steps.search.contacts | length > 0 %}}found{{% endif %}}"

        context = {"steps": {"search": {"contacts": [{"name": "Jean"}]}}}

        result = jinja_evaluator.evaluate(
            template_str=template,
            context=context,
            step_id="test",
        )

        assert result == "found"

    def test_complex_escaped_template(self, jinja_evaluator):
        """Test complex template with multiple escaped constructs."""
        # Real-world example from planner for GROUP + details
        template = (
            "{{% for g in steps.group.groups %}}"
            "{{% if g.count > 1 %}}"
            "{{% for item in g.members %}}"
            "{{{{ item.resource_name }}}}"
            "{{% if not loop.last %}},{{% endif %}}"
            "{{% endfor %}}"
            "{{% endif %}}"
            "{{% endfor %}}"
        )

        context = {
            "steps": {
                "group": {
                    "groups": [
                        {
                            "key": "addr1",
                            "members": [
                                {"resource_name": "people/c123"},
                                {"resource_name": "people/c456"},
                            ],
                            "count": 2,
                        }
                    ]
                }
            }
        }

        result = jinja_evaluator.evaluate(
            template_str=template,
            context=context,
            step_id="test",
        )

        assert "people/c123" in result
        assert "people/c456" in result
