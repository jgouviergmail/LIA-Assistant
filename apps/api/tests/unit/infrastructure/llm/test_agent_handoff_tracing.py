"""
Tests for Agent Handoff Tracing - Phase 3.1.5.3.

Test coverage:
- trace_agent_handoff() context manager - success/error paths
- enrich_handoff_metadata() - metadata enrichment
- track_conversation_flow() - conversation flow tracking
- Duration tracking
- Metadata capture (source_agent, target_agent, handoff_reason, success)
- Error handling and graceful degradation

Phase: 3.1.5.3 - Multi-Agent Tracing
Date: 2025-11-23
"""

import pytest

from src.infrastructure.llm.agent_handoff_tracing import (
    enrich_handoff_metadata,
    trace_agent_handoff,
    track_conversation_flow,
)

# ============================================================================
# TESTS: trace_agent_handoff - Context Manager
# ============================================================================


class TestTraceAgentHandoff:
    """Tests for trace_agent_handoff context manager."""

    def test_trace_handoff_success(self):
        """Test successful agent handoff tracing."""
        with trace_agent_handoff(
            source_agent="router",
            target_agent="contacts_agent",
            handoff_reason="high_confidence_routing",
        ) as handoff_ctx:
            # Simulate successful agent execution
            handoff_ctx["success"] = True
            handoff_ctx["agent_output"] = {"status": "success"}

        # Verify handoff context
        assert handoff_ctx["source_agent"] == "router"
        assert handoff_ctx["target_agent"] == "contacts_agent"
        assert handoff_ctx["handoff_reason"] == "high_confidence_routing"
        assert handoff_ctx["success"] is True
        assert handoff_ctx["agent_output"] == {"status": "success"}
        assert handoff_ctx.get("error") is None

        # Verify duration tracking
        assert "duration_ms" in handoff_ctx
        assert handoff_ctx["duration_ms"] >= 0

        # Verify timestamps
        assert "start_time" in handoff_ctx
        assert "end_time" in handoff_ctx
        assert handoff_ctx["end_time"] >= handoff_ctx["start_time"]

    def test_trace_handoff_failure(self):
        """Test agent handoff tracing with error."""
        with pytest.raises(ValueError, match="Agent execution failed"):
            with trace_agent_handoff(
                source_agent="router",
                target_agent="contacts_agent",
                handoff_reason="plan_execution",
            ):
                # Simulate agent failure
                raise ValueError("Agent execution failed")

        # Note: handoff_ctx not accessible after exception in pytest context
        # Error capture verified via exception propagation

    def test_trace_handoff_with_parent_trace_id(self):
        """Test handoff tracing with parent trace ID."""
        parent_trace_id = "trace_root_abc123"

        with trace_agent_handoff(
            source_agent="orchestrator",
            target_agent="emails_agent",
            handoff_reason="subgraph_invocation",
            parent_trace_id=parent_trace_id,
        ) as handoff_ctx:
            handoff_ctx["success"] = True

        # Verify parent trace ID captured
        assert handoff_ctx["parent_trace_id"] == parent_trace_id

    def test_trace_handoff_no_source_agent(self):
        """Test handoff tracing with no source agent (root invocation)."""
        with trace_agent_handoff(
            source_agent=None,  # Root graph (no source)
            target_agent="router",
            handoff_reason="initial_routing",
        ) as handoff_ctx:
            handoff_ctx["success"] = True

        # Verify None source agent handled
        assert handoff_ctx["source_agent"] is None
        assert handoff_ctx["target_agent"] == "router"

    def test_trace_handoff_with_custom_metadata(self):
        """Test handoff tracing with additional metadata."""
        custom_metadata = {
            "confidence_score": 0.95,
            "intent": "search_contacts",
        }

        with trace_agent_handoff(
            source_agent="router",
            target_agent="contacts_agent",
            handoff_reason="high_confidence",
            metadata=custom_metadata,
        ) as handoff_ctx:
            handoff_ctx["success"] = True

        # Verify custom metadata preserved
        assert handoff_ctx["confidence_score"] == 0.95
        assert handoff_ctx["intent"] == "search_contacts"

        # Verify standard metadata still there
        assert handoff_ctx["source_agent"] == "router"
        assert handoff_ctx["target_agent"] == "contacts_agent"

    def test_trace_handoff_duration_tracking(self):
        """Test that duration is accurately tracked."""
        import time

        with trace_agent_handoff(
            source_agent="router",
            target_agent="contacts_agent",
            handoff_reason="test",
        ) as handoff_ctx:
            # Simulate slow agent execution
            time.sleep(0.1)
            handoff_ctx["success"] = True

        # Verify duration is at least 100ms
        assert handoff_ctx["duration_ms"] >= 100

    def test_trace_handoff_multiple_handoffs(self):
        """Test multiple sequential handoffs (conversation flow)."""
        handoffs = []

        # Handoff 1: router -> contacts_agent
        with trace_agent_handoff(
            source_agent="router",
            target_agent="contacts_agent",
            handoff_reason="high_confidence",
        ) as ctx1:
            ctx1["success"] = True
            handoffs.append(dict(ctx1))

        # Handoff 2: contacts_agent -> response
        with trace_agent_handoff(
            source_agent="contacts_agent",
            target_agent="response",
            handoff_reason="task_completed",
        ) as ctx2:
            ctx2["success"] = True
            handoffs.append(dict(ctx2))

        # Verify sequence
        assert len(handoffs) == 2
        assert handoffs[0]["source_agent"] == "router"
        assert handoffs[0]["target_agent"] == "contacts_agent"
        assert handoffs[1]["source_agent"] == "contacts_agent"
        assert handoffs[1]["target_agent"] == "response"


