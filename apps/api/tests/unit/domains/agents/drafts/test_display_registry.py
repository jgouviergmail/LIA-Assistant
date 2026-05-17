"""Unit tests for the Draft Display Registry (ADR-085).

Covers:

- Registry completeness: every ``DraftType`` has an entry.
- ``assert_registry_completeness`` behavior.
- i18n parity: ``noun_key`` and ``verb_past_key`` resolve in all 6 supported
  languages.
- ``get_plural_form`` rules per language (special-case French zero,
  Chinese invariance).
- ``compose_result_header`` snapshots per language and grammar (gender +
  number agreement).
- ``resolve_nested_value`` dotted-path resolver.
- Existence of ``reminder_delete`` entries in the legacy success/cancel
  message tables (regression guard for the original bug).
"""

from __future__ import annotations

import pytest

from src.core.i18n_drafts import (
    DRAFT_CANCEL_MESSAGES,
    DRAFT_RESULT_NOUNS,
    DRAFT_RESULT_VERBS_PAST,
    DRAFT_SUCCESS_MESSAGES,
    RESULT_HEADER_TEMPLATES,
    compose_result_header,
    get_plural_form,
)
from src.domains.agents.drafts.display import (
    DRAFT_DISPLAY_REGISTRY,
    DraftDisplayConfig,
    assert_registry_completeness,
    get_draft_display_config,
    get_draft_emoji,
    resolve_nested_value,
)
from src.domains.agents.drafts.models import DraftType

# The 6 supported languages — kept local to avoid a fragile import path.
ALL_LANGUAGES: tuple[str, ...] = ("fr", "en", "es", "de", "it", "zh-CN")


# =============================================================================
# (a) Registry completeness
# =============================================================================


@pytest.mark.parametrize("draft_type", list(DraftType))
def test_every_draft_type_has_display_config(draft_type: DraftType) -> None:
    """Every ``DraftType`` value has an entry in the display registry."""
    assert (
        draft_type in DRAFT_DISPLAY_REGISTRY
    ), f"DraftType.{draft_type.name} is missing from DRAFT_DISPLAY_REGISTRY"


def test_assert_registry_completeness_passes_with_full_registry() -> None:
    """The assertion runs without raising when every type is registered."""
    assert_registry_completeness()


