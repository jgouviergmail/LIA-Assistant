"""Mixed scripts and adversarial URLs must remain correct and bounded."""

import subprocess
import sys

import pytest

from src.domains.sms.search import tokenize

pytestmark = pytest.mark.unit


def test_long_cjk_run_contains_all_search_terms_of_its_subphrase() -> None:
    assert set(tokenize("明天下午")).issubset(tokenize("明天下午吃饭"))


def test_adjacent_latin_and_cjk_words_keep_both_scripts_searchable() -> None:
    assert "alice" in tokenize("你好Alice明天")


def test_untrusted_url_repetition_cannot_monopolize_a_worker() -> None:
    source = "from src.domains.sms.sensitive_filter import contains_access_secret; print(contains_access_secret('https://x.test/auth' * 3000))"
    result = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, timeout=5, check=True
    )
    assert result.stdout.strip() in {"True", "False"}


def test_lexical_search_is_accent_insensitive() -> None:
    assert tokenize("DÉJEUNER au café") == tokenize("dejeuner au cafe")


def test_supplementary_cjk_characters_remain_segmented() -> None:
    assert set(tokenize("𠀋𠮷")).issubset(tokenize("𠀋𠮷𠮟你好"))
