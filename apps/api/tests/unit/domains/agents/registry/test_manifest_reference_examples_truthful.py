"""A published reference path must be one the tool actually produces.

Sibling of ``test_catalogue_registry_parity`` — same doctrine, one level
deeper. That test keeps the promise "the advertised tool exists"; this one
keeps "the advertised PATH resolves".

The defect it closes, measured in production 2026-08-01: the planner read
``contacts[0].name`` from ``get_contacts_tool``'s ``reference_examples``,
generated exactly that reference, and the run died on::

    Failed to resolve $steps.step_1.contacts[0].name:
    path 'contacts[0].name' not found in step result. Error: 'name'

Worse than a silent miss: ``ReferenceValidator`` validates a path AGAINST the
reference_examples first and returns "valid" on a match, so the guard built for
this case actively APPROVED the broken reference. The manifest is therefore the
only authority in play — and an authority that lies has to be caught here.

The oracle is the real pipeline, not a hand-written fixture: the tool's own
mixin builds the output, and the derivation below mirrors
``parallel_executor._execute_tool_step`` (registry payloads grouped by
``meta.domain``, then the tool's ``structured_data`` merged without overwrite),
which is what ``completed_steps`` holds when a ``$steps`` reference resolves.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from src.core.field_names import FIELD_REGISTRY_ID, FIELD_RESULT
from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = pytest.mark.unit


class _Builder(ToolOutputMixin):
    """Minimal host for the mixin builders (they only need ``operation``)."""

    operation = "search"


# --------------------------------------------------------------------------
# Provider payloads, in the shape the tools hand to their builder: RAW records
# straight from the provider. `google_contacts_tools` passes `result["person"]`
# / `connections` verbatim, `emails_tools` the Gmail message, etc. Using a
# pre-normalized dict here would test the fixture instead of the product.
# --------------------------------------------------------------------------
_PERSON = {
    "resourceName": "people/c6737050419687533025",
    "names": [{"displayName": "Alice Vernier", "givenName": "Alice"}],
    "emailAddresses": [{"value": "alice@example.com", "type": "home"}],
    "phoneNumbers": [{"value": "+33612345678", "type": "mobile"}],
    "addresses": [{"formattedValue": "1 rue de la Paix\n75002 Paris", "type": "home"}],
    "organizations": [{"name": "ACME"}],
    "birthdays": [{"date": {"year": 1985, "month": 4, "day": 12}}],
    "biographies": [{"value": "note"}],
}
_MESSAGE = {
    "id": "18f0a1b2c3d4e5f6",
    "threadId": "18f0a1b2c3d4e5f0",
    "snippet": "Bonjour, on se voit jeudi ?",
    "internalDate": "1753900000000",
    "payload": {
        "headers": [
            {"name": "Subject", "value": "Point de jeudi"},
            {"name": "From", "value": "Alice <alice@example.com>"},
        ]
    },
    "body": "Bonjour, on se voit jeudi ?",
}
_EVENT = {
    "id": "evt_123",
    "summary": "Point hebdo",
    "location": "Paris",
    "description": "ordre du jour",
    "calendar_id": "primary",
    "start": {"dateTime": "2026-08-06T10:00:00+02:00"},
    "end": {"dateTime": "2026-08-06T11:00:00+02:00"},
}
_TASK = {"id": "task_1", "title": "Rappeler Alice", "notes": "avant jeudi", "status": "needsAction"}
_FILE = {"id": "file_1", "name": "compte-rendu.pdf", "mimeType": "application/pdf", "content": "x"}
_PLACE = {
    "id": "place_1",
    "place_id": "place_1",
    "name": "Café de la Paix",
    "phone": "+33142000000",
    "opening_hours": ["lundi 08:00-19:00"],
}


def _build(tool_name: str) -> UnifiedToolOutput:
    """Build the tool's real output from a raw provider payload."""
    builder = _Builder()
    builders = {
        "get_contacts_tool": lambda: builder.build_contacts_output(contacts=[dict(_PERSON)]),
        "get_emails_tool": lambda: builder.build_emails_output(emails=[dict(_MESSAGE)]),
        "get_events_tool": lambda: builder.build_events_output(events=[dict(_EVENT)]),
        "get_tasks_tool": lambda: builder.build_tasks_output(tasks=[dict(_TASK)]),
        "get_files_tool": lambda: builder.build_files_output(files=[dict(_FILE)]),
        "get_places_tool": lambda: builder.build_places_output(places=[dict(_PLACE)]),
    }
    return builders[tool_name]()


def _completed_step(output: UnifiedToolOutput) -> dict[str, Any]:
    """Mirror ``parallel_executor._execute_tool_step``'s structured_data build.

    Registry payloads are grouped under ``meta.domain`` and enriched with their
    registry id; the tool's own ``structured_data`` is then merged WITHOUT
    overwriting a registry-derived key (the "gentle merge").
    """
    structured: dict[str, Any] = {FIELD_RESULT: output.summary_for_llm}
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for item_id, item in (output.registry_updates or {}).items():
        item_dict = item.model_dump() if hasattr(item, "model_dump") else item
        payload = item_dict.get("payload", {})
        meta = item_dict.get("meta", {})
        item_type = item_dict.get("type", "")
        key = meta.get("domain") or (f"{item_type.lower()}s" if item_type else "unknown")
        if payload:
            by_domain.setdefault(key, []).append({**payload, FIELD_REGISTRY_ID: item_id})
    structured.update(by_domain)
    if output.structured_data:
        for key, value in output.structured_data.items():
            structured.setdefault(key, value)
    return structured


#: The read tools whose output shape this test can build without a provider.
#: Every one of them is registry-enabled, so `format_registry_response` (which
#: delegates to the builder used here) IS the production path.
COVERED_TOOLS = (
    "get_contacts_tool",
    "get_emails_tool",
    "get_events_tool",
    "get_tasks_tool",
    "get_files_tool",
    "get_places_tool",
)


