"""Prompt assembly for the journal extraction and consolidation LLM calls.

Extracted from ``extraction_service`` / ``consolidation_service`` so the exact
prompt sent at runtime has a single, importable definition. Two layers:

- ``render_*`` — pure functions taking the templates as arguments. No I/O, no
  settings, no DB. This is what the measurement harness
  (``scripts/measure_journal_themes.py``) replays against candidate prompt
  files, which guarantees the harness can never drift from production.
- ``build_*`` — thin wrappers that load the shipped templates via
  ``load_prompt`` and delegate to the ``render_*`` layer.

The analyst persona is appended to BOTH prompts (it is independent of the
conversational personality, which only defines how the assistant *talks*).
"""

from __future__ import annotations

from src.domains.agents.prompts.prompt_loader import load_prompt

# The persona is appended after the main template, separated by a blank line.
_PERSONA_SEPARATOR = "\n\n"


def _render_persona(persona_template: str, personality_code: str | None) -> str:
    """Render the analyst persona block.

    Args:
        persona_template: Raw ``journal_analyst_persona`` template.
        personality_code: Active conversational personality code, or None.

    Returns:
        The rendered persona block.
    """
    return persona_template.format(personality_code=personality_code or "none")


def render_introspection_prompt(
    template: str,
    persona_template: str,
    *,
    conversation: str,
    existing_entries: str,
    current_chars: int,
    max_chars: int,
    size_warning: str,
    user_language: str,
    max_entry_chars: int,
    health_context: str,
    inner_state_section: str,
    previous_turn_directives_section: str,
    personality_code: str | None,
) -> str:
    """Render the post-conversation extraction prompt from explicit templates.

    Pure function — the caller supplies both templates, so a candidate prompt
    file can be rendered exactly the way production renders the shipped one.

    Args:
        template: Raw ``journal_introspection_prompt`` template.
        persona_template: Raw ``journal_analyst_persona`` template.
        conversation: Formatted conversation excerpt.
        existing_entries: Formatted pre-filtered existing entries.
        current_chars: Total characters currently used by active entries.
        max_chars: The user's configured total-size ceiling.
        size_warning: Pre-computed size warning (may be empty).
        user_language: The user's configured language code.
        max_entry_chars: Per-entry character ceiling.
        health_context: Optional health-metrics block (may be empty).
        inner_state_section: Optional psyche block (may be empty).
        previous_turn_directives_section: Optional deferred self-evaluation
            block listing the directives injected at turn T-1 (may be empty).
        personality_code: Active conversational personality code, or None.

    Returns:
        The complete prompt string sent to the extraction LLM.
    """
    prompt = template.format(
        conversation=conversation,
        existing_entries=existing_entries,
        current_chars=current_chars,
        max_chars=max_chars,
        size_warning=size_warning,
        user_language=user_language,
        max_entry_chars=max_entry_chars,
        health_context=health_context,
        inner_state_section=inner_state_section,
        previous_turn_directives_section=previous_turn_directives_section,
    )
    return prompt + _PERSONA_SEPARATOR + _render_persona(persona_template, personality_code)


def build_introspection_prompt(
    *,
    conversation: str,
    existing_entries: str,
    current_chars: int,
    max_chars: int,
    size_warning: str,
    user_language: str,
    max_entry_chars: int,
    health_context: str,
    inner_state_section: str,
    previous_turn_directives_section: str,
    personality_code: str | None,
) -> str:
    """Load the shipped templates and render the extraction prompt.

    Args:
        conversation: Formatted conversation excerpt.
        existing_entries: Formatted pre-filtered existing entries.
        current_chars: Total characters currently used by active entries.
        max_chars: The user's configured total-size ceiling.
        size_warning: Pre-computed size warning (may be empty).
        user_language: The user's configured language code.
        max_entry_chars: Per-entry character ceiling.
        health_context: Optional health-metrics block (may be empty).
        inner_state_section: Optional psyche block (may be empty).
        previous_turn_directives_section: Optional deferred self-evaluation
            block (may be empty).
        personality_code: Active conversational personality code, or None.

    Returns:
        The complete prompt string sent to the extraction LLM.
    """
    return render_introspection_prompt(
        str(load_prompt("journal_introspection_prompt")),
        str(load_prompt("journal_analyst_persona")),
        conversation=conversation,
        existing_entries=existing_entries,
        current_chars=current_chars,
        max_chars=max_chars,
        size_warning=size_warning,
        user_language=user_language,
        max_entry_chars=max_entry_chars,
        health_context=health_context,
        inner_state_section=inner_state_section,
        previous_turn_directives_section=previous_turn_directives_section,
        personality_code=personality_code,
    )


