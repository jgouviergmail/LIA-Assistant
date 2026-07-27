"""Doctrine guards for the two admission prompts (interests, long-term memory).

A prompt is behaviour. These rules were not written from taste: they were
measured on 2026-07-27 against the production database and 45 replayed real
conversation windows, and they moved the noise rate on negatives from 0.50 to
0.00 while keeping recall at 1.00 on a held-out battery. Nothing in the
repository prevents a future rewrite from quietly dropping them — hence these
guards, in the spirit of the existing ``TestMemoryExtractionPromptDoctrine``.

They pin the ADMISSION rules only: what may become an interest or a memory.
They do not freeze wording, and they must never be relaxed to accommodate a
regression — the measurement harness
(``scripts/measure_extraction_selectivity.py``) is the tool for re-tuning.
"""

from __future__ import annotations

import pytest

from src.core.constants import (
    DYNAMIC_CONTEXT_MARKER,
    INTEREST_EXTRACTION_MIN_CONFIDENCE_DEFAULT,
)
from src.domains.agents.prompts import load_prompt

pytestmark = pytest.mark.unit


def _flat(text: str) -> str:
    """Collapse whitespace so a guard pins doctrine, not line wrapping.

    These prompts are hand-wrapped at ~90 columns; asserting on raw substrings
    would fail the day someone reflows a paragraph without changing a rule.
    """
    return " ".join(text.split())


@pytest.fixture(scope="module")
def interest_prompt() -> str:
    return _flat(str(load_prompt("interest_extraction_prompt")))


@pytest.fixture(scope="module")
def memory_prompt() -> str:
    return _flat(str(load_prompt("memory_extraction_prompt")))


@pytest.fixture(scope="module")
def interest_prompt_raw() -> str:
    return str(load_prompt("interest_extraction_prompt"))


@pytest.fixture(scope="module")
def memory_prompt_raw() -> str:
    return str(load_prompt("memory_extraction_prompt"))


# =============================================================================
# Interests
# =============================================================================


class TestInterestAdmissionDoctrine:
    def test_it_formats_with_the_extractors_exact_kwargs(self, interest_prompt_raw: str) -> None:
        # The runtime calls .format(**kwargs); a placeholder drift crashes the
        # extraction at the first real turn, not here.
        rendered = interest_prompt_raw.format(
            conversation="USER: bonjour",
            existing_interests="- [id=x] escalade (sports)",
            current_datetime="27/07/2026 20:00",
            user_language="French",
        )

        assert "bonjour" in rendered

    @pytest.mark.parametrize(
        "ground",
        ["stated_passion", "own_practice", "prior_knowledge", "deep_dive"],
    )
    def test_each_admissible_ground_is_named(self, interest_prompt: str, ground: str) -> None:
        # A creation must be justifiable by a NAMED ground. Free-form judgement
        # ("it seemed to interest them") is what admitted every passing subject.
        assert ground in interest_prompt

    def test_a_creation_must_quote_the_user(self, interest_prompt: str) -> None:
        assert "evidence" in interest_prompt
        assert "quote the words that carry it" in interest_prompt
        assert "Do not manufacture one you cannot" in interest_prompt

    @pytest.mark.parametrize(
        ("label", "needle"),
        [
            ("the subject of a request", "THE SUBJECT OF A REQUEST"),
            ("a remark about the assistant", "A REMARK ABOUT THE ASSISTANT"),
            ("someone else's taste", "SOMEONE ELSE'S TASTE"),
            ("something tried once", "SOMETHING TRIED ONCE"),
            ("utilitarian and daily actions", "UTILITARIAN AND DAILY ACTIONS"),
            ("what the assistant introduced", "ANYTHING THE ASSISTANT INTRODUCED"),
        ],
    )
    def test_each_exclusion_class_is_stated(
        self, interest_prompt: str, label: str, needle: str
    ) -> None:
        # Classes, not examples: the model must recognise the mistake, not the
        # instance. Each of these mirrors interests the user actually blocked.
        assert needle in interest_prompt, label

    def test_asking_is_framed_as_a_task_not_a_taste(self, interest_prompt: str) -> None:
        assert "ASKING IS A TASK, NOT A TASTE" in interest_prompt

    def test_one_exchange_yields_at_most_one_creation(self, interest_prompt: str) -> None:
        # One production window produced a subject AND one of its facets.
        assert "At most ONE create per exchange" in interest_prompt

    def test_an_update_needs_a_ground_too(self, interest_prompt: str) -> None:
        # Otherwise a tightened `create` is simply displaced into `update`,
        # which consolidates just the same.
        assert "`update` needs a ground too" in interest_prompt

    def test_silence_is_stated_as_a_correct_answer(self, interest_prompt: str) -> None:
        assert "Most exchanges yield `[]`" in interest_prompt

    def test_the_written_confidence_floor_matches_the_enforced_one(
        self, interest_prompt: str
    ) -> None:
        # The prompt's lowest anchor and the SHIPPED floor are one rule
        # expressed twice; if they drift, either legitimate creations are
        # dropped or the floor stops meaning anything. Compared against the
        # constant, not the effective setting: a deployment that tunes its own
        # floor must not turn this doctrine guard red.
        floor = INTEREST_EXTRACTION_MIN_CONFIDENCE_DEFAULT
        assert f"below {floor} → do not create" in interest_prompt
        assert f"{floor} deep dive" in interest_prompt

    def test_the_static_prefix_stays_cacheable(self, interest_prompt_raw: str) -> None:
        # Guarded generally by test_prompt_cache_hygiene; restated here because
        # this prompt's rules live entirely in the cached prefix.
        marker = interest_prompt_raw.find(DYNAMIC_CONTEXT_MARKER)
        assert marker > 0
        assert "stated_passion" in interest_prompt_raw[:marker]


