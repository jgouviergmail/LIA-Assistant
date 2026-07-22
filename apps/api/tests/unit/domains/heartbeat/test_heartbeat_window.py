"""Tests for the enriched anti-redundancy window (ADR-135).

The 5-item, content-free window let the decision LLM repeat topics it had
already used (bench 2026-07-18: pivot away from A24 landed on "1664", a
memory-sourced motif invisible in the old summary).
"""

import pytest

from src.domains.heartbeat.prompts import build_decision_user_prompt
from src.domains.heartbeat.schemas import HeartbeatContext


@pytest.mark.unit
class TestRecentHeartbeatsSummary:
    def test_summary_includes_content_excerpt(self) -> None:
        ctx = HeartbeatContext(
            recent_heartbeats=[
                {
                    "sources_used": '["USER_INTERESTS"]',
                    "decision_reason": "evening interest",
                    "created_at": "2026-07-18 21:00",
                    "content": "Un film A24 ce soir, comme toujours",
                }
            ]
        )
        summary = ctx.recent_heartbeats_summary
        assert summary is not None
        assert "Un film A24 ce soir" in summary

    def test_summary_falls_back_to_reason_without_content(self) -> None:
        ctx = HeartbeatContext(
            recent_heartbeats=[
                {
                    "sources_used": '["UNREAD_EMAILS"]',
                    "decision_reason": "urgent email from boss",
                    "created_at": "2026-07-18 09:00",
                }
            ]
        )
        summary = ctx.recent_heartbeats_summary
        assert summary is not None
        assert "urgent email from boss" in summary

    def test_decision_prompt_labels_contents_block(self) -> None:
        ctx = HeartbeatContext(
            recent_heartbeats=[
                {
                    "sources_used": '["USER_INTERESTS"]',
                    "decision_reason": "r",
                    "created_at": "2026-07-18 21:00",
                    "content": "Un film A24 ce soir",
                }
            ]
        )
        prompt = build_decision_user_prompt(ctx)
        assert "contents shown" in prompt
        assert "Un film A24 ce soir" in prompt


@pytest.mark.unit
class TestRecentOtherNotificationsWindow:
    """P10 — the window must also cover reminders, automations, call reports.

    Scheduled-action results, fired reminders and telephony reports were
    invisible to the decision LLM: a same-morning multi-surface pile-up on
    one topic could not be detected.
    """

    def test_summary_renders_kind_and_content(self) -> None:
        ctx = HeartbeatContext(
            recent_other_notifications=[
                {
                    "kind": "scheduled_action",
                    "created_at": "2026-07-22 07:30",
                    "content": "Revue de presse IA",
                },
                {
                    "kind": "reminder",
                    "created_at": "2026-07-22 08:00",
                    "content": "Appeler le plombier",
                },
            ]
        )
        summary = ctx.recent_other_notifications_summary
        assert summary is not None
        assert "scheduled_action" in summary
        assert "Revue de presse IA" in summary
        assert "Appeler le plombier" in summary

    def test_summary_none_when_empty(self) -> None:
        assert HeartbeatContext().recent_other_notifications_summary is None

    def test_decision_prompt_includes_other_surfaces_section(self) -> None:
        ctx = HeartbeatContext(
            recent_other_notifications=[
                {
                    "kind": "phone_call",
                    "created_at": "2026-07-22 09:00",
                    "content": "Réservation restaurant confirmée samedi",
                }
            ]
        )
        prompt = build_decision_user_prompt(ctx)
        assert "OTHER RECENT PROACTIVE MESSAGES" in prompt
        assert "Réservation restaurant confirmée samedi" in prompt

    def test_decision_prompt_section_absent_placeholder_when_empty(self) -> None:
        prompt = build_decision_user_prompt(HeartbeatContext())
        assert "OTHER RECENT PROACTIVE MESSAGES" in prompt
        assert prompt.count("None sent recently.") >= 3
