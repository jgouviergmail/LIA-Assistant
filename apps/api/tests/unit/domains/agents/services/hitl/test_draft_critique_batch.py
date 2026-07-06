"""Tests for ``DraftCritiqueInteraction._generate_batch_critique``.

Covers the critical HITL confirmation bug (both facets):

- Facet 1 (wording): a NON-destructive batch (send / create / update) must not
  inherit the deletion wording. Before the fix, a batch of emails rendered
  "Cette action est irréversible." + "Confirmes-tu cette suppression ?" — a
  deletion prompt for a send. Destructive (delete) batches must keep that
  wording.
- Facet 2 (recipient): a batch email confirmation must show WHO each email goes
  to, so two same-subject rows are distinguishable (informed consent).

The renderer is action-type driven by the draft display registry (ADR-085),
so the assertions are grammar/locale aware but the logic covers every draft
type via its ``verb_past_key``.
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.hitl.interactions.draft_critique import (
    DraftCritiqueInteraction,
)


def _batch(draft_type: str) -> list[dict]:
    """Two same-subject email drafts to two distinct recipients."""
    return [
        {
            "draft_id": "d1",
            "draft_type": draft_type,
            "draft_content": {"to": "matheo@example.com", "subject": "Je t'aime"},
        },
        {
            "draft_id": "d2",
            "draft_type": draft_type,
            "draft_content": {"to": "hua@example.com", "subject": "Je t'aime"},
        },
    ]


@pytest.fixture
def interaction() -> DraftCritiqueInteraction:
    """``_generate_batch_critique`` does not touch the question generator."""
    return DraftCritiqueInteraction(question_generator=None)  # type: ignore[arg-type]


# =============================================================================
# Facet 1 — non-destructive batch must not use deletion wording
# =============================================================================


def test_email_batch_uses_send_wording_not_deletion_fr(
    interaction: DraftCritiqueInteraction,
) -> None:
    msg = interaction._generate_batch_critique(
        draft_type="email",
        batch_drafts=_batch("email"),
        batch_total=2,
        user_language="fr",
    )
    # Correct send title, no deletion wording anywhere.
    assert "Confirmation d'envoi" in msg, msg
    assert "suppression" not in msg.lower(), msg
    assert "irréversible" not in msg.lower(), msg
    # Neutral FOR_EACH question.
    assert "Veux-tu continuer" in msg, msg


def test_email_batch_uses_send_wording_not_deletion_en(
    interaction: DraftCritiqueInteraction,
) -> None:
    msg = interaction._generate_batch_critique(
        draft_type="email",
        batch_drafts=_batch("email"),
        batch_total=2,
        user_language="en",
    )
    assert "Confirm sending" in msg, msg
    assert "deletion" not in msg.lower(), msg
    assert "cannot be undone" not in msg.lower(), msg
    assert "Do you want to continue?" in msg, msg


@pytest.mark.parametrize(
    "draft_type,title_fr",
    [
        ("event", "Confirmation de création"),
        ("event_update", "Confirmation de modification"),
        ("contact", "Confirmation de création"),
        ("task", "Confirmation de création"),
    ],
)
def test_non_destructive_types_never_say_deletion(
    interaction: DraftCritiqueInteraction, draft_type: str, title_fr: str
) -> None:
    """Every non-delete draft type gets its own title and no deletion wording."""
    drafts = [
        {"draft_content": {"summary": "A", "title": "A", "name": "A"}},
        {"draft_content": {"summary": "B", "title": "B", "name": "B"}},
    ]
    msg = interaction._generate_batch_critique(
        draft_type=draft_type,
        batch_drafts=drafts,
        batch_total=2,
        user_language="fr",
    )
    assert title_fr in msg, msg
    assert "suppression" not in msg.lower(), msg
    assert "irréversible" not in msg.lower(), msg
    assert "Veux-tu continuer" in msg, msg


# =============================================================================
# Facet 1 — destructive batch KEEPS deletion wording (no regression)
# =============================================================================


def test_email_delete_batch_keeps_deletion_wording_fr(
    interaction: DraftCritiqueInteraction,
) -> None:
    drafts = [
        {"draft_content": {"subject": "Facture", "date": None}},
        {"draft_content": {"subject": "Spam", "date": None}},
    ]
    msg = interaction._generate_batch_critique(
        draft_type="email_delete",
        batch_drafts=drafts,
        batch_total=2,
        user_language="fr",
    )
    assert "Confirmation de suppression" in msg, msg
    assert "irréversible" in msg.lower(), msg
    assert "Confirmes-tu cette suppression" in msg, msg


def test_email_delete_batch_keeps_deletion_wording_en(
    interaction: DraftCritiqueInteraction,
) -> None:
    drafts = [{"draft_content": {"subject": "Invoice", "date": None}}]
    msg = interaction._generate_batch_critique(
        draft_type="email_delete",
        batch_drafts=drafts,
        batch_total=1,
        user_language="en",
    )
    assert "cannot be undone" in msg.lower(), msg
    assert "Do you confirm this deletion?" in msg, msg


# =============================================================================
# Facet 2 — recipients are shown and distinguishable in a batch
# =============================================================================


def test_email_batch_shows_distinct_recipients(
    interaction: DraftCritiqueInteraction,
) -> None:
    msg = interaction._generate_batch_critique(
        draft_type="email",
        batch_drafts=_batch("email"),
        batch_total=2,
        user_language="fr",
    )
    assert "matheo@example.com" in msg, msg
    assert "hua@example.com" in msg, msg
    # The two item rows must not be identical.
    rows = [line for line in msg.splitlines() if line.startswith("- ")]
    assert len(rows) == 2 and rows[0] != rows[1], rows
