"""The pre-deployment report for ADR-245, on data that is not this machine's.

`dev != prod`: the real per-agent configuration lives in the database and the
two deployments do not run the same models. Every figure in the ADR was
measured on dev, so the only honest thing to do before a production deployment
is to ask the target instance — which is what this report is for, and why its
answers are computed rather than recalled.

The checks that matter are the ones a green dev run cannot exercise: a
production instance has NOT migrated yet, so its rows still carry the legacy
shapes and the dead ladder vocabulary.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_PREFLIGHT = Path(__file__).resolve().parents[5] / "scripts" / "llm_catalogue" / "preflight.py"


def _load():  # type: ignore[no-untyped-def]
    """Import the CLI as a module — it lives outside the package tree."""
    spec = importlib.util.spec_from_file_location("_preflight_under_test", _PREFLIGHT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(model_name: str, *, provider: str = "openai", levels: list[str] | None = None):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        model_name=model_name,
        provider=SimpleNamespace(value=provider),
        kind=SimpleNamespace(value="chat"),
        reasoning_enum_values=levels,
    )


def _override(stored: dict | None):  # type: ignore[no-untyped-def]
    return SimpleNamespace(reasoning_effort=stored)


def test_it_counts_the_rows_the_migration_would_rewrite(capsys: pytest.CaptureFixture[str]) -> None:
    """A production instance still holds the four legacy shapes."""
    module = _load()
    module._report_reasoning(
        [_row("gpt-5.2")],
        [
            _override({"effort": "off"}),
            _override({"effort": "off"}),
            _override({"effort": "high"}),
            _override({"level": "high", "budget_tokens": None, "exclude_from_output": False}),
            _override(None),
        ],
        [],
    )
    out = capsys.readouterr().out
    assert "3 row(s) rewritten, 5 examined" in out
    assert "-> none" in out, "the report must say what each shape becomes"


def test_an_already_migrated_row_is_not_counted(capsys: pytest.CaptureFixture[str]) -> None:
    module = _load()
    module._report_reasoning(
        [_row("gpt-5.2")],
        [_override({"level": "none", "budget_tokens": None, "exclude_from_output": False})],
        [],
    )
    assert "0 row(s) rewritten" in capsys.readouterr().out


def test_it_names_the_ladders_that_speak_a_dead_vocabulary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `off` case: the narrowing drops it, leaving a ladder with no off switch."""
    module = _load()
    module._report_reasoning(
        [_row("deepseek-v4-flash", provider="deepseek", levels=["off", "high", "max"])],
        [],
        [],
    )
    out = capsys.readouterr().out
    assert "deepseek-v4-flash" in out
    assert "unknown: ['off']" in out
    assert "total: 1" in out


def test_a_clean_ladder_is_not_reported(capsys: pytest.CaptureFixture[str]) -> None:
    module = _load()
    module._report_reasoning(
        [_row("deepseek-v4-flash", provider="deepseek", levels=["none", "high", "max"])], [], []
    )
    assert "unknown:" not in capsys.readouterr().out


def test_a_curated_budget_range_is_reported_as_discarded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """It comes from the DATABASE: the ORM asking has already dropped the column."""
    module = _load()
    problems = module._report_reasoning(
        [_row("gpt-5.2")], [], ["claude-opus-4-5", "gemini-2.5-pro"]
    )
    out = capsys.readouterr().out
    assert "claude-opus-4-5" in out
    assert "already unused" in out
    # Reported, never blocking: the runtime reads the family's range.
    assert problems == 0


def test_nothing_to_report_needs_no_human(capsys: pytest.CaptureFixture[str]) -> None:
    module = _load()
    assert module._report_reasoning([_row("gpt-5.2")], [], []) == 0
    assert "[6] slots whose reasoning depth the runtime would COERCE" in capsys.readouterr().out


def test_an_unreachable_instance_gets_a_sentence_not_a_traceback() -> None:
    """Aiming the report elsewhere makes "wrong address" its likeliest failure.

    The repository's own ``.env`` names the Compose service, which resolves
    inside the network and nowhere else, so the message has to say where the
    address came from -- and never quote the credentials it carries.
    """
    module = _load()
    message = module._unreachable_message("postgres", 5432, OSError("getaddrinfo failed"))
    assert "postgres:5432" in message
    assert "getaddrinfo failed" in message
    assert "127.0.0.1:5432" in message  # the dev form, spelled out
    assert "docker-compose.prod.yml" in message  # where the prod tunnel is documented
    assert "<pass>" in message and "password" not in message.lower()


def test_a_model_pinned_only_by_the_environment_counts_as_referenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production pins the telephony agent's model that way, and only that way.

    Enumerating the domains that may pin one is how the list goes stale; every
    ``*_MODEL`` variable is read instead, and a value matching no catalogue row
    merely widens a set used for membership.
    """
    module = _load()
    monkeypatch.setenv("TELEPHONY_AGENT_LLM_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("SOME_EMBEDDING_MODEL", "  models/gemini-embedding-001  ")
    monkeypatch.setenv("NOT_A_MODEL_SETTING", "gpt-4.1-nano")
    monkeypatch.setenv("EMPTY_MODEL", "   ")

    found = module._models_named_in_the_environment()

    assert "gpt-5.4-mini" in found
    assert "models/gemini-embedding-001" in found  # stripped
    assert "gpt-4.1-nano" not in found  # the name does not end in _MODEL
    assert "" not in found and "   " not in found