# =============================================================================
# Memory
# =============================================================================


class TestMemoryAdmissionDoctrine:
    def test_it_formats_with_the_extractors_exact_kwargs(self, memory_prompt_raw: str) -> None:
        rendered = memory_prompt_raw.format(
            conversation="USER: bonjour",
            existing_memories="None",
            current_datetime="27/07/2026 20:00",
            known_relationships="No known relationships",
            health_context="",
        )

        assert "bonjour" in rendered

    def test_the_catch_all_clause_stays_closed(self, memory_prompt: str) -> None:
        # "…or useful informations" re-admitted everything the other three
        # criteria excluded. It must not come back.
        assert "useful informations" not in memory_prompt
        assert "LATER, unrelated conversation" in memory_prompt

    def test_the_subject_of_the_exchange_is_excluded(self, memory_prompt: str) -> None:
        assert "The SUBJECT of the exchange" in memory_prompt

    def test_a_strangers_facts_are_excluded(self, memory_prompt: str) -> None:
        # Production stored "X is a man" as a `relationship` — a person with no
        # link to the user is not a memory about the user.
        assert "A third party's own facts" in memory_prompt

    def test_a_universally_true_statement_is_excluded(self, memory_prompt: str) -> None:
        assert "not true of almost anyone" in memory_prompt

    def test_a_perishable_world_claim_is_excluded(self, memory_prompt: str) -> None:
        assert "false in a few months" in memory_prompt

    def test_a_recurring_slot_is_a_pattern_not_logistics(self, memory_prompt: str) -> None:
        # The ambiguity cost recall on "my son's tennis class every Monday":
        # a recurring slot shapes the user's weeks, a one-off does not.
        assert "A RECURRING slot is the opposite" in memory_prompt
        assert "a ONE-OFF appointment" in memory_prompt

    def test_the_near_miss_examples_are_present(self, memory_prompt: str) -> None:
        # Textbook positives only teach "extract"; boundary pairs teach where
        # the boundary is.
        assert "Near misses" in memory_prompt

    def test_the_transient_logistics_doctrine_survives(self, memory_prompt: str) -> None:
        # Pinned since 2026-07-23 by TestMemoryExtractionPromptDoctrine; the
        # rewrite must not have taken it out.
        lowered = memory_prompt.lower()
        assert "transient logistics" in lowered
        assert "appointment" in lowered and "reservation" in lowered
