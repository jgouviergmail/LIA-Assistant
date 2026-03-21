"""
Unit tests for connector mutual exclusivity model helpers.

Tests get_conflicting_connector_type(), get_conflicting_connector_types(),
get_functional_category(), ConnectorType.is_apple/is_google/is_microsoft properties,
and CONNECTOR_FUNCTIONAL_CATEGORIES completeness (3 providers + tasks category).
"""

import pytest

from src.domains.connectors.models import (
    CONNECTOR_FUNCTIONAL_CATEGORIES,
    ConnectorType,
    get_conflicting_connector_type,
    get_conflicting_connector_types,
    get_functional_category,
)

# ---------------------------------------------------------------------------
# get_conflicting_connector_type()
# ---------------------------------------------------------------------------


class TestGetConflictingConnectorType:
    """Tests for get_conflicting_connector_type() (singular, deprecated wrapper)."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "source",
        [
            ConnectorType.GOOGLE_GMAIL,
            ConnectorType.APPLE_EMAIL,
            ConnectorType.MICROSOFT_OUTLOOK,
            ConnectorType.GOOGLE_CALENDAR,
            ConnectorType.APPLE_CALENDAR,
            ConnectorType.MICROSOFT_CALENDAR,
            ConnectorType.GOOGLE_CONTACTS,
            ConnectorType.APPLE_CONTACTS,
            ConnectorType.MICROSOFT_CONTACTS,
            ConnectorType.GOOGLE_TASKS,
            ConnectorType.MICROSOFT_TASKS,
        ],
    )
    def test_categorized_returns_one_conflict(self, source: ConnectorType):
        """Categorized connectors return one conflict (deprecated singular API)."""
        result = get_conflicting_connector_type(source)
        assert result is not None
        assert result != source

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.GOOGLE_DRIVE,
            ConnectorType.OPENWEATHERMAP,
            ConnectorType.WIKIPEDIA,
            ConnectorType.PERPLEXITY,
            ConnectorType.BRAVE_SEARCH,
            ConnectorType.GOOGLE_ROUTES,
            ConnectorType.GOOGLE_PLACES,
            ConnectorType.SLACK,
            ConnectorType.NOTION,
            ConnectorType.GITHUB,
        ],
    )
    def test_uncategorized_returns_none(self, connector_type: ConnectorType):
        """Connector types not in a mutual-exclusivity category return None."""
        assert get_conflicting_connector_type(connector_type) is None


# ---------------------------------------------------------------------------
# get_conflicting_connector_types() (plural — primary API)
# ---------------------------------------------------------------------------


class TestGetConflictingConnectorTypes:
    """Tests for get_conflicting_connector_types() (plural, primary API)."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("source", "expected_conflicts"),
        [
            # Email: 3-way
            (
                ConnectorType.GOOGLE_GMAIL,
                frozenset({ConnectorType.APPLE_EMAIL, ConnectorType.MICROSOFT_OUTLOOK}),
            ),
            (
                ConnectorType.APPLE_EMAIL,
                frozenset({ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK}),
            ),
            (
                ConnectorType.MICROSOFT_OUTLOOK,
                frozenset({ConnectorType.GOOGLE_GMAIL, ConnectorType.APPLE_EMAIL}),
            ),
            # Calendar: 3-way
            (
                ConnectorType.GOOGLE_CALENDAR,
                frozenset({ConnectorType.APPLE_CALENDAR, ConnectorType.MICROSOFT_CALENDAR}),
            ),
            (
                ConnectorType.MICROSOFT_CALENDAR,
                frozenset({ConnectorType.GOOGLE_CALENDAR, ConnectorType.APPLE_CALENDAR}),
            ),
            # Contacts: 3-way
            (
                ConnectorType.GOOGLE_CONTACTS,
                frozenset({ConnectorType.APPLE_CONTACTS, ConnectorType.MICROSOFT_CONTACTS}),
            ),
            (
                ConnectorType.MICROSOFT_CONTACTS,
                frozenset({ConnectorType.GOOGLE_CONTACTS, ConnectorType.APPLE_CONTACTS}),
            ),
            # Tasks: 2-way (no Apple tasks)
            (
                ConnectorType.GOOGLE_TASKS,
                frozenset({ConnectorType.MICROSOFT_TASKS}),
            ),
            (
                ConnectorType.MICROSOFT_TASKS,
                frozenset({ConnectorType.GOOGLE_TASKS}),
            ),
        ],
    )
    def test_returns_all_conflicts(
        self, source: ConnectorType, expected_conflicts: frozenset[ConnectorType]
    ):
        """Each categorized connector returns ALL its conflicts as a frozenset."""
        assert get_conflicting_connector_types(source) == expected_conflicts

    @pytest.mark.unit
    def test_uncategorized_returns_empty_frozenset(self):
        """Uncategorized connectors return an empty frozenset."""
        result = get_conflicting_connector_types(ConnectorType.GOOGLE_DRIVE)
        assert result == frozenset()
        assert isinstance(result, frozenset)


