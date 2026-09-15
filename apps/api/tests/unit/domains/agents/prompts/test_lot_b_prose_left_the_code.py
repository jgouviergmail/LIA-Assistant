"""Prompt prose that lived in ``.py`` now lives in the store (prompt audit 2026-09-12, lot B).

Twelve assemblers carried their sentences inline — unreadable by the four prompt
guards (cache marker, tool names, model names, timezone) and by the placeholder
guard. Each site now renders from a versioned file or a ``key|template`` lines
file; these tests render through the REAL helpers and pin the wording the model
reads (characterization captured on the inline version), then check the sentence
is gone from the module's source.
"""

from __future__ import annotations

import inspect
import re

from src.domains.agents.orchestration import semantic_validator
from src.domains.agents.services import smart_planner_service
from src.domains.agents.services.hitl import draft_modifier, item_filter
from src.domains.agents.tools import perplexity_tools
from src.domains.heartbeat import prompts as heartbeat_prompts
from src.domains.interests.services import extraction_service
from src.domains.interests.services.content_sources import perplexity_source
from src.domains.journals import consolidation_service

_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")
LF = chr(10)


def _source_of(module: object) -> str:
    return inspect.getsource(module)  # type: ignore[arg-type]


class TestItemFilter:
    def test_prompt_renders_criteria_and_items(self) -> None:
        service = item_filter.ItemFilterService.__new__(item_filter.ItemFilterService)
        prompt = service._build_filter_prompt(
            [{"name": "Guy S."}, {"name": "Alice"}], "guy savoy", "fr"
        )
        assert 'User\'s exclusion criteria: "guy savoy"' in prompt
        assert "0. name: Guy S." in prompt and "1. name: Alice" in prompt
        assert "Return ONLY the JSON array" in prompt
        assert not _PLACEHOLDER_RE.findall(prompt)

    def test_prose_left_the_module(self) -> None:
        assert "item filter assistant" not in _source_of(item_filter)


class TestPlannerScaffolds:
    def test_preserved_parameters_section(self) -> None:
        section = smart_planner_service.SmartPlannerService._render_preserved_parameters(
            {"query": "jean", "limit": 5}
        )
        assert section == (
            LF
            + LF
            + "## PRESERVED PARAMETERS (FROM PREVIOUS CLARIFICATION)"
            + LF
            + "The following parameters were already set in a previous step. You MUST preserve "
            "these exact values in the new plan:"
            + LF
            + '- query: "jean"'
            + LF
            + '- limit: "5"'
            + LF
            + LF
            + "Do NOT modify or regenerate these values."
        )

    def test_mcp_format_reference_section(self) -> None:
        section = smart_planner_service.SmartPlannerService._render_mcp_format_reference(
            "github", "REF-DOC"
        )
        assert section.startswith(LF + "MCP TOOL FORMAT REFERENCE — github (MANDATORY):")
        assert "any github tool" in section and section.rstrip().endswith("REF-DOC")

    def test_prose_left_the_module(self) -> None:
        source = _source_of(
            smart_planner_service
        )  # a comment may NAME the block; the prose is gone
        assert "You MUST preserve these exact values" not in source
        assert "follow the exact structure, field names" not in source


class TestHeartbeat:
    def test_verified_facts_block(self) -> None:
        block = heartbeat_prompts.render_verified_facts("- fact one")
        assert block.startswith("VERIFIED FACTS about the user's interest")
        assert "- fact one" in block and "Never invent titles or facts" in block

    def test_prose_left_the_module(self) -> None:
        source = _source_of(heartbeat_prompts)
        assert "RECENT HEARTBEAT NOTIFICATIONS" not in source
        assert "VERIFIED FACTS" not in source
        assert "None sent recently" not in source