@pytest.fixture(scope="module")
def manifests() -> dict[str, ToolManifest]:
    """The catalogue as the planner receives it."""
    registry = AgentRegistry()
    initialize_catalogue(registry)
    return {manifest.name: manifest for manifest in registry.list_tool_manifests()}


@pytest.mark.parametrize("tool_name", COVERED_TOOLS)
class TestReferenceExamplesResolve:
    def test_every_reference_example_resolves(
        self, tool_name: str, manifests: dict[str, ToolManifest]
    ) -> None:
        """Each published path must resolve against the tool's real output."""
        manifest = manifests[tool_name]
        completed = {"step_1": _completed_step(_build(tool_name))}
        resolver = ReferenceResolver()

        broken: list[str] = []
        for example in manifest.reference_examples or []:
            try:
                resolver.resolve(f"$steps.step_1.{example}", completed, None)
            except (KeyError, ValueError):
                broken.append(example)

        assert not broken, (
            f"{tool_name} publishes {len(broken)} reference_example(s) its output does not "
            f"produce: {broken}. The planner reads these paths as a contract and "
            f"ReferenceValidator approves them on sight — a wrong one fails at execution, "
            f"after the plan is committed. Available top-level keys: "
            f"{sorted(completed['step_1'])}. Fix the manifest, or make the tool produce "
            f"the path (see the `subject`/`from` promotions in ToolOutputMixin)."
        )

    def test_every_declared_top_level_output_resolves(
        self, tool_name: str, manifests: dict[str, ToolManifest]
    ) -> None:
        """Top-level `outputs` entries are STRUCTURAL and must always resolve.

        Scoped to paths without ``[]`` on purpose. A per-item field
        (``places[].rating``, ``events[].attendees``) is absent whenever the
        provider held no value for THAT record — its absence proves nothing
        about the manifest, and asserting on it would only test the fixture.
        A top-level scalar (``total``, ``count``) does not depend on the data:
        either the execution exposes it for every call, or it never does.
        """
        manifest = manifests[tool_name]
        completed = {"step_1": _completed_step(_build(tool_name))}
        resolver = ReferenceResolver()

        broken: list[str] = []
        for output_field in manifest.outputs or []:
            if "[]" in output_field.path:
                continue
            try:
                resolver.resolve(f"$steps.step_1.{output_field.path}", completed, None)
            except (KeyError, ValueError):
                broken.append(output_field.path)

        assert not broken, (
            f"{tool_name} declares {len(broken)} top-level output path(s) its execution "
            f"never produces: {broken}. Available top-level keys: "
            f"{sorted(completed['step_1'])}."
        )


class TestEmptyResultStillCountable:
    """A zero-result read must still expose its count.

    `contacts[0]` cannot resolve on an empty search — but `count` must, so a
    plan can branch on "nothing found" without the reference blowing up.
    """

    @pytest.mark.parametrize("tool_name", COVERED_TOOLS)
    def test_count_resolves_on_empty_result(self, tool_name: str) -> None:
        builder = _Builder()
        empty = {
            "get_contacts_tool": lambda: builder.build_contacts_output(contacts=[]),
            "get_emails_tool": lambda: builder.build_emails_output(emails=[]),
            "get_events_tool": lambda: builder.build_events_output(events=[]),
            "get_tasks_tool": lambda: builder.build_tasks_output(tasks=[]),
            "get_files_tool": lambda: builder.build_files_output(files=[]),
            "get_places_tool": lambda: builder.build_places_output(places=[]),
        }[tool_name]()
        completed = {"step_1": _completed_step(empty)}

        assert ReferenceResolver().resolve("$steps.step_1.count", completed, None) == 0


class TestEveryManifestIsInternallyConsistent:
    """The WHOLE catalogue, not the six tools whose output can be built here.

    The tests above run the real pipeline, so they need a builder — which is why
    they cover 6 manifests. The other 50 that publish `reference_examples` were
    verified by nobody, and they are the same authority that lied about
    `contacts[0].name`: `ReferenceValidator` approves a path on sight when it
    matches an example, so an unverified example is an approved fiction.

    What CAN be checked without any provider is internal consistency: a
    published example must address something the manifest itself declares in
    `outputs`. It is weaker than resolving against a real payload, and it caught
    six real defects the day it was written — three Hue list tools publishing
    bare `name` / `is_on` / `brightness` / `children`, where the execution puts
    those fields INSIDE `hues[]` / `rooms[]` / `scenes[]` (and calls the last
    one `children_count`). A planner following them would have generated
    `$steps.step_1.name` and died exactly like the contacts case did.
    """

    @staticmethod
    def _root(path: str) -> str:
        """The top-level key a reference path addresses."""
        return re.split(r"[.\[]", path, maxsplit=1)[0]

    def test_no_manifest_publishes_a_path_it_does_not_declare(
        self, manifests: dict[str, ToolManifest]
    ) -> None:
        offenders: list[str] = []
        for manifest in manifests.values():
            declared = {self._root(output.path) for output in manifest.outputs or []}
            # No declared outputs at all = nothing to contradict. Those tools
            # are covered by the resolution tests above or by nothing yet, which
            # is a different (documented) gap.
            if not declared or not manifest.reference_examples:
                continue
            for example in manifest.reference_examples:
                if self._root(example) not in declared:
                    offenders.append(f"{manifest.name}: {example!r} (declares {sorted(declared)})")

        assert not offenders, (
            "reference_examples addressing a key the manifest never declares — "
            "the planner is told to read a path that does not exist:\n  "
            + "\n  ".join(sorted(offenders))
        )
