"""Every JEV usage the registry declares has its words on the screen, in six languages.

The « JEV integrations » screen renders ``settings.admin.jev.usages.<usage>`` and
``settings.admin.jev.usageHelp.<usage>`` by TEMPLATED key, each threshold slider
``settings.admin.jev.gates.<usage>.<gate>`` (ADR-374), and the LLM screen
``settings.admin.llmConfig.types.<slot>``: a usage the locales never learnt shows its
raw key. On 2026-11-06 the two classification usages had no help text in any of the
six languages. The other direction matters too: a key left behind by a retired usage
(ADR-374) is a sentence nothing can show.
"""

from __future__ import annotations

import json

import pytest

from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.domains.llm_config.jev_gates import JEV_GATES
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")

#: How each language names the expected reply (the badge's and the slider's word) and the
#: initiative, so the email usage's words can be read for what they say.
REPLY_WORD = {
    "en": "reply",
    "fr": "réponse",
    "de": "antwort",
    "es": "respuesta",
    "it": "risposta",
    "zh": "回复",
}
INITIATIVE_WORD = {
    "en": "initiative",
    "fr": "initiative",
    "de": "initiative",
    "es": "iniciativa",
    "it": "iniziativa",
    "zh": "主动建议",
}


def _locale(locale: str) -> dict:
    path = repo_root_or_skip() / "apps" / "web" / "locales" / locale / "translation.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("locale", LOCALES)
def test_every_declared_usage_has_its_label_help_and_slot_description(locale: str) -> None:
    data = _locale(locale)
    jev = data["settings"]["admin"]["jev"]
    slots = data["settings"]["admin"]["llmConfig"]["types"]
    missing = [
        key
        for usage, spec in JEV_USAGES.items()
        for key, present in (
            (f"usages.{usage.value}", usage.value in jev["usages"]),
            (f"usageHelp.{usage.value}", usage.value in jev["usageHelp"]),
            (f"llmConfig.types.{spec.llm_type}", spec.llm_type in slots),
        )
        if not present
    ]
    assert missing == [], f"{locale}: no words for {missing}"


@pytest.mark.parametrize("locale", LOCALES)
def test_no_usage_sentence_outlives_its_usage(locale: str) -> None:
    jev = _locale(locale)["settings"]["admin"]["jev"]
    declared = {usage.value for usage in JevUsage}
    stale = sorted((set(jev["usages"]) | set(jev["usageHelp"])) - declared)
    assert stale == [], f"{locale}: sentences for usages the registry no longer declares: {stale}"


@pytest.mark.parametrize("locale", LOCALES)
def test_every_declared_gate_and_only_those_has_its_label(locale: str) -> None:
    labels = _locale(locale)["settings"]["admin"]["jev"].get("gates", {})
    declared = {usage.value: {gate.key for gate in gates} for usage, gates in JEV_GATES.items()}
    present = {usage: set(keys) for usage, keys in labels.items()}
    assert present == declared, f"{locale}: gate labels differ from the declared gates"
    empty = [f"{u}.{k}" for u, keys in labels.items() for k, v in keys.items() if not v.strip()]
    assert empty == [], f"{locale}: empty gate labels {empty}"


@pytest.mark.parametrize("locale", LOCALES)
def test_the_email_usage_names_its_reply_question_wherever_it_is_described(locale: str) -> None:
    """The expected reply rides the email classification switch (ADR-374, lot F).

    The switch, its help and its LLM slot must say so, or nothing on screen tells where
    the question lives. The badge and the slider, which name it already, vouch for the
    word table. The help no longer ties the initiative to e-mails: the evaluator sees
    every tool turn, the e-mail-only gate having been withdrawn on 2026-11-08.
    """
    data = _locale(locale)
    jev = data["settings"]["admin"]["jev"]
    usage = JevUsage.EMAIL_CLASSIFICATION
    texts = {
        "badge": data["classification"]["reply_expected"],
        "slider": jev["gates"][usage.value]["reply_expected"],
        "switch": jev["usages"][usage.value],
        "help": jev["usageHelp"][usage.value],
        "llm slot": data["settings"]["admin"]["llmConfig"]["types"][JEV_USAGES[usage].llm_type],
    }
    reply = REPLY_WORD[locale]
    silent = sorted(name for name, text in texts.items() if reply not in text.lower())
    assert silent == [], f"{locale}: the expected reply is not named in {silent}"

    assert (
        INITIATIVE_WORD[locale] not in texts["help"].lower()
    ), f"{locale}: the help still says an e-mail is what opens the initiative"


def test_the_email_slot_title_names_its_reply_question() -> None:
    """The LLM configuration screen titles each slot with its declared name (English)."""
    slot = JEV_USAGES[JevUsage.EMAIL_CLASSIFICATION].llm_type
    assert "reply" in LLM_TYPES_REGISTRY[slot].display_name.lower()
