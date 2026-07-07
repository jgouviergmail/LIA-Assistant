"""Characterization tests for the prompt-assembly helpers extracted from
``response_node``: ``_build_response_system_prompt`` (directive injection) and
``_build_response_chain`` (dynamic system-block assembly).

These lock the *shape* of what reaches the LLM — which context directives get
appended, and which system blocks the ChatPromptTemplate is built from — which
the end-to-end suite does not assert directly.
"""

from unittest.mock import Mock, patch

from src.core.constants import STATE_KEY_INITIATIVE_SUGGESTION
from src.domains.agents.nodes.response_node import (
    _build_response_chain,
    _build_response_system_prompt,
)

_RESP = "src.domains.agents.nodes.response_node"


# ---------------------------------------------------------------------------
# _build_response_system_prompt
# ---------------------------------------------------------------------------


def _prompt(state=None, **kw):
    base = {
        "state": state if state is not None else {},
        "run_id": "r",
        "user_timezone": "UTC",
        "user_language": "fr",
        "user_viewport": "desktop",
        "user_display_mode": "markdown",
        "user_psyche_enabled": False,
        "personality_instruction": None,
        "conversation_history": "",
        "psychological_profile": "",
        "knowledge_context": "",
        "rag_context": "",
        "user_query_for_prompt": "q",
        "last_user_message": "q",
        "enriched_query": None,
        "data_for_filtering": "",
        "resolved_references": None,
        "anticipated_needs": None,
        "skills_context": "",
        "app_knowledge_context": "",
        "journal_context": "",
        "psyche_context": "",
        "user_model_block": None,
        "react_result": None,
    }
    base.update(kw)
    return _build_response_system_prompt(**base)


def test_system_prompt_base_only_when_no_extras():
    with (
        patch(f"{_RESP}.get_response_prompt", Mock(return_value="BASE")),
        patch(f"{_RESP}._should_inject_html_directive", Mock(return_value=False)),
    ):
        out = _prompt()
    assert out == "BASE"


def test_system_prompt_appends_user_model_block():
    with (
        patch(f"{_RESP}.get_response_prompt", Mock(return_value="BASE")),
        patch(f"{_RESP}._should_inject_html_directive", Mock(return_value=False)),
    ):
        out = _prompt(user_model_block="PORTRAIT")
    assert out == "BASE\n\nPORTRAIT"


def test_system_prompt_injects_initiative_suggestion():
    with (
        patch(f"{_RESP}.get_response_prompt", Mock(return_value="BASE")),
        patch(f"{_RESP}._should_inject_html_directive", Mock(return_value=False)),
    ):
        out = _prompt(state={STATE_KEY_INITIATIVE_SUGGESTION: "book a table"})
    assert "<InitiativeSuggestion>" in out
    assert "book a table" in out


def test_system_prompt_injects_html_directive_when_gated_on():
    with (
        patch(f"{_RESP}.get_response_prompt", Mock(return_value="BASE")),
        patch(f"{_RESP}._should_inject_html_directive", Mock(return_value=True)),
        patch(f"{_RESP}.load_prompt", Mock(return_value="HTML_DIRECTIVE")),
    ):
        out = _prompt(user_display_mode="html")
    assert "HTML_DIRECTIVE" in out


def test_system_prompt_injects_psyche_instruction_when_enabled():
    with (
        patch(f"{_RESP}.get_response_prompt", Mock(return_value="BASE")),
        patch(f"{_RESP}._should_inject_html_directive", Mock(return_value=False)),
        patch(f"{_RESP}.settings.psyche_enabled", True),
        patch(f"{_RESP}.load_prompt", Mock(return_value="PSYCHE_INSTR")),
    ):
        out = _prompt(user_psyche_enabled=True, psyche_context="present")
    assert "PSYCHE_INSTR" in out


# ---------------------------------------------------------------------------
# _build_response_chain
# ---------------------------------------------------------------------------


