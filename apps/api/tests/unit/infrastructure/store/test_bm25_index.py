"""Unit tests for the BM25 tokenizer and index manager.

The tokenizer is the lexical half of RAG hybrid retrieval, and LIA indexes
user documents in all 6 supported languages. Two properties are load-bearing:

- **Latin scripts must tokenize exactly as before.** The tokenizer is shared by
  every space; a change made for CJK that shifts French or German tokens would
  silently re-rank every existing corpus.
- **CJK runs must not collapse into one token.** ``[\\w']+`` matches a whole
  Chinese sentence as a single word, so BM25 degenerated into exact-sentence
  matching: measured 0.062 hit@5 BM25-only on a zh corpus, against 0.487 with
  character bigrams (2026-08-22 calibration, see ADR-242).
"""

from __future__ import annotations

import pytest

from src.infrastructure.store.bm25_index import tokenize_text


@pytest.mark.unit
class TestTokenizeTextLatin:
    """Latin-script behaviour is frozen: these are regression guards."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                "Comment connecter mon agenda Google ?",
                ["comment", "connecter", "mon", "agenda", "google"],
            ),
            ("How do I add an MCP server?", ["how", "do", "add", "an", "mcp", "server"]),
            ("Wie verbinde ich meinen Kalender?", ["wie", "verbinde", "ich", "meinen", "kalender"]),
            ("¿Cómo conecto mi calendario?", ["cómo", "conecto", "mi", "calendario"]),
            ("Come collego il mio calendario?", ["come", "collego", "il", "mio", "calendario"]),
        ],
        ids=["fr", "en", "de", "es", "it"],
    )
    def test_latin_languages_tokenize_to_lowercase_words(
        self, text: str, expected: list[str]
    ) -> None:
        assert tokenize_text(text) == expected

    def test_accents_and_diacritics_are_preserved(self) -> None:
        """Accents carry meaning in 5 of the 6 locales — stripping them would
        merge distinct words (``tache``/``tâche``)."""
        assert tokenize_text("Tâche prévoyance écrite") == ["tâche", "prévoyance", "écrite"]

    def test_intra_word_apostrophe_is_kept(self) -> None:
        """``l'assistant`` is one French token, not two."""
        assert tokenize_text("L'assistant n'est pas actif") == [
            "l'assistant",
            "n'est",
            "pas",
            "actif",
        ]

    def test_trailing_apostrophe_is_not_part_of_the_token(self) -> None:
        """``users'`` must match ``users`` elsewhere in the corpus."""
        assert tokenize_text("the users' documents") == ["the", "users", "documents"]

    def test_single_character_tokens_are_dropped_as_noise(self) -> None:
        assert tokenize_text("a b to be") == ["to", "be"]

    @pytest.mark.parametrize("text", ["", "   ", "!!! ??? ...", "\n\t"])
    def test_empty_and_punctuation_only_inputs_yield_no_tokens(self, text: str) -> None:
        assert tokenize_text(text) == []

    def test_digits_are_tokens(self) -> None:
        assert tokenize_text("contrat 2026 numero AZ4471") == [
            "contrat",
            "2026",
            "numero",
            "az4471",
        ]


@pytest.mark.unit
class TestTokenizeTextCJK:
    """CJK runs are split into overlapping character bigrams."""

    def test_chinese_sentence_is_not_a_single_token(self) -> None:
        tokens = tokenize_text("如何连接我的谷歌日历")
        assert len(tokens) > 1
        assert "如何连接我的谷歌日历" not in tokens

    def test_chinese_run_becomes_overlapping_bigrams(self) -> None:
        assert tokenize_text("谷歌日历") == ["谷歌", "歌日", "日历"]

    def test_overlapping_bigrams_let_a_substring_query_match(self) -> None:
        """The point of bigrams: a query term shares tokens with the document."""
        doc = set(tokenize_text("如何连接我的谷歌日历"))
        query = set(tokenize_text("谷歌日历"))
        assert query & doc == {"谷歌", "歌日", "日历"}

    def test_mixed_cjk_and_latin_keeps_both_forms(self) -> None:
        assert tokenize_text("LIA 支持 6 种语言") == ["lia", "支持", "种语", "语言"]

    def test_isolated_cjk_character_is_kept_whole(self) -> None:
        """A one-character run has no bigram; dropping it would lose the term."""
        assert tokenize_text("中 文") == ["中", "文"]

    def test_punctuation_separates_cjk_runs(self) -> None:
        assert tokenize_text("日历，提醒") == ["日历", "提醒"]

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("カレンダー", ["カレ", "レン", "ンダ", "ダー"]),
            ("일정", ["일정"]),
        ],
        ids=["japanese-katakana", "korean-hangul"],
    )
    def test_other_cjk_scripts_are_covered(self, text: str, expected: list[str]) -> None:
        assert tokenize_text(text) == expected


@pytest.mark.unit
class TestTokenizeTextProperties:
    """Invariants that must hold whatever the script."""

    @pytest.mark.parametrize(
        "text",
        [
            "Comment connecter mon agenda ?",
            "如何连接我的谷歌日历",
            "LIA 支持 6 种语言",
            "L'assistant n'est pas actif",
        ],
    )
    def test_tokenization_is_deterministic(self, text: str) -> None:
        assert tokenize_text(text) == tokenize_text(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Comment CONNECTER mon Agenda ?",
            "如何连接",
            "MiXeD CaSe 语言",
        ],
    )
    def test_output_is_always_lowercase(self, text: str) -> None:
        assert all(t == t.lower() for t in tokenize_text(text))