class TestPerplexity:
    def test_tool_system_prompt(self) -> None:
        prompt = perplexity_tools.build_perplexity_system_prompt("2026-09-12 10:00", "oncology")
        assert prompt == (
            "Current date and time: 2026-09-12 10:00"
            + LF
            + LF
            + "You are an expert in oncology. Provide accurate, well-researched answers focused on this domain."
        )
        assert (
            perplexity_tools.build_perplexity_system_prompt("NOW", None)
            == "Current date and time: NOW"
        )

    def test_interest_source_system_prompt_names_the_language(self) -> None:
        source = perplexity_source.PerplexityContentSource.__new__(
            perplexity_source.PerplexityContentSource
        )
        prompt = source._build_system_prompt("zh")
        assert "Respond in Simplified Chinese." in prompt
        assert "interesting facts and recent news" in prompt

    def test_prose_left_the_modules(self) -> None:
        assert "You are an expert in" not in _source_of(perplexity_tools)
        assert "interesting facts and recent news" not in _source_of(perplexity_source)


class TestJournalConsolidation:
    def test_size_directives_by_usage(self) -> None:
        exceeded = consolidation_service.size_directives(120.0)
        assert exceeded[0].startswith("CRITICAL: You have EXCEEDED")
        assert exceeded[1].startswith("You need to reduce total size")
        approaching = consolidation_service.size_directives(85.0)
        assert approaching[0].startswith("WARNING: You are approaching")
        assert approaching[1].startswith("You need to reduce total size")
        within = consolidation_service.size_directives(40.0)
        assert within == ("", "You are within the size limit. Only act if genuinely useful.")

    def test_prose_left_the_module(self) -> None:
        assert "EXCEEDED the size limit" not in _source_of(consolidation_service)


class TestSemanticValidator:
    def test_lines_are_read_from_the_store(self) -> None:
        lines = semantic_validator.validator_lines()
        assert lines["for_each_description"] == "for_each pattern issue detected"
        assert "NEVER invent contact details" in lines["placeholder_contact_fix"]
        assert (
            lines["scope_overflow_fix"]
            .format(writing_tools="send_email_tool")
            .count("send_email_tool")
            == 1
        )

    def test_prose_left_the_module(self) -> None:
        source = _source_of(semantic_validator)  # a comment may NAME the rule; the prose is gone
        assert "Either add a get_contacts_tool step" not in source
        assert "for_each pattern issue detected" not in source
        assert "asks for information, but the plan performs" not in source


class TestDraftModifier:
    def test_context_info_per_draft_type(self) -> None:
        service = draft_modifier.DraftModificationService.__new__(
            draft_modifier.DraftModificationService
        )
        assert service._build_context_info(
            {"to": "a@b.c", "cc": "d@e.f", "subject": "Hi"}, "email"
        ) == (
            "Current recipient (editable): a@b.c"
            + LF
            + "Current CC (editable): d@e.f"
            + LF
            + "Current subject: Hi"
        )
        assert (
            service._build_context_info({}, "email")
            == "Current recipient (editable): not specified"
        )
        assert service._build_context_info(
            {"summary": "Dentist", "start_datetime": "2026-09-15"}, "event"
        ) == ("Event: Dentist" + LF + "Date: 2026-09-15")
        assert service._build_context_info({"name": "Jean"}, "contact") == "Contact: Jean"
        assert service._build_context_info({"title": "Buy milk"}, "task") == "Task: Buy milk"
        assert service._build_context_info({}, "note") == "Generic draft"

    def test_contact_context_info(self) -> None:
        service = draft_modifier.DraftModificationService.__new__(
            draft_modifier.DraftModificationService
        )
        rendered = service._build_contact_context_info(
            [{"name": "Alice", "emails": ["a@b.c", "a2@b.c"]}]
        )
        assert (
            rendered == LF + "## Contact email addresses available" + LF + "- Alice: a@b.c, a2@b.c"
        )
        assert service._build_contact_context_info([{"name": "Bob", "emails": []}]) == ""

    def test_prose_left_the_module(self) -> None:
        source = _source_of(draft_modifier)
        assert "Modify the draft according to the instructions" not in source
        assert "SENDER (the user writing this)" not in source


class TestInterestExtraction:
    def test_empty_interest_list_is_not_french(self) -> None:
        assert "Aucun" not in _source_of(extraction_service)