def render_consolidation_prompt(
    template: str,
    persona_template: str,
    *,
    all_entries: str,
    current_chars: int,
    max_chars: int,
    size_warning: str,
    current_datetime: str,
    conversation_history_section: str,
    usage_patterns_section: str,
    user_language: str,
    max_entry_chars: int,
    size_management_instruction: str,
    health_signals_section: str,
    personality_code: str | None,
) -> str:
    """Render the periodic consolidation prompt from explicit templates.

    Pure function — see :func:`render_introspection_prompt`.

    Args:
        template: Raw ``journal_consolidation_prompt`` template.
        persona_template: Raw ``journal_analyst_persona`` template.
        all_entries: Formatted working set (every active entry).
        current_chars: Total characters currently used by active entries.
        max_chars: The user's configured total-size ceiling.
        size_warning: Pre-computed size warning (may be empty).
        current_datetime: Current UTC timestamp, human-readable.
        conversation_history_section: Optional recent-history block.
        usage_patterns_section: Optional usage-pattern block.
        user_language: The user's configured language code.
        max_entry_chars: Per-entry character ceiling.
        size_management_instruction: Pre-computed size directive.
        health_signals_section: Optional health-metrics block.
        personality_code: Active conversational personality code, or None.

    Returns:
        The complete prompt string sent to the consolidation LLM.
    """
    prompt = template.format(
        all_entries=all_entries,
        current_chars=current_chars,
        max_chars=max_chars,
        size_warning=size_warning,
        current_datetime=current_datetime,
        conversation_history_section=conversation_history_section,
        usage_patterns_section=usage_patterns_section,
        user_language=user_language,
        max_entry_chars=max_entry_chars,
        size_management_instruction=size_management_instruction,
        health_signals_section=health_signals_section,
    )
    return prompt + _PERSONA_SEPARATOR + _render_persona(persona_template, personality_code)


def build_consolidation_prompt(
    *,
    all_entries: str,
    current_chars: int,
    max_chars: int,
    size_warning: str,
    current_datetime: str,
    conversation_history_section: str,
    usage_patterns_section: str,
    user_language: str,
    max_entry_chars: int,
    size_management_instruction: str,
    health_signals_section: str,
    personality_code: str | None,
) -> str:
    """Load the shipped templates and render the consolidation prompt.

    Args:
        all_entries: Formatted working set (every active entry).
        current_chars: Total characters currently used by active entries.
        max_chars: The user's configured total-size ceiling.
        size_warning: Pre-computed size warning (may be empty).
        current_datetime: Current UTC timestamp, human-readable.
        conversation_history_section: Optional recent-history block.
        usage_patterns_section: Optional usage-pattern block.
        user_language: The user's configured language code.
        max_entry_chars: Per-entry character ceiling.
        size_management_instruction: Pre-computed size directive.
        health_signals_section: Optional health-metrics block.
        personality_code: Active conversational personality code, or None.

    Returns:
        The complete prompt string sent to the consolidation LLM.
    """
    return render_consolidation_prompt(
        str(load_prompt("journal_consolidation_prompt")),
        str(load_prompt("journal_analyst_persona")),
        all_entries=all_entries,
        current_chars=current_chars,
        max_chars=max_chars,
        size_warning=size_warning,
        current_datetime=current_datetime,
        conversation_history_section=conversation_history_section,
        usage_patterns_section=usage_patterns_section,
        user_language=user_language,
        max_entry_chars=max_entry_chars,
        size_management_instruction=size_management_instruction,
        health_signals_section=health_signals_section,
        personality_code=personality_code,
    )
