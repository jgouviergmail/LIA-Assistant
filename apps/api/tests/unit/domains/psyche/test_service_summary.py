"""
Unit tests for PsycheService — generate_summary() and snapshot creation.

Tests the LLM summary endpoint logic and history snapshot creation
in process_post_response using mocked dependencies.

Phase: evolution — Psyche Engine (Iteration 2)
Created: 2026-04-01
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.psyche.constants import SNAPSHOT_TYPE_MESSAGE
from src.domains.psyche.models import PsycheHistory, PsycheState

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _make_state(user_id: UUID | None = None, **overrides: object) -> MagicMock:
    """Create a minimal PsycheState mock for testing."""
    defaults = {
        "id": uuid4(),
        "user_id": user_id or uuid4(),
        "trait_openness": 0.5,
        "trait_conscientiousness": 0.5,
        "trait_extraversion": 0.5,
        "trait_agreeableness": 0.5,
        "trait_neuroticism": 0.5,
        "mood_pleasure": 0.15,
        "mood_arousal": 0.10,
        "mood_dominance": 0.05,
        "mood_quadrant_since": datetime.now(UTC),
        "active_emotions": [
            {"name": "curiosity", "intensity": 0.6, "triggered_at": "2026-04-01T10:00:00"},
        ],
        "self_efficacy": {},
        "relationship_stage": "EXPLORATORY",
        "relationship_depth": 0.25,
        "relationship_warmth_active": 0.6,
        "relationship_trust": 0.4,
        "relationship_interaction_count": 15,
        "relationship_total_duration_minutes": 45.0,
        "relationship_last_interaction": datetime.now(UTC),
        "drive_curiosity": 0.6,
        "drive_engagement": 0.5,
        "last_appraisal": None,
        "narrative_identity": None,
        "psyche_version": 1,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    state = MagicMock(spec=PsycheState)
    for k, v in defaults.items():
        setattr(state, k, v)
    return state


def _make_service_with_mocked_repo(user_id: UUID, state: MagicMock) -> Any:
    """Create a PsycheService with all repo/cache methods mocked.

    Args:
        user_id: User UUID for the state.
        state: Mocked PsycheState object.

    Returns:
        Configured PsycheService with mocked dependencies.
    """
    from src.domains.psyche.engine import PersonalityTraits
    from src.domains.psyche.service import PsycheService

    db = AsyncMock()
    service = PsycheService(db)
    service.get_or_create_state = AsyncMock(return_value=state)
    service._load_user_psyche_prefs = AsyncMock(return_value=(70, 60))
    service._load_personality_traits_and_override = AsyncMock(
        return_value=(PersonalityTraits(), None),
    )
    service._save_to_cache = AsyncMock()
    service.repo = MagicMock()
    service.repo.update = AsyncMock()
    service.repo.create_snapshot = AsyncMock()
    return service


class TestGenerateSummary:
    """Tests for PsycheService.generate_summary()."""

    async def test_summary_returns_llm_content(self):
        """generate_summary() should return LLM-generated text."""
        from src.domains.psyche.service import PsycheService

        user_id = uuid4()
        state = _make_state(user_id=user_id)

        mock_llm_result = MagicMock()
        mock_llm_result.content = "LIA is feeling curious and energized today."

        db = AsyncMock()
        service = PsycheService(db)
        service.get_or_create_state = AsyncMock(return_value=state)
        service._load_personality_name = AsyncMock(return_value="Philosopher")

        with (
            patch("src.infrastructure.llm.get_llm", return_value=MagicMock()),
            patch(
                "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
                new_callable=AsyncMock,
                return_value=mock_llm_result,
            ),
            patch(
                "src.domains.agents.prompts.prompt_loader.load_prompt",
                return_value=(
                    "Test {user_language} {personality_name} {mood_label} "
                    "{mood_p} {mood_a} {mood_d} {emotions_text} "
                    "{stage} {depth} {warmth} {trust} {interaction_count}"
                ),
            ),
        ):
            result = await service.generate_summary(user_id, "fr")

            assert result == "LIA is feeling curious and energized today."
            service.get_or_create_state.assert_awaited_once_with(user_id)
            service._load_personality_name.assert_awaited_once_with(user_id)

    async def test_summary_fallback_on_llm_failure(self):
        """generate_summary() should return template fallback when LLM fails."""
        from src.domains.psyche.service import PsycheService

        user_id = uuid4()
        state = _make_state(user_id=user_id)

        db = AsyncMock()
        service = PsycheService(db)
        service.get_or_create_state = AsyncMock(return_value=state)
        service._load_personality_name = AsyncMock(return_value="Default")

        with (
            patch("src.infrastructure.llm.get_llm", return_value=MagicMock()),
            patch(
                "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
                new_callable=AsyncMock,
                side_effect=Exception("LLM unavailable"),
            ),
            patch(
                "src.domains.agents.prompts.prompt_loader.load_prompt",
                return_value=(
                    "Test {user_language} {personality_name} {mood_label} "
                    "{mood_p} {mood_a} {mood_d} {emotions_text} "
                    "{stage} {depth} {warmth} {trust} {interaction_count}"
                ),
            ),
        ):
            result = await service.generate_summary(user_id, "en")

            # Should be a template fallback, not an exception
            assert "Mood:" in result
            assert "Emotions:" in result

    async def test_summary_formats_emotions_correctly(self):
        """generate_summary() should format multiple active emotions as CSV."""
        from src.domains.psyche.service import PsycheService

        user_id = uuid4()
        state = _make_state(
            user_id=user_id,
            active_emotions=[
                {"name": "joy", "intensity": 0.8, "triggered_at": "2026-04-01T10:00:00"},
                {"name": "curiosity", "intensity": 0.4, "triggered_at": "2026-04-01T10:01:00"},
            ],
        )

        mock_llm_result = MagicMock()
        mock_llm_result.content = "Summary with emotions."

        db = AsyncMock()
        service = PsycheService(db)
        service.get_or_create_state = AsyncMock(return_value=state)
        service._load_personality_name = AsyncMock(return_value="Default")

        captured_prompt = None

        def mock_load_prompt(name):
            return (
                "{user_language} {personality_name} {mood_label} "
                "{mood_p} {mood_a} {mood_d} {emotions_text} "
                "{stage} {depth} {warmth} {trust} {interaction_count}"
            )

        async def mock_invoke(llm, llm_type, messages, **kwargs):
            nonlocal captured_prompt
            captured_prompt = messages[0].content
            return mock_llm_result

        with (
            patch("src.infrastructure.llm.get_llm", return_value=MagicMock()),
            patch(
                "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
                side_effect=mock_invoke,
            ),
            patch(
                "src.domains.agents.prompts.prompt_loader.load_prompt",
                side_effect=mock_load_prompt,
            ),
        ):
            result = await service.generate_summary(user_id, "fr")

            assert result == "Summary with emotions."
            # Verify emotions were formatted as CSV in the prompt
            assert "joy (80%)" in captured_prompt
            assert "curiosity (40%)" in captured_prompt


class TestSnapshotCreation:
    """Tests for snapshot creation in process_post_response."""

    async def test_snapshot_created_after_post_response(self):
        """process_post_response should create a PsycheHistory snapshot."""
        from src.domains.psyche.engine import PsycheAppraisal

        user_id = uuid4()
        state = _make_state(user_id=user_id)
        service = _make_service_with_mocked_repo(user_id, state)

        appraisal = PsycheAppraisal(
            valence=0.5,
            arousal=0.3,
            emotion="curiosity",
            intensity=0.6,
            quality=0.8,
        )

        with patch("src.domains.psyche.service.settings") as mock_settings:
            mock_settings.psyche_appraisal_sensitivity = 0.7
            mock_settings.psyche_emotion_max_active = 7
            mock_settings.psyche_history_snapshot_enabled = True
            mock_settings.psyche_self_efficacy_prior_weight = 5.0

            result = await service.process_post_response(user_id, appraisal)

            # Verify snapshot was created
            assert service.repo.create_snapshot.called
            snapshot_arg = service.repo.create_snapshot.call_args[0][0]
            assert isinstance(snapshot_arg, PsycheHistory)
            assert snapshot_arg.user_id == user_id
            assert snapshot_arg.snapshot_type == SNAPSHOT_TYPE_MESSAGE
            assert snapshot_arg.mood_pleasure == state.mood_pleasure
            assert snapshot_arg.relationship_stage == state.relationship_stage

            # Verify dominant emotion captured
            assert snapshot_arg.dominant_emotion is not None

            # Verify result is a PsycheStateSummary
            assert result is not None
            assert result.mood_label is not None

    async def test_no_snapshot_when_disabled(self):
        """No snapshot when psyche_history_snapshot_enabled is False."""
        from src.domains.psyche.engine import PsycheAppraisal

        user_id = uuid4()
        state = _make_state(user_id=user_id)
        service = _make_service_with_mocked_repo(user_id, state)

        appraisal = PsycheAppraisal(
            valence=0.5,
            arousal=0.3,
            emotion="curiosity",
            intensity=0.6,
            quality=0.8,
        )

        with patch("src.domains.psyche.service.settings") as mock_settings:
            mock_settings.psyche_appraisal_sensitivity = 0.7
            mock_settings.psyche_emotion_max_active = 7
            mock_settings.psyche_history_snapshot_enabled = False
            mock_settings.psyche_self_efficacy_prior_weight = 5.0

            await service.process_post_response(user_id, appraisal)

            # Verify snapshot was NOT created
            assert not service.repo.create_snapshot.called

    async def test_snapshot_without_appraisal(self):
        """process_post_response without appraisal still creates snapshot."""
        user_id = uuid4()
        state = _make_state(user_id=user_id)
        service = _make_service_with_mocked_repo(user_id, state)

        with patch("src.domains.psyche.service.settings") as mock_settings:
            mock_settings.psyche_history_snapshot_enabled = True

            result = await service.process_post_response(user_id, appraisal=None)

            # Snapshot should still be created even without appraisal
            assert service.repo.create_snapshot.called
            snapshot_arg = service.repo.create_snapshot.call_args[0][0]
            assert snapshot_arg.snapshot_type == SNAPSHOT_TYPE_MESSAGE

            # Result should still return a summary
            assert result is not None
