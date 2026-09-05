"""Reading what a tool actually returned (ADR-263).

The gate wraps the RAW coroutine, so it sees the tool's own return value — a
``ToolResponse`` dict, a ``UnifiedToolOutput``, or whatever a legacy tool hands
back — never the ``ToolMessage`` the framework builds later.

Two readings, and each has a deliberate default:

- **Succeeded**: only an EXPLICIT ``success is False`` closes the row as failed.
  The opposite default would mark every legacy tool's effect as a failure and
  make the ledger lie in the safest-looking direction.
- **Provider reference**: the identifier the world gave back, when there is one.
  Absent is a perfectly normal answer; inventing one would be worse.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domains.agents.effects.outcome import PROVIDER_REF_KEYS, read_outcome

pytestmark = [pytest.mark.unit]


class TestSuccess:
    def test_an_explicit_failure_is_a_failure(self) -> None:
        assert read_outcome({"success": False, "error": "boom"}).succeeded is False

    def test_an_explicit_success_is_a_success(self) -> None:
        assert read_outcome({"success": True, "data": {}}).succeeded is True

    def test_a_legacy_result_without_the_field_counts_as_success(self) -> None:
        """It returned; nothing says it failed."""
        assert read_outcome({"anything": 1}).succeeded is True
        assert read_outcome("done").succeeded is True
        assert read_outcome(None).succeeded is True

    def test_an_object_result_is_read_the_same_way(self) -> None:
        assert read_outcome(SimpleNamespace(success=False)).succeeded is False
        assert read_outcome(SimpleNamespace(success=True)).succeeded is True


class TestProviderReference:
    @pytest.mark.parametrize("key", sorted(PROVIDER_REF_KEYS))
    def test_each_known_identifier_is_found(self, key: str) -> None:
        assert read_outcome({"success": True, "data": {key: "abc-1"}}).provider_ref == "abc-1"

    def test_it_is_read_at_the_top_level_too(self) -> None:
        assert read_outcome({"success": True, "message_id": "m1"}).provider_ref == "m1"

    def test_absent_is_a_normal_answer(self) -> None:
        assert read_outcome({"success": True, "data": {"count": 3}}).provider_ref is None

    def test_a_non_scalar_identifier_is_ignored(self) -> None:
        """A dict under ``id`` is not a provider reference."""
        assert read_outcome({"success": True, "data": {"id": {"nested": 1}}}).provider_ref is None

    def test_the_first_known_key_wins_deterministically(self) -> None:
        result = {"success": True, "data": {"id": "generic", "message_id": "specific"}}
        assert read_outcome(result).provider_ref == "specific"


class TestThePayloadTheLedgerKeeps:
    def test_the_whole_result_is_kept(self) -> None:
        outcome = read_outcome({"success": True, "data": {"id": "x"}})
        assert outcome.payload == {"success": True, "data": {"id": "x"}}

    def test_an_object_is_rendered_before_being_kept(self) -> None:
        """A Pydantic result must reach the ledger as data, not as a repr."""
        from pydantic import BaseModel

        class _Out(BaseModel):
            success: bool = True
            data: dict[str, str] = {"id": "z"}

        assert read_outcome(_Out()).payload == {"success": True, "data": {"id": "z"}}


class TestTheKeysStayAlignedWithTheDraftExecutor:
    def test_every_domain_id_key_is_a_known_provider_reference(self) -> None:
        """The draft executor already knows what an id looks like per domain."""
        from src.domains.agents.services.draft_executor import _DOMAIN_ID_KEYS

        declared = {key for keys in _DOMAIN_ID_KEYS.values() for key in keys}
        assert declared <= PROVIDER_REF_KEYS, sorted(declared - PROVIDER_REF_KEYS)
