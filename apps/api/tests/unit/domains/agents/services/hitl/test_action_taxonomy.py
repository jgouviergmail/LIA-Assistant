"""Action-type taxonomy: what the HITL classifier announces for a pending tool.

The announced action type is not cosmetic. It is interpolated into the
classifier prompt (``Action type: ...``) and selects the few-shot block that
tells the LLM which parameter an EDIT may touch. Announcing "envoi" for
``delete_email_tool`` therefore did two things at once: it hid the deletion from
the prompt's own safety rule ("If *Delete* action and user says *Wait*, default
to REPLAN/REJECT, never APPROVE"), and it primed the model with send examples
that steer an EDIT toward ``{"to": ...}``.

That defect survived because the pre-existing tests only ever fed hand-written,
unambiguous names (``delete_contact``, ``send_email``) — never a real one. The
registry-wide classes below close that gap: they assert over the tools the
application actually registers.
"""

from __future__ import annotations

import pytest

from src.domains.agents.constants import (
    ACTION_TYPE_CREATE,
    ACTION_TYPE_DELETE,
    ACTION_TYPE_DRAFT_CRITIQUE,
    ACTION_TYPE_FOR_EACH_CONFIRMATION,
    ACTION_TYPE_FORWARD,
    ACTION_TYPE_GENERIC,
    ACTION_TYPE_GET,
    ACTION_TYPE_LIST,
    ACTION_TYPE_PLAN_APPROVAL,
    ACTION_TYPE_REPLY,
    ACTION_TYPE_SEARCH,
    ACTION_TYPE_SEND,
    ACTION_TYPE_UPDATE,
)
from src.domains.agents.services.hitl.action_taxonomy import (
    EXAMPLES_INTENTIONAL_DEFAULT,
    assert_examples_coverage,
    classify_action_type,
    classify_tool_name,
    emittable_action_types,
)

pytestmark = pytest.mark.unit


# Verb prefixes whose action type is non-negotiable for every registered tool.
# A read verb must never be announced as a write, and a destructive verb must
# never be announced as anything else.
_DESTRUCTIVE_PREFIXES = ("delete_", "remove_", "cancel_")
_READ_PREFIXES = ("get_", "list_", "search_", "read_")
_WRITE_TYPES = frozenset(
    {ACTION_TYPE_SEND, ACTION_TYPE_DELETE, ACTION_TYPE_CREATE, ACTION_TYPE_UPDATE}
)


@pytest.fixture(scope="module")
def registered_tool_names() -> list[str]:
    """Every tool name the application registers at runtime."""
    from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

    ensure_tools_loaded()
    names = sorted(get_all_tools())
    assert names, "tool registry is empty — the oracle would be vacuous"
    return names


class TestRealRegistryInvariants:
    """Fail-closed invariants over the tools actually registered."""

    def test_every_destructive_tool_is_announced_as_a_deletion(
        self, registered_tool_names: list[str]
    ) -> None:
        offenders = {
            name: classify_tool_name(name)
            for name in registered_tool_names
            if name.startswith(_DESTRUCTIVE_PREFIXES)
            and classify_tool_name(name) != ACTION_TYPE_DELETE
        }
        assert not offenders, (
            "destructive tools announced as something else — the prompt's "
            f"delete-safety rule cannot fire for them: {offenders}"
        )

    def test_no_read_only_tool_is_announced_as_a_write(
        self, registered_tool_names: list[str]
    ) -> None:
        offenders = {
            name: classify_tool_name(name)
            for name in registered_tool_names
            if name.startswith(_READ_PREFIXES) and classify_tool_name(name) in _WRITE_TYPES
        }
        assert not offenders, f"read-only tools announced as writes: {offenders}"

    def test_email_tools_are_classified_by_their_verb_not_by_the_domain_noun(
        self, registered_tool_names: list[str]
    ) -> None:
        """The regression that motivated this module.

        Every email tool used to match the ``"email"`` needle sitting in the
        SEND branch. Only the verb may decide.
        """
        expected = {
            "delete_email_tool": ACTION_TYPE_DELETE,
            "get_emails_tool": ACTION_TYPE_GET,
            "get_email_details_tool": ACTION_TYPE_GET,
            "search_emails_tool": ACTION_TYPE_SEARCH,
            "send_email_tool": ACTION_TYPE_SEND,
            "reply_email_tool": ACTION_TYPE_REPLY,
            "forward_email_tool": ACTION_TYPE_FORWARD,
        }
        missing = sorted(set(expected) - set(registered_tool_names))
        assert not missing, f"oracle drifted from the registry, unknown tools: {missing}"
        assert {name: classify_tool_name(name) for name in expected} == expected

    def test_every_registered_tool_resolves_to_a_known_action_type(
        self, registered_tool_names: list[str]
    ) -> None:
        emittable = emittable_action_types()
        unknown = {
            name: classify_tool_name(name)
            for name in registered_tool_names
            if classify_tool_name(name) not in emittable
        }
        assert not unknown, f"tools resolving outside the declared taxonomy: {unknown}"


