"""What the two provenance routes answer when the identifier is not one.

Both routes exist to answer "why does LIA think this?", and both are reachable
with whatever string a client puts in the path. They must not differ from their
own neighbours on that:

- the journal route declares ``entry_id: UUID``, so FastAPI rejects a malformed
  identifier at the boundary — it never reaches the handler;
- the memory route declares ``memory_id: str``, like the four routes around it
  in the same file, and those four wrap ``UUID(...)`` in ``try/except`` and
  answer 404. The provenance route was doing the conversion BARE, so a
  malformed identifier raised ``ValueError`` and surfaced as a 500 — a
  different answer, from a different code path, for the same mistake.

A 500 where a 404 belongs is not cosmetic: it tells a caller "the server broke"
when the truth is "there is no such thing", and it is the one difference an
error-rate alert would notice.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.domains.memories.router import get_memory_provenance

pytestmark = pytest.mark.unit


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


class TestAMalformedIdentifierIsNotFound:
    async def test_the_memory_route_answers_not_found_not_server_error(self) -> None:
        with pytest.raises(ResourceNotFoundError):
            await get_memory_provenance(memory_id="not-a-uuid", user=_user(), db=MagicMock())

    async def test_an_unknown_memory_answers_the_same_way(self) -> None:
        """Unknown and malformed answer identically: neither confirms existence."""
        with patch(
            "src.domains.memories.router.MemoryRepository",
            return_value=MagicMock(get_by_id_for_user=AsyncMock(return_value=None)),
        ):
            with pytest.raises(ResourceNotFoundError):
                await get_memory_provenance(
                    memory_id=str(uuid.uuid4()), user=_user(), db=MagicMock()
                )
