"""Who decides whether LIA asks before a personal MCP tool, and who drives a server.

Spec 2026-10-30 (D1, D4, D9): a tool's confirmation is decided by the first level
that says something — its server, the account, the instance — and the ReAct shape of
an iterative server by its own choice, else the instance default. Both are resolved
by ONE module, so the page, the synthesis and a run cannot disagree about a default.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest

from src.core.config import settings
from src.infrastructure.mcp.confirmation import (
    ConfirmationReason,
    ConfirmationSource,
    ServerConfirmation,
    confirmation_reason,
    declaration_reason,
    declared_tool_category,
    effective_react_expand,
    instance_confirmation,
    resolve_server_confirmation,
)

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"


class TestServerConfirmation:
    @pytest.mark.parametrize(
        ("server", "account", "instance", "expected"),
        [
            (True, False, False, ServerConfirmation(True, ConfirmationSource.SERVER)),
            (False, True, True, ServerConfirmation(False, ConfirmationSource.SERVER)),
            (None, True, False, ServerConfirmation(True, ConfirmationSource.ACCOUNT)),
            (None, False, True, ServerConfirmation(False, ConfirmationSource.ACCOUNT)),
            (None, None, True, ServerConfirmation(True, ConfirmationSource.INSTANCE)),
            (None, None, False, ServerConfirmation(False, ConfirmationSource.INSTANCE)),
        ],
    )
    def test_the_first_level_that_says_something_decides(
        self,
        monkeypatch: pytest.MonkeyPatch,
        server: bool | None,
        account: bool | None,
        instance: bool,
        expected: ServerConfirmation,
    ) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", instance)

        assert resolve_server_confirmation(server, account) == expected

    def test_an_unreadable_value_falls_through_rather_than_failing_a_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Forgiving on read (the exchange rhythm's doctrine): writes are strict."""
        monkeypatch.setattr(settings, "mcp_hitl_required", True)

        resolved = resolve_server_confirmation("yes", object())  # type: ignore[arg-type]

        assert resolved == ServerConfirmation(True, ConfirmationSource.INSTANCE)

    def test_the_instance_value_is_the_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "mcp_hitl_required", True)
        assert instance_confirmation() is True
        monkeypatch.setattr(settings, "mcp_hitl_required", False)
        assert instance_confirmation() is False


class TestReactShape:
    @pytest.mark.parametrize("instance", [True, False])
    def test_a_server_that_never_chose_follows_the_instance(
        self, monkeypatch: pytest.MonkeyPatch, instance: bool
    ) -> None:
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", instance)

        assert effective_react_expand(None) is instance

    @pytest.mark.parametrize(("choice", "instance"), [(True, False), (False, True)])
    def test_a_server_s_own_choice_wins(
        self, monkeypatch: pytest.MonkeyPatch, choice: bool, instance: bool
    ) -> None:
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", instance)

        assert effective_react_expand(choice) is choice

    def test_an_unreadable_choice_follows_the_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", False)

        assert effective_react_expand("direct") is False  # type: ignore[arg-type]


_HINT_VALUES: tuple[object, ...] = (True, False, None, "absent")


def _annotations(read_only: object, destructive: object) -> dict[str, object]:
    hints: dict[str, object] = {}
    if read_only != "absent":
        hints["read_only_hint"] = read_only
    if destructive != "absent":
        hints["destructive_hint"] = destructive
    return hints


