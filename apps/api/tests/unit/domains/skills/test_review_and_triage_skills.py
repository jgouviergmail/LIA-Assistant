"""The weekly review and the inbox triage: what their plans read (lot 13).

Two system skills with a deterministic plan (the ADR-160 bypass): no planner
call, a fixed set of reads, the answer shaped by the skill's instructions. A
routine model in the studio asks for each by its words. What a plan reads is
the decision pinned here; that every step can run is the templates guard's.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.domains.skills.loader import parse_skill_file
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

SKILLS_DIR = repo_root_or_skip() / "data" / "skills" / "system"
LANGUAGES = {"fr", "en", "es", "de", "it", "zh"}


def _skill(name: str) -> dict[str, Any]:
    skill = parse_skill_file(SKILLS_DIR / name / "SKILL.md")
    assert skill is not None, f"{name}: no readable SKILL.md"
    return skill


def _reads(skill: dict[str, Any]) -> set[tuple[str, tuple[tuple[str, Any], ...]]]:
    return {
        (step["tool_name"], tuple(sorted((step.get("parameters") or {}).items())))
        for step in skill["plan_template"]["steps"]
    }


@pytest.mark.parametrize("name", ["revue-hebdomadaire", "tri-boite-reception"])
class TestBothSkills:
    def test_the_plan_runs_without_a_planner(self, name: str) -> None:
        template = _skill(name)["plan_template"]
        assert template["deterministic"] is True
        # Independent reads: they run together, none waits for another.
        assert all(step["depends_on"] == [] for step in template["steps"])

    def test_the_gallery_describes_it_in_the_six_languages(self, name: str) -> None:
        translations = json.loads((SKILLS_DIR / name / "translations.json").read_text("utf-8"))
        assert set(translations) == LANGUAGES
        assert all(len(text.strip()) > 20 for text in translations.values())

    def test_its_output_format_is_a_resource_it_names(self, name: str) -> None:
        skill = _skill(name)
        assert "output-format.md" in skill["references"]
        assert "references/output-format.md" in skill["instructions"]


class TestTheWeeklyReview:
    def test_it_reads_the_week_done_open_and_ahead(self) -> None:
        assert _reads(_skill("revue-hebdomadaire")) == {
            ("get_tasks_tool", (("only_completed", True),)),
            ("get_tasks_tool", (("show_completed", False),)),
            ("get_lia_open_loops_tool", ()),
            ("get_events_tool", (("days_ahead", 7),)),
            ("list_reminders_tool", ()),
        }


class TestTheInboxTriage:
    def test_it_reads_the_unread_inbox_once_with_digests(self) -> None:
        # The provider-neutral query (Gmail syntax, translated for Graph and
        # IMAP); `summary` is the digest the tool recommends for routines; the
        # page size is the operator's setting, never a number written here.
        assert _reads(_skill("tri-boite-reception")) == {
            ("get_emails_tool", (("detail", "summary"), ("query", "in:inbox is:unread"))),
        }
