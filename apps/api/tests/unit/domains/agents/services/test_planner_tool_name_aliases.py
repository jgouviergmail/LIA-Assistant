"""The planner's legacy tool aliases must actually be applied.

Production defect, 2026-07-30: every email request failed with
``Tool 'search_emails_tool' not found in catalogue`` /
``ToolManifestNotFound``. The catalogue was intact — the five email tools were
registered and ``get_emails_tool`` was offered to the planner — but the planner
emitted the PRE-UNIFICATION name, and the alias table that exists precisely to
repair that was never consulted.

Cause: ``_normalize_tool_name`` returned early on any name already ending in
``_tool``, while all 24 keys of the alias table end in ``_tool``. The table has
therefore been unreachable since the initial release (the unification dates
from v1.0.0, 2026-03-12), and only bites when the model reaches for a name it
remembers from the old vocabulary.

The alias is the last line of defence: a name with no manifest is rejected by
the validator, the adaptive replanner reads the failure as transient, retries
the identical plan, and the user is told the request failed with no usable
reason.
"""

import pytest

from src.domains.agents.services.smart_planner_service import SmartPlannerService

# Every unified family, one legacy spelling each — the shapes an LLM reaches
# for when it recalls the pre-unification vocabulary.
LEGACY_TO_UNIFIED = [
    ("search_emails_tool", "get_emails_tool", "email"),
    ("list_emails_tool", "get_emails_tool", "email"),
    ("get_email_details_tool", "get_emails_tool", "email"),
    ("search_events_tool", "get_events_tool", "event"),
    ("find_events_tool", "get_events_tool", "event"),
    ("search_contacts_tool", "get_contacts_tool", "contact"),
    ("search_tasks_tool", "get_tasks_tool", "task"),
    ("search_files_tool", "get_files_tool", "file"),
    ("search_places_tool", "get_places_tool", "place"),
]


@pytest.fixture
def planner() -> SmartPlannerService:
    """A planner whose collaborators are irrelevant to name normalization."""
    return SmartPlannerService()


@pytest.mark.parametrize(("legacy", "unified", "domain"), LEGACY_TO_UNIFIED)
def test_legacy_name_is_rewritten_to_the_manifested_one(planner, legacy, unified, domain):
    """The exact production failure: the alias must fire on a `_tool` name."""
    assert planner._normalize_tool_name(legacy, domain) == unified


def test_missing_suffix_is_still_added(planner):
    """The historical behaviour of the function is unchanged."""
    assert planner._normalize_tool_name("get_emails", "email") == "get_emails_tool"


def test_a_legacy_name_without_the_suffix_is_also_repaired(planner):
    """Both defects at once — suffix added, then the alias applied."""
    assert planner._normalize_tool_name("search_emails", "email") == "get_emails_tool"


def test_a_current_name_passes_through_untouched(planner):
    """No alias, no surprise: the overwhelmingly common case is a no-op."""
    for name in ("get_emails_tool", "send_email_tool", "get_peer_availability_tool"):
        assert planner._normalize_tool_name(name, "email") == name


def test_mcp_tools_are_never_suffixed_nor_aliased(planner):
    """MCP names do not follow the `_tool` convention and must stay verbatim."""
    assert planner._normalize_tool_name("mcp_excalidraw_create", "mcp") == "mcp_excalidraw_create"


def test_empty_name_stays_empty(planner):
    assert planner._normalize_tool_name("", "email") == ""


def test_every_alias_maps_onto_a_manifested_tool():
    """An alias pointing at a tool with no manifest would just move the defect.

    The table is data; nothing but this test connects it to the catalogue it
    is supposed to repair.
    """
    from src.domains.agents.registry.catalogue import ToolManifest  # noqa: F401
    from src.domains.agents.services import smart_planner_service as module

    source = module.__file__
    with open(source, encoding="utf-8") as handle:
        body = handle.read()
    targets = {
        line.split('": "')[1].split('"')[0]
        for line in body.splitlines()
        if '": "' in line and line.strip().startswith('"') and "_tool" in line
    }
    unified = {
        "get_emails_tool",
        "get_events_tool",
        "get_contacts_tool",
        "get_tasks_tool",
        "get_files_tool",
        "get_places_tool",
    }
    assert unified <= targets, f"alias targets drifted: {sorted(targets)}"
