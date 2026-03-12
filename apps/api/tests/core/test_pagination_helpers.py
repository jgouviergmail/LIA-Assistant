"""
Tests for core pagination helper utilities.

Tests all pagination logic including validation, skip calculation, and total pages.
"""

from src.core.pagination_helpers import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MIN_PAGE,
    MIN_PAGE_SIZE,
    PaginationParams,
    PaginationResult,
    calculate_skip,
    calculate_total_pages,
    get_pagination_params,
    validate_pagination,
)


class TestValidatePagination:
    """Tests for validate_pagination function."""

    def test_valid_parameters(self):
        """Should return unchanged values for valid parameters."""
        page, page_size = validate_pagination(2, 50)
        assert page == 2
        assert page_size == 50

    def test_page_below_minimum(self):
        """Should clamp page to minimum value of 1."""
        page, page_size = validate_pagination(0, 50)
        assert page == 1
        assert page_size == 50

        page, page_size = validate_pagination(-5, 50)
        assert page == 1
        assert page_size == 50

    def test_page_size_below_minimum(self):
        """Should set to DEFAULT_PAGE_SIZE when page_size is below minimum."""
        page, page_size = validate_pagination(1, 0)
        assert page == 1
        assert page_size == DEFAULT_PAGE_SIZE

        page, page_size = validate_pagination(1, -10)
        assert page == 1
        assert page_size == DEFAULT_PAGE_SIZE

    def test_page_size_above_maximum(self):
        """Should clamp page_size to MAX_PAGE_SIZE."""
        page, page_size = validate_pagination(1, 200)
        assert page == 1
        assert page_size == MAX_PAGE_SIZE

        page, page_size = validate_pagination(1, 999)
        assert page == 1
        assert page_size == MAX_PAGE_SIZE

    def test_both_parameters_invalid(self):
        """Should correct both parameters when both are invalid."""
        page, page_size = validate_pagination(-5, 200)
        assert page == 1
        assert page_size == MAX_PAGE_SIZE

    def test_edge_case_boundaries(self):
        """Should handle exact boundary values correctly."""
        # Test MIN_PAGE boundary
        page, page_size = validate_pagination(1, 50)
        assert page == 1

        # Test MAX_PAGE_SIZE boundary
        page, page_size = validate_pagination(1, MAX_PAGE_SIZE)
        assert page_size == MAX_PAGE_SIZE

        # Test MIN_PAGE_SIZE boundary
        page, page_size = validate_pagination(1, MIN_PAGE_SIZE)
        assert page_size == MIN_PAGE_SIZE


class TestCalculateSkip:
    """Tests for calculate_skip function."""

    def test_first_page(self):
        """First page should skip 0 records."""
        skip = calculate_skip(1, 50)
        assert skip == 0

    def test_second_page(self):
        """Second page should skip page_size records."""
        skip = calculate_skip(2, 50)
        assert skip == 50

    def test_arbitrary_page(self):
        """Should calculate skip correctly for any page."""
        skip = calculate_skip(5, 25)
        assert skip == 100  # (5-1) * 25

    def test_large_page_numbers(self):
        """Should handle large page numbers."""
        skip = calculate_skip(100, 50)
        assert skip == 4950  # (100-1) * 50

    def test_different_page_sizes(self):
        """Should calculate correctly for various page sizes."""
        assert calculate_skip(3, 10) == 20  # (3-1) * 10
        assert calculate_skip(3, 100) == 200  # (3-1) * 100


class TestCalculateTotalPages:
    """Tests for calculate_total_pages function."""

    def test_exact_division(self):
        """Should return exact page count when total divides evenly."""
        total_pages = calculate_total_pages(100, 50)
        assert total_pages == 2

    def test_with_remainder(self):
        """Should round up when there's a remainder."""
        total_pages = calculate_total_pages(101, 50)
        assert total_pages == 3  # Need 3 pages for 101 items

        total_pages = calculate_total_pages(75, 50)
        assert total_pages == 2  # Need 2 pages for 75 items

    def test_zero_total(self):
        """Should return 0 pages when total is 0."""
        total_pages = calculate_total_pages(0, 50)
        assert total_pages == 0

    def test_less_than_page_size(self):
        """Should return 1 page when total is less than page_size."""
        total_pages = calculate_total_pages(25, 50)
        assert total_pages == 1

    def test_exactly_one_item(self):
        """Should return 1 page for a single item."""
        total_pages = calculate_total_pages(1, 50)
        assert total_pages == 1

    def test_large_totals(self):
        """Should handle large totals correctly."""
        total_pages = calculate_total_pages(10000, 50)
        assert total_pages == 200

    def test_various_page_sizes(self):
        """Should calculate correctly for different page sizes."""
        assert calculate_total_pages(150, 50) == 3
        assert calculate_total_pages(150, 100) == 2
        assert calculate_total_pages(150, 25) == 6