class TestVerbMapping:
    """One representative name per mapped verb."""

    @pytest.mark.parametrize(
        "tool_name,expected",
        [
            # Read
            ("get_contact_details", ACTION_TYPE_GET),
            ("read_skill_resource", ACTION_TYPE_GET),
            ("fetch_web_page_tool", ACTION_TYPE_GET),
            ("list_contacts", ACTION_TYPE_LIST),
            ("search_contacts", ACTION_TYPE_SEARCH),
            ("find_places", ACTION_TYPE_SEARCH),
            ("recherche_contacts", ACTION_TYPE_SEARCH),
            # Write
            ("create_contact", ACTION_TYPE_CREATE),
            ("add_participant", ACTION_TYPE_CREATE),
            ("generate_image", ACTION_TYPE_CREATE),
            ("update_event_tool", ACTION_TYPE_UPDATE),
            ("edit_image", ACTION_TYPE_UPDATE),
            ("apply_labels_tool", ACTION_TYPE_UPDATE),
            ("complete_task_tool", ACTION_TYPE_UPDATE),
            ("set_current_item", ACTION_TYPE_UPDATE),
            # Destructive
            ("delete_contact", ACTION_TYPE_DELETE),
            ("remove_labels_tool", ACTION_TYPE_DELETE),
            ("cancel_reminder_tool", ACTION_TYPE_DELETE),
            # Outbound
            ("send_email", ACTION_TYPE_SEND),
            ("forward_email_tool", ACTION_TYPE_FORWARD),
            ("reply_email_tool", ACTION_TYPE_REPLY),
        ],
    )
    def test_verb_prefix_decides(self, tool_name: str, expected: str) -> None:
        assert classify_tool_name(tool_name) == expected

    def test_classification_is_case_insensitive(self) -> None:
        assert classify_tool_name("DELETE_EMAIL_TOOL") == ACTION_TYPE_DELETE

    def test_surrounding_whitespace_is_ignored(self) -> None:
        assert classify_tool_name("  delete_email_tool \n") == ACTION_TYPE_DELETE

    def test_unknown_verb_falls_back_to_generic(self) -> None:
        assert classify_tool_name("unknown_tool") == ACTION_TYPE_GENERIC

    def test_empty_name_is_generic(self) -> None:
        assert classify_tool_name("") == ACTION_TYPE_GENERIC
        assert classify_tool_name("   ") == ACTION_TYPE_GENERIC

    def test_deliberately_unmapped_verbs_stay_generic(self) -> None:
        """A guessed action type misleads the classifier; generic is honest."""
        for tool_name in ("activate_skill_tool", "control_hue_light_tool", "run_skill_script"):
            assert classify_tool_name(tool_name) == ACTION_TYPE_GENERIC


class TestSubstringFallback:
    """Names that are not verb-prefixed — MCP tools, user skills, web search."""

    @pytest.mark.parametrize(
        "tool_name,expected",
        [
            ("unified_web_search_tool", ACTION_TYPE_SEARCH),
            ("brave_search_tool", ACTION_TYPE_SEARCH),
            ("perplexity_search_tool", ACTION_TYPE_SEARCH),
            ("gmail_message_delete", ACTION_TYPE_DELETE),
            ("notion_page_create", ACTION_TYPE_CREATE),
            ("slack_message_send", ACTION_TYPE_SEND),
            ("jira_issue_update", ACTION_TYPE_UPDATE),
            ("mcp_calendar_list", ACTION_TYPE_LIST),
        ],
    )
    def test_fallback_recognises_the_verb_anywhere(self, tool_name: str, expected: str) -> None:
        assert classify_tool_name(tool_name) == expected

    def test_ambiguous_name_degrades_to_the_conservative_reading(self) -> None:
        """Destructive first: a name mentioning both must not read as the softer one."""
        assert classify_tool_name("mcp_search_and_delete") == ACTION_TYPE_DELETE
        assert classify_tool_name("mcp_list_then_remove") == ACTION_TYPE_DELETE


