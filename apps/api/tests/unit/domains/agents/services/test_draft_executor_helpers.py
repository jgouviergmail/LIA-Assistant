"""Unit tests for the pure helpers of ``draft_executor``.

These run right after the user CONFIRMS a draft, and they decide how the
Tool-Context Manager (TCM) is re-synchronised with reality:

- ``_classify_draft_type`` picks the sync family (create / update / delete);
- ``_extract_item_id`` finds the canonical id of the item just acted upon;
- ``_current_matches_id`` decides whether the "current item" the user is
  referring to is the one that was just changed or deleted.

Get any of them wrong and the conversational context silently points at a stale
or deleted entity — so the next "delete it" / "move it to 5pm" targets the wrong
row. None of the five had a test.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.services.draft_executor import (
    DraftExecutionResult,
    _classify_draft_type,
    _current_matches_id,
    _extract_item_id,
)

pytestmark = pytest.mark.unit


# ============================================================================
# _classify_draft_type — which TCM sync family applies
# ============================================================================


class TestClassifyDraftType:
    @pytest.mark.parametrize(
        "draft_type", ["event_delete", "contact_delete", "task_delete", "email_delete"]
    )
    def test_delete_suffix(self, draft_type: str) -> None:
        assert _classify_draft_type(draft_type) == "delete"

    @pytest.mark.parametrize("draft_type", ["event_update", "contact_update", "task_update"])
    def test_update_suffix(self, draft_type: str) -> None:
        assert _classify_draft_type(draft_type) == "update"

    @pytest.mark.parametrize(
        "draft_type", ["event", "contact", "task", "email", "email_reply", "email_forward"]
    )
    def test_everything_else_is_a_create(self, draft_type: str) -> None:
        """Create is the DEFAULT, so an unrecognised draft type is synced as a
        creation rather than skipped — pinned because a new "*_archive" family
        would silently land here."""
        assert _classify_draft_type(draft_type) == "create"

    def test_empty_type_is_a_create(self) -> None:
        assert _classify_draft_type("") == "create"

    def test_suffix_must_be_terminal(self) -> None:
        """ "..._delete_confirmation" is not a delete — matching is on the
        terminal suffix only."""
        assert _classify_draft_type("event_delete_confirmation") == "create"


# ============================================================================
# _extract_item_id — the canonical id of the item acted upon
# ============================================================================


class TestExtractItemId:
    def test_reads_the_declared_id_key_for_the_domain(self) -> None:
        assert _extract_item_id("event_update", {"event_id": "evt_1"}, None) == "evt_1"

    def test_contacts_use_resource_name(self) -> None:
        assert (
            _extract_item_id("contact_delete", {"resource_name": "people/c1"}, None) == "people/c1"
        )

    def test_result_data_wins_over_draft_content(self) -> None:
        """Post-execution data carries the FRESH id (a create returns the id the
        API just assigned); the draft's own content may be stale or absent."""
        assert (
            _extract_item_id("event_update", {"event_id": "stale"}, {"event_id": "fresh"})
            == "fresh"
        )

    def test_falls_back_to_draft_content_when_result_lacks_the_id(self) -> None:
        assert _extract_item_id("event_update", {"event_id": "evt_1"}, {}) == "evt_1"

    def test_tries_every_declared_key_in_order(self) -> None:
        """Emails declare ("message_id", "id") — the second is a legitimate
        fallback for raw API payloads."""
        assert _extract_item_id("email", {"id": "msg_1"}, None) == "msg_1"
        assert _extract_item_id("email", {"message_id": "m1", "id": "other"}, None) == "m1"

    @pytest.mark.parametrize("empty", [None, "", 0, []])
    def test_empty_values_are_skipped(self, empty: Any) -> None:
        """An id key present but empty must not be returned as an id — the
        caller would then sync the TCM against a meaningless key."""
        assert _extract_item_id("event_update", {"event_id": empty}, None) is None

    def test_missing_id_returns_none(self) -> None:
        assert _extract_item_id("event_update", {"summary": "no id here"}, None) is None

    def test_unknown_draft_type_has_no_keys(self) -> None:
        assert _extract_item_id("not_a_draft_type", {"event_id": "evt_1"}, None) is None

    def test_result_data_none_is_tolerated(self) -> None:
        assert _extract_item_id("task_update", {"task_id": "t1"}, None) == "t1"

    def test_ids_are_stringified(self) -> None:
        assert _extract_item_id("task_update", {"task_id": 42}, None) == "42"


# ============================================================================
# _current_matches_id — is the focused item the one we just touched?
# ============================================================================


class TestCurrentMatchesId:
    def test_matches_on_the_domain_id_key(self) -> None:
        assert _current_matches_id({"event_id": "evt_1"}, "evt_1", "event_delete") is True

    def test_matches_on_the_generic_id_fallback(self) -> None:
        """TCM-enriched items expose a generic "id" — both shapes must match."""
        assert _current_matches_id({"id": "evt_1"}, "evt_1", "event_delete") is True

    def test_different_id_does_not_match(self) -> None:
        assert _current_matches_id({"event_id": "evt_2"}, "evt_1", "event_delete") is False

    def test_absent_keys_do_not_match(self) -> None:
        assert _current_matches_id({"summary": "meeting"}, "evt_1", "event_delete") is False

    def test_numeric_ids_compare_as_strings(self) -> None:
        assert _current_matches_id({"task_id": 42}, "42", "task_delete") is True

    def test_unknown_draft_type_still_tries_the_generic_id(self) -> None:
        assert _current_matches_id({"id": "x1"}, "x1", "not_a_draft_type") is True

    def test_empty_item_id_would_match_an_idless_item(self) -> None:
        """CHARACTERIZATION of a sharp edge, not a live defect.

        Absent keys default to "", so an EMPTY ``item_id`` matches any item that
        carries no id — which would clear the wrong current item. It is not
        reachable today: ``_extract_item_id`` never returns "" (it skips falsy
        values) and ``_sync_delete`` guards with ``if not item_id: return``.
        Pinned so that guard is never dropped as "redundant".
        """
        assert _current_matches_id({"summary": "no id"}, "", "event_delete") is True


# ============================================================================
# DraftExecutionResult — user-facing messages
# ============================================================================


class TestDraftExecutionResultMessages:
    def test_success_result_is_flagged_success(self) -> None:
        result = DraftExecutionResult(
            success=True, draft_id="d1", draft_type="event", action="confirm"
        )
        payload = result.to_dict()
        assert payload["success"] is True
        assert payload["draft_id"] == "d1"

    def test_cancelled_result_is_not_a_success(self) -> None:
        result = DraftExecutionResult(
            success=False, draft_id="d1", draft_type="event", action="cancel"
        )
        assert result.to_dict()["success"] is False

    @pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
    def test_messages_are_localized_and_never_empty(self, language: str) -> None:
        """User-visible strings go through i18n for all six languages — an
        empty message would surface as a blank confirmation in the UI."""
        confirmed = DraftExecutionResult(
            success=True,
            draft_id="d1",
            draft_type="event",
            action="confirm",
            user_language=language,
        )
        cancelled = DraftExecutionResult(
            success=False,
            draft_id="d1",
            draft_type="event",
            action="cancel",
            user_language=language,
        )
        assert confirmed._get_success_message().strip()
        assert cancelled._get_cancel_message().strip()

    def test_error_is_carried_in_the_payload(self) -> None:
        result = DraftExecutionResult(
            success=False,
            draft_id="d1",
            draft_type="event",
            action="confirm",
            error="API refused",
        )
        assert result.to_dict()["error"] == "API refused"
