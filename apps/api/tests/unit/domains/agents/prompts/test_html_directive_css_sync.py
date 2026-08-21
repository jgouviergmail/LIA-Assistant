"""Sync guard: the HTML response directive and the frontend stylesheet (ADR-177).

Every ``lia-*`` class the directive advertises must exist in
``apps/web/src/styles/lia-components.css`` — a class advertised but unstyled
renders as plain markup and the feature dies invisibly (the registry-
completeness doctrine applied to the prompt/CSS pair). Runs as a plain unit
test: the backend CI job checks out the whole monorepo, so the stylesheet is
always present.
"""

from __future__ import annotations

import re

import pytest

from src.domains.agents.prompts import load_prompt
from tests._repo_paths import repo_root_or_skip

pytestmark = [pytest.mark.unit]

# Shared helper instead of a private Taskfile.yml walk: skips cleanly under the
# flat /app container mount instead of raising at import (ADR-241 follow-up).
_CSS_PATH = repo_root_or_skip() / "apps" / "web" / "src" / "styles" / "lia-components.css"


def _advertised_classes() -> set[str]:
    directive = str(load_prompt("html_response_directive"))
    grouped = re.findall(r'class="([^"]+)"', directive)
    return {cls for group in grouped for cls in group.split()}


def test_advertised_lia_classes_exist_in_stylesheet() -> None:
    css = _CSS_PATH.read_text(encoding="utf-8")
    lia_classes = {c for c in _advertised_classes() if c.startswith("lia-")}
    assert lia_classes, "directive advertises no lia-* class — was it rewritten?"
    missing = sorted(c for c in lia_classes if f".{c}" not in css)
    assert not missing, (
        f"classes advertised by html_response_directive.txt but absent from "
        f"lia-components.css: {missing} — the component would render unstyled."
    )


def test_icon_class_exists_in_stylesheet() -> None:
    directive = str(load_prompt("html_response_directive"))
    if "material-symbols-outlined" in directive:
        css = _CSS_PATH.read_text(encoding="utf-8")
        assert "material-symbols-outlined" in css, (
            "the directive advertises Material Symbols icons but the stylesheet "
            "carries no rule for them"
        )


def test_directive_invariants() -> None:
    directive = str(load_prompt("html_response_directive"))
    assert "lia-response" in directive, "wrapper class dropped from the directive"
    assert "NEVER emit a <style> block" in directive, (
        "the no-inline-style rule was dropped — the LLM would burn ~550 tokens "
        "of discarded CSS per reply again"
    )
    assert (
        "lia-callout-success" in directive
    ), "success callout undocumented — CSS supports it (ADR-177 vocabulary)"
    assert len(directive.splitlines()) <= 96, (
        "directive over its token budget (2x the pre-ADR-177 length): trim it "
        "instead of paying the cost on every action turn"
    )
