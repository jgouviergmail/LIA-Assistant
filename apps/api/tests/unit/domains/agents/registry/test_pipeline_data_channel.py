"""A read tool's data reaches the pipeline's response model, or says why not (ADR-347).

The pipeline response read a step's ``message`` and its registry items, and
nothing else: a read tool whose facts lived in ``structured_data`` handed the
response model a sentence about them (« 3 accepted connection(s). ») and kept
the facts. Since ADR-347 that data is projected into the step's data block by
default. Three tools carry their data another way and DECLARE it on the
manifest, with a reason the boot checks:

- the peer availability renders the busy slots in the ASKING user's timezone,
  where its ``structured_data`` keeps the peer's own frame — both side by side
  would give the model two clocks;
- the peer tasks render the same titles, framed as a peer's shared data;
- the sub-agent delegation's analysis is wrapped by the response formatter
  itself (``<SubAgentAnalysis>``).
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from src.domains.agents.registry import agent_registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    DEFAULT_PIPELINE_DATA_CHANNEL,
    PIPELINE_DATA_CHANNELS,
    CostProfile,
    MutationPolicy,
    PermissionProfile,
    PipelineDataChannel,
    ToolManifest,
    assert_pipeline_data_channel_completeness,
)
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from tests.unit.domains.agents.registry.catalogue_flags import enable_every_catalogue_flag

pytestmark = [pytest.mark.unit]


def _manifest(
    *,
    name: str = "get_probe_tool",
    mutation_policy: MutationPolicy | None = "read",
    mutation_policy_reason: str | None = None,
    pipeline_data_channel: PipelineDataChannel = "data_block",
    pipeline_data_channel_reason: str | None = None,
) -> ToolManifest:
    """A minimal read manifest; only the fields this rule reads vary."""
    return ToolManifest(
        name=name,
        agent="probe_agent",
        description="test",
        parameters=[],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mutation_policy=mutation_policy,
        mutation_policy_reason=mutation_policy_reason,
        pipeline_data_channel=pipeline_data_channel,
        pipeline_data_channel_reason=pipeline_data_channel_reason,
    )


def _problems(manifest: object) -> str:
    with pytest.raises(AssertionError) as refused:
        assert_pipeline_data_channel_completeness([manifest])
    return str(refused.value)


class TestTheDeclaration:
    def test_a_read_tool_projects_its_data_unless_it_says_otherwise(self) -> None:
        manifest = _manifest()

        assert manifest.pipeline_data_channel == DEFAULT_PIPELINE_DATA_CHANNEL == "data_block"
        assert manifest.pipeline_data_channel_reason is None
        assert_pipeline_data_channel_completeness([manifest])

    def test_the_vocabulary_is_closed(self) -> None:
        assert PIPELINE_DATA_CHANNELS == frozenset({"data_block", "message", "sub_agent_analysis"})

    @pytest.mark.parametrize("channel", ["message", "sub_agent_analysis"])
    def test_a_declared_channel_with_its_reason_passes(self, channel: PipelineDataChannel) -> None:
        manifest = _manifest(
            pipeline_data_channel=channel, pipeline_data_channel_reason="Rendered in the message."
        )

        assert_pipeline_data_channel_completeness([manifest])


class TestTheBootRefuses:
    @pytest.mark.parametrize("reason", [None, "", "   "])
    def test_a_channel_declared_without_a_reason(self, reason: str | None) -> None:
        manifest = _manifest(pipeline_data_channel="message", pipeline_data_channel_reason=reason)

        assert "without a reason" in _problems(manifest)

    def test_a_reason_with_nothing_to_justify(self) -> None:
        manifest = _manifest(pipeline_data_channel_reason="Kept out of the block.")

        assert "nothing to justify" in _problems(manifest)

    def test_an_acting_tool_declaring_a_channel(self) -> None:
        manifest = _manifest(
            mutation_policy="reversible",
            mutation_policy_reason="Undone by one more call.",
            pipeline_data_channel="message",
            pipeline_data_channel_reason="Rendered in the message.",
        )

        assert "acting tool" in _problems(manifest)

    def test_an_unknown_channel_is_reported_not_crashed(self) -> None:
        """The boot reads whatever the catalogue holds; a dataclass validates nothing."""
        manifest = SimpleNamespace(
            name="odd_tool",
            mutation_policy="read",
            pipeline_data_channel="side_door",
            pipeline_data_channel_reason="Kept out.",
        )

        assert "unknown pipeline_data_channel" in _problems(manifest)

    def test_every_offender_is_listed_not_just_the_first(self) -> None:
        offenders = [
            _manifest(name="a_tool", pipeline_data_channel="message"),
            _manifest(name="b_tool", pipeline_data_channel_reason="Kept out."),
        ]

        with pytest.raises(AssertionError) as refused:
            assert_pipeline_data_channel_completeness(offenders)

        assert "a_tool" in str(refused.value)
        assert "b_tool" in str(refused.value)


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Iterator[AgentRegistry]:
    """The WHOLE catalogue as a global registry, the previous one restored after.

    Every flag a manifest loads behind is on: the peer tools load only with
    ``peers_enabled``, and a guard run over the default catalogue would never
    see them.
    """
    enable_every_catalogue_flag(monkeypatch)
    previous = registry_module._global_registry
    registry = AgentRegistry()
    initialize_catalogue(registry)
    registry_module._global_registry = registry
    try:
        yield registry
    finally:
        registry_module._global_registry = previous


#: The tools whose data reaches the response another way, pinned so that
#: removing a declaration is a visible decision: without it the peer's raw
#: slots, in the PEER's timezone, would sit beside the message's slots in the
#: asking user's, and a sub-agent's analysis would be handed over twice.
DECLARED_CHANNELS: dict[str, str] = {
    "get_peer_availability_tool": "message",
    "get_peer_tasks_tool": "message",
    "delegate_to_sub_agent_tool": "sub_agent_analysis",
}


class TestTheRealCatalogue:
    def test_the_native_catalogue_is_complete(self, catalogue: AgentRegistry) -> None:
        assert_pipeline_data_channel_completeness(catalogue.list_tool_manifests())

    @pytest.mark.parametrize(("tool_name", "channel"), sorted(DECLARED_CHANNELS.items()))
    def test_the_declared_channels(
        self, catalogue: AgentRegistry, tool_name: str, channel: str
    ) -> None:
        assert catalogue.get_tool_manifest(tool_name).pipeline_data_channel == channel

    def test_no_other_tool_keeps_its_data_out_of_the_block(self, catalogue: AgentRegistry) -> None:
        """Adding a declaration is as visible a decision as removing one."""
        declared = {
            manifest.name: manifest.pipeline_data_channel
            for manifest in catalogue.list_tool_manifests()
            if manifest.pipeline_data_channel != DEFAULT_PIPELINE_DATA_CHANNEL
        }

        assert declared == DECLARED_CHANNELS
