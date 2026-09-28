"""Only the final answer's selected records may become HTML cards."""

import pytest

from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.response_node import (
    _apply_relevant_ids_filtering,
    _render_response_html,
)

pytestmark = pytest.mark.unit


def test_cards_without_a_model_selection_do_not_display_every_search_result() -> None:
    content, selected = _apply_relevant_ids_filtering(
        final_content="Only one appointment matters.",
        original_content="Only one appointment matters.",
        current_turn_registry={"event_a": {"type": "EVENT"}, "event_b": {"type": "EVENT"}},
        state=MessagesState(),
        result_domains={"events"},
        last_user_message="Find a useful appointment.",
        run_id="selection-proof",
        require_selection=True,
    )
    assert selected == {}
    assert content == "Only one appointment matters."


def test_empty_selection_in_a_mixed_weather_email_turn_stays_empty() -> None:
    content, selected = _apply_relevant_ids_filtering(
        final_content="<relevant_ids></relevant_ids>No useful matches.",
        original_content="<relevant_ids></relevant_ids>No useful matches.",
        current_turn_registry={
            "email_a": {"type": "EMAIL", "payload": {"subject": "Discarded email"}},
            "weather_a": {"type": "WEATHER", "payload": {"temperature": 12}},
        },
        state=MessagesState(),
        result_domains={"emails", "weathers"},
        last_user_message="Find a useful appointment.",
        run_id="selection-proof",
    )
    assert selected == {}
    assert content == "No useful matches."


@pytest.mark.parametrize("display_mode", ["cards", "html_cards"])
def test_rejected_reference_records_are_not_reintroduced_by_html_fallback(
    display_mode: str,
) -> None:
    answer = _render_response_html(
        final_content="No useful matches.",
        current_turn_registry={},
        resolved_context_for_html={
            "items": [{"id": "discarded", "subject": "Discarded email", "from": "a@example.com"}]
        },
        user_display_mode=display_mode,
        user_viewport="desktop",
        user_language="en",
        user_timezone="UTC",
        run_id="selection-proof",
    )
    assert answer == "No useful matches."


def test_selection_keeps_only_answer_records_and_required_widgets() -> None:
    content, selected = _apply_relevant_ids_filtering(
        final_content="<relevant_ids>email_useful</relevant_ids>Here is the useful email.",
        original_content="<relevant_ids>email_useful</relevant_ids>Here is the useful email.",
        current_turn_registry={
            "email_useful": {"type": "EMAIL", "payload": {"subject": "Useful"}},
            "email_unused": {"type": "EMAIL", "payload": {"subject": "Unused"}},
            "draft_action": {"type": "DRAFT", "payload": {}},
        },
        state=MessagesState(),
        result_domains={"emails"},
        last_user_message="Find the useful email.",
        run_id="selection-proof",
    )
    assert selected is not None
    assert set(selected) == {"email_useful", "draft_action"}
    answer = _render_response_html(
        final_content=content,
        current_turn_registry={
            key: value for key, value in selected.items() if key != "draft_action"
        },
        resolved_context_for_html=None,
        user_display_mode="cards",
        user_viewport="desktop",
        user_language="en",
        user_timezone="UTC",
        run_id="selection-proof",
    )
    assert "Useful" in answer
    assert "Unused" not in answer


def test_proactive_search_candidates_also_need_selection_in_cards_mode() -> None:
    _, selected = _apply_relevant_ids_filtering(
        final_content="<relevant_ids>email_useful</relevant_ids>Useful email.",
        original_content="<relevant_ids>email_useful</relevant_ids>Useful email.",
        current_turn_registry={
            "email_useful": {"type": "EMAIL"},
            "event_unused": {"type": "EVENT"},
        },
        state=MessagesState(initiative_results=[{"registry_ids": ["event_unused"]}]),
        result_domains={"emails", "events"},
        last_user_message="Find a useful email.",
        run_id="selection-proof",
        require_selection=True,
    )
    assert selected is not None
    assert set(selected) == {"email_useful"}
