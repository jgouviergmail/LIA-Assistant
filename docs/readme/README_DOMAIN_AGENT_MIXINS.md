# Agent Service Mixins

**Last Updated**: 2025-11-11 (Phase 3.3 Complete)
**Status**: ✅ Production-ready

---

## Overview

AgentService uses minimal mixins for core infrastructure concerns only. Business logic has been extracted to autonomous services following dependency injection pattern.

---

## Current Architecture (Phase 3.3)

```
AgentService (561 lines) - Main orchestration
├── GraphManagementMixin (graph_management.py)
│   ├── Lazy graph initialization from AgentRegistry
│   ├── HITL classifier + question generator initialization
│   └── _ensure_graph_built() - Lazy build pattern
│
└── StreamingMixin (streaming.py)
    └── buffer_and_enrich_resumption_chunks() - Token enrichment
```

### Business Logic Services (Dependency Injection)

Business logic extracted to autonomous services:

- **OrchestrationService**: Graph execution, state management (incl. HITL
  decision parsing via `_parse_approval_decision`)
- **StreamingService**: SSE formatting, HITL detection & question streaming
- **ConversationOrchestrator**: Conversation lifecycle, persistence

> **v1.21.16 (ADR-107)**: `HITLOrchestrator` (987 lines) was removed — it was
> instantiated here but never called (ghost service). Live HITL logic:
> `HitlResponseClassifier`, `services/hitl/` (interactions, resumption,
> question generator) and `OrchestrationService`.

---

## Mixin Descriptions

### GraphManagementMixin

**Responsibility**: Graph lifecycle management

**Methods**:
- `_ensure_graph_built()`: Lazy initialization of LangGraph from AgentRegistry
- Initializes the HITL classifier and question generator used by the run

**Location**: [graph_management.py](graph_management.py)

### StreamingMixin

**Responsibility**: Token aggregation helper for HITL resumption

**Methods**:
- `buffer_and_enrich_resumption_chunks()`: Enriches SSE chunks with aggregated token metadata

**Location**: [streaming.py](streaming.py)

---

## Migration History

### Phase 3.3 (Days 1-7) - Service Extraction

**Completed**: HITLManagementMixin (1,069 lines) → HITLOrchestrator service
*(the orchestrator itself was later found unused and removed in v1.21.16 —
ADR-107; its live responsibilities are covered by `services/hitl/` and
`OrchestrationService`)*

**Benefits**:
- ✅ Dependency injection (explicit dependencies)
- ✅ Testable in isolation (no AgentService coupling)
- ✅ Reusable across different contexts
- ✅ Clear separation of concerns

**Documentation**:
- [PHASE_3.3_DAY5-6_MIGRATION_COMPLETE.md](../../../../../PHASE_3.3_DAY5-6_MIGRATION_COMPLETE.md)
- [PHASE_3.3_DAY7_CLEANUP_COMPLETE.md](../../../../../PHASE_3.3_DAY7_CLEANUP_COMPLETE.md)

---

## Design Principles

1. **Mixins for Infrastructure Only**: Graph lifecycle, token enrichment
2. **Services for Business Logic**: HITL, orchestration, streaming, conversation
3. **Dependency Injection**: Explicit dependencies via constructor
4. **Single Responsibility**: Each component has one clear purpose

---

## See Also

- [OrchestrationService](../../services/orchestration/service.py) - Graph execution
- [StreamingService](../../services/streaming/service.py) - SSE formatting
- [ConversationOrchestrator](../../services/conversation_orchestrator.py) - Conversation lifecycle
