"""The live vocabulary means the same thing on both sides of the wire (ADR-299).

The banner and the closing card build their keys from what the API sends
(``live.outcome.<outcome>``, ``live.error.<code>``); TypeScript cannot see a
value that arrives in a response, so an outcome the API can emit and the
frontend does not declare is a raw translation key on the screen, and a code
the frontend declares and the API never emits is a label nobody can reach.
The frontend guards its LABELS; this one guards that the two lists are the
same list — the shape of ``test_source_vocabulary_crosses_the_stack.py``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import get_args

import pytest

from src.domains.live import errors
from src.domains.live.schemas import LiveOutcome

pytestmark = pytest.mark.unit

_WEB_LIVE = Path(__file__).resolve().parents[5] / "web" / "src" / "lib" / "live"
_TYPES_FILE = _WEB_LIVE / "types.ts"
_MESSAGE_FILE = _WEB_LIVE / "live-message.ts"
_PROVIDERS_FILE = _WEB_LIVE / "providers.ts"
_ERRORS_FILE = Path(errors.__file__)

#: Refusals the BROWSER raises itself, before any request leaves; the API
#: never names them and must not be asked to.
_CLIENT_ONLY_CODES = {"unsupported_browser"}


def _declared(path: Path, constant: str) -> set[str]:
    """The values one frontend runtime list declares."""
    match = re.search(
        rf"export const {constant} = \[(?P<values>[^\]]*)\] as const;",
        path.read_text(encoding="utf-8"),
    )
    assert match is not None, (
        f"{constant} not found in {path.name} — if the declaration moved, move "
        "this guard with it rather than deleting it"
    )
    return {value.strip().strip("'\"") for value in match["values"].split(",") if value.strip()}


def _backend_codes() -> set[str]:
    """Every ``code=`` a raiser of ``errors.py`` hands ``LiveRefusedError``."""
    tree = ast.parse(_ERRORS_FILE.read_text(encoding="utf-8"))
    codes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "code" and isinstance(keyword.value, ast.Constant):
                codes.add(str(keyword.value.value))
    assert codes, "no coded refusal found in errors.py"
    return codes


class TestTheTwoSidesShareOneVocabulary:
    def test_the_frontend_files_are_where_this_guard_expects_them(self) -> None:
        assert _TYPES_FILE.is_file(), f"{_TYPES_FILE} not found"
        assert _MESSAGE_FILE.is_file(), f"{_MESSAGE_FILE} not found"

    def test_every_outcome_is_the_same_on_both_sides(self) -> None:
        backend = set(get_args(LiveOutcome))
        frontend = _declared(_TYPES_FILE, "LIVE_OUTCOMES")
        assert backend - frontend == set(), (
            f"the API can end a session on {sorted(backend - frontend)} and the "
            "frontend declares no label for it"
        )
        assert frontend - backend == set(), (
            f"the frontend declares {sorted(frontend - backend)} and the API can "
            "never send it — dead vocabulary that reads as supported"
        )

    def test_every_refusal_code_is_the_same_on_both_sides(self) -> None:
        backend = _backend_codes()
        frontend = _declared(_MESSAGE_FILE, "LIVE_ERROR_CODES")
        assert backend - frontend == set(), (
            f"the API can refuse with {sorted(backend - frontend)} and the frontend "
            "would show the generic line instead of its sentence"
        )
        assert frontend - backend == _CLIENT_ONLY_CODES, (
            f"the frontend declares {sorted(frontend - backend - _CLIENT_ONLY_CODES)} "
            "and the API never emits it — declare it client-only with a reason, or drop it"
        )

    def test_the_portal_voice_sentinel_is_the_same_word_on_both_sides(self) -> None:
        # ADR-300 wave 4: a portal-voiced model (an agent) is stored with a
        # voice the API knows and the form never offers; the browser writes it
        # from its own constant, so the two must be one word.
        from src.core.constants import ELEVENLABS_LIVE_PORTAL_VOICE

        match = re.search(
            r"export const LIVE_PORTAL_VOICE = '(?P<word>[^']+)';",
            _PROVIDERS_FILE.read_text(encoding="utf-8"),
        )
        assert match is not None, "LIVE_PORTAL_VOICE not found in providers.ts"
        assert match["word"] == ELEVENLABS_LIVE_PORTAL_VOICE

    def test_every_live_provider_the_api_serves_has_its_row_in_the_browser(self) -> None:
        # A provider the API names in `LiveSessionStart.provider` that the
        # browser has no row (no transport, no brand) for is a session that
        # opens nothing. The connector types travel with the rows.
        from src.domains.live.providers import PROVIDERS

        source = _PROVIDERS_FILE.read_text(encoding="utf-8")
        rows = {
            (m["id"], m["type"])
            for m in re.finditer(r"id: '(?P<id>[^']+)',\s*connectorType: '(?P<type>[^']+)'", source)
        }
        expected = {(p.provider_id, p.connector_type.value) for p in PROVIDERS.values()}
        assert rows == expected

    def test_every_backend_code_has_its_six_sentences(self) -> None:
        from src.core.i18n import SUPPORTED_LANGUAGES
        from src.core.i18n_live import LIVE_PHRASES

        for language in SUPPORTED_LANGUAGES:
            missing = _backend_codes() - set(LIVE_PHRASES[language])
            assert not missing, f"{language} has no sentence for {sorted(missing)}"
