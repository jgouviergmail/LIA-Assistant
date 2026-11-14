"""The skill detection bench: its corpus, and how a detection is read and judged (lot 13)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables import RunnableConfig

from scripts.skills import measure_skill_detection as bench
from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.services.query_analyzer_service import QueryAnalysisResult
from src.domains.skills.cache import SkillsCache
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

SKILLS_DIR = repo_root_or_skip() / "data" / "skills" / "system"


def _result(**overrides: Any) -> QueryAnalysisResult:
    fields: dict[str, Any] = {
        "intent": "action",
        "primary_domain": "email",
        "secondary_domains": [],
        "confidence": 0.9,
        "english_query": "x",
        "resolved_references": [],
        "reasoning": "",
        "raw_output": {},
    }
    return QueryAnalysisResult(**{**fields, **overrides})


def test_every_skill_the_corpus_expects_is_a_system_skill() -> None:
    on_disk = {path.name for path in SKILLS_DIR.iterdir() if path.is_dir()}
    assert {request.expected for request in bench.CORPUS if request.expected} <= on_disk
    assert set(bench.UNDER_TEST) <= on_disk


def test_each_skill_under_test_has_triggers_and_neighbours_try_to_lure_it() -> None:
    for skill in bench.UNDER_TEST:
        assert sum(request.expected == skill for request in bench.CORPUS) >= 4, skill
    assert sum(request.expected not in bench.UNDER_TEST for request in bench.CORPUS) >= 8
    texts = [request.text for request in bench.CORPUS]
    assert len(texts) == len(set(texts))


def test_a_failed_analysis_is_an_error_never_a_skill_left_out() -> None:
    assert bench.read_detection(_result(raw_output={"error": "timeout"})) == (None, "timeout")
    assert bench.read_detection(_result(skill_name="tri-boite-reception")) == (
        "tri-boite-reception",
        None,
    )
    assert bench.read_detection(_result()) == (None, None)


def test_a_hijack_and_a_miss_are_counted_apart() -> None:
    review, triage, _generator = bench.UNDER_TEST
    rows = [
        bench.Detection("m", "found", review, detected=review),
        bench.Detection("m", "missed", review, detected=None),
        bench.Detection("m", "lured", None, detected=triage),
        bench.Detection("m", "left alone", None, detected=None),
        bench.Detection("m", "another skill", "briefing-quotidien", detected="briefing-quotidien"),
        bench.Detection("m", "crossed", review, detected=triage),
        bench.Detection("m", "failed", None, error="timeout"),
    ]

    assert bench.totals(rows) == {
        "m": {"asked": 7, "errors": 1, "correct": 3, "misses": 2, "hijacks": 2, "other": 0}
    }


def test_an_instance_whose_skills_are_off_measures_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The analyzer lists no skill there: every trigger would read as a miss.
    monkeypatch.setattr(settings, "skills_enabled", False)
    with pytest.raises(SystemExit, match="skills are switched off"):
        bench.require_skills_on()
    monkeypatch.setattr(settings, "skills_enabled", True)
    bench.require_skills_on()


def test_the_usage_handler_can_join_a_set_of_callbacks() -> None:
    # Measured 2026-11-13: a provider's native structured output keeps its
    # callbacks in a set; an unhashable handler failed every one of its calls.
    first, second = bench._Usage(), bench._Usage()
    assert len({first, second}) == 2


def test_the_analyzer_is_shown_the_skills_of_this_checkout() -> None:
    SkillsCache.reset()
    try:
        listed = bench.analyzer_skill_list(SKILLS_DIR)
    finally:
        SkillsCache.reset()
    for skill in bench.UNDER_TEST:
        assert f"**{skill}**" in listed


@pytest.mark.asyncio
async def test_a_detection_runs_the_production_analyzer_on_the_family_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    llm = FakeListChatModel(responses=[])
    config = get_llm_config_for_agent(settings, "query_analyzer").model_copy(
        update={"model": "gpt-4.1-mini"}
    )

    async def fake_analyze_query(
        query: str, base_config: RunnableConfig | None = None
    ) -> QueryAnalysisResult:
        # Where `analyze_query` reads its model and its configuration, at call time.
        from src.core import llm_config_helper
        from src.infrastructure import llm as llm_package

        seen["llm"] = llm_package.get_llm("query_analyzer")
        seen["config"] = llm_config_helper.get_llm_config_for_agent(settings, "query_analyzer")
        assert base_config is not None
        usage = base_config["callbacks"][0]
        message = AIMessage(
            content="{}",
            usage_metadata={"input_tokens": 1200, "output_tokens": 40, "total_tokens": 1240},
            response_metadata={"model_name": "gpt-4.1-mini"},
        )
        await usage.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]))
        return _result(skill_name="revue-hebdomadaire")

    monkeypatch.setattr(bench, "analyze_query", fake_analyze_query)
    monkeypatch.setattr(bench, "get_cached_cost_usd_eur", lambda *args, **kwargs: (0.001, 0.0009))
    request = bench.Request("Do my weekly review", "revue-hebdomadaire")

    row = await bench.detect(request, "gpt-4.1-mini", llm, config)

    assert (seen["llm"], seen["config"]) == (llm, config)
    assert (row.detected, row.correct, row.error) == ("revue-hebdomadaire", True, None)
    assert (row.tokens_in, row.tokens_out, row.cost_eur) == (1200, 40, 0.0009)
