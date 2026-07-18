"""Tests for interest subject-selection settings wiring (ADR-131)."""

from src.core.config import settings


class TestInterestSubjectSettings:
    """New settings exist, are typed, and carry the benched defaults."""

    def test_selection_mode_default(self) -> None:
        assert settings.interest_selection_mode in ("uniform", "subject_rarity")

    def test_numeric_settings_exist_with_sane_bounds(self) -> None:
        assert 1 <= settings.interest_subject_cooldown_hours <= 168
        assert 0.0 <= settings.interest_subject_rarity_gamma <= 3.0
        assert 0.0 <= settings.interest_subject_weight_beta <= 3.0
        assert 0.0 <= settings.interest_intra_subject_rarity_gamma <= 3.0
        assert 7 <= settings.interest_rarity_lookback_days <= 90
        assert 5 <= settings.interest_subject_recluster_interval_minutes <= 240
        assert 0 <= settings.interest_subject_recluster_full_hour <= 23
        assert 1 <= settings.interest_subject_recluster_batch_size <= 500
        assert 0.90 <= settings.interest_merge_similarity_threshold <= 0.99
        assert 0 <= settings.interest_sources_max_links <= 10
        assert 20 <= settings.interest_subject_max_length <= 200

    def test_job_id_constants(self) -> None:
        from src.core.constants import (
            SCHEDULER_JOB_INTEREST_SUBJECT_FULL,
            SCHEDULER_JOB_INTEREST_SUBJECT_STALE,
        )

        assert SCHEDULER_JOB_INTEREST_SUBJECT_STALE == "interest_subject_stale"
        assert SCHEDULER_JOB_INTEREST_SUBJECT_FULL == "interest_subject_full"
