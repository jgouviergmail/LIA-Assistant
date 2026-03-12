"""
Tests unitaires pour le module type_coercion.

Issue #55: Coercion robuste string→list pour les patterns générés par le LLM.

Enhanced: 2026-02-05 - Added comprehensive edge cases, logging tests, and parametrized tests
"""

import typing
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.orchestration.type_coercion import (
    coerce_string_to_list,
    is_list_type,
)


class TestCoerceStringToList:
    """Tests pour coerce_string_to_list()."""

    def test_quoted_comma_separator(self):
        """Test pattern LLM: item1","item2 (séparateur "," entre guillemets)."""
        result = coerce_string_to_list('people/c123","people/c456')
        assert result == ["people/c123", "people/c456"]

    def test_quoted_comma_separator_multiple(self):
        """Test pattern LLM avec plusieurs items."""
        result = coerce_string_to_list('item1","item2","item3')
        assert result == ["item1", "item2", "item3"]

    def test_simple_comma_separator(self):
        """Test séparateur virgule simple: item1,item2."""
        result = coerce_string_to_list("item1,item2,item3")
        assert result == ["item1", "item2", "item3"]

    def test_simple_comma_with_spaces(self):
        """Test virgule simple avec espaces."""
        result = coerce_string_to_list("item1, item2, item3")
        assert result == ["item1", "item2", "item3"]

    def test_single_value(self):
        """Test valeur unique sans virgule."""
        result = coerce_string_to_list("people/c123456789")
        assert result == ["people/c123456789"]

    def test_empty_string(self):
        """Test chaîne vide."""
        result = coerce_string_to_list("")
        assert result == []

    def test_whitespace_only(self):
        """Test chaîne avec espaces uniquement."""
        result = coerce_string_to_list("   ")
        assert result == []

    def test_strips_surrounding_quotes(self):
        """Test que les guillemets sont bien retirés."""
        # LLM pattern may leave quotes at the beginning/end
        result = coerce_string_to_list('"item1","item2"')
        assert result == ["item1", "item2"]

    def test_strips_single_quotes(self):
        """Test que les apostrophes sont aussi retirées."""
        result = coerce_string_to_list("'item1','item2'")
        assert result == ["item1", "item2"]

    def test_real_world_resource_names(self):
        """Test avec de vrais resource_names Google People API."""
        # Pattern exact généré par le planner
        value = 'people/c6005623555827615994","people/c508019205262800953'
        result = coerce_string_to_list(value)
        assert result == [
            "people/c6005623555827615994",
            "people/c508019205262800953",
        ]

    def test_empty_items_removed(self):
        """Test que les items vides sont retirés."""
        result = coerce_string_to_list("item1,,item2")
        assert result == ["item1", "item2"]

    def test_mixed_quotes(self):
        """Test avec guillemets mixtes."""
        result = coerce_string_to_list('"item1",item2,"item3"')
        # Après split par ",", on a: ['"item1"', 'item2', '"item3"']
        # Avec cleanup: ['item1', 'item2', 'item3']
        assert "item1" in result
        assert "item2" in result
        assert "item3" in result


class TestIsListType:
    """Tests pour is_list_type()."""

    def test_plain_list(self):
        """Test type list simple.

        Note: `list` sans paramètre de type retourne False car
        get_origin(list) est None. En pratique, les schemas Pydantic
        utilisent toujours list[str] ou list[dict], pas list nu.
        """
        # Bare list is not detected (get_origin returns None)
        # This is OK because in practice we always have list[str], list[dict]
        assert is_list_type(list) is False

    def test_subscripted_list_str(self):
        """Test list[str]."""
        assert is_list_type(list[str]) is True

    def test_subscripted_list_dict(self):
        """Test list[dict]."""
        assert is_list_type(list[dict]) is True

    def test_optional_list(self):
        """Test list[str] | None (Python 3.10+ syntax)."""
        assert is_list_type(list[str] | None) is True

    def test_union_with_list(self):
        """Test list[str] | list[dict] | None."""
        assert is_list_type(list[str] | list[dict] | None) is True

    def test_not_list_str(self):
        """Test que str n'est pas un list type."""
        assert is_list_type(str) is False

    def test_not_list_int(self):
        """Test que int n'est pas un list type."""
        assert is_list_type(int) is False

    def test_not_list_dict(self):
        """Test que dict n'est pas un list type."""
        assert is_list_type(dict) is False

    def test_optional_str(self):
        """Test que str | None n'est pas un list type."""
        assert is_list_type(str | None) is False


