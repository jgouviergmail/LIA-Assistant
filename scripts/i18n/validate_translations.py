#!/usr/bin/env python3
"""Canonical frontend i18n key-parity validator (single source of truth).

English (``en``) is the reference language: every leaf key in ``en`` must exist
in each other locale, and no locale may declare extra keys. This is the parity
contract documented in ``CLAUDE.md`` and enforced by the pre-commit hook and CI —
both of which invoke this script so there is exactly one implementation.

Design (audit F027, which fixed a broken ``validate-translations.js`` that used a
wrong ``__dirname`` path, omitted ``zh`` and only checked top-level sections):

- **CWD-independent**: the locales directory is resolved from this file's
  location, not the current working directory.
- **All six languages required**: en, fr, de, es, it, zh. A missing locale file
  (the original ``zh`` omission) is a hard error.
- **Recursive parity**: keys are compared as fully-qualified leaf paths.
- **No unrendered placeholder**: a value holding ``{NAME}`` — one brace each
  side — is a variable an edit script never rendered, read as typed by every
  reader (a ``{NB}`` reached the French FAQ on 2026-10-31). i18next's own
  interpolation is ``{{name}}`` and passes. ``scripts/audit/doc_maps.py``
  applies the same rule to the living maps' text.
- **Deterministic exit codes**: ``0`` in sync, ``1`` on any missing language,
  invalid JSON, key drift (missing or extra) or an unrendered placeholder.

Usage::

    python scripts/i18n/validate_translations.py [--locales-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCALES_DIR = REPO_ROOT / "apps" / "web" / "locales"
REFERENCE_LANG = "en"
# Frontend locale codes (Chinese is ``zh`` here — see CLAUDE.md; the backend
# tables use the canonical ``zh-CN``).
REQUIRED_LANGUAGES: tuple[str, ...] = ("en", "fr", "de", "es", "it", "zh")
# ``{NAME}`` with exactly one brace each side; ``{{name}}`` is i18next's.
_UNRENDERED_PLACEHOLDER = re.compile(r"(?<!\{)\{[A-Za-z_][A-Za-z0-9_]*\}(?!\})")


def unrendered_placeholders(text: str) -> list[str]:
    """The script variables a text still carries, as written (``{NB}``)."""
    return _UNRENDERED_PLACEHOLDER.findall(text)


def _leaf_values(obj: object, prefix: str = "") -> Iterator[tuple[str, str]]:
    """Every string leaf of a locale, with its fully-qualified key path."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _leaf_values(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _leaf_values(value, f"{prefix}[{index}]")
    elif isinstance(obj, str):
        yield prefix, obj


def leaf_keys(obj: dict, prefix: str = "") -> set[str]:
    """Return the set of fully-qualified leaf key paths of a nested dict."""
    keys: set[str] = set()
    for key, value in obj.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= leaf_keys(value, full)
        else:
            keys.add(full)
    return keys


def validate(
    locales_dir: Path,
    required_languages: tuple[str, ...] = REQUIRED_LANGUAGES,
    reference_lang: str = REFERENCE_LANG,
) -> list[str]:
    """Validate locale key parity.

    Args:
        locales_dir: Directory holding ``<lang>/translation.json`` files.
        required_languages: Languages that must all be present.
        reference_lang: Language whose keys are the reference set.

    Returns:
        A list of human-readable error strings. Empty means fully in sync.
    """
    errors: list[str] = []
    parsed: dict[str, dict] = {}

    for lang in required_languages:
        path = locales_dir / lang / "translation.json"
        if not path.exists():
            errors.append(f"missing language file: {lang}/translation.json")
            continue
        try:
            parsed[lang] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON in {lang}/translation.json: {exc}")

    if reference_lang not in parsed:
        errors.append(f"reference language '{reference_lang}' unavailable; cannot compare parity")
        return errors

    ref_keys = leaf_keys(parsed[reference_lang])
    for lang in required_languages:
        if lang == reference_lang or lang not in parsed:
            continue
        tgt_keys = leaf_keys(parsed[lang])
        missing = sorted(ref_keys - tgt_keys)
        extra = sorted(tgt_keys - ref_keys)
        if missing:
            errors.append(f"{lang}: {len(missing)} missing keys (e.g. {missing[:5]})")
        if extra:
            errors.append(f"{lang}: {len(extra)} extra keys (e.g. {extra[:5]})")
    for lang, locale in parsed.items():
        for key, value in _leaf_values(locale):
            for placeholder in unrendered_placeholders(value):
                errors.append(f"{lang}: {key} carries an unrendered placeholder {placeholder}")
    return errors


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code (0 ok, 1 on any problem)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--locales-dir",
        type=Path,
        default=DEFAULT_LOCALES_DIR,
        help="Directory of <lang>/translation.json files (default: apps/web/locales).",
    )
    args = parser.parse_args(argv)

    errors = validate(args.locales_dir)
    if errors:
        print("i18n parity check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(
        f"i18n parity OK: all {len(REQUIRED_LANGUAGES)} languages in sync "
        f"with '{REFERENCE_LANG}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