# ---------------------------------------------------------------------------
# get_functional_category()
# ---------------------------------------------------------------------------


class TestGetFunctionalCategory:
    """Tests for get_functional_category()."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("connector_type", "expected_category"),
        [
            (ConnectorType.GOOGLE_GMAIL, "email"),
            (ConnectorType.APPLE_EMAIL, "email"),
            (ConnectorType.MICROSOFT_OUTLOOK, "email"),
            (ConnectorType.GOOGLE_CALENDAR, "calendar"),
            (ConnectorType.APPLE_CALENDAR, "calendar"),
            (ConnectorType.MICROSOFT_CALENDAR, "calendar"),
            (ConnectorType.GOOGLE_CONTACTS, "contacts"),
            (ConnectorType.APPLE_CONTACTS, "contacts"),
            (ConnectorType.MICROSOFT_CONTACTS, "contacts"),
            (ConnectorType.GOOGLE_TASKS, "tasks"),
            (ConnectorType.MICROSOFT_TASKS, "tasks"),
        ],
    )
    def test_returns_correct_category(self, connector_type: ConnectorType, expected_category: str):
        """Each categorized connector returns its functional category name."""
        assert get_functional_category(connector_type) == expected_category

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.GOOGLE_DRIVE,
            ConnectorType.OPENWEATHERMAP,
            ConnectorType.WIKIPEDIA,
        ],
    )
    def test_uncategorized_returns_none(self, connector_type: ConnectorType):
        """Connector types not in any category return None."""
        assert get_functional_category(connector_type) is None


# ---------------------------------------------------------------------------
# ConnectorType.is_apple property
# ---------------------------------------------------------------------------


class TestIsAppleProperty:
    """Tests for the ConnectorType.is_apple property."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.APPLE_EMAIL,
            ConnectorType.APPLE_CALENDAR,
            ConnectorType.APPLE_CONTACTS,
        ],
    )
    def test_apple_types_return_true(self, connector_type: ConnectorType):
        """Apple connector types return is_apple=True."""
        assert connector_type.is_apple is True

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.GOOGLE_GMAIL,
            ConnectorType.GOOGLE_CALENDAR,
            ConnectorType.GOOGLE_CONTACTS,
            ConnectorType.GOOGLE_DRIVE,
            ConnectorType.GOOGLE_TASKS,
            ConnectorType.MICROSOFT_OUTLOOK,
            ConnectorType.OPENWEATHERMAP,
            ConnectorType.SLACK,
        ],
    )
    def test_non_apple_types_return_false(self, connector_type: ConnectorType):
        """Non-Apple connector types return is_apple=False."""
        assert connector_type.is_apple is False


# ---------------------------------------------------------------------------
# ConnectorType.is_google property
# ---------------------------------------------------------------------------


