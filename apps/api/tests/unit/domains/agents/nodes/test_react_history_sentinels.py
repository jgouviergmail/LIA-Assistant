"""The ReAct history window must not teach the model to write widget markup.

``response_node`` writes the enriched answer — sentinel included — back into
``state["messages"]``, and ``_window_messages_for_react`` served that history
RAW to the ReAct loop (the response path neutralizes HTML, this one never did).
That is where the model learned the markup by imitation, which produced the
duplicate widgets and the phantom sentinels of 2026-07-21.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.core.constants import CONTEXT_WIDGET_DISPLAYED_PLACEHOLDER
from src.domains.agents.nodes.react_nodes import _neutralize_widget_sentinels

_SENTINEL = (
    '<div class="lia-skill-app" data-registry-id="skill_app_545e26">'
    '<div class="lia-skill-app__placeholder">'
    '<div class="lia-skill-app__loading">Chargement du skill…</div>'
    "</div></div>"
)


class TestNeutralizeWidgetSentinels:
    def test_replaces_the_sentinel_with_an_opaque_marker(self) -> None:
        history = [AIMessage(content=f"<p>Voilà.</p>\n\n{_SENTINEL}")]

        out = _neutralize_widget_sentinels(history)

        assert len(out) == 1
        content = str(out[0].content)
        assert "lia-skill-app" not in content
        assert "skill_app_545e26" not in content
        # The FACT that a widget was displayed survives — only the how-to goes.
        assert CONTEXT_WIDGET_DISPLAYED_PLACEHOLDER in content
        assert "<p>Voilà.</p>" in content

    def test_preserves_the_message_id_so_the_reducer_still_matches(self) -> None:
        history = [AIMessage(content=_SENTINEL, id="msg-42")]
        assert _neutralize_widget_sentinels(history)[0].id == "msg-42"

    def test_preserves_tool_calls_and_provider_metadata(self) -> None:
        """Rebuilding the message instead of copying it would orphan the
        ToolMessages that answer these calls — the provider then rejects the
        whole request, or `enforce_tool_message_pairing` drops them silently."""
        carrier = AIMessage(
            content=f"<p>ok</p>{_SENTINEL}",
            id="msg-7",
            tool_calls=[{"name": "run_skill_script", "args": {}, "id": "call_1"}],
            additional_kwargs={"provider_raw": "keep-me"},
        )

        out = _neutralize_widget_sentinels([carrier])[0]

        assert "lia-skill-app" not in str(out.content)
        assert isinstance(out, AIMessage)
        assert [tc["id"] for tc in out.tool_calls] == ["call_1"]
        assert out.additional_kwargs == {"provider_raw": "keep-me"}
        assert out.id == "msg-7"

    def test_passes_untouched_messages_through_by_identity(self) -> None:
        """No sentinel, no copy — the windowed list must stay cheap."""
        plain = AIMessage(content="<p>Just prose</p>")
        human = HumanMessage(content="salut")
        tool = ToolMessage(content='{"ok": true}', tool_call_id="c1")

        out = _neutralize_widget_sentinels([human, plain, tool])

        assert out[0] is human
        assert out[1] is plain
        assert out[2] is tool

    def test_leaves_non_ai_messages_alone_even_if_they_contain_markup(self) -> None:
        """A tool result quoting the markup is data, not a style precedent."""
        tool = ToolMessage(content=_SENTINEL, tool_call_id="c1")
        assert _neutralize_widget_sentinels([tool])[0] is tool

    def test_empty_history_is_a_no_op(self) -> None:
        assert _neutralize_widget_sentinels([]) == []
