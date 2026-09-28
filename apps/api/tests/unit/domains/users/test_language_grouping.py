"""Broadcast recipients are grouped by CANONICAL language (ADR-323).

Two spellings of one language are one group, so a broadcast is translated once
per language and every reader finds its translation; a stored value no
supported language matches joins the instance default's group, never a group
of its own that no translation would ever fill.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.i18n import language_scope
from src.domains.users.repository import UserRepository

pytestmark = pytest.mark.unit


def test_two_spellings_of_one_language_are_one_group() -> None:
    fr, fr_fr, zh, zh_cn = uuid4(), uuid4(), uuid4(), uuid4()

    grouped = UserRepository._group_users_by_language(
        [(fr, "fr"), (fr_fr, "fr-FR"), (zh, "zh"), (zh_cn, "zh-CN")]
    )

    assert grouped == {"fr": [fr, fr_fr], "zh-CN": [zh, zh_cn]}


def test_an_unreadable_language_joins_the_instance_default() -> None:
    """Under a declared language too: a stored value belongs to its person. The
    default is pinned off French, so a French literal fallback cannot pass."""
    known, unknown, empty = uuid4(), uuid4(), uuid4()

    with patch.object(settings, "default_language", "es"), language_scope("de"):
        grouped = UserRepository._group_users_by_language(
            [(known, "es"), (unknown, "klingon"), (empty, "")]
        )

    assert grouped == {"es": [known, unknown, empty]}


def test_no_row_is_no_group() -> None:
    assert UserRepository._group_users_by_language([]) == {}
