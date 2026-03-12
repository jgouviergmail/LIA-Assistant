# Agent Tests Documentation

**Project:** LIA API - Agent Domain
**Component:** Agent Test Suite
**Version:** 1.0.0
**Date:** 2025-11-22
**Status:** Production-Ready Documentation

---

## Table of Contents

1. [Overview](#1-overview)
2. [Agent Testing Philosophy](#2-agent-testing-philosophy)
3. [Test Directory Structure](#3-test-directory-structure)
4. [LangGraph Testing Patterns](#4-langgraph-testing-patterns)
5. [HITL Testing Strategies](#5-hitl-testing-strategies)
6. [Orchestration Testing](#6-orchestration-testing)
7. [Tool Testing](#7-tool-testing)
8. [Message Windowing Testing](#8-message-windowing-testing)
9. [Context Management Testing](#9-context-management-testing)
10. [Plan Execution Testing](#10-plan-execution-testing)
11. [Mocking Strategies](#11-mocking-strategies)
12. [Performance Testing](#12-performance-testing)
13. [Best Practices](#13-best-practices)
14. [Common Patterns](#14-common-patterns)
15. [Troubleshooting](#15-troubleshooting)
16. [References](#16-references)

---

## 1. Overview

### 1.1 Agent Test Suite Scope

The agent test suite covers **31% of the entire test codebase** (51 files) and focuses on testing the LangGraph-based multi-agent orchestration system, including:

- **HITL (Human-in-the-Loop) workflows** - User approval, rejection, and editing
- **LangGraph state management** - MessagesState, agent results, routing history
- **Agent orchestration** - Sequential and parallel execution
- **Tool invocation** - Gmail, Contacts, generic tools
- **Message windowing** - Token optimization via conversation truncation
- **Context management** - Cross-agent context sharing
- **Plan validation** - Step dependencies and execution order

### 1.2 Test Statistics

```
Agent Test Metrics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Agent Test Files:          51 files
Total Lines of Agent Tests:      ~23,000 lines
Largest Test File:               test_hitl_classifier.py (1,123 lines)
                                 services/test_hitl_classifier.py (390 lines)
Average Lines per Test:          ~450 lines
Coverage Target:                 80%+ (agent domain)
Test-to-Code Ratio:              1.5:1 (Good)
```

### 1.3 Test Distribution

```
Agent Test Distribution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HITL Tests:                      ~15 files (29%)
Orchestration Tests:             ~12 files (24%)
Tool Tests:                      ~8 files (16%)
Context Tests:                   ~6 files (12%)
Message/Windowing Tests:         ~5 files (10%)
Registry/Catalogue Tests:        ~3 files (6%)
Other (E2E, Performance):        ~2 files (3%)
```

---

## 2. Agent Testing Philosophy

### 2.1 LangGraph-Specific Testing

**LangGraph Architecture:**
```python
# State-based workflow with typed dictionary
MessagesState = TypedDict("MessagesState", {
    "messages": list[BaseMessage],
    "metadata": dict,
    "routing_history": list[RouterOutput],
    "agent_results": dict[str, AgentResult],
    "orchestration_plan": OrchestratorPlan | None,
    "context": dict[str, list[dict]],
})
```

**Testing Principles:**
1. **State Immutability** - Test that state updates don't mutate previous state
2. **Graph Structure** - Verify node connections and conditional edges
3. **Checkpointing** - Test state persistence and resumption
4. **Interrupts** - Validate HITL interrupts and resumption
5. **Streaming** - Test token-by-token streaming responses

### 2.2 HITL Testing Philosophy

**HITL Workflow:**
```
1. Agent proposes action → 2. Graph interrupts → 3. User responds → 4. Classifier decides → 5. Execute/Reject/Edit
```

**Testing Focus:**
- **Classification Accuracy** - APPROVE/REJECT/EDIT/AMBIGUOUS decisions
- **Action Type Extraction** - search/send/delete/create/list/get
- **Confidence Thresholds** - Low confidence → demotion to AMBIGUOUS
- **EDIT Demotion** - Missing params → AMBIGUOUS with clarification
- **Contextual Examples** - Different action types get different examples
- **Metrics Tracking** - Token count, latency, classification distribution

### 2.3 Test Pyramid for Agents

```
         ┌─────────────┐
         │   E2E (5%)  │  integration/test_hitl_streaming_e2e.py
         │  Full flows │  test_phase32_e2e_integration.py
         └─────────────┘
        ┌───────────────┐
        │ Integration   │  test_orchestration.py
        │   (25%)       │  orchestration/test_dependency_graph.py
        │ Multi-node    │  test_graph_build.py
        └───────────────┘
      ┌─────────────────────┐
      │   Unit (70%)        │  test_hitl_classifier.py (390 lines)
      │ Single functions    │  test_message_windowing.py
      │ Mocked LLMs         │  test_condition_evaluator.py
      └─────────────────────┘
```

---

## 3. Test Directory Structure

### 3.1 Complete Agent Tests Tree

```
tests/agents/
│
├── __init__.py
│
├── services/                                    # HITL & Core Services (6 files)
│   ├── __init__.py
│   ├── test_hitl_classifier.py                 # 390 lines - HITL classification
│   ├── test_hitl_classifier_multi_provider.py  # Multi-LLM provider support
│   ├── test_hitl_question_streaming.py         # Streaming clarification questions
│   ├── test_question_generator.py              # Generate clarification questions
│   ├── test_resumption_strategies.py           # Resume after HITL interrupts
│   └── test_schema_validator.py                # Pydantic schema validation
│
├── integration/                                 # E2E Integration Tests (1 file)
│   └── test_hitl_streaming_e2e.py              # Full HITL streaming workflow
│
├── mixins/                                      # Mixin Tests (1 file)
│   ├── __init__.py
│   └── test_streaming_mixin.py                 # Streaming response mixin
│
├── tools/                                       # Tool Tests (2 files)
│   ├── __init__.py
│   ├── test_google_contacts_tools.py           # Google Contacts integration
│   └── test_rate_limiting.py                   # Tool-level rate limiting
│
├── test_agent_registry.py                      # Agent registration & discovery
├── test_agent_result_schemas.py                # AgentResult Pydantic schemas
├── test_catalogue_manifests.py                 # Tool & agent manifests
├── test_composite_key_format_consistency.py    # Context key format validation
├── test_conditional_step_evaluation.py         # Conditional plan steps
├── test_condition_evaluator.py                 # Condition logic evaluation
├── test_context_cleanup_on_reset.py            # Context lifecycle management
├── test_context_manager_expanded.py            # Context CRUD operations
├── test_execution_result_mapping.py            # Map tool results to state
├── test_get_contact_details_save_mode.py       # Contact save flow
├── test_get_context_list_tool.py               # Context listing tool
├── test_graph_build.py                         # LangGraph construction
├── test_hitl_cache_integration.py              # HITL decision caching
├── test_hitl_classifier.py                     # 1,123 lines - Main HITL classifier
├── test_phase32_e2e_integration.py             # Phase 3.2 E2E integration tests
├── test_hitl_middleware.py                     # HITL middleware layer
├── test_hitl_store.py                          # HITL state persistence
├── test_manifest_builder.py                    # Tool manifest generation
├── test_mappers.py                             # Data transformation
├── test_message_filters.py                     # Message filtering logic
├── test_message_windowing.py                   # Conversation windowing
├── test_multi_keys_store_pattern.py            # Multi-key context storage
├── test_nodes_windowing_integration.py         # Node-level windowing
├── test_node_utils.py                          # Node utility functions
├── test_no_legacy_registry_imports.py          # Import validation
├── test_orchestration.py                       # Orchestration logic
├── test_phase32_e2e_integration.py             # Phase 3.2 E2E tests
├── test_dependency_graph.py                    # Plan dependency graph (in orchestration/)
├── test_enhanced_plan_editor.py                # Plan editor (in orchestration/)
├── test_plan_validator.py                      # Plan validation rules
├── test_pydantic_normalization.py              # Schema normalization
├── test_agent_registry.py                      # Agent registration & discovery
├── test_response_node.py                       # Response node logic
├── test_response_node_formatting.py            # Response formatting
├── test_resumption_strategies.py               # Resumption after interrupts
├── test_runtime_helpers.py                     # Runtime utility functions
├── test_save_details_current_management.py     # Detail persistence
├── test_state_performance.py                   # State performance benchmarks
├── test_tool_dependencies_concurrency.py       # Concurrent tool execution
├── test_tool_schemas.py                        # Tool schema validation
└── test_structured_output_helper.py            # LLM structured output parsing
```

### 3.2 File Categories

| Category | Files | Focus |
|----------|-------|-------|
| **HITL Services** | 6 | Classification, streaming, questions |
| **Orchestration** | 5 | Plan creation, validation, execution |
| **Tools** | 4 | Tool registration, invocation, schemas |
| **Context** | 6 | Context CRUD, cleanup, multi-key patterns |
| **Message Handling** | 5 | Windowing, filtering, formatting |
| **Registry** | 3 | Agent/tool registration, manifests |
| **Integration** | 3 | E2E workflows, Python 3.12 compatibility |
| **Performance** | 2 | State performance, concurrency |
| **Other** | 17 | Utilities, mappers, validators |

---

## 4. LangGraph Testing Patterns

### 4.1 State Testing

#### Testing State Updates

```python
from src.domains.agents.models import MessagesState
from langchain_core.messages import HumanMessage, AIMessage

def test_state_update_immutability():
    """Test that state updates don't mutate original state."""
    # ARRANGE
    initial_state: MessagesState = {
        "messages": [HumanMessage(content="Hello")],
        "metadata": {"user_id": "test-user"},
        "routing_history": [],
        "agent_results": {},
        "orchestration_plan": None,
    }

    # ACT
    updated_state = {
        **initial_state,
        "messages": [*initial_state["messages"], AIMessage(content="Hi!")],
    }

    # ASSERT
    assert len(initial_state["messages"]) == 1  # Original unchanged
    assert len(updated_state["messages"]) == 2  # Updated has new message
```

#### Testing Agent Results Accumulation

```python
def test_agent_results_accumulation():
    """Test that agent results accumulate correctly in state."""
    # ARRANGE
    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [],
        "agent_results": {},
        "orchestration_plan": None,
    }

    # ACT - First agent
    state["agent_results"]["contacts_agent"] = AgentResult(
        agent_name="contacts_agent",
        status="success",
        data=[{"name": "John Doe"}],
    )

    # ACT - Second agent
    state["agent_results"]["emails_agent"] = AgentResult(
        agent_name="emails_agent",
        status="success",
        data=[{"subject": "Test"}],
    )

    # ASSERT
    assert len(state["agent_results"]) == 2
    assert "contacts_agent" in state["agent_results"]
    assert "emails_agent" in state["agent_results"]
```

### 4.2 Graph Structure Testing

#### Testing Node Registration

```python
from src.domains.agents.graph import build_agent_graph

def test_graph_nodes_registered():
    """Test that all expected nodes are registered in graph."""
    # ACT
    graph = build_agent_graph()

    # ASSERT
    expected_nodes = [
        "router",
        "task_orchestrator",
        "contacts_agent",
        "emails_agent",
        "response",
    ]

    for node in expected_nodes:
        assert node in graph.nodes
```

#### Testing Conditional Edges

```python
def test_router_conditional_edge():
    """Test router decides next node based on intention."""
    # ARRANGE
    state: MessagesState = {
        "messages": [HumanMessage(content="Search my contacts")],
        "routing_history": [
            RouterOutput(
                intention="contacts_search",
                next_node="task_orchestrator",
                confidence=0.9,
            )
        ],
        # ... other state fields
    }

    # ACT
    next_node = decide_next_node(state)

    # ASSERT
    assert next_node == "task_orchestrator"
```

### 4.3 Checkpointing Testing

#### Testing State Persistence

```python
@pytest.mark.asyncio
async def test_checkpoint_saves_state():
    """Test that checkpointer persists state correctly."""
    # ARRANGE
    checkpointer = MemorySaver()
    graph = build_agent_graph(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "test-thread"}}
    initial_state = {"messages": [HumanMessage(content="Hello")]}

    # ACT
    await graph.ainvoke(initial_state, config)

    # Retrieve checkpoint
    checkpoint = await checkpointer.aget(config)

    # ASSERT
    assert checkpoint is not None
    assert len(checkpoint["messages"]) == 2  # User + AI message
```

### 4.4 Interrupt Testing (HITL)

#### Testing Graph Interrupts

```python
@pytest.mark.asyncio
async def test_hitl_interrupt_before_tool_execution():
    """Test that graph interrupts before tool execution for HITL."""
    # ARRANGE
    graph = build_agent_graph(interrupt_before=["contacts_agent"])
    config = {"configurable": {"thread_id": "test-thread"}}

    # ACT
    events = []
    async for event in graph.astream(
        {"messages": [HumanMessage(content="Search contacts")]},
        config,
    ):
        events.append(event)

    # ASSERT
    # Should stop at interrupt, not execute tool
    assert events[-1]["node"] == "__interrupt__"
    assert "contacts_agent" in events[-1]["interrupts"]
```

#### Testing Resume After HITL

```python
@pytest.mark.asyncio
async def test_resume_after_hitl_approval():
    """Test graph resumes execution after HITL approval."""
    # ARRANGE
    graph = build_agent_graph(interrupt_before=["contacts_agent"])
    config = {"configurable": {"thread_id": "test-thread"}}

    # Step 1: Run until interrupt
    async for event in graph.astream(
        {"messages": [HumanMessage(content="Search contacts")]},
        config,
    ):
        pass

    # Step 2: User approves
    approval_update = {"hitl_decision": "APPROVE"}

    # ACT - Resume execution
    events = []
    async for event in graph.astream(approval_update, config):
        events.append(event)

    # ASSERT
    # Should complete execution after approval
    assert events[-1]["node"] == "response"
```

---

## 5. HITL Testing Strategies

### 5.1 Classification Testing

**File:** `services/test_hitl_classifier.py` (390 lines)

#### Testing APPROVE Classification

```python
@pytest.mark.asyncio
async def test_classify_approve_oui(classifier, sample_action_context):
    """Test classification of 'oui' as APPROVE."""
    # ACT
    result = await classifier.classify(
        user_response="oui",
        action_context=sample_action_context
    )

    # ASSERT
    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8  # High confidence for clear approval
    assert result.reasoning is not None
    assert result.edited_params is None
    assert result.clarification_question is None
```

#### Testing REJECT Classification

```python
@pytest.mark.asyncio
async def test_classify_reject_non(classifier, sample_action_context):
    """Test classification of 'non' as REJECT."""
    # ACT
    result = await classifier.classify(
        user_response="non",
        action_context=sample_action_context
    )

    # ASSERT
    assert result.decision == "REJECT"
    assert result.confidence >= 0.8
    assert result.reasoning is not None
    assert result.edited_params is None
```

#### Testing EDIT Classification

```python
@pytest.mark.asyncio
async def test_classify_edit_with_params(classifier):
    """Test EDIT classification with parameter corrections."""
    # ARRANGE
    action_context = [
        {
            "tool_name": "search_contacts_tool",
            "tool_args": {"query": "jean"},
            "tool_description": "Recherche contacts par nom",
        }
    ]

    # ACT
    result = await classifier.classify(
        user_response="non, cherche paul à la place",
        action_context=action_context
    )

    # ASSERT
    assert result.decision == "EDIT"
    assert result.edited_params is not None
    assert "query" in result.edited_params
    assert result.edited_params["query"] == "paul"
```

#### Testing AMBIGUOUS Classification

```python
@pytest.mark.asyncio
async def test_classify_ambiguous_unclear_response(classifier, sample_action_context):
    """Test AMBIGUOUS classification for unclear responses."""
    # ACT
    result = await classifier.classify(
        user_response="peut-être",  # Ambiguous
        action_context=sample_action_context
    )

    # ASSERT
    assert result.decision == "AMBIGUOUS"
    assert result.clarification_question is not None
    assert result.edited_params is None
```

### 5.2 Action Type Testing

**File:** `test_hitl_classifier.py` (1,123 lines)

#### Testing Action Type Extraction

```python
@pytest.mark.asyncio
async def test_extract_action_type_search():
    """Test extraction of SEARCH action type."""
    # ARRANGE
    action_context = [
        {
            "tool_name": "search_contacts_tool",
            "tool_args": {"query": "John"},
            "tool_description": "Recherche contacts",
        }
    ]

    # ACT
    action_type = extract_action_type(action_context)

    # ASSERT
    assert action_type == ACTION_TYPE_SEARCH
```

#### Testing Action Type Examples

```python
def test_get_contextual_examples_for_search():
    """Test that SEARCH action type gets search-specific examples."""
    # ARRANGE
    action_type = ACTION_TYPE_SEARCH

    # ACT
    examples = get_contextual_examples(action_type)

    # ASSERT
    assert len(examples) > 0
    assert any("search" in ex.lower() for ex in examples)
    assert any("APPROVE" in ex for ex in examples)
```

### 5.3 Confidence Threshold Testing

#### Testing Low Confidence Demotion

```python
@pytest.mark.asyncio
async def test_edit_demoted_to_ambiguous_low_confidence():
    """Test EDIT with low confidence is demoted to AMBIGUOUS."""
    # ARRANGE
    mock_llm_response = ClassificationResult(
        decision="EDIT",
        confidence=0.4,  # Low confidence
        reasoning="Uncertain about edit",
        edited_params={"query": "paul"},
    )

    # ACT
    final_result = apply_demotion_logic(mock_llm_response)

    # ASSERT
    assert final_result.decision == "AMBIGUOUS"
    assert final_result.clarification_question is not None
```

#### Testing Missing Params Demotion

```python
@pytest.mark.asyncio
async def test_edit_demoted_to_ambiguous_missing_params():
    """Test EDIT with missing edited_params is demoted to AMBIGUOUS."""
    # ARRANGE
    mock_llm_response = ClassificationResult(
        decision="EDIT",
        confidence=0.85,  # High confidence
        reasoning="User wants to edit",
        edited_params=None,  # Missing params!
    )

    # ACT
    final_result = apply_demotion_logic(mock_llm_response)

    # ASSERT
    assert final_result.decision == "AMBIGUOUS"
    assert "cannot determine" in final_result.clarification_question.lower()
```

### 5.4 Streaming HITL Testing

**File:** `services/test_hitl_question_streaming.py`

#### Testing Streaming Clarification Questions

```python
@pytest.mark.asyncio
async def test_stream_clarification_question():
    """Test streaming of clarification question to user."""
    # ARRANGE
    question_generator = HITLQuestionGenerator()

    # ACT
    chunks = []
    async for chunk in question_generator.astream_question(
        decision="AMBIGUOUS",
        action_context=[{"tool_name": "search_contacts", "tool_args": {"query": "John"}}],
    ):
        chunks.append(chunk)

    # ASSERT
    assert len(chunks) > 0
    full_question = "".join(chunks)
    assert "clarification" in full_question.lower() or "préciser" in full_question.lower()
```

---

## 6. Orchestration Testing

### 6.1 Plan Creation Testing

**File:** `test_orchestration.py`

#### Testing Contacts Search Plan

```python
@pytest.mark.asyncio
async def test_create_orchestration_plan_contacts_search():
    """Test orchestration plan creation for contacts search."""
    # ARRANGE
    router_output = RouterOutput(
        intention="contacts_search",
        confidence=0.9,
        context_label="contact",
        next_node="task_orchestrator",
        reasoning="User wants to search contacts",
    )

    state: MessagesState = {
        "messages": [],
        "metadata": {"user_id": "test-user"},
        "routing_history": [router_output],
        "agent_results": {},
        "orchestration_plan": None,
    }

    # ACT
    plan = await create_orchestration_plan(router_output, state)

    # ASSERT
    assert isinstance(plan, OrchestratorPlan)
    assert plan.agents_to_call == ["contacts_agent"]
    assert plan.execution_mode == "sequential"
    assert plan.metadata["intention"] == "contacts_search"
```

#### Testing Multi-Agent Plan

```python
@pytest.mark.asyncio
async def test_create_orchestration_plan_multi_agent():
    """Test plan with multiple agents in sequence."""
    # ARRANGE
    router_output = RouterOutput(
        intention="contacts_and_emails",
        next_node="task_orchestrator",
        confidence=0.85,
    )

    # ACT
    plan = await create_orchestration_plan(router_output, state)

    # ASSERT
    assert len(plan.agents_to_call) == 2
    assert "contacts_agent" in plan.agents_to_call
    assert "emails_agent" in plan.agents_to_call
    assert plan.execution_mode == "sequential"
```

### 6.2 Plan Execution Testing

**File:** `test_orchestration.py` (plan execution patterns)

#### Testing Sequential Execution

```python
def test_get_next_agent_from_plan_sequential():
    """Test getting agents in sequence from plan."""
    # ARRANGE
    plan = OrchestratorPlan(
        agents_to_call=["contacts_agent", "emails_agent"],
        execution_mode="sequential",
    )

    state: MessagesState = {
        "orchestration_plan": plan,
        "agent_results": {},
    }

    # ACT - First call
    next_agent = get_next_agent_from_plan(state)
    assert next_agent == "contacts_agent"

    # Execute first agent
    state["agent_results"]["contacts_agent"] = AgentResult(status="success")

    # ACT - Second call
    next_agent = get_next_agent_from_plan(state)
    assert next_agent == "emails_agent"
```

#### Testing Plan Completion

```python
def test_plan_is_complete_when_all_agents_executed():
    """Test plan completion detection."""
    # ARRANGE
    plan = OrchestratorPlan(
        agents_to_call=["contacts_agent", "emails_agent"],
        execution_mode="sequential",
    )

    state: MessagesState = {
        "orchestration_plan": plan,
        "agent_results": {
            "contacts_agent": AgentResult(status="success"),
            "emails_agent": AgentResult(status="success"),
        },
    }

    # ACT
    is_complete = is_plan_complete(state)

    # ASSERT
    assert is_complete is True
```

### 6.3 Plan Validation Testing

**File:** `test_plan_validator.py`

#### Testing Step Dependencies

```python
def test_validate_step_dependencies():
    """Test that validator checks step dependencies are satisfied."""
    # ARRANGE
    plan = OrchestratorPlan(
        agents_to_call=["emails_agent"],  # Requires contacts_agent first
        execution_mode="sequential",
    )

    # ACT
    validation_result = validate_plan_dependencies(plan)

    # ASSERT
    assert validation_result.is_valid is False
    assert "missing dependency" in validation_result.error.lower()
    assert "contacts_agent" in validation_result.error
```

---

## 7. Tool Testing

### 7.1 Tool Registration Testing

**File:** `test_catalogue_manifests.py`

#### Testing Tool Manifest Creation

```python
def test_create_tool_manifest():
    """Test creating tool manifest with all required fields."""
    # ACT
    manifest = ToolManifest(
        name="search_contacts_tool",
        agent="contacts_agent",
        description="Search contacts by name or email",
        parameters=[
            ParameterSchema(
                name="query",
                type="string",
                required=True,
                description="Search query",
            )
        ],
        outputs=[
            OutputSchema(
                name="contacts",
                type="array",
                description="List of matching contacts",
            )
        ],
        cost=CostProfile(est_cost_usd=0.001),
        permissions=PermissionProfile(required_scopes=["contacts.read"]),
        version="1.0.0",
    )

    # ASSERT
    assert manifest.name == "search_contacts_tool"
    assert len(manifest.parameters) == 1
    assert manifest.parameters[0].required is True
```

### 7.2 Tool Invocation Testing

**File:** `tools/test_google_contacts_tools.py`

#### Testing Contacts Search Tool

```python
@pytest.mark.asyncio
async def test_search_contacts_tool_success():
    """Test successful contacts search via tool."""
    # ARRANGE
    mock_connector = AsyncMock()
    mock_connector.search_contacts.return_value = [
        {"name": "John Doe", "email": "john@example.com"}
    ]

    # ACT
    result = await search_contacts_tool.ainvoke(
        {"query": "John"},
        connector=mock_connector,
    )

    # ASSERT
    assert result["status"] == "success"
    assert len(result["contacts"]) == 1
    assert result["contacts"][0]["name"] == "John Doe"
```

#### Testing Tool Error Handling

```python
@pytest.mark.asyncio
async def test_search_contacts_tool_error_handling():
    """Test tool handles connector errors gracefully."""
    # ARRANGE
    mock_connector = AsyncMock()
    mock_connector.search_contacts.side_effect = Exception("API Error")

    # ACT
    result = await search_contacts_tool.ainvoke(
        {"query": "John"},
        connector=mock_connector,
    )

    # ASSERT
    assert result["status"] == "error"
    assert result["error_code"] == ToolErrorCode.CONNECTOR_ERROR
    assert "API Error" in result["error_message"]
```

### 7.3 Tool Schema Validation

**File:** `test_tool_schemas.py`

#### Testing Parameter Validation

```python
def test_tool_parameter_schema_validation():
    """Test Pydantic validation of tool parameters."""
    # ACT - Valid params
    params = ToolParameters(query="John", limit=10)
    assert params.query == "John"
    assert params.limit == 10

    # ACT - Invalid params (negative limit)
    with pytest.raises(ValidationError) as exc:
        ToolParameters(query="John", limit=-5)

    # ASSERT
    assert "limit" in str(exc.value)
```

### 7.4 Rate Limiting Testing

**File:** `tools/test_rate_limiting.py`

#### Testing Tool-Level Rate Limits

```python
@pytest.mark.asyncio
async def test_tool_rate_limiting():
    """Test that tool enforces rate limits."""
    # ARRANGE
    rate_limiter = create_tool_rate_limiter(max_calls=3, per_seconds=60)

    # ACT - First 3 calls should succeed
    for i in range(3):
        result = await rate_limited_tool.ainvoke({"query": f"test{i}"})
        assert result["status"] == "success"

    # ACT - 4th call should be rate limited
    result = await rate_limited_tool.ainvoke({"query": "test4"})

    # ASSERT
    assert result["status"] == "error"
    assert result["error_code"] == ToolErrorCode.RATE_LIMITED
```

---

## 8. Message Windowing Testing

### 8.1 Core Windowing Testing

**File:** `test_message_windowing.py`

#### Testing Window Size

```python
def test_get_windowed_messages_window_size():
    """Test that windowing keeps only last N turns."""
    # ARRANGE
    messages = [
        SystemMessage(content="System"),
        HumanMessage(content="Turn 1 user"),
        AIMessage(content="Turn 1 assistant"),
        HumanMessage(content="Turn 2 user"),
        AIMessage(content="Turn 2 assistant"),
        HumanMessage(content="Turn 3 user"),
        AIMessage(content="Turn 3 assistant"),
    ]

    # ACT
    result = get_windowed_messages(messages, window_size=1)  # Last 1 turn only

    # ASSERT
    assert len(result) == 3  # System + last turn (2 messages)
    assert isinstance(result[0], SystemMessage)
    assert result[1].content == "Turn 3 user"
    assert result[2].content == "Turn 3 assistant"
```

#### Testing System Message Inclusion

```python
def test_system_message_always_included():
    """Test that SystemMessage is always included regardless of window."""
    # ARRANGE
    messages = [
        SystemMessage(content="You are a helpful assistant"),
        HumanMessage(content="Hello"),
        AIMessage(content="Hi!"),
    ]

    # ACT
    result = get_windowed_messages(messages, window_size=1)

    # ASSERT
    assert len(result) == 3
    assert isinstance(result[0], SystemMessage)
    assert result[0].content == "You are a helpful assistant"
```

### 8.2 Node-Specific Windowing

**File:** `test_nodes_windowing_integration.py`

#### Testing Router Windowing

```python
def test_router_windowed_messages():
    """Test router gets windowed messages optimized for intent detection."""
    # ARRANGE
    messages = create_long_conversation(turns=10)

    # ACT
    windowed = get_router_windowed_messages(messages)

    # ASSERT
    # Router should get last 3 turns for context
    assert len(windowed) <= 7  # System + 3 turns = 7 messages max
```

#### Testing Planner Windowing

```python
def test_planner_windowed_messages():
    """Test planner gets appropriate context window."""
    # ARRANGE
    messages = create_long_conversation(turns=10)

    # ACT
    windowed = get_planner_windowed_messages(messages)

    # ASSERT
    # Planner needs more context (5 turns)
    assert len(windowed) <= 11  # System + 5 turns = 11 messages max
```

### 8.3 Performance Testing

#### Testing Token Reduction

```python
def test_windowing_reduces_token_count():
    """Test that windowing significantly reduces token count."""
    # ARRANGE
    messages = create_long_conversation(turns=20)
    full_token_count = count_tokens(messages)

    # ACT
    windowed = get_windowed_messages(messages, window_size=3)
    windowed_token_count = count_tokens(windowed)

    # ASSERT
    reduction_ratio = windowed_token_count / full_token_count
    assert reduction_ratio < 0.5  # At least 50% reduction
```

---

## 9. Context Management Testing

### 9.1 Context CRUD Testing

**File:** `test_context_manager_expanded.py`

#### Testing Context Creation

```python
@pytest.mark.asyncio
async def test_save_context_item():
    """Test saving item to context store."""
    # ARRANGE
    context_manager = ContextManager(store=in_memory_store)

    # ACT
    await context_manager.save_item(
        context_type="contact",
        item_id="contact-123",
        data={"name": "John Doe", "email": "john@example.com"},
        user_id="user-456",
    )

    # ASSERT
    retrieved = await context_manager.get_item(
        context_type="contact",
        item_id="contact-123",
        user_id="user-456",
    )

    assert retrieved["name"] == "John Doe"
```

#### Testing Context Listing

```python
@pytest.mark.asyncio
async def test_list_context_items():
    """Test listing all items of a context type."""
    # ARRANGE
    context_manager = ContextManager(store=in_memory_store)

    # Save multiple items
    await context_manager.save_item("contact", "c1", {"name": "John"}, "user-1")
    await context_manager.save_item("contact", "c2", {"name": "Jane"}, "user-1")

    # ACT
    items = await context_manager.list_items(
        context_type="contact",
        user_id="user-1",
    )

    # ASSERT
    assert len(items) == 2
    assert any(item["name"] == "John" for item in items)
    assert any(item["name"] == "Jane" for item in items)
```

### 9.2 Context Cleanup Testing

**File:** `test_context_cleanup_on_reset.py`

#### Testing Reset Cleanup

```python
@pytest.mark.asyncio
async def test_context_cleanup_on_conversation_reset():
    """Test that context is cleaned up when conversation resets."""
    # ARRANGE
    context_manager = ContextManager(store=in_memory_store)

    # Save context for conversation
    await context_manager.save_item(
        "contact", "c1", {"name": "John"}, "user-1", conversation_id="conv-1"
    )

    # ACT
    await context_manager.reset_conversation_context("conv-1")

    # ASSERT
    items = await context_manager.list_items("contact", "user-1", conversation_id="conv-1")
    assert len(items) == 0  # Context cleared
```

### 9.3 Multi-Key Store Pattern

**File:** `test_multi_keys_store_pattern.py`

#### Testing Composite Keys

```python
def test_composite_key_format():
    """Test composite key format for context storage."""
    # ARRANGE
    context_type = "contact"
    user_id = "user-123"
    conversation_id = "conv-456"

    # ACT
    composite_key = build_composite_key(context_type, user_id, conversation_id)

    # ASSERT
    assert composite_key == "contact:user-123:conv-456"

    # Test parsing
    parsed = parse_composite_key(composite_key)
    assert parsed["context_type"] == "contact"
    assert parsed["user_id"] == "user-123"
    assert parsed["conversation_id"] == "conv-456"
```

---

## 10. Plan Execution Testing

### 10.1 Reference Resolution Testing

**File:** `orchestration/test_dependency_graph.py`

#### Testing Context References

```python
@pytest.mark.asyncio
async def test_resolve_context_reference():
    """Test resolving @context references in tool args."""
    # ARRANGE
    resolver = ReferenceResolver(context_manager=context_manager)

    # Save context
    await context_manager.save_item(
        "contact", "c1", {"name": "John", "email": "john@example.com"}, "user-1"
    )

    tool_args = {
        "contact_id": "@context:contact:c1:email"  # Reference
    }

    # ACT
    resolved_args = await resolver.resolve(tool_args, user_id="user-1")

    # ASSERT
    assert resolved_args["contact_id"] == "john@example.com"  # Resolved!
```

#### Testing Missing Reference Error

```python
@pytest.mark.asyncio
async def test_resolve_missing_reference_error():
    """Test error when referenced context doesn't exist."""
    # ARRANGE
    resolver = ReferenceResolver(context_manager=context_manager)

    tool_args = {
        "contact_id": "@context:contact:nonexistent:email"
    }

    # ACT & ASSERT
    with pytest.raises(ReferenceResolutionError) as exc:
        await resolver.resolve(tool_args, user_id="user-1")

    assert "not found" in str(exc.value).lower()
```

### 10.2 Tool Execution Testing

#### Testing Successful Execution

```python
@pytest.mark.asyncio
async def test_execute_tool_success():
    """Test successful tool execution."""
    # ARRANGE
    executor = PlanExecutor(registry=agent_registry)

    step = PlanStep(
        tool_name="search_contacts_tool",
        tool_args={"query": "John"},
        dependencies=[],
    )

    # ACT
    result = await executor.execute_step(step, user_id="user-1")

    # ASSERT
    assert result.status == "success"
    assert "contacts" in result.data
```

#### Testing Tool Failure Handling

```python
@pytest.mark.asyncio
async def test_execute_tool_failure_handling():
    """Test graceful handling of tool execution failures."""
    # ARRANGE
    executor = PlanExecutor(registry=agent_registry)

    # Mock tool to fail
    mock_tool = AsyncMock(side_effect=Exception("API Timeout"))
    agent_registry.get_tool = MagicMock(return_value=mock_tool)

    step = PlanStep(tool_name="search_contacts_tool", tool_args={"query": "John"})

    # ACT
    result = await executor.execute_step(step, user_id="user-1")

    # ASSERT
    assert result.status == "error"
    assert "API Timeout" in result.error_message
```

---

## 11. Mocking Strategies

### 11.1 Mocking LLMs

#### Mock LangChain ChatOpenAI

```python
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_llm():
    """Mock LangChain ChatOpenAI LLM."""
    with patch("src.domains.agents.services.hitl_classifier.ChatOpenAI") as mock:
        llm_instance = MagicMock()
        llm_instance.ainvoke = AsyncMock()
        mock.return_value = llm_instance
        yield llm_instance

# Usage
@pytest.mark.asyncio
async def test_with_mock_llm(mock_llm):
    """Test classifier with mocked LLM."""
    # ARRANGE
    mock_llm.ainvoke.return_value = MagicMock(
        content='{"decision": "APPROVE", "confidence": 0.95, "reasoning": "Clear approval"}'
    )

    classifier = HitlResponseClassifier()

    # ACT
    result = await classifier.classify("oui", action_context=[...])

    # ASSERT
    assert result.decision == "APPROVE"
    mock_llm.ainvoke.assert_called_once()
```

### 11.2 Mocking Tools

#### Mock Tool Registry

```python
@pytest.fixture
def mock_registry():
    """Mock AgentRegistry with test tools."""
    registry = MagicMock(spec=AgentRegistry)

    # Mock search_contacts_tool
    search_tool = AsyncMock()
    search_tool.ainvoke.return_value = {
        "status": "success",
        "contacts": [{"name": "John Doe"}]
    }

    registry.get_tool.return_value = search_tool

    return registry
```

### 11.3 Mocking Context Store

#### Mock LangGraph BaseStore

```python
from langchain_core.stores import InMemoryBaseStore

@pytest.fixture
def in_memory_store():
    """Provide in-memory store for testing."""
    return InMemoryBaseStore()

# Usage
@pytest.mark.asyncio
async def test_with_in_memory_store(in_memory_store):
    """Test context manager with in-memory store."""
    context_manager = ContextManager(store=in_memory_store)

    await context_manager.save_item("contact", "c1", {"name": "John"}, "user-1")

    retrieved = await context_manager.get_item("contact", "c1", "user-1")
    assert retrieved["name"] == "John"
```

### 11.4 Mocking Connectors

#### Mock Google Contacts Connector

```python
@pytest.fixture
def mock_contacts_connector():
    """Mock Google Contacts connector."""
    connector = AsyncMock()

    connector.search_contacts.return_value = [
        {"name": "John Doe", "email": "john@example.com"},
        {"name": "Jane Doe", "email": "jane@example.com"},
    ]

    connector.get_contact.return_value = {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1234567890",
    }

    return connector
```

---

## 12. Performance Testing

### 12.1 State Performance Testing

**File:** `test_state_performance.py`

#### Testing State Copy Performance

```python
import time

def test_state_copy_performance():
    """Test that state copying is performant."""
    # ARRANGE
    large_state: MessagesState = {
        "messages": [HumanMessage(content=f"Message {i}") for i in range(100)],
        "metadata": {"user_id": "test"},
        "routing_history": [],
        "agent_results": {},
    }

    # ACT
    start = time.perf_counter()
    for _ in range(1000):
        copied_state = {**large_state}
    elapsed = time.perf_counter() - start

    # ASSERT
    assert elapsed < 1.0  # 1000 copies in < 1 second
```

#### Testing Message Windowing Performance

```python
def test_windowing_performance():
    """Test windowing performance with large message history."""
    # ARRANGE
    messages = [
        HumanMessage(content=f"Turn {i} user")
        for i in range(1000)
    ]

    # ACT
    start = time.perf_counter()
    windowed = get_windowed_messages(messages, window_size=5)
    elapsed = time.perf_counter() - start

    # ASSERT
    assert elapsed < 0.01  # < 10ms for 1000 messages
    assert len(windowed) == 11  # System + 5 turns
```

### 12.2 Concurrency Testing

**File:** `test_tool_dependencies_concurrency.py`

#### Testing Concurrent Tool Execution

```python
import asyncio

@pytest.mark.asyncio
async def test_concurrent_tool_execution():
    """Test executing independent tools concurrently."""
    # ARRANGE
    executor = PlanExecutor(registry=agent_registry)

    steps = [
        PlanStep(tool_name="tool_a", tool_args={}),
        PlanStep(tool_name="tool_b", tool_args={}),
        PlanStep(tool_name="tool_c", tool_args={}),
    ]

    # ACT
    start = time.perf_counter()
    results = await asyncio.gather(*[
        executor.execute_step(step, user_id="user-1")
        for step in steps
    ])
    elapsed = time.perf_counter() - start

    # ASSERT
    assert len(results) == 3
    assert all(r.status == "success" for r in results)
    # Should be faster than sequential (each tool sleeps 0.1s)
    assert elapsed < 0.15  # Concurrent < 0.15s vs Sequential ~0.3s
```

---

## 13. Best Practices

### 13.1 Agent Test Structure

**✅ Do:**
- Test state immutability
- Test graph structure (nodes, edges)
- Test interrupts and resumption
- Use realistic MessagesState fixtures
- Test both success and error paths

**❌ Don't:**
- Mutate state directly in tests
- Skip testing conditional edges
- Ignore checkpointing tests
- Use unrealistic test data

### 13.2 HITL Testing

**✅ Do:**
- Test all decision types (APPROVE/REJECT/EDIT/AMBIGUOUS)
- Test confidence thresholds
- Test demotion logic (low confidence, missing params)
- Test action type extraction
- Mock LLMs for deterministic tests

**❌ Don't:**
- Rely on real LLM calls in unit tests
- Skip edge cases (empty context, ambiguous responses)
- Ignore metrics tracking tests

### 13.3 Naming Conventions

```python
# ✅ Good - Descriptive test names
def test_classify_approve_oui()
def test_edit_demoted_to_ambiguous_low_confidence()
def test_parallel_executor_resolves_context_references()

# ❌ Bad - Unclear names
def test_classifier()
def test_demotion()
def test_executor()
```

### 13.4 Fixture Organization

```python
# ✅ Good - Reusable fixtures
@pytest.fixture
def sample_action_context():
    """Standard action context for HITL tests."""
    return [
        {
            "tool_name": "search_contacts_tool",
            "tool_args": {"query": "John"},
            "tool_description": "Search contacts",
        }
    ]

@pytest.fixture
def mock_llm():
    """Mock LangChain LLM for deterministic tests."""
    with patch("src.domains.agents.services.hitl_classifier.ChatOpenAI") as mock:
        llm_instance = MagicMock()
        llm_instance.ainvoke = AsyncMock()
        mock.return_value = llm_instance
        yield llm_instance
```

---

## 14. Common Patterns

### 14.1 AAA Pattern in Agent Tests

```python
@pytest.mark.asyncio
async def test_orchestration_plan_creation():
    """Test creating orchestration plan from router output."""
    # ARRANGE
    router_output = RouterOutput(
        intention="contacts_search",
        next_node="task_orchestrator",
        confidence=0.9,
    )

    state: MessagesState = {
        "messages": [],
        "routing_history": [router_output],
        "agent_results": {},
    }

    # ACT
    plan = await create_orchestration_plan(router_output, state)

    # ASSERT
    assert plan.agents_to_call == ["contacts_agent"]
    assert plan.execution_mode == "sequential"
```

### 14.2 Parametrized HITL Tests

```python
@pytest.mark.parametrize("user_response,expected_decision", [
    ("oui", "APPROVE"),
    ("ok", "APPROVE"),
    ("d'accord", "APPROVE"),
    ("non", "REJECT"),
    ("annule", "REJECT"),
    ("stop", "REJECT"),
    ("peut-être", "AMBIGUOUS"),
])
@pytest.mark.asyncio
async def test_classify_various_responses(classifier, user_response, expected_decision):
    """Test classification of various user responses."""
    result = await classifier.classify(user_response, action_context=[...])
    assert result.decision == expected_decision
```

### 14.3 Mock Chaining

```python
@pytest.mark.asyncio
async def test_full_agent_flow_with_mocks():
    """Test complete agent flow with mocked dependencies."""
    # ARRANGE
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = MagicMock(content='{"decision": "APPROVE"}')

    mock_connector = AsyncMock()
    mock_connector.search_contacts.return_value = [{"name": "John"}]

    mock_registry = MagicMock()
    mock_registry.get_tool.return_value = create_tool_with_connector(mock_connector)

    # ACT
    result = await run_agent_flow(
        user_message="Search John",
        llm=mock_llm,
        registry=mock_registry,
    )

    # ASSERT
    assert result["status"] == "success"
    assert len(result["contacts"]) == 1
```

---

## 15. Troubleshooting

### 15.1 LangGraph State Errors

**Error:**
```
TypeError: 'MessagesState' object does not support item assignment
```

**Solution:**
```python
# ❌ Bad - Direct mutation
state["messages"].append(new_message)

# ✅ Good - Create new state
state = {
    **state,
    "messages": [*state["messages"], new_message],
}
```

### 15.2 Async Test Failures

**Error:**
```
RuntimeWarning: coroutine 'test_classify_approve' was never awaited
```

**Solution:**
```python
# ❌ Bad - Missing decorator
async def test_classify_approve(classifier):
    result = await classifier.classify("oui", [...])

# ✅ Good - Add @pytest.mark.asyncio
@pytest.mark.asyncio
async def test_classify_approve(classifier):
    result = await classifier.classify("oui", [...])
```

### 15.3 Mock LLM Not Working

**Problem:** LLM still making real API calls

**Solution:**
```python
# ✅ Patch at the right location (where it's imported, not defined)
@patch("src.domains.agents.services.hitl_classifier.ChatOpenAI")
def test_with_mock_llm(mock_openai):
    # Mock the instance returned by ChatOpenAI()
    llm_instance = MagicMock()
    llm_instance.ainvoke = AsyncMock(return_value=...)
    mock_openai.return_value = llm_instance
```

### 15.4 Context Store Leakage

**Problem:** Tests affecting each other via shared context

**Solution:**
```python
# ✅ Use function-scoped in-memory store
@pytest.fixture
def in_memory_store():
    """Fresh in-memory store for each test."""
    return InMemoryBaseStore()

# OR reset between tests
@pytest.fixture(autouse=True)
async def cleanup_store(in_memory_store):
    yield
    # Cleanup after test
    await in_memory_store.clear()
```

### 15.5 Plan Executor Reference Errors

**Error:**
```
ReferenceResolutionError: Context reference @context:contact:c1 not found
```

**Solution:**
```python
# ✅ Ensure context is saved before resolving
await context_manager.save_item("contact", "c1", data, user_id)

# Then resolve
resolved = await resolver.resolve(
    {"contact_id": "@context:contact:c1:email"},
    user_id=user_id
)
```

---

## 16. References

### 16.1 LangGraph Documentation

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangGraph State Management](https://langchain-ai.github.io/langgraph/concepts/state/)
- [LangGraph Checkpointing](https://langchain-ai.github.io/langgraph/concepts/checkpointing/)
- [LangGraph Human-in-the-Loop](https://langchain-ai.github.io/langgraph/concepts/human-in-the-loop/)
- [LangGraph Streaming](https://langchain-ai.github.io/langgraph/concepts/streaming/)

### 16.2 LangChain Testing

- [LangChain Testing Guide](https://python.langchain.com/docs/contributing/testing)
- [LangChain Tools](https://python.langchain.com/docs/concepts/tools/)
- [LangChain Messages](https://python.langchain.com/docs/concepts/messages/)

### 16.3 Project-Specific Resources

**Internal Documentation:**
- `tests/README.md` - Main test suite documentation
- `tests/agents/README.md` - This document
- `docs/optim_monitoring/TESTS_INVENTORY_ANALYSIS.md` - Comprehensive test analysis
- `.github/workflows/tests.yml` - CI/CD test workflow

**Key Test Files:**
- `tests/agents/test_hitl_classifier.py` (1,123 lines) - Main HITL classifier
- `tests/agents/services/test_hitl_classifier.py` (390 lines) - HITL service tests
- `tests/agents/test_orchestration.py` - Orchestration patterns
- `tests/agents/orchestration/test_dependency_graph.py` - Plan dependencies
- `tests/agents/test_message_windowing.py` - Message windowing

### 16.4 Best Practices

- [Testing Async Code in Python](https://superfastpython.com/asyncio-unit-test/)
- [Pytest Async Testing](https://pytest-asyncio.readthedocs.io/)
- [Mocking Best Practices](https://realpython.com/python-mock-library/)

---

## Appendix

### A. Quick Reference

**Running Agent Tests:**
```bash
# All agent tests
pytest tests/agents/

# HITL tests only
pytest tests/agents/ -k "hitl"

# Orchestration tests only
pytest tests/agents/test_orchestration.py

# With coverage
pytest tests/agents/ --cov=src/domains/agents --cov-report=html

# Verbose output
pytest tests/agents/ -vv
```

**Common Test Patterns:**
```bash
# Test specific HITL decision
pytest tests/agents/services/test_hitl_classifier.py::test_classify_approve_oui

# Test plan dependencies
pytest tests/agents/orchestration/test_dependency_graph.py -v

# Test message windowing
pytest tests/agents/test_message_windowing.py -v
```

### B. Agent Test Statistics

**Coverage by Category:**
- HITL Services: ~75% coverage (Good)
- Orchestration: ~60% coverage (Target: 80%)
- Tools: ~70% coverage (Good)
- Context Management: ~65% coverage (Target: 80%)
- Message Windowing: ~85% coverage (Excellent)

**Largest Test Files:**
1. `test_hitl_classifier.py` - 1,123 lines
2. `services/test_hitl_classifier.py` - 390 lines
3. `test_orchestration.py` - ~350 lines (estimated)

**Test Execution Time:**
- Unit tests: ~5s
- Integration tests: ~15s
- E2E tests: ~30s
- **Total:** ~50s for all agent tests

---

**Version:** 1.0.0
**Last Updated:** 2025-11-22
**Status:** Production-Ready Documentation
**Next Review:** 2025-12-22

**Changelog:**
- **v1.0.0 (2025-11-22):** Initial comprehensive agent tests documentation
  - 51 test files documented
  - LangGraph testing patterns
  - HITL testing strategies
  - Orchestration and tool testing
  - Message windowing patterns
  - Context management best practices
  - Mocking strategies for LLMs and tools
  - Performance testing guidelines
