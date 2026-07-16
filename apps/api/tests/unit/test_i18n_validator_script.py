"""Tests for the canonical frontend i18n parity validator (audit F027).

``scripts/i18n/validate_translations.py`` is the single source of truth used by
the pre-commit hook and CI. The previous ``validate-translations.js`` was broken
(wrong ``__dirname`` path, omitted ``zh``, shallow section-only check). This
suite pins the real contract: CWD-independent, all six languages required,
recursive key parity, deterministic errors — and JSON/CWD robustness.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
VALIDATOR_PATH = REPO_ROOT / "scripts" / "i18n" / "validate_translations.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_translations", VALIDATOR_PATH)
    assert spec and spec.loader, f"cannot load validator at {VALIDATOR_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def _write_locale(locales_dir: Path, lang: str, payload: object) -> None:
    lang_dir = locales_dir / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    (lang_dir / "translation.json").write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )


def _all_langs(locales_dir: Path, payload: dict) -> None:
    for lang in validator.REQUIRED_LANGUAGES:
        _write_locale(locales_dir, lang, payload)


def test_identical_locales_pass(tmp_path):
    """All six languages with identical key sets → no errors."""
    _all_langs(tmp_path, {"a": {"b": "x"}, "c": "y"})
    assert validator.validate(tmp_path) == []


def test_missing_language_dir_fails(tmp_path):
    """A missing language (e.g. zh omitted) is reported — the exact F027 defect."""
    for lang in validator.REQUIRED_LANGUAGES:
        if lang == "zh":
            continue
        _write_locale(tmp_path, lang, {"a": "x"})
    errors = validator.validate(tmp_path)
    assert any("zh" in e for e in errors), errors


def test_missing_key_fails(tmp_path):
    """A key present in en but absent in fr fails parity."""
    _all_langs(tmp_path, {"a": "x", "b": "y"})
    _write_locale(tmp_path, "fr", {"a": "x"})  # missing "b"
    errors = validator.validate(tmp_path)
    assert any("fr" in e and "missing" in e for e in errors), errors


def test_extra_key_fails(tmp_path):
    """A key present in de but absent in en fails parity (strict, per CLAUDE.md)."""
    _all_langs(tmp_path, {"a": "x"})
    _write_locale(tmp_path, "de", {"a": "x", "z": "extra"})
    errors = validator.validate(tmp_path)
    assert any("de" in e and "extra" in e for e in errors), errors


def test_invalid_json_fails(tmp_path):
    """Malformed JSON is reported, not silently skipped."""
    _all_langs(tmp_path, {"a": "x"})
    _write_locale(tmp_path, "it", "{not: valid json,,}")
    errors = validator.validate(tmp_path)
    assert any("it" in e and "JSON" in e for e in errors), errors


def test_real_locales_pass_from_two_cwds(tmp_path, monkeypatch):
    """Default path resolves from __file__: real locales pass from any CWD."""
    # From the repo root
    monkeypatch.chdir(REPO_ROOT)
    assert validator.validate(validator.DEFAULT_LOCALES_DIR) == []
    # From an unrelated temp directory — same result (CWD-independent)
    monkeypatch.chdir(tmp_path)
    assert validator.validate(validator.DEFAULT_LOCALES_DIR) == []


def test_main_exit_codes(tmp_path):
    """main() returns 0 on success and 1 on any parity error."""
    _all_langs(tmp_path, {"a": "x"})
    assert validator.main(["--locales-dir", str(tmp_path)]) == 0
    _write_locale(tmp_path, "fr", {"a": "x", "b": "extra"})
    assert validator.main(["--locales-dir", str(tmp_path)]) == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