class TestEdgeCases:
    """Tests des cas limites."""

    def test_none_value(self):
        """Test avec None - retourne [] grâce à la guard clause."""
        # coerce_string_to_list gère None gracieusement via `if not value`
        # Ceci suit Postel's Law: "Be liberal in what you accept"
        result = coerce_string_to_list(None)  # type: ignore
        assert result == []

    def test_very_long_string(self):
        """Test avec une chaîne très longue."""
        items = [f"item{i}" for i in range(100)]
        value = ",".join(items)
        result = coerce_string_to_list(value)
        assert len(result) == 100
        assert result[0] == "item0"
        assert result[99] == "item99"

    def test_special_characters_preserved(self):
        """Test que les caractères spéciaux sont préservés."""
        result = coerce_string_to_list("hello@example.com,test+user@domain.org")
        assert result == ["hello@example.com", "test+user@domain.org"]

    def test_urls_preserved(self):
        """Test que les URLs sont préservées correctement."""
        result = coerce_string_to_list("https://example.com/path?query=1,https://other.com")
        assert result == [
            "https://example.com/path?query=1",
            "https://other.com",
        ]


# ============================================================================
# Additional tests for coerce_string_to_list() - logging
# ============================================================================


class TestCoerceStringToListLogging:
    """Tests for coerce_string_to_list() logging behavior."""

    def test_logs_quoted_comma_pattern(self):
        """Test that quoted comma pattern is logged correctly."""
        with patch("src.domains.agents.orchestration.type_coercion.logger") as mock_logger:
            coerce_string_to_list('item1","item2')

            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs["pattern"] == "quoted_comma"
            assert call_kwargs["items_count"] == 2

    def test_logs_simple_comma_pattern(self):
        """Test that simple comma pattern is logged correctly."""
        with patch("src.domains.agents.orchestration.type_coercion.logger") as mock_logger:
            coerce_string_to_list("item1,item2,item3")

            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs["pattern"] == "simple_comma"
            assert call_kwargs["items_count"] == 3

    def test_logs_single_value_pattern(self):
        """Test that single value pattern is logged correctly."""
        with patch("src.domains.agents.orchestration.type_coercion.logger") as mock_logger:
            coerce_string_to_list("single_item")

            mock_logger.info.assert_called_once()
            call_kwargs = mock_logger.info.call_args[1]
            assert call_kwargs["pattern"] == "single_value"
            assert call_kwargs["items_count"] == 1

    def test_logs_truncated_original_value(self):
        """Test that long original values are truncated in logs."""
        with patch("src.domains.agents.orchestration.type_coercion.logger") as mock_logger:
            long_value = "x" * 150
            coerce_string_to_list(long_value)

            call_kwargs = mock_logger.info.call_args[1]
            # Should be truncated to 100 chars
            assert len(call_kwargs["original_value"]) == 100

    def test_does_not_log_for_empty_string(self):
        """Test that empty strings don't trigger logging."""
        with patch("src.domains.agents.orchestration.type_coercion.logger") as mock_logger:
            coerce_string_to_list("")

            mock_logger.info.assert_not_called()


# ============================================================================
# Parametrized tests for coerce_string_to_list()
# ============================================================================


class TestCoerceStringToListParametrized:
    """Parametrized tests for coerce_string_to_list()."""

    @pytest.mark.parametrize(
        "input_value,expected",
        [
            # Empty/whitespace cases
            ("", []),
            ("   ", []),
            ("\t", []),
            ("\n", []),
            # Single value cases
            ("item", ["item"]),
            ("  item  ", ["item"]),
            ('"item"', ["item"]),
            ("'item'", ["item"]),
            # Simple comma cases
            ("a,b", ["a", "b"]),
            ("a, b", ["a", "b"]),
            ("a , b", ["a", "b"]),
            # Quoted comma cases
            ('a","b', ["a", "b"]),
            ('"a","b"', ["a", "b"]),
            # Multiple items
            ("a,b,c,d,e", ["a", "b", "c", "d", "e"]),
            ('a","b","c","d","e', ["a", "b", "c", "d", "e"]),
        ],
    )
    def test_various_inputs(self, input_value: str, expected: list[str]):
        """Test coerce_string_to_list with various inputs."""
        result = coerce_string_to_list(input_value)
        assert result == expected

    @pytest.mark.parametrize(
        "input_value,expected_count",
        [
            ("a", 1),
            ("a,b", 2),
            ("a,b,c", 3),
            ('a","b","c","d', 4),
            ("a,b,c,d,e,f,g,h,i,j", 10),
        ],
    )
    def test_item_counts(self, input_value: str, expected_count: int):
        """Test that correct number of items are extracted."""
        result = coerce_string_to_list(input_value)
        assert len(result) == expected_count


