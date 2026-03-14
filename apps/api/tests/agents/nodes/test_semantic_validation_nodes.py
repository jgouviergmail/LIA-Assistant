"""
Unit tests for Semantic Validation Nodes (Phase 2.6 OPTIMPLAN).

Tests cover:
- semantic_validator_node (plan validation)
- clarification_node (HITL interrupt for clarification)
- route_from_semantic_validator (routing logic)

Created: 2025-11-26
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.constants import (
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_SEMANTIC_VALIDATION,
)

# ============================================================================
# semantic_validator_node Tests
# ============================================================================


class TestSemanticValidatorNode:
    """Test suite for semantic_validator_node."""

    @pytest.fixture
    def mock_execution_plan(self):
        """Create mock execution plan."""
        plan = MagicMock()
        plan.plan_id = "test-plan-123"
        plan.steps = [
            MagicMock(step_id="step_1", tool_name="search_contacts_tool"),
            MagicMock(step_id="step_2", tool_name="send_email_tool"),
        ]
        return plan

    @pytest.fixture
    def mock_message(self):
        """Create mock message."""
        msg = MagicMock()
        msg.content = "Envoie un email à tous mes contacts"
        return msg

    @pytest.fixture
    def valid_state(self, mock_execution_plan, mock_message):
        """Create valid state with execution plan."""
        return {
            STATE_KEY_EXECUTION_PLAN: mock_execution_plan,
            "messages": [mock_message],
            "user_language": "fr",
        }

    @pytest.mark.asyncio
    async def test_no_execution_plan(self):
        """Test fallback when no execution plan in state."""
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node

        state = {"messages": [], "user_language": "fr"}

        result = await semantic_validator_node(state, config=None)

        assert STATE_KEY_SEMANTIC_VALIDATION in result
        validation = result[STATE_KEY_SEMANTIC_VALIDATION]
        # Should fallback to valid (fail-open)
        assert validation.is_valid is True
        assert validation.used_fallback is True

    @pytest.mark.asyncio
    async def test_no_messages(self, mock_execution_plan):
        """Test handling when no messages in state."""
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node

        with patch(
            "src.domains.agents.nodes.semantic_validator_node.PlanSemanticValidator"
        ) as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate = AsyncMock(
                return_value=MagicMock(
                    is_valid=True,
                    requires_clarification=False,
                    issues=[],
                    confidence=0.9,
                    validation_duration_seconds=0.5,
                    used_fallback=False,
                )
            )
            mock_validator_class.return_value = mock_validator

            state = {
                STATE_KEY_EXECUTION_PLAN: mock_execution_plan,
                "messages": [],
                "user_language": "en",
            }

            result = await semantic_validator_node(state, config=None)

            assert STATE_KEY_SEMANTIC_VALIDATION in result
            # Should have called validator with empty user_request
            mock_validator.validate.assert_called_once()
            call_args = mock_validator.validate.call_args
            assert call_args[1]["user_request"] == ""

    @pytest.mark.asyncio
    async def test_successful_validation(self, valid_state):
        """Test successful validation flow."""
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticValidationResult,
        )

        with patch(
            "src.domains.agents.nodes.semantic_validator_node.PlanSemanticValidator"
        ) as mock_validator_class:
            mock_result = SemanticValidationResult(
                is_valid=True,
                issues=[],
                confidence=0.95,
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=0.6,
                used_fallback=False,
            )

            mock_validator = MagicMock()
            mock_validator.validate = AsyncMock(return_value=mock_result)
            mock_validator_class.return_value = mock_validator

            result = await semantic_validator_node(valid_state, config=None)

            assert STATE_KEY_SEMANTIC_VALIDATION in result
            validation = result[STATE_KEY_SEMANTIC_VALIDATION]
            assert validation.is_valid is True
            assert validation.confidence == 0.95

    @pytest.mark.asyncio
    async def test_validation_requires_clarification(self, valid_state):
        """Test validation that requires clarification."""
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticIssue,
            SemanticIssueType,
            SemanticValidationResult,
        )

        with patch(
            "src.domains.agents.nodes.semantic_validator_node.PlanSemanticValidator"
        ) as mock_validator_class:
            mock_result = SemanticValidationResult(
                is_valid=False,
                issues=[
                    SemanticIssue(
                        issue_type=SemanticIssueType.CARDINALITY_MISMATCH,
                        description="User said 'pour chaque' but plan does single op",
                    )
                ],
                confidence=0.8,
                requires_clarification=True,
                clarification_questions=["Voulez-vous UN ou TOUS les contacts ?"],
                validation_duration_seconds=0.7,
                used_fallback=False,
            )

            mock_validator = MagicMock()
            mock_validator.validate = AsyncMock(return_value=mock_result)
            mock_validator_class.return_value = mock_validator

            result = await semantic_validator_node(valid_state, config=None)

            validation = result[STATE_KEY_SEMANTIC_VALIDATION]
            assert validation.requires_clarification is True
            assert len(validation.clarification_questions) == 1

    @pytest.mark.asyncio
    async def test_unexpected_error_fallback(self, valid_state):
        """Test fallback on unexpected error."""
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node

        with patch(
            "src.domains.agents.nodes.semantic_validator_node.PlanSemanticValidator"
        ) as mock_validator_class:
            mock_validator = MagicMock()
            mock_validator.validate = AsyncMock(side_effect=RuntimeError("Unexpected error"))
            mock_validator_class.return_value = mock_validator

            result = await semantic_validator_node(valid_state, config=None)

            # Should fallback to valid (fail-open)
            validation = result[STATE_KEY_SEMANTIC_VALIDATION]
            assert validation.is_valid is True
            assert validation.used_fallback is True


# ============================================================================
# clarification_node Tests
# ============================================================================


class TestClarificationNode:
    """Test suite for clarification_node."""

    @pytest.fixture
    def semantic_validation_requires_clarification(self):
        """Create semantic validation that requires clarification."""
        return {
            "requires_clarification": True,
            "clarification_questions": ["Voulez-vous UN ou TOUS les contacts ?"],
            "issues": [
                {
                    "issue_type": {"value": "cardinality_mismatch"},
                    "description": "Cardinality issue",
                    "severity": "high",
                }
            ],
            "is_valid": False,
            "confidence": 0.8,
        }

    @pytest.fixture
    def state_with_clarification(self, semantic_validation_requires_clarification):
        """Create state that requires clarification."""
        return {
            "semantic_validation": semantic_validation_requires_clarification,
            "user_language": "fr",
            STATE_KEY_PLANNER_ITERATION: 0,
        }

    @pytest.mark.asyncio
    async def test_no_semantic_validation_noop(self):
        """Test that node is no-op without semantic_validation in state."""
        from src.domains.agents.nodes.clarification_node import clarification_node

        state = {"user_language": "fr"}

        result = await clarification_node(state, config=None)

        # Should return state unchanged
        assert result == state

    @pytest.mark.asyncio
    async def test_clarification_not_required_noop(self):
        """Test that node is no-op when clarification not required."""
        from src.domains.agents.nodes.clarification_node import clarification_node

        state = {
            "semantic_validation": {
                "requires_clarification": False,
                "is_valid": True,
            },
            "user_language": "fr",
        }

        result = await clarification_node(state, config=None)

        # Should return state unchanged
        assert result == state

    @pytest.mark.asyncio
    async def test_interrupt_triggered(self, state_with_clarification):
        """Test that interrupt is triggered when clarification is required."""
        from src.domains.agents.nodes.clarification_node import clarification_node

        with patch("src.domains.agents.nodes.clarification_node.interrupt") as mock_interrupt:
            # Simulate user response via Command(resume=...)
            mock_interrupt.return_value = {"clarification": "Tous les contacts"}

            # Patch metrics at their actual location
            with patch(
                "src.infrastructure.observability.metrics_agents.semantic_validation_clarification_requests"
            ) as mock_metric:
                mock_metric.inc = MagicMock()

                result = await clarification_node(state_with_clarification, config=None)

                # Verify interrupt was called
                mock_interrupt.assert_called_once()
                interrupt_payload = mock_interrupt.call_args[0][0]

                assert "action_requests" in interrupt_payload
                assert interrupt_payload["generate_question_streaming"] is True
                assert interrupt_payload["user_language"] == "fr"

                # Verify state updates
                assert result["clarification_response"] == "Tous les contacts"
                assert result["needs_replan"] is True
                # NOTE: planner_iteration is no longer returned by clarification_node
                # (BUG FIX 2026-01-14: user clarifications don't increment iteration)

    @pytest.mark.asyncio
    async def test_interrupt_payload_format(self, state_with_clarification):
        """Test interrupt payload format for HITL streaming."""
        from src.domains.agents.nodes.clarification_node import clarification_node

        with patch("src.domains.agents.nodes.clarification_node.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"clarification": "Response"}

            # Patch metrics at their actual location
            with patch(
                "src.infrastructure.observability.metrics_agents.semantic_validation_clarification_requests"
            ):
                await clarification_node(state_with_clarification, config=None)

                interrupt_payload = mock_interrupt.call_args[0][0]
                action_requests = interrupt_payload["action_requests"]

                assert len(action_requests) == 1
                action = action_requests[0]

                assert action["type"] == "clarification"
                assert "clarification_questions" in action
                assert "semantic_issues" in action

    @pytest.mark.asyncio
    async def test_pydantic_model_conversion(self):
        """Test handling of Pydantic model in semantic_validation."""
        from src.domains.agents.nodes.clarification_node import clarification_node

        # Mock Pydantic model with model_dump()
        mock_validation = MagicMock()
        mock_validation.model_dump.return_value = {
            "requires_clarification": True,
            "clarification_questions": ["Question?"],
            "issues": [],
            "is_valid": False,
        }

        state = {
            "semantic_validation": mock_validation,
            "user_language": "en",
            STATE_KEY_PLANNER_ITERATION: 1,
        }

        with patch("src.domains.agents.nodes.clarification_node.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"clarification": "Answer"}

            # Patch metrics at their actual location
            with patch(
                "src.infrastructure.observability.metrics_agents.semantic_validation_clarification_requests"
            ):
                result = await clarification_node(state, config=None)

                # Should have called model_dump()
                mock_validation.model_dump.assert_called_once()

                # planner_iteration is no longer returned by clarification_node
                # (BUG FIX 2026-01-14: user clarifications don't increment iteration)
                assert "planner_iteration" not in result

    @pytest.mark.asyncio
    async def test_string_resume_data(self, state_with_clarification):
        """Test handling of string resume data (instead of dict)."""
        from src.domains.agents.nodes.clarification_node import clarification_node

        with patch("src.domains.agents.nodes.clarification_node.interrupt") as mock_interrupt:
            # Some frontends might send plain string
            mock_interrupt.return_value = "Plain string response"

            # Patch metrics at their actual location
            with patch(
                "src.infrastructure.observability.metrics_agents.semantic_validation_clarification_requests"
            ):
                result = await clarification_node(state_with_clarification, config=None)

                # Should convert to string
                assert result["clarification_response"] == "Plain string response"


# ============================================================================
# route_from_semantic_validator Tests
# ============================================================================


class TestRouteFromSemanticValidator:
    """Test suite for route_from_semantic_validator routing function."""

    @pytest.fixture
    def mock_metrics(self):
        """Patch metrics to prevent errors."""
        with patch(
            "src.domains.agents.nodes.routing.langgraph_conditional_edges_total"
        ) as mock_edges:
            mock_edges.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
            with patch(
                "src.domains.agents.nodes.routing.langgraph_node_transitions_total"
            ) as mock_transitions:
                mock_transitions.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
                yield (mock_edges, mock_transitions)

    def test_route_to_planner_on_needs_replan(self, mock_metrics):
        """Test routing to planner when needs_replan=True."""
        from src.domains.agents.nodes.routing import route_from_semantic_validator

        state = {
            STATE_KEY_SEMANTIC_VALIDATION: {
                "requires_clarification": False,
                "is_valid": True,
            },
            STATE_KEY_PLANNER_ITERATION: 1,
            "needs_replan": True,
        }

        result = route_from_semantic_validator(state)

        assert result == "planner"

    def test_route_to_planner_on_needs_replan_even_at_max_iterations(self, mock_metrics):
        """Test that needs_replan=True takes priority over max iterations.

        BUG FIX 2026-01-14: User's clarification response must always be processed,
        even if max_iterations is reached. Max iterations only prevents auto-replans.
        """
        from src.domains.agents.nodes.routing import route_from_semantic_validator

        state = {
            STATE_KEY_SEMANTIC_VALIDATION: {
                "requires_clarification": True,
            },
            STATE_KEY_PLANNER_ITERATION: 3,  # Max iterations
            "needs_replan": True,
        }

        result = route_from_semantic_validator(state)

        # needs_replan=True has priority: user's response must be processed
        assert result == "planner"

    def test_route_to_approval_on_no_validation(self, mock_metrics):
        """Test routing to approval_gate when no validation result."""
        from src.domains.agents.nodes.routing import route_from_semantic_validator

        state = {
            STATE_KEY_PLANNER_ITERATION: 0,
        }

        result = route_from_semantic_validator(state)

        assert result == "approval_gate"

    def test_route_to_clarification(self, mock_metrics):
        """Test routing to clarification when required."""
        from src.domains.agents.nodes.routing import route_from_semantic_validator

        state = {
            STATE_KEY_SEMANTIC_VALIDATION: {
                "requires_clarification": True,
                "clarification_questions": ["Question?"],
            },
            STATE_KEY_PLANNER_ITERATION: 0,
            "needs_replan": False,
        }

        result = route_from_semantic_validator(state)

        assert result == "clarification"

    def test_route_to_approval_on_valid(self, mock_metrics):
        """Test routing to approval_gate when validation passes."""
        from src.domains.agents.nodes.routing import route_from_semantic_validator

        state = {
            STATE_KEY_SEMANTIC_VALIDATION: {
                "requires_clarification": False,
                "is_valid": True,
            },
            STATE_KEY_PLANNER_ITERATION: 0,
            "needs_replan": False,
        }

        result = route_from_semantic_validator(state)

        assert result == "approval_gate"

    def test_pydantic_model_handling(self, mock_metrics):
        """Test handling of Pydantic model in validation result."""
        from src.domains.agents.nodes.routing import route_from_semantic_validator

        # Mock Pydantic model
        mock_validation = MagicMock()
        mock_validation.model_dump.return_value = {
            "requires_clarification": True,
            "clarification_questions": ["Question?"],
        }

        state = {
            STATE_KEY_SEMANTIC_VALIDATION: mock_validation,
            STATE_KEY_PLANNER_ITERATION: 1,
            "needs_replan": False,
        }

        result = route_from_semantic_validator(state)

        assert result == "clarification"
        mock_validation.model_dump.assert_called_once()

    def test_feedback_loop_protection(self, mock_metrics):
        """Test feedback loop protection (respects planner_max_replans setting).

        BUG FIX 2026-01-14: needs_replan=True (user response) always routes to planner.
        Max iterations only blocks auto-replans (needs_replan=False with requires_clarification).
        """
        from src.domains.agents.nodes.routing import route_from_semantic_validator

        # Patch settings to use max_replans=3 for this test
        with patch("src.core.config.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.planner_max_replans = 3
            mock_get_settings.return_value = mock_settings

            # All iterations with needs_replan=True should route to planner
            # (user's response always takes priority)
            for iteration in range(4):
                state = {
                    STATE_KEY_SEMANTIC_VALIDATION: {"requires_clarification": False},
                    STATE_KEY_PLANNER_ITERATION: iteration,
                    "needs_replan": True,
                }
                result = route_from_semantic_validator(state)
                assert (
                    result == "planner"
                ), f"Iteration {iteration} should route to planner (needs_replan)"

            # Max iterations only blocks when needs_replan=False (auto-replan scenario)
            # With max_replans=3, iteration must be > 3 to trigger bypass
            state = {
                STATE_KEY_SEMANTIC_VALIDATION: {"requires_clarification": True},
                STATE_KEY_PLANNER_ITERATION: 4,
                "needs_replan": False,
            }
            result = route_from_semantic_validator(state)
            assert result == "approval_gate"


# ============================================================================
# Integration Tests
# ============================================================================


class TestSemanticValidationIntegration:
    """Integration tests for the full semantic validation flow."""

    @pytest.mark.asyncio
    async def test_full_validation_flow_valid(self):
        """Test full flow: planner → validator → approval (valid plan)."""
        from src.domains.agents.nodes.routing import route_from_semantic_validator
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticValidationResult,
        )

        # Initial state after planner
        initial_state = {
            STATE_KEY_EXECUTION_PLAN: MagicMock(plan_id="test", steps=[MagicMock(), MagicMock()]),
            "messages": [MagicMock(content="Test request")],
            "user_language": "fr",
            STATE_KEY_PLANNER_ITERATION: 0,
        }

        with patch(
            "src.domains.agents.nodes.semantic_validator_node.PlanSemanticValidator"
        ) as mock_validator_class:
            mock_result = SemanticValidationResult(
                is_valid=True,
                issues=[],
                confidence=0.95,
                requires_clarification=False,
                clarification_questions=[],
                validation_duration_seconds=0.5,
                used_fallback=False,
            )
            mock_validator = MagicMock()
            mock_validator.validate = AsyncMock(return_value=mock_result)
            mock_validator_class.return_value = mock_validator

            # Step 1: Validation
            state_after_validation = await semantic_validator_node(initial_state, config=None)

            # Step 2: Routing (need to patch metrics)
            with patch(
                "src.domains.agents.nodes.routing.langgraph_conditional_edges_total"
            ) as mock_edges:
                mock_edges.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
                with patch(
                    "src.domains.agents.nodes.routing.langgraph_node_transitions_total"
                ) as mock_transitions:
                    mock_transitions.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

                    merged_state = {**initial_state, **state_after_validation}
                    next_node = route_from_semantic_validator(merged_state)

                    assert next_node == "approval_gate"

    @pytest.mark.asyncio
    async def test_full_clarification_flow(self):
        """Test full flow: validator → clarification → planner (replan)."""
        from src.domains.agents.nodes.clarification_node import clarification_node
        from src.domains.agents.nodes.routing import route_from_semantic_validator
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticIssue,
            SemanticIssueType,
            SemanticValidationResult,
        )

        initial_state = {
            STATE_KEY_EXECUTION_PLAN: MagicMock(plan_id="test", steps=[MagicMock(), MagicMock()]),
            "messages": [MagicMock(content="Pour chaque contact, envoie un email")],
            "user_language": "fr",
            STATE_KEY_PLANNER_ITERATION: 0,
        }

        with patch(
            "src.domains.agents.nodes.semantic_validator_node.PlanSemanticValidator"
        ) as mock_validator_class:
            mock_result = SemanticValidationResult(
                is_valid=False,
                issues=[
                    SemanticIssue(
                        issue_type=SemanticIssueType.CARDINALITY_MISMATCH,
                        description="Issue",
                    )
                ],
                confidence=0.8,
                requires_clarification=True,
                clarification_questions=["Voulez-vous UN ou TOUS ?"],
                validation_duration_seconds=0.6,
                used_fallback=False,
            )
            mock_validator = MagicMock()
            mock_validator.validate = AsyncMock(return_value=mock_result)
            mock_validator_class.return_value = mock_validator

            # Step 1: Validation
            state_after_validation = await semantic_validator_node(initial_state, config=None)

            # Step 2: Routing (should go to clarification)
            merged_state = {**initial_state, **state_after_validation}
            next_node = route_from_semantic_validator(merged_state)
            assert next_node == "clarification"

            # Step 3: Clarification node
            with patch("src.domains.agents.nodes.clarification_node.interrupt") as mock_interrupt:
                mock_interrupt.return_value = {"clarification": "TOUS les contacts"}

                # Patch metrics at their actual location
                with patch(
                    "src.infrastructure.observability.metrics_agents.semantic_validation_clarification_requests"
                ):
                    state_after_clarification = await clarification_node(merged_state, config=None)

                    assert state_after_clarification["needs_replan"] is True
                    assert (
                        state_after_clarification["clarification_response"] == "TOUS les contacts"
                    )

                    # Step 4: Routing after clarification (should go to planner)
                    final_state = {**merged_state, **state_after_clarification}
                    next_node = route_from_semantic_validator(final_state)
                    assert next_node == "planner"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