# ============================================================================
# TESTS: enrich_handoff_metadata - Metadata Enrichment
# ============================================================================


class TestEnrichHandoffMetadata:
    """Tests for enrich_handoff_metadata function."""

    def test_enrich_handoff_metadata_success(self):
        """Test metadata enrichment for successful handoff."""
        metadata = {
            "langfuse_session_id": "sess_123",
            "langfuse_user_id": "user_456",
        }

        enriched = enrich_handoff_metadata(
            metadata,
            source_agent="router",
            target_agent="contacts_agent",
            handoff_reason="high_confidence",
            success=True,
            duration_ms=245.678,
        )

        # Verify original metadata preserved
        assert enriched["langfuse_session_id"] == "sess_123"
        assert enriched["langfuse_user_id"] == "user_456"

        # Verify handoff metadata added
        assert enriched["langfuse_handoff_source"] == "router"
        assert enriched["langfuse_handoff_target"] == "contacts_agent"
        assert enriched["langfuse_handoff_reason"] == "high_confidence"
        assert enriched["langfuse_handoff_success"] is True
        assert enriched["langfuse_handoff_duration_ms"] == 245.68  # Rounded to 2 decimals
        assert enriched["langfuse_handoff_error"] is None

    def test_enrich_handoff_metadata_failure(self):
        """Test metadata enrichment for failed handoff."""
        metadata = {"langfuse_session_id": "sess_123"}

        enriched = enrich_handoff_metadata(
            metadata,
            source_agent="router",
            target_agent="contacts_agent",
            handoff_reason="plan_execution",
            success=False,
            duration_ms=123.456,
            error="Agent timeout error",
        )

        # Verify handoff metadata
        assert enriched["langfuse_handoff_source"] == "router"
        assert enriched["langfuse_handoff_target"] == "contacts_agent"
        assert enriched["langfuse_handoff_success"] is False
        assert enriched["langfuse_handoff_duration_ms"] == 123.46
        assert enriched["langfuse_handoff_error"] == "Agent timeout error"

    def test_enrich_handoff_metadata_no_source(self):
        """Test metadata enrichment with no source agent (root)."""
        enriched = enrich_handoff_metadata(
            {},
            source_agent=None,
            target_agent="router",
            handoff_reason="initial_routing",
            success=True,
            duration_ms=50.0,
        )

        # Verify None source handled
        assert enriched["langfuse_handoff_source"] is None
        assert enriched["langfuse_handoff_target"] == "router"

    def test_enrich_handoff_metadata_duration_rounding(self):
        """Test that duration_ms is rounded to 2 decimal places."""
        enriched = enrich_handoff_metadata(
            {},
            source_agent="router",
            target_agent="agent",
            handoff_reason="test",
            success=True,
            duration_ms=123.456789,
        )

        # Verify rounding
        assert enriched["langfuse_handoff_duration_ms"] == 123.46


# ============================================================================
# TESTS: track_conversation_flow - Flow Tracking
# ============================================================================


class TestTrackConversationFlow:
    """Tests for track_conversation_flow function."""

    def test_track_conversation_flow_first_agent(self):
        """Test tracking first agent in conversation."""
        state = {}

        flow = track_conversation_flow(state, "router")

        # Verify flow started
        assert len(flow) == 1
        assert flow[0]["agent"] == "router"
        assert "timestamp" in flow[0]
        assert flow[0]["timestamp"] > 0

    def test_track_conversation_flow_multiple_agents(self):
        """Test tracking multiple agent transitions."""
        state = {}

        # Track sequence: router -> contacts_agent -> response
        flow1 = track_conversation_flow(state, "router")
        state["conversation_flow"] = flow1

        flow2 = track_conversation_flow(state, "contacts_agent")
        state["conversation_flow"] = flow2

        flow3 = track_conversation_flow(state, "response")

        # Verify complete flow
        assert len(flow3) == 3
        assert flow3[0]["agent"] == "router"
        assert flow3[1]["agent"] == "contacts_agent"
        assert flow3[2]["agent"] == "response"

        # Verify timestamps are sequential
        assert flow3[0]["timestamp"] <= flow3[1]["timestamp"]
        assert flow3[1]["timestamp"] <= flow3[2]["timestamp"]

    def test_track_conversation_flow_preserves_existing(self):
        """Test that existing flow is preserved when tracking new agent."""
        # Pre-existing flow
        existing_flow = [
            {"agent": "router", "timestamp": 1700000000.0},
            {"agent": "planner", "timestamp": 1700000001.0},
        ]
        state = {"conversation_flow": existing_flow}

        # Track new agent
        flow = track_conversation_flow(state, "contacts_agent")

        # Verify existing flow preserved + new agent added
        assert len(flow) == 3
        assert flow[0]["agent"] == "router"
        assert flow[1]["agent"] == "planner"
        assert flow[2]["agent"] == "contacts_agent"

    def test_track_conversation_flow_complex_sequence(self):
        """Test complex multi-agent conversation flow."""
        state = {}

        # Simulate complex orchestration
        agents_sequence = [
            "router",
            "planner",
            "task_orchestrator",
            "contacts_agent",
            "emails_agent",
            "response",
        ]

        flow = []
        for agent_name in agents_sequence:
            state["conversation_flow"] = flow
            flow = track_conversation_flow(state, agent_name)

        # Verify complete sequence
        assert len(flow) == 6
        assert [step["agent"] for step in flow] == agents_sequence

        # Verify all timestamps present and increasing
        timestamps = [step["timestamp"] for step in flow]
        assert all(t > 0 for t in timestamps)
        assert timestamps == sorted(timestamps)  # Monotonically increasing