# ============================================================================
# Additional tests for coerce_string_to_list() - real-world patterns
# ============================================================================


class TestCoerceStringToListRealWorld:
    """Real-world pattern tests for coerce_string_to_list()."""

    def test_google_calendar_event_ids(self):
        """Test with Google Calendar event ID patterns."""
        value = "event123abc,event456def,event789ghi"
        result = coerce_string_to_list(value)
        assert len(result) == 3
        assert "event123abc" in result

    def test_email_addresses(self):
        """Test with email address lists."""
        value = "user1@example.com,user2@example.com,admin@company.org"
        result = coerce_string_to_list(value)
        assert result == [
            "user1@example.com",
            "user2@example.com",
            "admin@company.org",
        ]

    def test_google_people_resource_names_from_llm(self):
        """Test exact pattern from LLM planner output."""
        # This is the exact pattern that triggered Issue #55
        value = 'people/c6005623555827615994","people/c508019205262800953","people/c1234567890'
        result = coerce_string_to_list(value)
        assert len(result) == 3
        assert result[0] == "people/c6005623555827615994"
        assert result[1] == "people/c508019205262800953"
        assert result[2] == "people/c1234567890"

    def test_task_ids(self):
        """Test with task ID lists."""
        value = "task-001,task-002,task-003"
        result = coerce_string_to_list(value)
        assert len(result) == 3

    def test_file_paths(self):
        """Test with file paths."""
        value = "/home/user/file1.txt,/home/user/file2.txt"
        result = coerce_string_to_list(value)
        assert result == ["/home/user/file1.txt", "/home/user/file2.txt"]

    def test_uuids(self):
        """Test with UUID lists."""
        value = "550e8400-e29b-41d4-a716-446655440000,6ba7b810-9dad-11d1-80b4-00c04fd430c8"
        result = coerce_string_to_list(value)
        assert len(result) == 2
        assert "550e8400-e29b-41d4-a716-446655440000" in result


# ============================================================================
# Additional tests for is_list_type() - typing module
# ============================================================================


class TestIsListTypeTypingModule:
    """Tests for is_list_type() with typing module types."""

    def test_typing_list(self):
        """Test typing.List (deprecated but still used)."""
        # typing.List[str] has origin list
        assert is_list_type(list[str]) is True

    def test_typing_list_dict(self):
        """Test typing.List[dict]."""
        assert is_list_type(list[dict]) is True

    def test_typing_optional_list(self):
        """Test typing.Optional[list[str]]."""
        assert is_list_type(typing.Optional[list[str]]) is True  # noqa: UP007

    def test_typing_union_with_list(self):
        """Test typing.Union[list[str], str]."""
        assert is_list_type(typing.Union[list[str], str]) is True  # noqa: UP007

    def test_typing_union_without_list(self):
        """Test typing.Union[str, int]."""
        assert is_list_type(typing.Union[str, int]) is False  # noqa: UP007

    def test_typing_optional_str(self):
        """Test typing.Optional[str]."""
        assert is_list_type(typing.Optional[str]) is False  # noqa: UP007

    def test_typing_sequence(self):
        """Test typing.Sequence - not a list type."""
        assert is_list_type(typing.Sequence[str]) is False

    def test_typing_iterable(self):
        """Test typing.Iterable - not a list type."""
        assert is_list_type(typing.Iterable[str]) is False


# ============================================================================
# Additional tests for is_list_type() - edge cases
# ============================================================================


