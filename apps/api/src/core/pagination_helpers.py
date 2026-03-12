"""
Shared pagination utilities.

Provides standardized pagination logic to avoid code duplication across services.
All pagination calculations follow consistent patterns for skip/offset and total_pages.

Usage:
    from src.core.pagination_helpers import (
        validate_pagination,
        calculate_skip,
        calculate_total_pages,
        PaginationResult,
    )

    # Validate and sanitize pagination parameters
    page, page_size = validate_pagination(page, page_size)

    # Calculate database skip/offset
    skip = calculate_skip(page, page_size)

    # Calculate total pages from total count
    total_pages = calculate_total_pages(total_count, page_size)

    # Return paginated results with metadata
    return PaginationResult(
        items=users,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=calculate_total_pages(total_count, page_size)
    )
"""

from dataclasses import dataclass
from typing import TypeVar

from src.core.field_names import FIELD_TOTAL

# Generic type for pagination results
T = TypeVar("T")


# Default pagination limits
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MIN_PAGE_SIZE = 1
MIN_PAGE = 1


@dataclass
class PaginationParams:
    """Validated pagination parameters."""

    page: int
    page_size: int
    skip: int


@dataclass
class PaginationResult[T]:
    """
    Standardized pagination result container.

    Provides consistent structure for paginated API responses across all endpoints.

    Type Parameters:
        T: Type of items in the result list

    Attributes:
        items: List of items for current page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        page_size: Number of items per page
        total_pages: Total number of pages

    Properties:
        has_next: Whether there is a next page
        has_prev: Whether there is a previous page
        is_first_page: Whether this is the first page
        is_last_page: Whether this is the last page

    Example:
        >>> result = PaginationResult(
        ...     items=[user1, user2, user3],
        ...     total=150,
        ...     page=2,
        ...     page_size=50,
        ...     total_pages=3
        ... )
        >>> print(result.has_next)  # True (page 2 of 3)
        >>> print(result.has_prev)  # True (not first page)

    Usage in API responses:
        >>> return {
        ...     "items": [user.to_dict() for user in result.items],
        ...     "pagination": {
        ...         "total": result.total,
        ...         "page": result.page,
        ...         "page_size": result.page_size,
        ...         "total_pages": result.total_pages,
        ...         "has_next": result.has_next,
        ...         "has_prev": result.has_prev,
        ...     }
        ... }
    """

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        """Whether there is a next page."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Whether there is a previous page."""
        return self.page > 1

    @property
    def is_first_page(self) -> bool:
        """Whether this is the first page."""
        return self.page == 1

    @property
    def is_last_page(self) -> bool:
        """Whether this is the last page."""
        return self.page >= self.total_pages

    def to_dict(self) -> dict:
        """
        Convert pagination metadata to dictionary.

        Useful for JSON API responses.

        Returns:
            Dictionary with pagination metadata (excludes items)

        Example:
            >>> result = PaginationResult(items=users, total=100, page=1, page_size=50, total_pages=2)
            >>> print(result.to_dict())
            {
                'total': 100,
                'page': 1,
                'page_size': 50,
                'total_pages': 2,
                'has_next': True,
                'has_prev': False
            }
        """
        return {
            FIELD_TOTAL: self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }


def validate_pagination(page: int, page_size: int) -> tuple[int, int]:
    """
    Validate and sanitize pagination parameters.

    Ensures:
    - page >= 1
    - MIN_PAGE_SIZE <= page_size <= MAX_PAGE_SIZE

    Args:
        page: Requested page number (1-indexed)
        page_size: Requested items per page

    Returns:
        Tuple of (validated_page, validated_page_size)

    Example:
        >>> page, page_size = validate_pagination(0, 200)
        >>> print(page, page_size)
        1 100  # Clamped to valid range
    """
    # Ensure page is at least 1
    validated_page = max(MIN_PAGE, page)

    # Clamp page_size to valid range
    if page_size < MIN_PAGE_SIZE:
        validated_page_size = DEFAULT_PAGE_SIZE
    elif page_size > MAX_PAGE_SIZE:
        validated_page_size = MAX_PAGE_SIZE
    else:
        validated_page_size = page_size

    return validated_page, validated_page_size


def calculate_skip(page: int, page_size: int) -> int:
    """
    Calculate database skip/offset for pagination.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Number of records to skip (0-indexed offset)

    Example:
        >>> calculate_skip(1, 50)
        0  # First page, skip 0 records
        >>> calculate_skip(3, 50)
        100  # Third page, skip 100 records
    """
    return (page - 1) * page_size


def calculate_total_pages(total_count: int, page_size: int) -> int:
    """
    Calculate total number of pages.

    Uses ceiling division to ensure all records are included.
    Returns 0 if total_count is 0.

    Args:
        total_count: Total number of records
        page_size: Items per page

    Returns:
        Total number of pages

    Example:
        >>> calculate_total_pages(100, 50)
        2
        >>> calculate_total_pages(101, 50)
        3  # Ceiling division: need 3 pages for 101 items
        >>> calculate_total_pages(0, 50)
        0  # No records = no pages
    """
    if total_count == 0:
        return 0
    return (total_count + page_size - 1) // page_size


def get_pagination_params(page: int, page_size: int) -> PaginationParams:
    """
    Convenience function to get all pagination parameters at once.

    Args:
        page: Requested page number
        page_size: Requested items per page

    Returns:
        PaginationParams with validated page, page_size, and calculated skip

    Example:
        >>> params = get_pagination_params(2, 75)
        >>> print(params.page, params.page_size, params.skip)
        2 75 75
    """
    validated_page, validated_page_size = validate_pagination(page, page_size)
    skip = calculate_skip(validated_page, validated_page_size)

    return PaginationParams(
        page=validated_page,
        page_size=validated_page_size,
        skip=skip,
    )
