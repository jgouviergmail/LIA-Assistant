"""Every out-of-turn surface says who asked — none of them may be guessed.

``track_proactive_tokens`` is named for the funnel, not for the initiative, and
the two are not the same thing. Verified 2026-09-07 by reading the call graph
rather than the name:

- the **briefing** is reached only from ``GET /briefing/*`` and from chat
  suggestions — no scheduler calls it. A request arrived; nobody took an
  initiative. (It runs 154 times between 02:00 and 07:00 Paris over fourteen
  days, which says a client refreshes at night, not that LIA decided to.)
- a **reminder** is the person's own instruction, fired later: that is
  ``scheduled``, the value the routines already use.
- the **heartbeat** and the interest sweeps come from the proactive runner:
  those, and only those, are LIA's own initiative.

A default would have quietly filed all three the same way. So the parameter is
required, and this guard refuses any call site that omits it — the ADR-085
doctrine (a silent fallback on an unknown key is how a feature dies invisibly)
applied to the register's authorship.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"

_FUNNELS = {"track_proactive_tokens", "track_proactive_tokens_from_result"}


def _calls_missing_source() -> list[str]:
    """Every call to the funnel that does not name its origin."""
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        if path.name == "tracking.py" and path.parent.name == "proactive":
            continue  # the funnel's own definition and its docstring examples
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError, UnicodeDecodeError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in _FUNNELS:
                continue
            if not any(kw.arg == "source" for kw in node.keywords):
                relative = path.relative_to(_SRC).as_posix()
                offenders.append(f"{relative}:{node.lineno}")
    return sorted(offenders)


class TestNoSurfaceLeavesItsAuthorshipToADefault:
    """The register's authorship is declared at every call site."""

    def test_every_call_names_its_source(self) -> None:
        offenders = _calls_missing_source()
        assert not offenders, (
            "out-of-turn spend recorded without saying who asked: "
            f"{offenders} — pass source=EffectSource.<USER|SCHEDULED|PROACTIVE>.value. "
            "The funnel is named for the plumbing, not for the initiative: a "
            "briefing is a request, a reminder is the person's own deferred "
            "instruction, only a runner sweep is LIA's own idea."
        )

    def test_the_funnel_refuses_to_guess(self) -> None:
        """``source`` has no default, so omitting it is a TypeError, not a lie."""
        import inspect

        from src.infrastructure.proactive.tracking import track_proactive_tokens

        parameter = inspect.signature(track_proactive_tokens).parameters["source"]
        assert parameter.default is inspect.Parameter.empty


class TestTheDeclaredSourceReachesTheRegister:
    """What a caller declares is what the row says."""

    @pytest.mark.parametrize("declared", ["user", "scheduled", "proactive"])
    async def test_the_row_carries_the_declared_source(self, declared: str) -> None:
        import uuid
        from unittest.mock import AsyncMock, patch

        from src.infrastructure.proactive.tracking import track_proactive_tokens

        class _Tracker:
            async def __aenter__(self) -> _Tracker:
                return self

            async def __aexit__(self, *_: object) -> None:
                return None

            async def record_node_tokens(self, **_: object) -> None:
                return None

            async def commit(self) -> None:
                return None

        recorded: list[object] = []
        with (
            patch("src.domains.chat.service.TrackingContext", lambda **_: _Tracker()),
            patch(
                "src.domains.agents.effects.decision_recorder.record_decision",
                AsyncMock(side_effect=lambda decision: recorded.append(decision)),
            ),
        ):
            await track_proactive_tokens(
                user_id=uuid.uuid4(),
                task_type="probe",
                target_id="target-1234567890",
                conversation_id=None,
                tokens_in=10,
                tokens_out=5,
                model_name="gpt-5.6-luna",
                source=declared,
            )

        assert recorded[0].source == declared


class TestTheDeclaredValuesAreRealOnes:
    """A literal is typo-prone; the vocabulary is checked, not trusted."""

    def test_every_declared_literal_is_a_known_source(self) -> None:
        from src.domains.agents.effects.models import EffectSource

        known = {member.value for member in EffectSource}
        offenders: list[str] = []
        for path in _SRC.rglob("*.py"):
            if path.name == "tracking.py" and path.parent.name == "proactive":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError, UnicodeDecodeError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name not in _FUNNELS:
                    continue
                for keyword in node.keywords:
                    if keyword.arg != "source":
                        continue
                    value = keyword.value
                    if isinstance(value, ast.Constant) and value.value not in known:
                        relative = path.relative_to(_SRC).as_posix()
                        offenders.append(f"{relative}:{node.lineno} -> {value.value!r}")
        assert not offenders, f"unknown source declared: {offenders}"

    def test_no_surface_is_left_on_a_single_authorship(self) -> None:
        """All three origins are actually used somewhere.

        The point of the correction: before it, every one of these surfaces
        would have been filed identically. If a refactor ever collapses them
        again, this fails rather than passing quietly.
        """
        declared: set[str] = set()
        for path in _SRC.rglob("*.py"):
            if path.name == "tracking.py" and path.parent.name == "proactive":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError, UnicodeDecodeError:  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name not in _FUNNELS:
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "source" and isinstance(keyword.value, ast.Constant):
                        declared.add(str(keyword.value.value))
        assert declared == {"user", "scheduled", "proactive"}, (
            f"out-of-turn surfaces declare only {sorted(declared)} — the funnel "
            "serves requests, deferred instructions AND initiatives"
        )
