"""The planner's batch size comes from settings, never from prompt prose.

``smart_planner_prompt.txt`` used to instruct "set max_results = 20–50" as a
literal. Nothing could reconcile that number with a tool's configured cap:
the catalogue published no bound, so the model obeyed the prompt, the
validator rejected the plan for obeying, and — since v1.27.3 — the response
layer reported that verdict to the user as a failure (production 2026-07-31,
requests 2f6c6366 / 52e54297 / 83c98053, "my 3 latest emails" against an email
cap of 10).

The batch target now comes from ``planner_semantic_broad_batch``, the same
setting the validator's semantic-leak autocorrect already used — one source of
truth instead of two numbers that could drift apart.
"""

from __future__ import annotations

import re

import pytest

from src.core.config import get_settings
from src.domains.agents.prompts import get_smart_planner_prompt
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = [pytest.mark.unit]


def _prompt(**overrides: object) -> str:
    kwargs: dict = {
        "user_goal": "find_info",
        "intent": "search",
        "domains": "email",
        "anticipated_needs": "",
        "catalogue": "[]",
        "original_query": "mes 3 derniers emails",
    }
    kwargs.update(overrides)
    return get_smart_planner_prompt(**kwargs)  # type: ignore[arg-type]


def test_the_configured_batch_size_reaches_the_rendered_prompt():
    rendered = _prompt()

    assert f"aim for {get_settings().planner_semantic_broad_batch} results" in rendered


def test_a_changed_setting_changes_the_prompt(monkeypatch: pytest.MonkeyPatch):
    """Proves the value is read at render time, not frozen in the template."""
    monkeypatch.setattr(get_settings(), "planner_semantic_broad_batch", 42, raising=False)

    assert "aim for 42 results" in _prompt()


def test_the_template_carries_no_hardcoded_batch_range():
    """The literal that caused the defect must not come back."""
    template = load_prompt("smart_planner_prompt", version=get_settings().planner_prompt_version)

    assert not re.search(r"\b20\s*[–-]\s*50\b", template)


def test_the_prompt_subordinates_the_target_to_the_published_bound():
    """A batch target that outranks a hard limit is how the defect happened."""
    rendered = _prompt()

    assert "NEVER exceed the `max`" in rendered


def test_rendering_stays_safe_when_the_catalogue_carries_braces():
    """The entry now embeds `min`/`max` keys — the JSON braces must not format."""
    rendered = _prompt(catalogue='[{"name":"get_emails_tool","max":10}]')

    assert '"max":10' in rendered
