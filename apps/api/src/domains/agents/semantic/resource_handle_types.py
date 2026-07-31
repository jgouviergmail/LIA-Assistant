"""Resource handle semantic types — values no user can utter and no tool resolves.

A *resource handle* is a value that satisfies BOTH conditions:

1. the user cannot supply it from their own phrasing (an opaque id, not a name
   they would say out loud), and
2. the receiving tool does not resolve it internally from a human label.

Only such a parameter makes a catalogue ill-formed: when a tool declaring one
as REQUIRED reaches the planner without a tool that PRODUCES it, the space of
valid plans is empty before the model starts, and it can only invent a tool
name (production incident 2026-07-30, ``search_emails_tool``).

Both conditions matter — the first alone yields false positives. Counter-examples
measured on this codebase, all correctly left unannotated:

- ``get_peer_availability_tool.peer_name`` — resolved internally by folded
  match against the caller's connections (``peers_read_tools._resolve``), so
  "is Marie free tomorrow?" is a valid single-step plan.
- ``control_hue_light_tool.light_name_or_id`` — ``_find_resource_by_name``
  matches on id OR lowercased name, and lists the available names on failure.
- ``get_wikipedia_article_tool.title`` — a title the user pronounces.

By contrast ``toggle_scheduled_action_tool.action_id`` parses a strict ``UUID``
and fails outright on anything else: nobody dictates a UUID, and only
``list_scheduled_actions_tool`` exposes the real ones.

Why a separate module: ``core_types.py`` is frozen by the file-size ratchet
(``tests/unit/file_size_baseline.json``) with barely any headroom, and CLAUDE.md
forbids raising a cap — a feature that outgrows a file gets a cohesive module.
Keeping the criterion documented beside the types is the point: the expensive
mistake is adding a type here for a parameter the tool already resolves.
"""

from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.domains.agents.semantic.type_registry import TypeRegistry

AUTOMATION_ID = SemanticType(
    name="automation_id",
    parent="Identifier",
    category=TypeCategory.RESOURCE_ID,
    description=(
        "UUID of a user automation (scheduled action). toggle_scheduled_action_tool "
        "parses it strictly and resolves nothing from a title, so the value can "
        "only come from list_scheduled_actions_tool."
    ),
    labels={"en": "Automation id", "fr": "Identifiant d'automatisation"},
    examples=["3f2b9c14-8e7a-4d51-9b0e-1a2c3d4e5f60"],
    source_domains=["automation"],
    used_in_tools=["list_scheduled_actions_tool", "toggle_scheduled_action_tool"],
)


ALL_RESOURCE_HANDLE_TYPES: tuple[SemanticType, ...] = (AUTOMATION_ID,)


def load_resource_handle_types(registry: TypeRegistry) -> None:
    """Register every resource-handle type into the registry.

    Called from ``load_core_types`` so that every caller — application startup,
    integration fixtures, unit tests building their own registry — gets the
    complete ontology through a single entry point.

    Args:
        registry: TypeRegistry instance to populate.
    """
    for semantic_type in ALL_RESOURCE_HANDLE_TYPES:
        registry.register(semantic_type)


__all__ = [
    "ALL_RESOURCE_HANDLE_TYPES",
    "AUTOMATION_ID",
    "load_resource_handle_types",
]
