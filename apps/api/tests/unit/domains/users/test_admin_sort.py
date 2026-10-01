"""The administrators' user listing sorts by a declared vocabulary, and nothing else.

``get_users_with_stats_paginated`` used to resolve an unknown key with
``getattr(User, sort_by, User.created_at)``: ``hashed_password`` ordered the
directory by password hash, and a misspelled key fell back to the creation
date without a word. The route now refuses what ``ADMIN_USER_SORT_KEYS`` does
not name, and the repository resolves exactly that vocabulary — the two are
checked against each other here, so neither can grow alone.
"""

from __future__ import annotations

import pytest
from sqlalchemy.sql.elements import ColumnElement

from src.domains.users.admin_columns import ADMIN_USER_SORT_KEYS, ADMIN_USER_STATISTIC_SORTS
from src.domains.users.repository import _statistic_sort_expressions, admin_sort_expression

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("key", sorted(ADMIN_USER_SORT_KEYS))
def test_every_declared_key_resolves_to_an_expression(key: str) -> None:
    assert isinstance(admin_sort_expression(key), ColumnElement)


@pytest.mark.parametrize("key", ["hashed_password", "id", "typo", ""])
def test_a_key_outside_the_vocabulary_is_refused(key: str) -> None:
    with pytest.raises(ValueError, match="sort"):
        admin_sort_expression(key)


def test_the_repository_sums_exactly_the_declared_statistics() -> None:
    """A sum the repository computes but the route refuses is dead; the reverse fails."""
    assert set(_statistic_sort_expressions()) == set(ADMIN_USER_STATISTIC_SORTS)