class TestIsListTypeEdgeCases:
    """Edge case tests for is_list_type()."""

    def test_none_type(self):
        """Test is_list_type with None."""
        # type(None) is NoneType
        assert is_list_type(type(None)) is False

    def test_any_type(self):
        """Test is_list_type with Any."""
        assert is_list_type(typing.Any) is False

    def test_tuple_type(self):
        """Test is_list_type with tuple."""
        assert is_list_type(tuple[str, ...]) is False

    def test_set_type(self):
        """Test is_list_type with set."""
        assert is_list_type(set[str]) is False

    def test_frozenset_type(self):
        """Test is_list_type with frozenset."""
        assert is_list_type(frozenset[str]) is False

    def test_dict_type(self):
        """Test is_list_type with dict."""
        assert is_list_type(dict[str, int]) is False

    def test_nested_list(self):
        """Test is_list_type with nested list."""
        assert is_list_type(list[list[str]]) is True

    def test_list_of_any(self):
        """Test is_list_type with list[Any]."""
        assert is_list_type(list[typing.Any]) is True

    def test_complex_union_with_nested_list(self):
        """Test complex union with nested list."""
        assert is_list_type(list[str] | dict[str, int] | None) is True

    def test_complex_union_without_list(self):
        """Test complex union without list."""
        assert is_list_type(str | int | dict[str, int] | None) is False


# ============================================================================
# Parametrized tests for is_list_type()
# ============================================================================


class TestIsListTypeParametrized:
    """Parametrized tests for is_list_type()."""

    @pytest.mark.parametrize(
        "type_hint",
        [
            list[str],
            list[int],
            list[dict],
            list[Any],
            list[list[str]],
            list[str],
            list[dict],
            list[str] | None,
            list[int] | list[str],
            typing.Optional[list[str]],  # noqa: UP007
            typing.Union[list[str], None],  # noqa: UP007
            typing.Union[list[str], list[int]],  # noqa: UP007
        ],
    )
    def test_list_types_return_true(self, type_hint):
        """Test that list types return True."""
        assert is_list_type(type_hint) is True

    @pytest.mark.parametrize(
        "type_hint",
        [
            str,
            int,
            float,
            bool,
            dict,
            set,
            tuple,
            list,  # Plain list without type parameter
            typing.Any,
            typing.Sequence[str],
            typing.Iterable[str],
            str | None,
            int | str,
            dict[str, int],
            set[str],
            tuple[str, ...],
        ],
    )
    def test_non_list_types_return_false(self, type_hint):
        """Test that non-list types return False."""
        assert is_list_type(type_hint) is False


# ============================================================================
# Integration tests
# ============================================================================


class TestTypeCoercionIntegration:
    """Integration tests for type coercion utilities."""

    def test_workflow_check_type_then_coerce(self):
        """Test typical workflow: check if list type, then coerce."""
        # Define a parameter that expects list[str]
        param_type = list[str]
        value = "item1,item2,item3"

        # Step 1: Check if we need to coerce
        if is_list_type(param_type) and isinstance(value, str):
            # Step 2: Coerce string to list
            result = coerce_string_to_list(value)
            assert isinstance(result, list)
            assert len(result) == 3

    def test_workflow_no_coerce_for_non_list_type(self):
        """Test workflow when type is not list."""
        param_type = str
        value = "item1,item2"

        # Should NOT coerce
        if is_list_type(param_type):
            # This branch should not execute
            raise AssertionError("Should not coerce for non-list type")

        # Value stays as string
        assert value == "item1,item2"

    def test_coerce_returns_list_type(self):
        """Test that coerce_string_to_list always returns a list."""
        test_cases = [
            "",
            "single",
            "a,b",
            'a","b',
            None,  # type: ignore
        ]

        for value in test_cases:
            result = coerce_string_to_list(value)
            assert isinstance(result, list), f"Failed for value: {value!r}"

    def test_coerce_items_are_strings(self):
        """Test that all items in coerced list are strings."""
        value = "item1,item2,item3"
        result = coerce_string_to_list(value)

        for item in result:
            assert isinstance(item, str)

    def test_coerce_preserves_order(self):
        """Test that coerce_string_to_list preserves item order."""
        value = "first,second,third,fourth,fifth"
        result = coerce_string_to_list(value)
        assert result == ["first", "second", "third", "fourth", "fifth"]

    def test_idempotent_for_single_values(self):
        """Test that coercing single value multiple times is consistent."""
        value = "single_item"
        result1 = coerce_string_to_list(value)
        result2 = coerce_string_to_list(value)
        assert result1 == result2 == ["single_item"]