def _chain_system_blocks(**kw):
    """Build the chain and return the list of system-message contents assembled."""
    base = {
        "base_system_prompt": "BASE",
        "agent_results_summary": "",
        "skills_context": "",
        "plan_rejection_reason": None,
        "state": {},
        "user_language": "fr",
        "llm": Mock(),
    }
    base.update(kw)
    captured = {}

    def _from_messages(messages):
        captured["messages"] = messages
        prompt = Mock()
        prompt.__or__ = Mock(return_value="CHAIN")
        return prompt

    with (
        patch(f"{_RESP}.ChatPromptTemplate.from_messages", side_effect=_from_messages),
        patch(
            f"{_RESP}.load_prompt", Mock(return_value=Mock(format=Mock(return_value="INJECTED")))
        ),
    ):
        chain = _build_response_chain(**base)
    assert chain == "CHAIN"
    return [m[1] for m in captured["messages"] if isinstance(m, tuple) and m[0] == "system"]


def test_chain_base_only_has_single_system_block():
    blocks = _chain_system_blocks()
    assert blocks == ["BASE"]


def test_chain_appends_authoritative_data_block():
    blocks = _chain_system_blocks(agent_results_summary="DATA")
    assert any("DATA" in b and "AUTHORITATIVE" in b for b in blocks)


def test_chain_injects_rejection_override_block():
    blocks = _chain_system_blocks(plan_rejection_reason="refused")
    assert "INJECTED" in blocks  # rejection directive rendered via load_prompt


def test_chain_injects_skill_contract_block():
    blocks = _chain_system_blocks(skills_context="SKILL RULES")
    assert "INJECTED" in blocks  # skill contract prefix rendered via load_prompt
    assert blocks[0] == "BASE"  # base prompt always first


# ---------------------------------------------------------------------------
# Versioned prompt files (byte-exact regression guard vs the previously-inline
# scaffolding — protects against accidental edits to the .txt directives)
# ---------------------------------------------------------------------------


def test_initiative_suggestion_directive_file_is_byte_exact():
    from src.domains.agents.prompts.prompt_loader import load_prompt

    rendered = load_prompt("initiative_suggestion_directive").format(initiative_suggestion="SUGG")
    assert rendered == (
        "<InitiativeSuggestion>\n"
        "The assistant proactively identified a useful follow-up action. "
        "Include this suggestion naturally in your response as a helpful offer:\n"
        "SUGG\n"
        "</InitiativeSuggestion>"
    )


def test_proactive_findings_directive_file_is_byte_exact():
    from src.domains.agents.prompts.prompt_loader import load_prompt

    assert load_prompt("proactive_findings_directive") == (
        "<ProactiveFindings>\n"
        "Beyond the direct answer, additional proactive read-only findings were "
        "gathered this turn (present in the current turn data). Weave the relevant "
        "ones naturally into your reply as a helpful complement — do not list them "
        "mechanically and never expose how they were obtained.\n"
        "</ProactiveFindings>"
    )


def test_system_prompt_injects_proactive_findings_in_react_with_initiative():
    """ReAct mode + an Initiative that acted injects the ProactiveFindings directive."""
    with (
        patch(f"{_RESP}.get_response_prompt", Mock(return_value="BASE")),
        patch(f"{_RESP}._should_inject_html_directive", Mock(return_value=False)),
    ):
        out = _prompt(
            state={"execution_mode": "react", "initiative_results": [{"actions_executed": 1}]},
            react_result={"final_message": "answer"},
        )
    assert "<ProactiveFindings>" in out


def test_system_prompt_no_proactive_findings_outside_react():
    """No ProactiveFindings when not in ReAct mode (even if an Initiative acted)."""
    with (
        patch(f"{_RESP}.get_response_prompt", Mock(return_value="BASE")),
        patch(f"{_RESP}._should_inject_html_directive", Mock(return_value=False)),
    ):
        out = _prompt(
            state={"execution_mode": "pipeline", "initiative_results": [{"actions_executed": 1}]},
            react_result={"final_message": "answer"},
        )
    assert "<ProactiveFindings>" not in out


def test_system_prompt_initiative_value_with_braces_is_format_safe():
    """A suggestion value containing curly braces must be inserted literally (no format crash)."""
    with (
        patch(f"{_RESP}.get_response_prompt", Mock(return_value="BASE")),
        patch(f"{_RESP}._should_inject_html_directive", Mock(return_value=False)),
    ):
        out = _prompt(state={STATE_KEY_INITIATIVE_SUGGESTION: "reserve {table} for 2"})
    assert "reserve {table} for 2" in out
