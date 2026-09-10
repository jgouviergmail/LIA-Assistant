"""Every refusal the board can answer with must have a sentence to show.

The API reports a guard failure as a stable machine code and nothing else — no
prose, no language (ADR-276): the frontend translates the code, and a model
rephrases it in the chat. That contract has one failure mode, and it is silent:
a code the service raises but the frontend never learnt renders the GENERIC
sentence, so the person is told « that could not be done » where the board knew
exactly why.

This guard walks the codes the SERVICE and the ROUTER actually raise and holds
each one to an entry in `apps/web/src/lib/workboard/errors.ts`.

The SAME contract binds the other family: `RunError` is what a run that ended
without an answer stores in `last_run_error`, and `core/i18n_workboard`'s own
docstring states that « the board resolves the code from the frontend
locales ». It did not — the card and the detail panel printed the raw string —
so `workboard_assignee_inactive` was read by a person, in English, in all six
languages. One family, one guard, two tables.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

#: Codes that never reach a screen, with the reason each one is exempt.
#:
#: Shrink-only in spirit: an entry leaves this map when a surface starts showing
#: the code, never the reverse without a written reason.
NOT_SHOWN_ON_THE_BOARD: dict[str, str] = {
    "workboard_ambiguous_reference": (
        "raised by `resolve_reference`, which only the chat tools call: the model "
        "rephrases it with the candidate titles, and the board addresses tickets by id"
    ),
}


def _api_source() -> str:
    """Every module of the domain that can raise a refusal at a caller."""
    root = Path(__file__).resolve()
    api = root.parents[4] / "src" / "domains" / "workboard"
    return "\n".join(
        (api / name).read_text(encoding="utf-8")
        for name in ("service.py", "router.py", "repository.py")
    )


def _errors_ts() -> str:
    """The frontend's error tables, as source."""
    root = repo_root_or_skip()
    path = Path(root) / "apps" / "web" / "src" / "lib" / "workboard" / "errors.ts"
    if not path.exists():  # pragma: no cover - the frontend tree is absent
        pytest.skip("apps/web is not checked out beside apps/api")
    return path.read_text(encoding="utf-8")


def _table_keys(table: str) -> set[str]:
    """The codes one declared table maps, read from the source.

    Args:
        table: The exported constant's name.

    Returns:
        Its `workboard_*` keys.
    """
    source = _errors_ts()
    body = source.split(f"{table}: Record<string, string> = {{", 1)
    if len(body) < 2:  # pragma: no cover - the table is missing entirely
        return set()
    return set(re.findall(r"^\s+(workboard_[a-z_]+):", body[1].split("};", 1)[0], re.M))


def _frontend_keys() -> set[str]:
    """The refusal codes the frontend knows how to say."""
    return _table_keys("WORKBOARD_ERROR_KEYS")


def _raised_codes() -> set[str]:
    """The codes the API raises, read from the enum members it names."""
    from src.domains.workboard.constants import WorkboardError

    names = set(re.findall(r"WorkboardError\.([A-Z_]+)", _api_source()))
    return {WorkboardError[name].value for name in names}


class TestEveryRefusalHasASentence:
    def test_no_code_reaches_the_screen_without_a_translation(self) -> None:
        missing = _raised_codes() - _frontend_keys() - set(NOT_SHOWN_ON_THE_BOARD)
        assert not missing, (
            "codes the API raises that the board cannot say: "
            f"{sorted(missing)} — add each to WORKBOARD_ERROR_KEYS with its message"
        )

    def test_the_frontend_declares_no_code_the_api_never_raises(self) -> None:
        """A stale entry is a message nobody can trigger, and a reader of the
        table would take it for a reachable state."""
        stale = _frontend_keys() - _raised_codes()
        # `workboard_not_found` is the 404 the ownership check answers with,
        # raised by the shared raiser rather than by a named enum member.
        assert stale <= {"workboard_not_found"}, sorted(stale - {"workboard_not_found"})

    def test_every_exemption_carries_a_written_reason(self) -> None:
        for code, reason in NOT_SHOWN_ON_THE_BOARD.items():
            assert reason.strip(), code


class TestEveryRunErrorHasASentence:
    """A failed run says WHY, in the reader's language — never its code.

    `last_run_error` carries a typed code and, sometimes, a bounded technical
    message after it. The code is the sentence; the message is evidence for
    whoever wants it. Printing the raw string put `workboard_run_failed:
    TimeoutError…` on a card in six languages.
    """

    @staticmethod
    def _run_codes() -> set[str]:
        from src.domains.workboard.constants import RunError

        return {member.value for member in RunError}

    def test_every_run_error_has_a_translation(self) -> None:
        missing = self._run_codes() - _table_keys("WORKBOARD_RUN_ERROR_KEYS")
        assert not missing, (
            "run failures the board cannot say: "
            f"{sorted(missing)} — add each to WORKBOARD_RUN_ERROR_KEYS"
        )

    def test_the_frontend_declares_no_run_error_the_api_never_stores(self) -> None:
        stale = _table_keys("WORKBOARD_RUN_ERROR_KEYS") - self._run_codes()
        assert not stale, sorted(stale)

    def test_the_two_families_never_share_a_code(self) -> None:
        """A refusal and a failed run are different sentences: one code
        answering to two tables is one of them shown in the wrong place."""
        assert not (_frontend_keys() & _table_keys("WORKBOARD_RUN_ERROR_KEYS"))