def test_assert_registry_completeness_fails_when_type_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The assertion raises with a useful message when an entry is missing."""
    # Remove one entry under a monkeypatched copy so the registry itself is unchanged.
    incomplete = dict(DRAFT_DISPLAY_REGISTRY)
    incomplete.pop(DraftType.REMINDER_DELETE)
    monkeypatch.setattr(
        "src.domains.agents.drafts.display.DRAFT_DISPLAY_REGISTRY",
        incomplete,
    )

    with pytest.raises(AssertionError, match="reminder_delete"):
        assert_registry_completeness()


@pytest.mark.parametrize("draft_type", list(DraftType))
def test_display_config_invariants(draft_type: DraftType) -> None:
    """Each config has a non-empty emoji, at least one label field, and a noun/verb pair."""
    cfg = DRAFT_DISPLAY_REGISTRY[draft_type]
    assert isinstance(cfg, DraftDisplayConfig)
    assert cfg.emoji.strip(), f"{draft_type.value}: emoji is empty"
    assert cfg.item_label_fields, f"{draft_type.value}: item_label_fields is empty"
    assert cfg.noun_key, f"{draft_type.value}: noun_key is empty"
    assert cfg.verb_past_key, f"{draft_type.value}: verb_past_key is empty"


# =============================================================================
# (b) i18n parity — noun and verb keys resolve in every supported language
# =============================================================================


@pytest.mark.parametrize("language", ALL_LANGUAGES)
@pytest.mark.parametrize("draft_type", list(DraftType))
def test_registry_noun_resolves_in_every_language(language: str, draft_type: DraftType) -> None:
    """``noun_key`` declared by every config exists in every language."""
    cfg = DRAFT_DISPLAY_REGISTRY[draft_type]
    nouns = DRAFT_RESULT_NOUNS[language]  # type: ignore[index]
    assert (
        cfg.noun_key in nouns
    ), f"{draft_type.value}: noun_key '{cfg.noun_key}' missing in DRAFT_RESULT_NOUNS[{language}]"
    entry = nouns[cfg.noun_key]
    assert (
        "singular" in entry and "plural" in entry
    ), f"{draft_type.value} / {language}: noun entry missing singular/plural"


@pytest.mark.parametrize("language", ALL_LANGUAGES)
@pytest.mark.parametrize("draft_type", list(DraftType))
def test_registry_verb_resolves_in_every_language(language: str, draft_type: DraftType) -> None:
    """``verb_past_key`` declared by every config exists in every language."""
    cfg = DRAFT_DISPLAY_REGISTRY[draft_type]
    verbs = DRAFT_RESULT_VERBS_PAST[language]  # type: ignore[index]
    assert cfg.verb_past_key in verbs, (
        f"{draft_type.value}: verb_past_key '{cfg.verb_past_key}' missing in "
        f"DRAFT_RESULT_VERBS_PAST[{language}]"
    )


@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_result_header_template_exists_for_every_language(language: str) -> None:
    """Every supported language declares a header template with the required placeholders."""
    template = RESULT_HEADER_TEMPLATES[language]  # type: ignore[index]
    assert "{count}" in template, f"{language}: template missing {{count}}"
    assert "{noun}" in template, f"{language}: template missing {{noun}}"
    assert "{verb}" in template, f"{language}: template missing {{verb}}"


@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_gender_field_present_for_agreement_languages(language: str) -> None:
    """Languages with participle agreement (fr/es/it) declare a gender on every noun."""
    needs_gender = language in {"fr", "es", "it"}
    nouns = DRAFT_RESULT_NOUNS[language]  # type: ignore[index]
    for noun_key, entry in nouns.items():
        if needs_gender:
            assert "gender" in entry, (
                f"{language}: noun '{noun_key}' missing 'gender' field "
                "required for participle agreement"
            )
            assert entry["gender"] in {
                "m",
                "f",
            }, f"{language}: noun '{noun_key}' has invalid gender '{entry['gender']}'"


@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_verb_forms_complete_for_agreement_languages(language: str) -> None:
    """For fr/es/it, every verb declares all 4 gender/number forms."""
    needs_agreement = language in {"fr", "es", "it"}
    verbs = DRAFT_RESULT_VERBS_PAST[language]  # type: ignore[index]
    expected_keys = {"m_sing", "m_plur", "f_sing", "f_plur"}
    for verb_key, entry in verbs.items():
        if needs_agreement:
            assert isinstance(
                entry, dict
            ), f"{language}: verb '{verb_key}' should be a dict with gender/number forms"
            missing = expected_keys - set(entry.keys())
            assert not missing, f"{language}: verb '{verb_key}' missing forms: {sorted(missing)}"
        else:
            assert isinstance(
                entry, str
            ), f"{language}: verb '{verb_key}' should be invariant (str) — got {type(entry).__name__}"


# =============================================================================
# (c) Pluralization rules
# =============================================================================


@pytest.mark.parametrize(
    "language,count,expected",
    [
        # French: 0 and 1 are singular; ≥2 plural.
        ("fr", 0, "singular"),
        ("fr", 1, "singular"),
        ("fr", 2, "plural"),
        ("fr", 100, "plural"),
        # English: 1 singular; everything else plural.
        ("en", 0, "plural"),
        ("en", 1, "singular"),
        ("en", 2, "plural"),
        # Spanish/German/Italian: same as English.
        ("es", 0, "plural"),
        ("es", 1, "singular"),
        ("es", 2, "plural"),
        ("de", 0, "plural"),
        ("de", 1, "singular"),
        ("de", 2, "plural"),
        ("it", 0, "plural"),
        ("it", 1, "singular"),
        ("it", 2, "plural"),
        # Chinese: invariant; always returns "singular" as a no-op label.
        ("zh-CN", 0, "singular"),
        ("zh-CN", 1, "singular"),
        ("zh-CN", 100, "singular"),
    ],
)
def test_get_plural_form(language: str, count: int, expected: str) -> None:
    """Pluralization rules per language."""
    assert get_plural_form(count, language) == expected


def test_get_plural_form_normalizes_language() -> None:
    """Variant codes like ``zh`` and ``fr-FR`` resolve to the supported language."""
    assert get_plural_form(3, "zh") == "singular"
    assert get_plural_form(3, "fr-FR") == "plural"
    assert get_plural_form(0, "fr_CA") == "singular"
    # Unknown language falls back to default (fr).
    assert get_plural_form(0, "ja") == "singular"


# =============================================================================
# (d) Header composition — snapshot tests per language and grammar pattern
# =============================================================================


@pytest.mark.parametrize(
    "language,success,total,noun_key,verb_key,expected",
    [
        # French — masculine + plural agreement
        ("fr", 3, 3, "reminder", "deleted", "3 rappels supprimés"),
        ("fr", 1, 1, "reminder", "deleted", "1 rappel supprimé"),
        ("fr", 0, 0, "reminder", "deleted", "0 rappel supprimé"),
        # French — feminine + agreement (tâche/créée/créées)
        ("fr", 1, 1, "task", "created", "1 tâche créée"),
        ("fr", 3, 3, "task", "created", "3 tâches créées"),
        # French — partial result; agreement on total
        ("fr", 2, 3, "email", "sent", "2/3 emails envoyés"),
        # English — invariant participle
        ("en", 3, 3, "reminder", "deleted", "3 reminders deleted"),
        ("en", 1, 1, "reminder", "deleted", "1 reminder deleted"),
        ("en", 0, 0, "reminder", "deleted", "0 reminders deleted"),
        ("en", 2, 3, "email", "sent", "2/3 emails sent"),
        # Spanish — feminine agreement
        ("es", 1, 1, "task", "created", "1 tarea creada"),
        ("es", 3, 3, "task", "created", "3 tareas creadas"),
        ("es", 3, 3, "reminder", "deleted", "3 recordatorios eliminados"),
        # German — invariant participle, noun changes form
        ("de", 1, 1, "event", "deleted", "1 Termin gelöscht"),
        ("de", 3, 3, "event", "deleted", "3 Termine gelöscht"),
        # Italian — feminine invariant for number, verb still agrees
        ("it", 1, 1, "task", "created", "1 attività creata"),
        ("it", 3, 3, "task", "created", "3 attività create"),
        ("it", 3, 3, "reminder", "deleted", "3 promemoria eliminati"),
        # Chinese — different word order, no grammar
        ("zh-CN", 3, 3, "reminder", "deleted", "已删除 3 个提醒"),
        ("zh-CN", 1, 1, "reminder", "deleted", "已删除 1 个提醒"),
        ("zh-CN", 2, 3, "reminder", "deleted", "已删除 2/3 个提醒"),
    ],
)
def test_compose_result_header_snapshots(
    language: str, success: int, total: int, noun_key: str, verb_key: str, expected: str
) -> None:
    """End-to-end grammatical agreement per language."""
    assert compose_result_header(success, total, noun_key, verb_key, language) == expected


# =============================================================================
# (e) Public helper APIs
# =============================================================================


def test_get_draft_display_config_returns_none_for_unknown() -> None:
    """Unknown draft types return ``None`` rather than raising."""
    assert get_draft_display_config("totally_unknown_type") is None
    assert get_draft_display_config("") is None


def test_get_draft_display_config_returns_config_for_known() -> None:
    """Known draft types return the registered config."""
    cfg = get_draft_display_config(DraftType.REMINDER_DELETE.value)
    assert cfg is not None
    assert cfg.noun_key == "reminder"
    assert cfg.verb_past_key == "deleted"


def test_get_draft_emoji_returns_empty_for_unknown() -> None:
    """``get_draft_emoji`` returns ``""`` for unknown types (matches legacy)."""
    assert get_draft_emoji("not_a_real_type") == ""


def test_get_draft_emoji_returns_registered_emoji() -> None:
    """``get_draft_emoji`` returns the registered emoji for known types."""
    emoji = get_draft_emoji(DraftType.REMINDER_DELETE.value)
    assert emoji  # non-empty
    assert "🔔" in emoji


# =============================================================================
# (f) Nested resolution helper
# =============================================================================


def test_resolve_nested_value_flat_key() -> None:
    """Flat keys resolve like a normal dict lookup."""
    assert resolve_nested_value({"a": 1}, "a") == 1


def test_resolve_nested_value_nested_dict() -> None:
    """Dotted keys walk nested dicts."""
    assert resolve_nested_value({"file": {"name": "report.pdf"}}, "file.name") == "report.pdf"


def test_resolve_nested_value_list_index() -> None:
    """Numeric segments index into lists."""
    assert resolve_nested_value({"a": [{"b": 1}, {"b": 2}]}, "a.0.b") == 1
    assert resolve_nested_value({"a": [{"b": 1}, {"b": 2}]}, "a.1.b") == 2


def test_resolve_nested_value_missing_path_returns_none() -> None:
    """Missing segments cleanly return ``None``."""
    assert resolve_nested_value({"a": 1}, "a.b") is None
    assert resolve_nested_value({"a": {"b": 1}}, "a.c") is None
    assert resolve_nested_value({"a": [1]}, "a.5") is None


# =============================================================================
# (g) Regression guards for the original bug (reminder fallback to _default)
# =============================================================================


@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_reminder_delete_has_success_message_in_every_language(language: str) -> None:
    """``reminder_delete`` no longer falls back to the bland ``_default`` message."""
    messages = DRAFT_SUCCESS_MESSAGES[language]  # type: ignore[index]
    assert (
        "reminder_delete" in messages
    ), f"{language}: 'reminder_delete' missing — would fall back to '_default'"
    assert messages["reminder_delete"] != messages["_default"]


@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_reminder_delete_has_cancel_message_in_every_language(language: str) -> None:
    """``reminder_delete`` has a dedicated cancel message in every language."""
    messages = DRAFT_CANCEL_MESSAGES[language]  # type: ignore[index]
    assert "reminder_delete" in messages