class TestIsGoogleProperty:
    """Tests for the ConnectorType.is_google property."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.GOOGLE_GMAIL,
            ConnectorType.GOOGLE_CALENDAR,
            ConnectorType.GOOGLE_CONTACTS,
            ConnectorType.GOOGLE_DRIVE,
            ConnectorType.GOOGLE_TASKS,
        ],
    )
    def test_google_types_return_true(self, connector_type: ConnectorType):
        """Google connector types return is_google=True."""
        assert connector_type.is_google is True

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.APPLE_EMAIL,
            ConnectorType.MICROSOFT_OUTLOOK,
            ConnectorType.OPENWEATHERMAP,
        ],
    )
    def test_non_google_types_return_false(self, connector_type: ConnectorType):
        """Non-Google connector types return is_google=False."""
        assert connector_type.is_google is False


# ---------------------------------------------------------------------------
# ConnectorType.is_microsoft property
# ---------------------------------------------------------------------------


class TestIsMicrosoftProperty:
    """Tests for the ConnectorType.is_microsoft property."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.MICROSOFT_OUTLOOK,
            ConnectorType.MICROSOFT_CALENDAR,
            ConnectorType.MICROSOFT_CONTACTS,
            ConnectorType.MICROSOFT_TASKS,
        ],
    )
    def test_microsoft_types_return_true(self, connector_type: ConnectorType):
        """Microsoft connector types return is_microsoft=True."""
        assert connector_type.is_microsoft is True

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.GOOGLE_GMAIL,
            ConnectorType.APPLE_EMAIL,
            ConnectorType.OPENWEATHERMAP,
        ],
    )
    def test_non_microsoft_types_return_false(self, connector_type: ConnectorType):
        """Non-Microsoft connector types return is_microsoft=False."""
        assert connector_type.is_microsoft is False


# ---------------------------------------------------------------------------
# CONNECTOR_FUNCTIONAL_CATEGORIES completeness
# ---------------------------------------------------------------------------


class TestFunctionalCategoriesCompleteness:
    """Tests for CONNECTOR_FUNCTIONAL_CATEGORIES structure and completeness."""

    @pytest.mark.unit
    def test_expected_categories_exist(self):
        """All expected categories are present."""
        assert set(CONNECTOR_FUNCTIONAL_CATEGORIES.keys()) == {
            "email",
            "calendar",
            "contacts",
            "tasks",
            "smart_home",
        }

    @pytest.mark.unit
    def test_three_provider_categories_have_three_types(self):
        """Email, calendar, contacts categories have 3 providers (Google, Apple, Microsoft)."""
        for category in ("email", "calendar", "contacts"):
            types = CONNECTOR_FUNCTIONAL_CATEGORIES[category]
            assert (
                len(types) == 3
            ), f"Category '{category}' should have 3 providers, got {len(types)}"
            names = [ct.value for ct in types]
            assert any("google" in n for n in names), f"Category '{category}' missing Google"
            assert any("apple" in n for n in names), f"Category '{category}' missing Apple"
            assert any("microsoft" in n for n in names), f"Category '{category}' missing Microsoft"

    @pytest.mark.unit
    def test_tasks_category_has_two_providers(self):
        """Tasks category has 2 providers (Google Tasks + Microsoft To Do, no Apple)."""
        types = CONNECTOR_FUNCTIONAL_CATEGORIES["tasks"]
        assert len(types) == 2, f"Tasks category should have 2 providers, got {len(types)}"
        names = [ct.value for ct in types]
        assert any("google" in n for n in names), "Tasks category missing Google"
        assert any("microsoft" in n for n in names), "Tasks category missing Microsoft"
        assert not any("apple" in n for n in names), "Tasks category should not have Apple"

    @pytest.mark.unit
    def test_categories_use_frozensets(self):
        """Category values are frozensets (immutable)."""
        for category, types in CONNECTOR_FUNCTIONAL_CATEGORIES.items():
            assert isinstance(types, frozenset), f"Category '{category}' should be a frozenset"

    @pytest.mark.unit
    def test_no_connector_in_multiple_categories(self):
        """A connector type should not appear in more than one category."""
        seen: dict[ConnectorType, str] = {}
        for category, types in CONNECTOR_FUNCTIONAL_CATEGORIES.items():
            for ct in types:
                assert ct not in seen, f"{ct.value} appears in both '{seen[ct]}' and '{category}'"
                seen[ct] = category

    @pytest.mark.unit
    def test_conflict_is_symmetric(self):
        """If A conflicts with B, then B must conflict with A."""
        for category, types in CONNECTOR_FUNCTIONAL_CATEGORIES.items():
            for ct in types:
                conflicts = get_conflicting_connector_types(ct)
                assert len(conflicts) > 0, f"{ct.value} in '{category}' has no conflicts"
                for conflict in conflicts:
                    reverse_conflicts = get_conflicting_connector_types(conflict)
                    assert ct in reverse_conflicts, (
                        f"Conflict not symmetric: {ct.value} conflicts with {conflict.value} "
                        f"but {conflict.value} does not conflict with {ct.value}"
                    )
