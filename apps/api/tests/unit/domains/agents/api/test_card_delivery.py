"""The answer's cards reach the archive and the done chunk through ONE door (ADR-327)."""

from __future__ import annotations

import pytest

from src.domains.agents.api.card_delivery import attach_archived_cards, attach_done_cards
from src.domains.document_generation.document_store import PendingDocument, store_pending_document
from src.domains.image_generation.image_store import store_pending_image
from src.domains.skills.proposals import SkillProposal, queue_proposal_card

pytestmark = pytest.mark.unit


def _queue_one_of_each(conversation_id: str) -> None:
    store_pending_image(conversation_id, "/api/v1/attachments/i", "an image")
    store_pending_document(
        conversation_id,
        PendingDocument(
            url="/api/v1/attachments/d", filename="a.pdf", doc_type="pdf", size_bytes=1
        ),
    )
    queue_proposal_card(
        conversation_id,
        SkillProposal(
            id="d" * 32,
            owner_id="owner",
            name="ma-skill",
            description="Useful.",
            files={"SKILL.md": "x"},
            sizes={"SKILL.md": 1},
            created_at="2026-09-30T10:00:00+00:00",
            expires_at="2026-10-01T10:00:00+00:00",
            replaces=None,
            changes=None,
        ),
    )


def test_the_archive_keeps_every_family_and_the_done_chunk_frees_them() -> None:
    _queue_one_of_each("conv")
    archived: dict[str, object] = {}
    done: dict[str, object] = {}

    attach_archived_cards(archived, "conv")
    attach_done_cards(done, "conv")

    families = {"generated_images", "generated_documents", "skill_proposals"}
    assert set(archived) == families
    assert archived == done, "the live card and the archived card must be the same"
    after: dict[str, object] = {}
    attach_done_cards(after, "conv")
    assert after == {}


def test_an_answer_without_cards_carries_no_key() -> None:
    metadata: dict[str, object] = {}

    attach_archived_cards(metadata, "empty")
    attach_done_cards(metadata, "empty")

    assert metadata == {}
