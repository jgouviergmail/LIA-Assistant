"""What the draft tools publish is what they enforce, to BOTH readers (ADR-344).

The planner reads the manifest; the ReAct loop binds the tool's schema and never
sees the manifest (ADR-310). A bound only one of them states is hidden from the
other (ADR-184), so each count parameter reads ONE wording, which states the
bound the tool clamps to.
"""

from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.core.config import settings
from src.domains.agents.emails import mailbox_drafts_manifests as manifests
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.tools.mailbox_draft_edit_tools import delete_mailbox_drafts_tool
from src.domains.agents.tools.mailbox_drafts_tools import list_mailbox_drafts_tool

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("tool", "manifest", "wording", "bound"),
    [
        (
            list_mailbox_drafts_tool,
            manifests.list_mailbox_drafts_catalogue_manifest,
            manifests.LIST_MAX_RESULTS_DESCRIPTION,
            "emails_tool_default_max_results",
        ),
        (
            delete_mailbox_drafts_tool,
            manifests.delete_mailbox_drafts_catalogue_manifest,
            manifests.DELETE_MAX_RESULTS_DESCRIPTION,
            "email_drafts_bulk_max",
        ),
    ],
    ids=["list", "delete"],
)
def test_both_readers_bind_one_wording_stating_the_enforced_bound(
    tool: BaseTool, manifest: ToolManifest, wording: str, bound: str
) -> None:
    bound_schema = tool.args_schema
    assert isinstance(bound_schema, type) and issubclass(bound_schema, BaseModel)
    schema = bound_schema.model_fields["max_results"].description
    published = next(p for p in manifest.parameters if p.name == "max_results")
    maximum = next(c.value for c in published.constraints if c.kind == "maximum")

    assert schema is not None and schema.startswith(wording)
    assert published.description == wording
    assert maximum == getattr(settings, bound)
    assert str(maximum) in wording


class TestTheHandlesHaveTheirSources:
    """The catalogue closure (ADR-335) reads these manifests' semantic types."""

    @staticmethod
    def _email_family() -> list[ToolManifest]:
        from src.domains.agents.emails.catalogue_manifests import (
            forward_email_catalogue_manifest,
            reply_email_catalogue_manifest,
            send_email_catalogue_manifest,
        )
        from src.domains.agents.emails.get_emails_manifest import get_emails_catalogue_manifest

        return [
            get_emails_catalogue_manifest,
            send_email_catalogue_manifest,
            reply_email_catalogue_manifest,
            forward_email_catalogue_manifest,
            *manifests.MAILBOX_DRAFT_TOOL_MANIFESTS,
        ]

    def _added_for(self, consumer: ToolManifest) -> list[str]:
        from src.domains.agents.services.catalogue.closure import resolve_closure_additions

        return resolve_closure_additions([consumer], self._email_family()).additions

    def test_a_draft_to_edit_comes_from_the_listing_never_from_a_write(self) -> None:
        added = self._added_for(manifests.update_mailbox_draft_catalogue_manifest)

        assert added == ["list_mailbox_drafts_tool"]

    def test_a_deletion_selects_its_own_drafts(self) -> None:
        """Its handles are optional: a search, a count or « all » names them."""
        assert self._added_for(manifests.delete_mailbox_drafts_catalogue_manifest) == []

    @pytest.mark.parametrize(
        "consumer",
        [
            manifests.create_mailbox_reply_draft_catalogue_manifest,
            manifests.create_mailbox_forward_draft_catalogue_manifest,
        ],
        ids=["reply", "forward"],
    )
    def test_the_message_answered_comes_from_the_mailbox_never_from_a_draft(
        self, consumer: ToolManifest
    ) -> None:
        added = self._added_for(consumer)

        assert "get_emails_tool" in added
        assert "list_mailbox_drafts_tool" not in added


@pytest.mark.parametrize("manifest", manifests.MAILBOX_DRAFT_TOOL_MANIFESTS, ids=lambda m: m.name)
def test_no_draft_is_ever_offered_as_a_message_to_answer(manifest: ToolManifest) -> None:
    """A draft's message id answered by reply_email_tool would reply to one's own draft."""
    from src.domains.agents.services.catalogue.source_paths import produced_types

    assert "message_id" not in produced_types(manifest)
