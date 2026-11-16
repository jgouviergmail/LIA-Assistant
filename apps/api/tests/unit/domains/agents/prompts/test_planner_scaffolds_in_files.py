"""The planner's scaffolds live in versioned files, never in a ``.py`` (ADR-284).

Found 2026-11-15 (ADR-390 qualification): the section the planner reads on every
multi-domain plan — the « Primary domain » line, « gather ALL data from each
domain » and the cross-domain example — and the FOR_EACH cardinality hints were
string literals in ``prompts/__init__.py``, where no prompt guard reads.
"""

from __future__ import annotations

import inspect

import pytest

from src.domains.agents import prompts
from src.domains.agents.prompts import _multi_domain_section
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = pytest.mark.unit


def test_the_multi_domain_section_is_the_versioned_file() -> None:
    expected = load_prompt("planner_multi_domain_section").strip().format(primary_domain="task")

    assert _multi_domain_section("task", is_multi_domain=True) == f"\n{expected}"


def test_a_single_domain_plan_reads_no_section() -> None:
    assert _multi_domain_section("task", is_multi_domain=False) == ""


def test_no_planner_prose_is_left_in_the_module() -> None:
    source = inspect.getsource(prompts)

    for sentence in (
        "gather ALL data from each domain",
        "CROSS-DOMAIN WITH RESOLVED CONTEXT",
        "unknown number of",
    ):
        assert sentence not in source, sentence
