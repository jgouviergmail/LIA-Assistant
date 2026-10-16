"""Every code a confirmation card can receive is worded, or declared generic.

On a confirmation no model writes the answer: the execution card IS the answer
(ADR-303 amendment 2026-10-14), and it reads ``refusal_message``, which reads
``core/i18n_draft_refusals``. Until 2026-10-14 a code nobody had worded reached
the card as its raw letters (« SCHEMA_CHANGED », « CONFIRMATION_MISSING »); a
code an owner adds tomorrow would read the generic sentence in silence. This
census walks the sources that produce a draft refusal and refuses a code that is
neither worded nor declared generic with its reason — and a vocabulary entry no
source produces any more.

What it reads, by AST (nothing is imported or executed):

- ``CommandRejected(...)``, ``LiveConnectorSettingsRefused(...)`` and the send
  tool's ``_refused(...)``: their first argument;
- ``_failed_outcome(...)``: its third argument; in the application commands
  (ADR-339), any ``error_code=`` keyword;
- anywhere in the sources, a dict literal carrying ``success: False`` and an
  ``error_code`` — the refusal shape an executor returns;
- what ``application_access_error_code`` projects an authorization failure to.

A string, a conditional between two strings, an ``or`` default and a name bound
to a module-level string are all read. A code computed at run time cannot be
seen: those are declared in ``_RUNTIME_CODES`` with the place they come from.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.core.i18n_draft_refusals import GENERIC_REFUSAL_CODES, WORDED_REFUSAL_CODES

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"

#: Where a draft refusal is produced: the agents domain (its executors, the
#: effect gate, the application commands), the live preference gateway the
#: application commands call, and the SMTP outcome a send failure carries.
_SOURCES = (
    _SRC / "domains" / "agents",
    _SRC / "domains" / "live" / "connector_preference_gateway.py",
    _SRC / "infrastructure" / "email" / "smtp_outcome.py",
)
_APPLICATION = _SRC / "domains" / "agents" / "application"

#: Callables whose first argument IS the refusal code.
_CODE_FIRST = frozenset({"CommandRejected", "LiveConnectorSettingsRefused", "_refused"})

#: Codes no literal carries, each with the place it comes from at run time.
_RUNTIME_CODES = {
    "CANCELLED": (
        "application/command_service.validate_execution projects a cancelled command's "
        "ApplicationPhase.value.upper(); confirmation must not replay it"
    ),
    "instance_budget_exhausted": (
        "UsageLimitExceededError.error_code (INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE), "
        "read by the application commands' usage-limit branch"
    ),
    "CONNECTOR_NOT_ACTIVATED": (
        "tools/common.connector_not_activated_refusal; refusal_message names the "
        "connector itself rather than reading the vocabulary"
    ),
}


def _python_files() -> Iterator[Path]:
    for source in _SOURCES:
        if source.is_file():
            yield source
        else:
            yield from sorted(source.rglob("*.py"))


def _module_strings(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "value"`` and ``NAME: T = "value"`` bindings."""
    strings: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value.value, str):
                    strings[target.id] = node.value.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            strings[node.target.id] = node.value.value
    return strings


def _codes_in(node: ast.expr | None, strings: dict[str, str]) -> set[str]:
    """The string codes an expression can evaluate to."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name) and node.id in strings:
        return {strings[node.id]}
    if isinstance(node, ast.IfExp):
        return _codes_in(node.body, strings) | _codes_in(node.orelse, strings)
    if isinstance(node, ast.BoolOp):
        return set().union(*(_codes_in(value, strings) for value in node.values))
    return set()


def _callee(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _key(node: ast.expr | None) -> str | None:
    """A dict key as the field it names: a literal or a ``FIELD_*`` constant."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return {"FIELD_SUCCESS": "success", "FIELD_ERROR_CODE": "error_code"}.get(node.id)
    return None


def _refusal_dict_codes(node: ast.Dict, strings: dict[str, str]) -> set[str]:
    fields = {_key(key): value for key, value in zip(node.keys, node.values, strict=True)}
    refused = fields.get("success")
    if not (isinstance(refused, ast.Constant) and refused.value is False):
        return set()
    return _codes_in(fields.get("error_code"), strings)


def _projected_access_codes(tree: ast.Module) -> set[str]:
    """What ``application_access_error_code`` returns for an authorization failure."""
    codes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "application_access_error_code":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Return):
                    codes |= _codes_in(inner.value, {})
    return codes


def _census() -> dict[str, set[str]]:
    """Every refusal code a source produces, with the files producing it."""
    found: dict[str, set[str]] = {}
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        strings = _module_strings(tree)
        in_application = _APPLICATION in path.parents
        codes: set[str] = _projected_access_codes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                codes |= _refusal_dict_codes(node, strings)
            elif isinstance(node, ast.Call):
                callee = _callee(node)
                if callee in _CODE_FIRST and node.args:
                    codes |= _codes_in(node.args[0], strings)
                elif callee == "_failed_outcome" and len(node.args) >= 3:
                    codes |= _codes_in(node.args[2], strings)
                if in_application:
                    for keyword in node.keywords:
                        if keyword.arg == "error_code":
                            codes |= _codes_in(keyword.value, strings)
        for code in codes:
            found.setdefault(code, set()).add(path.relative_to(_SRC).as_posix())
    return found


_CENSUS = _census()


class TestTheCensusReadsTheProducers:
    """Guards against scan rot: an empty census would make every rule pass."""

    @pytest.mark.parametrize(
        "code",
        [
            "CONFIRMATION_MISSING",  # the effect gate's dict
            "STALE_STATE",  # CommandRejected
            "RESOURCE_BUSY",  # a conditional inside CommandRejected
            "USAGE_LIMIT_EXCEEDED",  # an ``or`` default in _failed_outcome
            "INTERACTION_EXPIRED",  # an error_code= keyword
            "DRAFT_CHANGED",  # a Final constant through _refused
            "PARTIAL_SEND",  # the SMTP outcome's dict
            "EXTERNAL_API_ERROR",  # the live preference gateway
            "CANCELLATION_UNAVAILABLE",  # the dispatcher's cancel refusal
            "FORBIDDEN",  # the authorization projection
        ],
    )
    def test_a_known_producer_is_seen(self, code: str) -> None:
        assert code in _CENSUS


class TestEveryProducedCodeIsDecided:
    def test_no_code_reaches_the_card_undecided(self) -> None:
        decided = WORDED_REFUSAL_CODES | set(GENERIC_REFUSAL_CODES) | set(_RUNTIME_CODES)
        undecided = {code: sorted(files) for code, files in _CENSUS.items() if code not in decided}
        assert not undecided, (
            "A refusal code reaches the confirmation card with no sentence: word it in "
            f"core/i18n_draft_refusals.py or declare it generic with its reason: {undecided}"
        )

    def test_a_runtime_code_is_worded_or_said_by_the_card_itself(self) -> None:
        said_by_card = {"CONNECTOR_NOT_ACTIVATED"}
        assert set(_RUNTIME_CODES) <= (
            WORDED_REFUSAL_CODES | set(GENERIC_REFUSAL_CODES) | said_by_card
        )


class TestNoEntryOutlivesItsProducer:
    def test_every_worded_or_generic_code_is_still_produced(self) -> None:
        declared = WORDED_REFUSAL_CODES | set(GENERIC_REFUSAL_CODES)
        stale = sorted(declared - set(_CENSUS) - set(_RUNTIME_CODES))
        assert not stale, f"These codes are produced nowhere any more: {stale}"