class TestDeclarationReason:
    @pytest.mark.parametrize(
        ("read_only", "destructive", "expected"),
        [
            (False, True, ConfirmationReason.DECLARED_DESTRUCTIVE),
            ("absent", True, ConfirmationReason.DECLARED_DESTRUCTIVE),
            (True, True, ConfirmationReason.DECLARED_DESTRUCTIVE),
            (False, "absent", ConfirmationReason.DECLARED_MODIFYING),
            (False, None, ConfirmationReason.DECLARED_MODIFYING),
            (False, False, ConfirmationReason.DECLARED_ADDITIVE),
            (True, "absent", ConfirmationReason.DECLARED_READ_ONLY),
            (True, False, ConfirmationReason.DECLARED_READ_ONLY),
            ("absent", "absent", ConfirmationReason.NOT_DECLARED),
            ("absent", False, ConfirmationReason.NOT_DECLARED),
        ],
    )
    def test_each_declaration_has_its_reason(
        self, read_only: object, destructive: object, expected: ConfirmationReason
    ) -> None:
        assert declaration_reason(_annotations(read_only, destructive)) == expected

    def test_a_malformed_declaration_declares_nothing(self) -> None:
        assert declaration_reason(None) == ConfirmationReason.NOT_DECLARED
        assert declaration_reason(["destructive"]) == ConfirmationReason.NOT_DECLARED

    @pytest.mark.parametrize(
        ("read_only", "destructive"), list(itertools.product(_HINT_VALUES, _HINT_VALUES))
    )
    def test_the_reason_never_contradicts_the_category_the_manifest_carries(
        self, read_only: object, destructive: object
    ) -> None:
        """One reading of a declaration: the reason says what the category acts on."""
        annotations = _annotations(read_only, destructive)
        reason = declaration_reason(annotations)
        category = declared_tool_category(annotations)

        expected = {
            ConfirmationReason.DECLARED_DESTRUCTIVE: "delete",
            ConfirmationReason.DECLARED_MODIFYING: "delete",
            ConfirmationReason.DECLARED_ADDITIVE: "update",
            ConfirmationReason.DECLARED_READ_ONLY: None,
            ConfirmationReason.NOT_DECLARED: None,
        }[reason]
        assert category == expected


class TestConfirmationReason:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            (ConfirmationSource.SERVER, ConfirmationReason.SERVER_ALWAYS),
            (ConfirmationSource.ACCOUNT, ConfirmationReason.ACCOUNT_ALWAYS),
            (ConfirmationSource.INSTANCE, ConfirmationReason.INSTANCE_ALWAYS),
        ],
    )
    def test_always_names_the_level_that_asked_for_it(
        self, source: ConfirmationSource, expected: ConfirmationReason
    ) -> None:
        reason = confirmation_reason(ServerConfirmation(True, source), {"read_only_hint": True})

        assert reason == expected

    def test_as_declared_names_the_declaration(self) -> None:
        reason = confirmation_reason(
            ServerConfirmation(False, ConfirmationSource.ACCOUNT), {"destructive_hint": True}
        )

        assert reason == ConfirmationReason.DECLARED_DESTRUCTIVE


def _setting_reads(source: str, setting: str) -> list[int]:
    """Lines reading ``settings.<setting>`` or ``getattr(settings, "<setting>", …)``."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == setting
            and isinstance(node.value, ast.Name)
            and node.value.id == "settings"
        ):
            lines.append(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "settings"
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == setting
        ):
            lines.append(node.lineno)
    return lines


class TestOneReaderOfEachDefault:
    """A default read in two places is two defaults the day one of them changes."""

    @pytest.mark.parametrize("setting", ["mcp_hitl_required", "react_mcp_expand_iterative_enabled"])
    def test_only_the_resolution_reads_the_instance_default(self, setting: str) -> None:
        owner = "infrastructure/mcp/confirmation.py"
        assert (_SRC / owner).is_file()  # a wrong root would pass on nothing
        offenders = [
            f"{path.relative_to(_SRC).as_posix()}:{line}"
            for path in _SRC.rglob("*.py")
            if path.relative_to(_SRC).as_posix() != owner
            and setting in (text := path.read_text(encoding="utf-8"))
            for line in _setting_reads(text, setting)
        ]

        assert offenders == []

    def test_the_guard_sees_both_shapes_of_a_read(self) -> None:
        assert _setting_reads("x = settings.mcp_hitl_required\n", "mcp_hitl_required") == [1]
        assert _setting_reads(
            'x = getattr(settings, "mcp_hitl_required", True)\n', "mcp_hitl_required"
        ) == [1]
        assert _setting_reads("x = user.mcp_hitl_required\n", "mcp_hitl_required") == []
