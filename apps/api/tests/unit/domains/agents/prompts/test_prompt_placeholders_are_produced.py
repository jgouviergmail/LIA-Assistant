"""Every placeholder a prompt file declares is filled by the module that loads it.

Measured 2026-09-12 (prompt audit): ``hitl_question_generator_prompt.txt`` carried
``{context_instructions}``, ``{tool_name}`` and ``{tool_args}`` since v1.0.0 while its
assembler only ever ``.replace()``d two other keys — the model read
``Tool name: {tool_name}`` on every confirmation, and the ``{{…}}`` few-shot examples,
written for ``str.format``, reached it with their braces doubled. The cache-hygiene
guard scans the STATIC prefix only, so a dead placeholder below the marker was
invisible to every guard.

This guard is the missing half: it reads, per prompt file, the modules that load it
(the file stem quoted in their source) and the keys those modules PRODUCE — keyword
arguments of ``.format(...)`` / ``.format_map({...})`` calls and the first argument of
``.replace("{key}", …)`` calls — then requires:

- every ``{placeholder}`` of the file to be produced by at least one loader;
- a file written for ``str.format`` (it contains ``{{``) to be loaded by a module
  that actually calls ``.format``, never one that only ``.replace``s.

A loader that spreads ``**kwargs`` into ``.format`` is read as producing anything
(the keys are not visible to an AST); the file is then only checked for the
doubled-brace rule. Prompt files nobody loads by their quoted stem are listed in
``LOADED_INDIRECTLY`` with the mechanism, so a genuinely orphaned placeholder cannot
hide behind a dynamic loader.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[5]
SRC = API_ROOT / "src"
PROMPTS_DIR = SRC / "domains" / "agents" / "prompts" / "v1"

# ``{name}`` — single braces only; ``{{name}}`` is an escaped literal for str.format.
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")

#: Produced by ``format_with_current_datetime`` (a ``.replace`` behind a helper) and
#: by ``get_current_datetime_context`` call sites — the one helper every assembler
#: shares, so it is credited to any module that calls it.
_DATETIME_HELPERS = frozenset({"format_with_current_datetime", "get_current_datetime_context"})

#: Modules that mention prompt stems for a reason other than loading them.
_NOT_LOADERS = (
    SRC / "domains" / "agents" / "prompts" / "prompt_loader.py",
    SRC / "core" / "config",
    SRC / "core" / "constants.py",
)

#: Prompt files whose stem is never quoted by a loader because the loader derives
#: the name (a table, a per-agent suffix). Each entry names the mechanism; the file
#: is still checked for the doubled-brace rule against that mechanism's module.
LOADED_INDIRECTLY: dict[str, str] = {}

#: Prompt files whose text is loaded in one module and RENDERED in another (the
#: name travels through a constant or a constructor argument). The renderer is
#: declared, source-relative, and read by the same AST walk — a wrong path or a
#: renderer that stopped producing a key fails the build.
RENDERED_BY: dict[str, tuple[str, ...]] = {
    # The name is a constant of ``briefing/constants.py``; ``briefing/llm.py`` formats.
    "briefing_greeting_prompt": ("domains/briefing/llm.py",),
    "briefing_synthesis_prompt": ("domains/briefing/llm.py",),
    # ``{language}`` is deliberately left for the per-language batch in
    # ``diagnostics/diagnosis.py`` (one variant per admin language).
    "diagnostician_prompt": ("domains/diagnostics/diagnosis.py",),
    # The engine returns the frame NAME and its dynamic block; the service formats.
    "psyche_embodied_faint": ("domains/psyche/service.py",),
    "psyche_embodied_frame": ("domains/psyche/service.py",),
    # The name is a constant of ``debrief/prompts.py``; ``debrief/llm.py`` formats.
    "relation_debrief_prompt": ("domains/relations/debrief/llm.py",),
    # Loaded by the agents-side wrapper, rendered by the diagnostics builder.
    "runtime_failures_directive": ("domains/diagnostics/failure_context.py",),
    # Both are the ``prompt_name`` of a ``ReactSubAgentRunner``, which formats.
    "skill_react_agent_prompt": ("domains/agents/tools/react_runner.py",),
    "subagent_react_prompt": ("domains/agents/tools/react_runner.py",),
}

#: Files whose ``{{x}}`` is NOT a ``str.format`` escape but a third party's own
#: variable syntax, filled by that party — the double brace must reach it intact.
PROVIDER_TEMPLATE_SYNTAX: dict[str, str] = {
    # ElevenLabs dynamic variables ({{objective}}, {{callee_name}}, …), injected by
    # the vendor at call time — see ``telephony/agent_prompt.py``.
    "telephony_agent_system_prompt": "ElevenLabs dynamic variables",
}


def _prompt_files() -> list[Path]:
    return sorted(PROMPTS_DIR.glob("*.txt"))


def _is_excluded(path: Path) -> bool:
    return any(path == p or (p.is_dir() and p in path.parents) for p in _NOT_LOADERS)


def _loaders_of(stem: str) -> list[Path]:
    """Modules quoting the stem, plus the declared renderers (which must exist)."""
    needle = f'"{stem}"'
    found: list[Path] = []
    for path in sorted(SRC.rglob("*.py")):
        if _is_excluded(path):
            continue
        if needle in path.read_text(encoding="utf-8"):
            found.append(path)
    for relative in RENDERED_BY.get(stem, ()):
        renderer = SRC / relative
        assert renderer.is_file(), f"RENDERED_BY[{stem!r}] names a missing module: {relative}"
        if renderer not in found:
            found.append(renderer)
    return found


class _Producers(ast.NodeVisitor):
    """Keys a module hands to ``str.format`` / ``str.replace`` on a template."""

    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.calls_format = False
        self.spreads_kwargs = False

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 — ast visitor API
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "format":
                self.calls_format = True
                for kw in node.keywords:
                    if kw.arg is None:
                        self.spreads_kwargs = True
                    else:
                        self.keys.add(kw.arg)
            elif func.attr == "format_map" and node.args:
                self.calls_format = True
                mapping = node.args[0]
                if isinstance(mapping, ast.Dict):
                    self.keys.update(
                        k.value
                        for k in mapping.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    )
                else:
                    self.spreads_kwargs = True
            elif func.attr == "replace" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    self.keys.update(_PLACEHOLDER_RE.findall(first.value))
        if isinstance(func, ast.Name) and func.id in _DATETIME_HELPERS:
            self.keys.add("current_datetime")
        if isinstance(func, ast.Attribute) and func.attr in _DATETIME_HELPERS:
            self.keys.add("current_datetime")
        self.generic_visit(node)


def _producers(path: Path) -> _Producers:
    visitor = _Producers()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return visitor


@pytest.mark.parametrize("prompt", _prompt_files(), ids=lambda p: p.stem)
def test_every_placeholder_has_a_producer(prompt: Path) -> None:
    """A ``{placeholder}`` nobody fills reaches the model as literal text."""
    text = prompt.read_text(encoding="utf-8")
    placeholders = set(_PLACEHOLDER_RE.findall(text))
    loaders = _loaders_of(prompt.stem)
    if not loaders:
        assert prompt.stem in LOADED_INDIRECTLY, (
            f"{prompt.name} is loaded by no module quoting its stem — either it is an "
            "orphan (delete it) or its loader derives the name: declare the mechanism "
            "in LOADED_INDIRECTLY."
        )
        return
    if not placeholders:
        return
    produced: set[str] = set()
    for loader in loaders:
        visitor = _producers(loader)
        if visitor.spreads_kwargs:
            return  # keys invisible to the AST; only the brace rule applies
        produced |= visitor.keys
    missing = placeholders - produced
    assert not missing, (
        f"{prompt.name} declares {sorted(missing)} but none of its loaders "
        f"({', '.join(p.relative_to(SRC).as_posix() for p in loaders)}) produces them: "
        "the model reads the placeholder as literal text. Fill it or delete it."
    )


@pytest.mark.parametrize("prompt", _prompt_files(), ids=lambda p: p.stem)
def test_doubled_braces_are_rendered_by_format(prompt: Path) -> None:
    """``{{`` is an escape for ``str.format``; a ``.replace``-only loader ships it doubled."""
    text = prompt.read_text(encoding="utf-8")
    if "{{" not in text or prompt.stem in PROVIDER_TEMPLATE_SYNTAX:
        return
    loaders = _loaders_of(prompt.stem)
    if not loaders:
        return  # covered by the producer test
    formatting = [p for p in loaders if _producers(p).calls_format]
    assert formatting, (
        f"{prompt.name} contains '{{{{' (a str.format escape) but its loaders "
        f"({', '.join(p.relative_to(SRC).as_posix() for p in loaders)}) never call "
        ".format(): the model receives doubled braces. Render it with .format() or "
        "write single braces."
    )
