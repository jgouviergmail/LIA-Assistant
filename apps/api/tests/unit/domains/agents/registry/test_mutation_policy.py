"""Mutation policy is a DECLARATION on the manifest, never a guess (ADR-263).

Measured 2026-09-03 (spec simulation 1): 13 native non-read-only tools ran in
BOTH execution modes with no confirmation gate — and nothing in the catalogue
said whether that was a decision or an omission. The existing guard
(``test_hitl_required_consistency``) only checks the INVERSE invariant: that a
draft-based tool does not ALSO ask for a pre-execution interrupt.

So the manifest now says what confirmation a tool owes:

- a ``search`` tool declares nothing — and it is the ONLY exemption, because
  ``search`` comes from an explicit ``get_``/``search_``/``list_`` name while
  ``readonly`` is the INFERENCE FALLBACK, which is exactly where the dangerous
  tools sit;
- every other native tool declares one of ``MUTATION_POLICIES``, a genuine
  reader saying ``read``;
- ``reversible``/``artefact``/``sandboxed`` — the policies that EXEMPT an
  acting tool from a confirmation — carry a written reason.

Owner rule (2026-09-03): confirm what modifies, deletes or communicates to a
third party; never a read; and no paranoia — neither the lights nor the browser
may rain confirmation cards on the user.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.domains.agents.registry import agent_registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    MUTATION_POLICIES,
    POLICIES_REQUIRING_REASON,
    POLICY_EXEMPT_CATEGORIES,
    CostProfile,
    PermissionProfile,
    ToolManifest,
    assert_mutation_policy_completeness,
)
from src.domains.agents.registry.catalogue_loader import initialize_catalogue

pytestmark = [pytest.mark.unit]


def _manifest(**overrides: object) -> ToolManifest:
    """A minimal non-read-only manifest, overridable field by field."""
    base: dict[str, object] = {
        "name": "control_hue_light_tool",
        "agent": "hue_agent",
        "description": "test",
        "parameters": [],
        "outputs": [],
        "cost": CostProfile(),
        "permissions": PermissionProfile(),
        "tool_category": "update",
    }
    base.update(overrides)
    return ToolManifest(**base)  # type: ignore[arg-type]


class TestTheDeclaration:
    """The two fields and their closed vocabulary."""

    def test_policy_fields_default_to_none(self) -> None:
        manifest = _manifest()
        assert manifest.mutation_policy is None
        assert manifest.mutation_policy_reason is None

    def test_policy_vocabulary_is_closed(self) -> None:
        assert MUTATION_POLICIES == frozenset(
            {"read", "draft", "confirm", "reversible", "artefact", "sandboxed"}
        )

    def test_only_the_exempting_policies_need_a_reason(self) -> None:
        """draft and confirm ASK the user — they owe no written justification."""
        assert POLICIES_REQUIRING_REASON == frozenset({"reversible", "artefact", "sandboxed"})
        assert POLICIES_REQUIRING_REASON < MUTATION_POLICIES

    def test_policy_and_reason_are_carried(self) -> None:
        manifest = _manifest(
            mutation_policy="reversible", mutation_policy_reason="one call undoes it"
        )
        assert manifest.mutation_policy == "reversible"
        assert manifest.mutation_policy_reason == "one call undoes it"


class TestTheExemptionIsMeasuredNotComfortable:
    """Only ``search`` is exempt, and the measurement says why.

    ``infer_tool_category`` assigns ``search`` from an explicit
    ``get_``/``search_``/``list_`` name, but falls back to ``"readonly"`` when
    no convention applies — and that fallback is where the three most dangerous
    tools sit (measured 2026-09-03), declared read-only on purpose to keep the
    semantic validator from rerouting them (ADR-256 §C). Exempting "read-only"
    would have exempted exactly them.
    """

    def test_only_search_is_exempt(self) -> None:
        assert POLICY_EXEMPT_CATEGORIES == frozenset({"search"})

    def test_a_search_tool_declares_nothing(self) -> None:
        assert_mutation_policy_completeness(
            [_manifest(name="get_emails_tool", tool_category="search")]
        )

    def test_a_search_tool_may_not_claim_to_act(self) -> None:
        """Declaring an acting policy on a search tool is a contradiction."""
        with pytest.raises(AssertionError, match="search tool declares an acting policy"):
            assert_mutation_policy_completeness(
                [
                    _manifest(
                        name="get_emails_tool",
                        tool_category="search",
                        mutation_policy="reversible",
                        mutation_policy_reason="x",
                    )
                ]
            )

    def test_a_readonly_category_tool_must_still_declare(self) -> None:
        """The fallback category is not an exemption — it is where the trap was."""
        with pytest.raises(AssertionError, match="declare no mutation_policy: claude_server"):
            assert_mutation_policy_completeness(
                [_manifest(name="claude_server_task_tool", tool_category="readonly")]
            )

    def test_a_system_category_tool_must_still_declare(self) -> None:
        with pytest.raises(AssertionError, match="declare no mutation_policy: set_current_item"):
            assert_mutation_policy_completeness(
                [_manifest(name="set_current_item", tool_category="system")]
            )

    def test_a_genuine_reader_says_read(self) -> None:
        assert_mutation_policy_completeness(
            [
                _manifest(
                    name="get_current_weather_tool",
                    tool_category="readonly",
                    mutation_policy="read",
                ),
                _manifest(name="resolve_reference", tool_category="system", mutation_policy="read"),
            ]
        )

    def test_read_is_refused_where_the_category_acts(self) -> None:
        with pytest.raises(AssertionError, match=r"declares read but its category \(delete\) acts"):
            assert_mutation_policy_completeness(
                [
                    _manifest(
                        name="delete_event_tool", tool_category="delete", mutation_policy="read"
                    )
                ]
            )

    def test_a_readonly_tool_must_still_declare_even_when_it_pauses_react(self) -> None:
        """The fallback category exempts nothing, flag or no flag."""
        with pytest.raises(AssertionError, match="declare no mutation_policy"):
            assert_mutation_policy_completeness(
                [
                    _manifest(
                        name="delegate_to_sub_agent_tool",
                        tool_category="readonly",
                        permissions=PermissionProfile(hitl_required=True),
                    )
                ]
            )


class TestTheGuardRefusesAnOmission:
    """Each rule closes one way a tool could act without saying what it owes."""

    def test_non_read_only_manifest_must_declare_a_policy(self) -> None:
        with pytest.raises(AssertionError, match="declare no mutation_policy: control_hue"):
            assert_mutation_policy_completeness([_manifest()])

    def test_exempting_policy_needs_a_reason(self) -> None:
        with pytest.raises(AssertionError, match="without a reason"):
            assert_mutation_policy_completeness([_manifest(mutation_policy="reversible")])

    def test_a_blank_reason_is_not_a_reason(self) -> None:
        with pytest.raises(AssertionError, match="without a reason"):
            assert_mutation_policy_completeness(
                [_manifest(mutation_policy="artefact", mutation_policy_reason="   ")]
            )

    def test_the_flag_and_the_policy_answer_different_questions(self) -> None:
        """``hitl_required`` is about COST; the policy is about EFFECT (ADR-263).

        ``delegate_to_sub_agent_tool`` pauses ReAct because a research loop is
        expensive, and changes nothing in the world. Deriving one from the
        other classified it as a mutation and would have made it unusable in
        pipeline mode once the gate refused unconfirmed ones.
        """
        assert_mutation_policy_completeness(
            [
                _manifest(
                    name="delegate_to_sub_agent_tool",
                    tool_category="readonly",
                    permissions=PermissionProfile(hitl_required=True),
                    mutation_policy="read",
                )
            ]
        )

    def test_draft_policy_forbids_hitl_required(self) -> None:
        """The draft IS the confirmation — a pre-execution card would ask twice."""
        with pytest.raises(AssertionError, match="draft policy with hitl_required=True"):
            assert_mutation_policy_completeness(
                [
                    _manifest(
                        name="send_email_tool",
                        tool_category="send",
                        permissions=PermissionProfile(hitl_required=True),
                        mutation_policy="draft",
                    )
                ]
            )

    def test_unknown_policy_value_is_refused(self) -> None:
        with pytest.raises(AssertionError, match="unknown mutation_policy"):
            assert_mutation_policy_completeness([_manifest(mutation_policy="maybe")])

    def test_every_problem_is_listed_not_just_the_first(self) -> None:
        """An operator fixing a boot refusal must see the whole list at once."""
        with pytest.raises(AssertionError) as excinfo:
            assert_mutation_policy_completeness(
                [
                    _manifest(name="a_tool"),
                    _manifest(name="b_tool"),
                    _manifest(name="c_tool", mutation_policy="sandboxed"),
                ]
            )
        message = str(excinfo.value)
        assert "a_tool" in message and "b_tool" in message and "c_tool" in message
        assert "3 mutation policy problem(s)" in message

    def test_a_complete_catalogue_passes(self) -> None:
        assert_mutation_policy_completeness(
            [
                _manifest(name="get_emails_tool", tool_category="search"),
                _manifest(
                    name="get_weather_tool", tool_category="readonly", mutation_policy="read"
                ),
                _manifest(
                    mutation_policy="reversible", mutation_policy_reason="one call undoes it"
                ),
                _manifest(name="send_email_tool", tool_category="send", mutation_policy="draft"),
                _manifest(
                    name="delegate_to_sub_agent_tool",
                    permissions=PermissionProfile(hitl_required=True),
                    mutation_policy="confirm",
                ),
            ]
        )

    def test_third_party_mcp_manifest_is_derived_never_asserted(self) -> None:
        """ADR-255 owns what a server declares; the guard covers the NATIVE catalogue."""
        assert_mutation_policy_completeness(
            [_manifest(name="mcp_era_cancel_subscription", tool_category="delete")]
        )


# ============================================================================
# The real catalogue
# ============================================================================


@pytest.fixture
def catalogue() -> Iterator[AgentRegistry]:
    """Install a catalogue-populated global registry, then restore the previous one.

    Same save/restore as ``test_tool_category_completeness``: the registry is a
    process-wide singleton, and loading into it directly makes a suite green
    alone and RED in the full run (a sibling has already registered the same
    manifests, and ``initialize_catalogue`` refuses a duplicate).
    """
    previous = registry_module._global_registry
    registry = AgentRegistry()
    initialize_catalogue(registry)
    registry_module._global_registry = registry
    try:
        yield registry
    finally:
        registry_module._global_registry = previous


# Owner decision 2026-09-03 (spec §7 n°2), pinned so a later edit is a VISIBLE
# decision rather than a drift: confirm what modifies, deletes or communicates
# to a third party; never a read; no paranoia.
OWNER_PINNED_POLICIES: dict[str, str] = {
    # Reversible: the user is not asked, and the reason says why.
    "activate_hue_scene_tool": "reversible",
    "control_hue_light_tool": "reversible",
    "control_hue_room_tool": "reversible",
    "apply_labels_tool": "reversible",
    "remove_labels_tool": "reversible",
    "complete_task_tool": "reversible",
    "toggle_scheduled_action_tool": "reversible",
    "browser_task_tool": "reversible",
    # Local artefacts.
    "generate_image": "artefact",
    "edit_image": "artefact",
    "generate_document": "artefact",
    # Model-authored code, container only.
    "run_python_tool": "sandboxed",
    # Draft-based: the draft IS the confirmation.
    "send_email_tool": "draft",
    "delete_event_tool": "draft",
    "claude_server_task_tool": "draft",
    # The single pre-execution card.
    "delegate_to_sub_agent_tool": "read",
    # Genuine readers sitting on the inference fallback.
    "get_current_weather_tool": "read",
    "resolve_reference": "read",
}


class TestTheRealCatalogue:
    """The guard, run in CI over the catalogue as production loads it."""

    def test_native_catalogue_is_complete(self, catalogue: AgentRegistry) -> None:
        assert_mutation_policy_completeness(catalogue.list_tool_manifests())

    @pytest.mark.parametrize(("tool_name", "policy"), sorted(OWNER_PINNED_POLICIES.items()))
    def test_owner_pinned_policies(
        self, catalogue: AgentRegistry, tool_name: str, policy: str
    ) -> None:
        assert catalogue.get_tool_manifest(tool_name).mutation_policy == policy

    def test_no_native_tool_asks_for_a_pre_execution_card(self, catalogue: AgentRegistry) -> None:
        """No native tool is ``confirm``: the 25 draft tools already ask.

        Only a third-party MCP tool whose owner turned confirmation on reaches
        that policy, and it does so by DERIVATION, never by declaration.
        """
        confirm = sorted(
            m.name for m in catalogue.list_tool_manifests() if m.mutation_policy == "confirm"
        )
        assert confirm == []

    def test_every_exemption_carries_its_reason(self, catalogue: AgentRegistry) -> None:
        """An exemption nobody wrote down is an omission nobody can audit."""
        for manifest in catalogue.list_tool_manifests():
            if manifest.mutation_policy in POLICIES_REQUIRING_REASON:
                reason = (manifest.mutation_policy_reason or "").strip()
                assert reason, manifest.name
                assert reason.endswith("."), f"{manifest.name}: reason must be a sentence"


class TestTheGuardCannotRefuseAProductionBoot:
    """The catalogue is built behind feature flags, so the guard runs on BOTH.

    Measured 2026-09-03: ``place_phone_call_tool`` — a call to a third party —
    was invisible to the first inventory because ``telephony_enabled`` was off
    in the measuring environment. A manifest gated OFF in CI would escape the
    guard here and refuse the boot in production: the very defect this guard
    exists to prevent, pointing the other way.
    """

    FLAGS = (
        "health_metrics_enabled",
        "sub_agents_enabled",
        "image_generation_enabled",
        "document_generation_enabled",
        "devops_enabled",
        "diagnostics_enabled",
        "python_sandbox_tool_enabled",
        "telephony_enabled",
        # ``peers_enabled`` — NOT "peer_connections_enabled", which does not
        # exist: the phantom name silently disabled this branch and four peer
        # manifests escaped the guard entirely (measured 2026-09-04).
        "peers_enabled",
        "skills_enabled",
        "mcp_enabled",
    )

    def test_every_feature_flag_on_is_still_complete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        for flag in self.FLAGS:
            if hasattr(settings, flag):
                monkeypatch.setattr(settings, flag, True, raising=False)

        previous = registry_module._global_registry
        registry = AgentRegistry()
        initialize_catalogue(registry)
        registry_module._global_registry = registry
        try:
            manifests = registry.list_tool_manifests()
            # Guard against a vacuous pass: the flags must have loaded more than
            # the default catalogue, or this test proves nothing.
            assert len(manifests) > 96, f"only {len(manifests)} manifests — flags did not take"
            assert_mutation_policy_completeness(manifests)
            # Anti-vacuity PER FLAG, not just in aggregate: a phantom flag name
            # silently disables its branch, and every manifest behind it escapes
            # (measured — that is exactly how the four peer manifests hid).
            assert registry.get_tool_manifest("place_phone_call_tool").mutation_policy == "draft"
            assert registry.get_tool_manifest("send_peer_message_tool").mutation_policy == "draft"
            assert registry.get_tool_manifest("run_python_tool").mutation_policy == "sandboxed"
        finally:
            registry_module._global_registry = previous


class TestConfirmStandsOnItsOwn:
    """Since the gate exists, ``confirm`` no longer needs the ReAct flag.

    The gate asks in BOTH modes, so a tool may declare ``confirm`` without
    ``hitl_required`` — the flag would only add a second card in ReAct.
    """

    def test_confirm_without_the_flag_is_accepted(self) -> None:
        assert_mutation_policy_completeness(
            [_manifest(name="dangerous_tool", mutation_policy="confirm")]
        )

    def test_confirm_with_the_flag_passes(self) -> None:
        assert_mutation_policy_completeness(
            [
                _manifest(
                    name="delegate_to_sub_agent_tool",
                    permissions=PermissionProfile(hitl_required=True),
                    mutation_policy="confirm",
                )
            ]
        )


class TestTheGuardSurvivesAnUnexpectedShape:
    """It runs at boot over whatever the catalogue holds; it must not raise itself."""

    def test_an_object_without_a_category_is_reported_not_crashed(self) -> None:
        class _Bare:
            name = "bare_tool"

        with pytest.raises(AssertionError, match="declare no mutation_policy: bare_tool"):
            assert_mutation_policy_completeness([_Bare()])
