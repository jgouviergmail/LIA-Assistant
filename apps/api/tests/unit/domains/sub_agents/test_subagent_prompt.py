"""Validate the subagent_react_prompt (ADR-083): loadable, has required slots, states constraints."""

import pytest


@pytest.mark.unit
def test_subagent_react_prompt_loads_with_required_slots():
    """The prompt must load and expose the {expertise} and {current_datetime} placeholders."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt")

    assert prompt, "subagent_react_prompt must not be empty"
    assert "{expertise}" in prompt, "must expose an {expertise} slot for the persona"
    assert (
        "{current_datetime}" in prompt
    ), "must expose {current_datetime} (injected by ReactSubAgentRunner)"


@pytest.mark.unit
def test_subagent_react_prompt_states_read_only_and_no_delegation():
    """The prompt must articulate the two hard constraints: read-only, no nested delegation."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt").lower()

    assert "read-only" in prompt, "must state the read-only constraint"
    assert "delegate" in prompt, "must mention the no-delegation rule"


@pytest.mark.unit
def test_subagent_react_prompt_imposes_value_contract():
    """The prompt must impose the 'materially better than principal direct answer' value contract."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt").lower()

    # The contract signal: the sub-agent must beat what the principal could write directly.
    assert (
        "materially better" in prompt
    ), "must state the materially-better-than-principal value contract"
    assert "10+ years" in prompt, "must anchor the expertise bar"


@pytest.mark.unit
def test_subagent_react_prompt_forbids_markdown_tables():
    """The prompt must explicitly forbid markdown tables (user preference)."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt")

    assert "NO markdown tables" in prompt, "must explicitly forbid markdown tables"


@pytest.mark.unit
def test_subagent_react_prompt_provides_task_calibration_lexicon():
    """The prompt must provide signal lexicon to calibrate output to the task nature."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt").lower()

    # Output forms covered (polyvalent: analysis/synthesis/summary/comparison)
    for keyword in ("analyse", "synthèse", "résumé", "comparaison"):
        assert keyword in prompt, f"calibration lexicon must include '{keyword}'"


@pytest.mark.unit
def test_subagent_react_prompt_imposes_self_check():
    """The prompt must impose a pre-emit self-check protocol."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt").lower()

    assert "self-check" in prompt, "must impose a self-check protocol before emitting"


@pytest.mark.unit
def test_subagent_react_prompt_explicit_anti_patterns():
    """The prompt must include explicit anti-pattern examples to exclude."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("subagent_react_prompt").lower()

    assert "anti-patterns" in prompt, "must include an explicit anti-patterns section"


@pytest.mark.unit
def test_response_prompt_has_subagent_delivery_override():
    """The response_node prompt must include the SubAgentDeliveryOverride block that preserves expert output."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("response_system_prompt_base")

    assert (
        "<SubAgentDeliveryOverride" in prompt
    ), "must include the SubAgentDeliveryOverride block preserving sub-agent expert output"
    assert "VERBATIM" in prompt, "override must mandate verbatim restitution"


@pytest.mark.unit
def test_response_prompt_keys_off_subagent_analysis_tag():
    """The override must key off the deterministic `<SubAgentAnalysis>` tag (not an LLM heuristic)."""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    prompt = load_prompt("response_system_prompt_base")

    # The tag is injected deterministically by `_wrap_subagent_analysis` in
    # `formatters/agent_results.py`. The response_node prompt must reference
    # this exact tag (opening and closing) so the LLM's detection logic is
    # deterministic, not heuristic over markdown structure / voice / length.
    assert (
        "<SubAgentAnalysis" in prompt
    ), "override must reference the opening <SubAgentAnalysis ...> tag"
    assert (
        "</SubAgentAnalysis>" in prompt
    ), "override must reference the closing </SubAgentAnalysis> tag"
    # The tags themselves must NOT leak into the final user-facing response
    assert (
        "DO NOT include the `<SubAgentAnalysis" in prompt
        or "DO NOT include the <SubAgentAnalysis" in prompt
    ), "override must instruct the LLM not to leak the infrastructure tags into the response"