class TestInterruptTypes:
    """Interrupt-level types win over the tool behind them."""

    @pytest.mark.parametrize(
        "interrupt_type,expected",
        [
            ("plan_approval", ACTION_TYPE_PLAN_APPROVAL),
            ("draft_critique", ACTION_TYPE_DRAFT_CRITIQUE),
            ("for_each_confirmation", ACTION_TYPE_FOR_EACH_CONFIRMATION),
        ],
    )
    def test_interrupt_type_short_circuits_the_tool_name(
        self, interrupt_type: str, expected: str
    ) -> None:
        context = [{"type": interrupt_type, "name": "send_email_tool"}]
        assert classify_action_type(context) == expected

    def test_unknown_interrupt_type_falls_through_to_the_tool_name(self) -> None:
        context = [{"type": "something_new", "name": "delete_email_tool"}]
        assert classify_action_type(context) == ACTION_TYPE_DELETE


class TestContextShape:
    """`classify_action_type` on the raw interrupt payload."""

    def test_empty_context_is_generic(self) -> None:
        assert classify_action_type([]) == ACTION_TYPE_GENERIC

    def test_multiple_actions_are_generic(self) -> None:
        """No single action can be announced precisely."""
        context = [{"name": "search_contacts"}, {"name": "send_email"}]
        assert classify_action_type(context) == ACTION_TYPE_GENERIC

    @pytest.mark.parametrize("key", ["name", "tool", "tool_name"])
    def test_every_accepted_name_key_is_read(self, key: str) -> None:
        assert classify_action_type([{key: "delete_email_tool"}]) == ACTION_TYPE_DELETE

    def test_action_without_a_name_is_generic_not_an_error(self) -> None:
        assert classify_action_type([{"args": {"query": "x"}}]) == ACTION_TYPE_GENERIC

    def test_non_string_tool_name_is_coerced(self) -> None:
        """The validator stringifies malformed payloads; classification follows."""
        assert classify_action_type([{"name": 42}]) == ACTION_TYPE_GENERIC


class TestExamplesCoverage:
    """Every announced action type must resolve to a deliberate example block."""

    def test_real_examples_file_covers_every_emittable_type(self) -> None:
        from src.domains.agents.services.hitl_classifier import (
            _load_classifier_example_sections,
        )

        assert_examples_coverage(_load_classifier_example_sections())

    def test_missing_default_section_is_rejected(self) -> None:
        with pytest.raises(AssertionError, match="no '=== default ===' section"):
            assert_examples_coverage({ACTION_TYPE_DELETE: "..."})

    def test_uncovered_type_is_rejected(self) -> None:
        sections = {"default": "...", ACTION_TYPE_GENERIC: "..."}
        with pytest.raises(AssertionError, match="no example section"):
            assert_examples_coverage(sections)

    def test_intentional_default_types_are_accepted_without_a_section(self) -> None:
        sections = {"default": "..."}
        sections.update(
            {
                action_type: "..."
                for action_type in emittable_action_types()
                if action_type not in EXAMPLES_INTENTIONAL_DEFAULT
            }
        )
        assert_examples_coverage(sections)


class TestClassifierDelegation:
    """The classifier must not keep a second, divergent copy of this logic."""

    def test_extract_action_type_delegates_to_the_taxonomy(self) -> None:
        from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

        # __new__: the constructor builds an LLM, which this contract does not need.
        classifier = HitlResponseClassifier.__new__(HitlResponseClassifier)
        for tool_name in ("delete_email_tool", "get_emails_tool", "reply_email_tool"):
            context = [{"tool_name": tool_name}]
            assert classifier._extract_action_type(context) == classify_tool_name(tool_name)
