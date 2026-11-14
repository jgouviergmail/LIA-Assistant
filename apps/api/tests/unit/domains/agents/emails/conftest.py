"""What every test of an e-mail tool starts from."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.emails import writing_style
from src.domains.agents.tools import email_files


@pytest.fixture(autouse=True)
def person_signs_with_nothing() -> Iterator[AsyncMock]:
    """A signature is read from the database: a test that wants one says so."""
    with patch.object(email_files, "read_signature", AsyncMock(return_value="")) as read:
        yield read


@pytest.fixture(autouse=True)
def person_has_no_known_style() -> Iterator[AsyncMock]:
    """A writing style is read from the database (ADR-383): a test that wants one says so."""
    with patch.object(writing_style, "writing_style_for", AsyncMock(return_value=None)) as read:
        yield read
