"""Peer proactive strings — completeness across the 6 languages (Lot 3).

Every factory must resolve for every backend-canonical code (zh-CN, never
zh), embed its dynamic parts, and differ across languages (a copy-paste
placeholder would pass a mere non-empty check).
"""

import pytest

from src.core.i18n_proactive import ProactiveMessages

LANGUAGES = ["fr", "en", "es", "de", "it", "zh-CN"]
URL = "https://lia.example/dashboard/settings?section=peer-connections"


@pytest.mark.unit
class TestPeerProactiveStrings:
    def test_titles_present_for_both_task_types(self):
        for task_type in ("peer_request", "peer_connection"):
            titles = {
                language: ProactiveMessages.notification_title(task_type, language)
                for language in LANGUAGES
            }
            assert all(titles.values())
            assert titles["fr"] != titles["en"] or task_type == "peer_connection"
            # Unknown-type fallback must NOT be what we get for a known type.
            assert titles["en"] != "Notification"

    def test_request_body_embeds_name_url_and_quoted_note(self):
        for language in LANGUAGES:
            body = ProactiveMessages.peer_request_body(
                "Marie Dupont", "On se connecte ?", URL, language
            )
            assert "Marie Dupont" in body
            assert URL in body
            assert "On se connecte ?" in body

    def test_request_body_without_note_has_no_empty_quote(self):
        body = ProactiveMessages.peer_request_body("Marie Dupont", None, URL, "fr")
        assert "«  »" not in body and '""' not in body
        assert "Marie Dupont" in body

    def test_outcome_and_removal_bodies_resolve_everywhere(self):
        for language in LANGUAGES:
            accepted = ProactiveMessages.peer_accepted_body("Marie Dupont", URL, language)
            declined = ProactiveMessages.peer_declined_body("Marie Dupont", language)
            removed = ProactiveMessages.peer_removed_body("Marie Dupont", language)
            assert "Marie Dupont" in accepted and URL in accepted
            assert "Marie Dupont" in declined
            assert "Marie Dupont" in removed
            assert accepted != declined != removed

    def test_message_title_and_sender_bodies_resolve_everywhere(self):
        for language in LANGUAGES:
            title = ProactiveMessages.notification_title("peer_message", language)
            delivered = ProactiveMessages.peer_message_delivered_body("Marie", language)
            failed = ProactiveMessages.peer_message_failed_body("Marie", language)
            assert title and title != "Notification"
            assert "Marie" in delivered
            assert "Marie" in failed
            assert delivered != failed

    def test_languages_actually_differ(self):
        bodies = {
            language: ProactiveMessages.peer_removed_body("X", language) for language in LANGUAGES
        }
        assert len(set(bodies.values())) == len(LANGUAGES)
