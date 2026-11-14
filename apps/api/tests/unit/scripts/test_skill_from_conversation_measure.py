"""The skill-from-conversation bench reads a generated skill the way it claims (lot 20)."""

from __future__ import annotations

import json

import pytest

from scripts.skills.measure_skill_from_conversation import (
    ARMS,
    CATALOGUE_TOOLS,
    GENERALISE,
    SCENARIOS,
    extract_skill,
    history_for,
    runner_messages,
    score,
)

pytestmark = pytest.mark.unit

MORNING = SCENARIOS[0]


def test_every_scenario_expects_catalogue_tools_and_asks_with_its_own_words() -> None:
    for scenario in SCENARIOS:
        assert set(scenario.expected) <= CATALOGUE_TOOLS, scenario.key
        ran = [tool for turn in scenario.turns for tool in turn.tools]
        assert ran == list(scenario.expected), scenario.key
        # A planted fact must be in the conversation, or copying it proves nothing.
        said = " ".join(turn.user + turn.answer for turn in scenario.turns)
        assert all(canary in said for canary in scenario.canaries), scenario.key


def test_the_arms_differ_by_the_steps_alone() -> None:
    plain, steps = (history_for(MORNING, arm) for arm in ("history", "steps"))
    assert history_for(MORNING, "general") == plain
    assert ARMS == ("history", "steps", "general")

    assert "[STEPS RUN]" not in plain and "get_emails_tool" not in plain
    assert steps.count("[STEPS RUN]") == len(MORNING.turns)
    assert steps.index("get_emails_tool") < steps.index("create_task_tool")
    # Removing the steps lines gives today's history back.
    kept = "\n".join(line for line in steps.splitlines() if not line.startswith("[STEPS RUN]"))
    assert kept == plain


def test_a_skill_is_read_from_its_fenced_block_or_whole() -> None:
    skill = "---\nname: tri\ndescription: x\n---\nBody"
    assert extract_skill(f"Voilà :\n```yaml\n{skill}\n```\nBonne journée") == skill
    assert extract_skill(skill) == skill
    # A block the answer never closed.
    assert extract_skill(f"```yaml\n{skill}") == skill


def test_a_skill_handed_to_a_tool_written_as_text_is_read_from_its_argument() -> None:
    """With no tool bound, a family writes its validation call as text: the skill is in it."""
    skill = '---\nname: tri\ndescription: "x"\n---\nBody'
    call = '<calls>\n<invoke name="run_skill_script">{"content": ' + json.dumps(skill) + "}"
    assert extract_skill(call) == skill


def test_the_general_arm_adds_the_generalisation_rule_alone() -> None:
    history, general = (runner_messages(MORNING, arm)[1].content for arm in ("history", "general"))
    assert isinstance(history, str) and isinstance(general, str)
    assert GENERALISE in general and GENERALISE not in history
    assert general.replace(GENERALISE, "", 1) == history


def test_the_score_counts_tools_unknown_tools_and_copied_facts() -> None:
    skill = (
        "---\nname: tri-matin\ndescription: Sorts the morning mail.\ncategory: productivity\n"
        "priority: 50\n---\n# Tri\n\nCall get_emails_tool, then create_task_tool, then "
        "send_fax_tool. Answer Sophie first."
    )

    result = score(MORNING, skill)

    assert result["tools"] == 2 and result["expected"] == 3
    assert result["unknown"] == ["send_fax_tool"]
    assert result["leaks"] == ["Sophie"]
    assert result["order"] is True