class TestGetPaginationParams:
    """Tests for get_pagination_params convenience function."""

    def test_returns_pagination_params(self):
        """Should return PaginationParams dataclass."""
        params = get_pagination_params(2, 50)
        assert isinstance(params, PaginationParams)
        assert params.page == 2
        assert params.page_size == 50
        assert params.skip == 50

    def test_validates_parameters(self):
        """Should validate parameters before returning."""
        params = get_pagination_params(0, 200)
        assert params.page == 1  # Validated
        assert params.page_size == MAX_PAGE_SIZE  # Clamped
        assert params.skip == 0  # Calculated from validated values

    def test_calculates_skip_correctly(self):
        """Should include correctly calculated skip value."""
        params = get_pagination_params(5, 25)
        assert params.skip == 100  # (5-1) * 25

    def test_first_page(self):
        """Should handle first page correctly."""
        params = get_pagination_params(1, 50)
        assert params.page == 1
        assert params.page_size == 50
        assert params.skip == 0


class TestPaginationIntegration:
    """Integration tests simulating real-world pagination scenarios."""

    def test_typical_pagination_flow(self):
        """Test complete pagination workflow."""
        # Setup: 250 total records, 50 per page = 5 pages
        total_records = 250
        page_size = 50

        # Page 1
        page, size = validate_pagination(1, page_size)
        skip = calculate_skip(page, size)
        total_pages = calculate_total_pages(total_records, size)

        assert skip == 0
        assert total_pages == 5

        # Page 3
        page, size = validate_pagination(3, page_size)
        skip = calculate_skip(page, size)

        assert skip == 100
        assert total_pages == 5

        # Last page
        page, size = validate_pagination(5, page_size)
        skip = calculate_skip(page, size)

        assert skip == 200
        assert total_pages == 5

    def test_user_service_scenario(self):
        """Test scenario similar to UserService.get_all_users."""
        # User requests invalid pagination
        requested_page = -1
        requested_page_size = 500

        # Validate
        page, page_size = validate_pagination(requested_page, requested_page_size)

        # Should be corrected
        assert page == 1
        assert page_size == MAX_PAGE_SIZE

        # Calculate for database query
        skip = calculate_skip(page, page_size)
        assert skip == 0

        # Simulate database returning 75 total users
        total = 75
        total_pages = calculate_total_pages(total, page_size)
        assert total_pages == 1  # All fit in one page

    def test_llm_routes_scenario(self):
        """Test scenario similar to LLM Routes pagination."""
        # User requests page 2 with 25 items
        page = 2
        page_size = 25

        # Validate and calculate
        page, page_size = validate_pagination(page, page_size)
        offset = calculate_skip(page, page_size)

        assert offset == 25

        # Simulate database returning 100 total records
        total = 100
        total_pages = calculate_total_pages(total, page_size)
        assert total_pages == 4

    def test_empty_results_scenario(self):
        """Test pagination with no results."""
        page = 1
        page_size = 50

        page, page_size = validate_pagination(page, page_size)
        skip = calculate_skip(page, page_size)

        # Query returns 0 results
        total = 0
        total_pages = calculate_total_pages(total, page_size)

        assert skip == 0
        assert total_pages == 0

    def test_single_item_scenario(self):
        """Test pagination with exactly one result."""
        page = 1
        page_size = 50

        page, page_size = validate_pagination(page, page_size)
        skip = calculate_skip(page, page_size)

        # Query returns 1 result
        total = 1
        total_pages = calculate_total_pages(total, page_size)

        assert skip == 0
        assert total_pages == 1


