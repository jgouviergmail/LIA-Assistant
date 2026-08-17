"""Contract tests for the peers catalogue manifests.

Two contracts pinned after the 2026-08-17 prod incident (request 2ecc670c —
a 6,149-char relay refused by the tool but announced as delivered):

1. **The published bound IS the enforced bound.** ``send_peer_message_tool``
   enforces ``settings.peers_message_max_chars`` at runtime; the manifest used
   to hardcode ``2000``. The setting is operator-tunable (100..10000) — after
   a ``.env`` change the planner and the validator would keep trusting a stale
   bound while the tool enforces another (ADR-184: an enforced-but-mislabeled
   bound is a trap, not a contract).

2. **Peer recipient resolution is self-contained.** The tool resolves
   ``recipient_name`` among the caller's ACCEPTED connections — never the
   address book. Without the note the planner prepended a Google
   ``search_contacts`` step and wrapped the send in a FOR_EACH over contacts
   (misleading "mass operation" card). The availability/tasks manifests
   already carry the note; the send manifest was the odd one out.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.peer.catalogue_manifests import (
    send_peer_message_catalogue_manifest,
)


def _constraint_value(parameter_name: str, kind: str) -> object:
    parameter = next(
        p for p in send_peer_message_catalogue_manifest.parameters if p.name == parameter_name
    )
    return next(c.value for c in parameter.constraints if c.kind == kind)


@pytest.mark.unit
class TestSendPeerMessageManifestContract:
    """The manifest must publish what the tool actually enforces."""

    def test_message_max_length_matches_the_enforced_setting(self) -> None:
        assert _constraint_value("message", "max_length") == settings.peers_message_max_chars

    def test_send_manifest_declares_self_contained_resolution(self) -> None:
        description = send_peer_message_catalogue_manifest.description

        assert "SELF-CONTAINED" in description
        assert "never add a contacts lookup" in description
