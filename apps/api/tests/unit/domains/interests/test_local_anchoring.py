"""Local anchoring of interests (P9) + skill nudge rule (P13) — Lot 6.

P9: when a city is resolved and the flag is on, the shared search-query
builder appends a localized "near {city} this week" suffix so interest
content becomes locally actionable. P13: prompt-driven meeting-prep nudge.
"""

import pytest

from src.domains.interests.helpers import build_localized_search_query

TEMPLATES = {"fr": "Actualités sur {topic}", "en": "News about {topic}"}


@pytest.mark.unit
class TestLocalizedQueryLocality:
    def test_no_locality_keeps_historical_query(self):
        q = build_localized_search_query("jazz", "fr", TEMPLATES)
        assert q == "Actualités sur jazz"

    def test_anchored_topic_flows_through_query_builder(self):
        """Anchoring happens ONCE at the generator level (topic rewrite); the
        per-source query builders then compose naturally — they take no
        locality parameter of their own."""
        from src.domains.interests.helpers import anchor_topic_locally

        anchored = anchor_topic_locally("jazz", "fr", "Lyon")
        q = build_localized_search_query(anchored, "fr", TEMPLATES)
        assert q == "Actualités sur jazz près de Lyon cette semaine"

    def test_all_supported_languages_have_suffix(self):
        from src.domains.interests.helpers import LOCALITY_SUFFIX_TEMPLATES

        for lang in ("fr", "en", "es", "de", "it", "zh"):
            assert "{locality}" in LOCALITY_SUFFIX_TEMPLATES[lang], lang


@pytest.mark.unit
class TestContentContextLocality:
    def test_context_carries_optional_locality(self):
        from src.domains.interests.services.content_sources.base import (
            ContentGenerationContext,
        )

        ctx = ContentGenerationContext(
            interest_id="i",
            topic="jazz",
            category="music",
            user_id="u",
            user_language="fr",
            locality="Lyon",
        )
        assert ctx.locality == "Lyon"

    def test_locality_defaults_to_none(self):
        from src.domains.interests.services.content_sources.base import (
            ContentGenerationContext,
        )

        ctx = ContentGenerationContext(
            interest_id="i", topic="jazz", category="music", user_id="u", user_language="fr"
        )
        assert ctx.locality is None


@pytest.mark.unit
class TestSkillNudgeRule:
    def test_rule_21_present_in_decision_prompt(self):
        from src.domains.agents.prompts.prompt_loader import load_prompt

        content = load_prompt("heartbeat_decision_prompt")
        assert "21." in content
        assert "prépare" in content or "prepare this meeting" in content


@pytest.mark.unit
class TestAnchorTopicLocally:
    def test_identity_without_locality(self):
        from src.domains.interests.helpers import anchor_topic_locally

        assert anchor_topic_locally("jazz", "fr", None) == "jazz"

    def test_appends_localized_suffix(self):
        from src.domains.interests.helpers import anchor_topic_locally

        assert anchor_topic_locally("jazz", "fr", "Lyon") == "jazz près de Lyon cette semaine"
        assert anchor_topic_locally("jazz", "en-US", "Lyon") == "jazz near Lyon this week"