# ============================================================================
# TESTS: Integration - Full Workflow
# ============================================================================


class TestAgentHandoffTracingIntegration:
    """Integration tests for complete handoff tracing workflow."""

    def test_complete_handoff_workflow(self):
        """Test complete workflow: handoff trace + metadata enrichment + flow tracking."""
        # Step 1: Initialize state
        state = {}

        # Step 2: Trace first handoff (router -> contacts_agent)
        with trace_agent_handoff(
            source_agent=None,  # Root
            target_agent="router",
            handoff_reason="initial_routing",
            parent_trace_id="trace_root_xyz",
        ) as ctx1:
            # Track flow
            flow = track_conversation_flow(state, "router")
            state["conversation_flow"] = flow

            ctx1["success"] = True
            ctx1["agent_output"] = {"next_agent": "contacts_agent"}

        # Step 3: Enrich metadata with first handoff
        base_metadata = {
            "langfuse_session_id": "sess_123",
            "langfuse_user_id": "user_456",
        }

        enriched_metadata1 = enrich_handoff_metadata(
            base_metadata,
            source_agent=ctx1["source_agent"],
            target_agent=ctx1["target_agent"],
            handoff_reason=ctx1["handoff_reason"],
            success=ctx1["success"],
            duration_ms=ctx1["duration_ms"],
        )

        # Step 4: Trace second handoff (router -> contacts_agent)
        with trace_agent_handoff(
            source_agent="router",
            target_agent="contacts_agent",
            handoff_reason="high_confidence_routing",
            parent_trace_id="trace_root_xyz",
        ) as ctx2:
            # Track flow
            flow = track_conversation_flow(state, "contacts_agent")
            state["conversation_flow"] = flow

            ctx2["success"] = True
            ctx2["agent_output"] = {"contacts": [...]}

        # Step 5: Enrich metadata with second handoff
        enriched_metadata2 = enrich_handoff_metadata(
            enriched_metadata1,  # Build on previous metadata
            source_agent=ctx2["source_agent"],
            target_agent=ctx2["target_agent"],
            handoff_reason=ctx2["handoff_reason"],
            success=ctx2["success"],
            duration_ms=ctx2["duration_ms"],
        )

        # Verify complete workflow
        # 1. Both handoffs captured
        assert enriched_metadata1["langfuse_handoff_target"] == "router"
        assert enriched_metadata2["langfuse_handoff_target"] == "contacts_agent"

        # 2. Conversation flow tracked
        assert len(state["conversation_flow"]) == 2
        assert state["conversation_flow"][0]["agent"] == "router"
        assert state["conversation_flow"][1]["agent"] == "contacts_agent"

        # 3. Original metadata preserved
        assert enriched_metadata2["langfuse_session_id"] == "sess_123"
        assert enriched_metadata2["langfuse_user_id"] == "user_456"

    def test_error_handoff_workflow(self):
        """Test error workflow: handoff failure + enrichment."""
        state = {}

        try:
            with trace_agent_handoff(
                source_agent="router",
                target_agent="failing_agent",
                handoff_reason="plan_execution",
            ):
                # Track flow (even though will fail)
                flow = track_conversation_flow(state, "failing_agent")
                state["conversation_flow"] = flow

                # Simulate agent failure
                raise RuntimeError("Agent execution timeout")
        except RuntimeError:
            pass  # Expected exception

        # Verify flow tracked even on error
        assert len(state["conversation_flow"]) == 1
        assert state["conversation_flow"][0]["agent"] == "failing_agent"

        # Simulate capturing error metadata
        error_metadata = enrich_handoff_metadata(
            {},
            source_agent="router",
            target_agent="failing_agent",
            handoff_reason="plan_execution",
            success=False,
            duration_ms=50.0,
            error="Agent execution timeout",
        )

        assert error_metadata["langfuse_handoff_success"] is False
        assert error_metadata["langfuse_handoff_error"] == "Agent execution timeout"
