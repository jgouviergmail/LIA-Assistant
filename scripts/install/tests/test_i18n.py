"""Wizard i18n contract: every message exists in both wizard languages."""

from __future__ import annotations

import re

from scripts.install.i18n import MESSAGES, msg
from scripts.install.model import WIZARD_LANGUAGES

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def test_every_message_id_exists_in_both_languages() -> None:
    assert WIZARD_LANGUAGES == ("en", "fr")
    for message_id, translations in MESSAGES.items():
        assert set(translations) == set(WIZARD_LANGUAGES), message_id
        for language in WIZARD_LANGUAGES:
            assert translations[language].strip(), f"{message_id}:{language} empty"


def test_placeholders_are_identical_across_languages() -> None:
    for message_id, translations in MESSAGES.items():
        placeholder_sets = {
            language: set(_PLACEHOLDER.findall(text))
            for language, text in translations.items()
        }
        assert (
            placeholder_sets["en"] == placeholder_sets["fr"]
        ), f"{message_id}: placeholder drift {placeholder_sets}"


def test_msg_interpolates_and_rejects_unknown_ids() -> None:
    sample_id = next(iter(MESSAGES))
    assert msg(sample_id, "en") == MESSAGES[sample_id]["en"].format()
    try:
        msg("does_not_exist", "en")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown message id must raise KeyError")