class TestPaginationConstants:
    """Tests to verify pagination constants are reasonable."""

    def test_constants_are_positive(self):
        """All constants should be positive."""
        assert DEFAULT_PAGE_SIZE > 0
        assert MAX_PAGE_SIZE > 0
        assert MIN_PAGE_SIZE > 0
        assert MIN_PAGE > 0

    def test_constants_relationships(self):
        """Constants should have logical relationships."""
        assert MIN_PAGE_SIZE <= DEFAULT_PAGE_SIZE <= MAX_PAGE_SIZE
        assert MIN_PAGE == 1  # Pages are 1-indexed

    def test_max_page_size_prevents_dos(self):
        """MAX_PAGE_SIZE should be reasonable to prevent DoS attacks."""
        assert MAX_PAGE_SIZE <= 1000  # Should not allow excessive queries


class TestPaginationResult:
    """Tests for PaginationResult dataclass."""

    def test_basic_creation(self):
        """Should create PaginationResult with all fields."""
        result = PaginationResult(
            items=[1, 2, 3],
            total=150,
            page=2,
            page_size=50,
            total_pages=3,
        )

        assert result.items == [1, 2, 3]
        assert result.total == 150
        assert result.page == 2
        assert result.page_size == 50
        assert result.total_pages == 3

    def test_has_next_true(self):
        """Should return True when there are more pages."""
        result = PaginationResult(
            items=[],
            total=150,
            page=2,
            page_size=50,
            total_pages=3,
        )
        assert result.has_next is True

    def test_has_next_false(self):
        """Should return False on last page."""
        result = PaginationResult(
            items=[],
            total=150,
            page=3,
            page_size=50,
            total_pages=3,
        )
        assert result.has_next is False

    def test_has_prev_true(self):
        """Should return True when not on first page."""
        result = PaginationResult(
            items=[],
            total=150,
            page=2,
            page_size=50,
            total_pages=3,
        )
        assert result.has_prev is True

    def test_has_prev_false(self):
        """Should return False on first page."""
        result = PaginationResult(
            items=[],
            total=150,
            page=1,
            page_size=50,
            total_pages=3,
        )
        assert result.has_prev is False

    def test_is_first_page_true(self):
        """Should return True on first page."""
        result = PaginationResult(
            items=[],
            total=150,
            page=1,
            page_size=50,
            total_pages=3,
        )
        assert result.is_first_page is True

    def test_is_first_page_false(self):
        """Should return False when not on first page."""
        result = PaginationResult(
            items=[],
            total=150,
            page=2,
            page_size=50,
            total_pages=3,
        )
        assert result.is_first_page is False

    def test_is_last_page_true(self):
        """Should return True on last page."""
        result = PaginationResult(
            items=[],
            total=150,
            page=3,
            page_size=50,
            total_pages=3,
        )
        assert result.is_last_page is True

    def test_is_last_page_false(self):
        """Should return False when not on last page."""
        result = PaginationResult(
            items=[],
            total=150,
            page=2,
            page_size=50,
            total_pages=3,
        )
        assert result.is_last_page is False

    def test_to_dict(self):
        """Should convert pagination metadata to dictionary."""
        result = PaginationResult(
            items=[1, 2, 3],
            total=150,
            page=2,
            page_size=50,
            total_pages=3,
        )

        metadata = result.to_dict()

        assert metadata == {
            "total": 150,
            "page": 2,
            "page_size": 50,
            "total_pages": 3,
            "has_next": True,
            "has_prev": True,
        }
        # Should not include items
        assert "items" not in metadata

    def test_empty_results(self):
        """Should handle empty results correctly."""
        result = PaginationResult(
            items=[],
            total=0,
            page=1,
            page_size=50,
            total_pages=0,
        )

        assert result.items == []
        assert result.total == 0
        assert result.has_next is False
        assert result.has_prev is False
        assert result.is_first_page is True
        assert result.is_last_page is True

    def test_single_page_results(self):
        """Should handle single page results correctly."""
        result = PaginationResult(
            items=[1, 2, 3],
            total=3,
            page=1,
            page_size=50,
            total_pages=1,
        )

        assert result.has_next is False
        assert result.has_prev is False
        assert result.is_first_page is True
        assert result.is_last_page is True

    def test_type_safety_with_generic(self):
        """Should support generic types for type safety."""
        # String items
        str_result = PaginationResult[str](
            items=["a", "b", "c"],
            total=10,
            page=1,
            page_size=3,
            total_pages=4,
        )
        assert isinstance(str_result.items[0], str)

        # Integer items
        int_result = PaginationResult[int](
            items=[1, 2, 3],
            total=10,
            page=1,
            page_size=3,
            total_pages=4,
        )
        assert isinstance(int_result.items[0], int)
