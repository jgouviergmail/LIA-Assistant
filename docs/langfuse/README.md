# Langfuse LLM Observability - Guide Utilisateur

**Version**: 1.1.1
**Phase**: 3.1 - Advanced Langfuse Integration
**Date**: 2025-12-27
**Status**: Production Ready ✅

---

> **DEPRECATION NOTICE (2025-12-05)**
>
> The following features have been **removed** from the codebase and sections
> referencing them in this documentation are **deprecated**:
>
> - **Evaluators** (`apps/api/src/infrastructure/llm/evaluators/`) - REMOVED
> - **A/B Testing** (`apps/api/src/infrastructure/llm/ab_testing/`) - REMOVED
> - **Evaluation Pipeline** (`apps/api/src/infrastructure/llm/evaluation_pipeline.py`) - REMOVED
>
> These sections remain for historical reference. The core Langfuse tracing,
> prompt management, and cost tracking features are still active.
>
> See [GUIDE_AB_TESTING.md](./GUIDE_AB_TESTING.md) and
> [GUIDE_EVALUATION_SCORES.md](./GUIDE_EVALUATION_SCORES.md) for archived documentation.

---

## 📋 Table des Matières

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Features Disponibles](#features-disponibles)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Guides Utilisateurs](#guides-utilisateurs)
7. [Monitoring & Dashboards](#monitoring--dashboards)
8. [Troubleshooting](#troubleshooting)
9. [Best Practices 2025](#best-practices-2025)

---

## Introduction

### Qu'est-ce que Langfuse?

**Langfuse** est une plateforme open-source d'engineering LLM qui fournit:

- **Prompt Management**: Versioning et A/B testing de prompts
- **Tracing**: Visualisation hiérarchique des workflows multi-agents
- **Evaluation**: Scoring automatique de qualité (relevance, hallucination, correctness)
- **Analytics**: Tracking de coûts, latence, et métriques qualité
- **Monitoring**: Prometheus metrics + Grafana dashboards

### Pourquoi Langfuse dans LIA?

LIA intègre Langfuse pour offrir une observabilité **production-grade** des LLMs:

1. **Debugging**: Comprendre pourquoi un agent a pris telle décision
2. **Optimization**: Comparer performance de différentes versions de prompts
3. **Quality Assurance**: Détecter hallucinations et réponses non pertinentes
4. **Cost Control**: Tracker coûts par conversation, user, agent
5. **Performance**: Identifier bottlenecks de latence dans orchestration multi-agents

---

## Architecture Overview

### Composants Phase 3.1

```
┌─────────────────────────────────────────────────────────────┐
│                    LIA API                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Prompt     │  │  Evaluation  │  │  A/B Testing │     │
│  │  Versioning  │  │   Pipeline   │  │   Manager    │     │
│  │  (3.1.2)     │  │   (3.1.3)    │  │   (3.1.4)    │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                 │              │
│         └─────────────────┴─────────────────┘              │
│                           │                                │
│                  ┌────────▼────────┐                       │
│                  │  Langfuse SDK   │                       │
│                  │  Callbacks      │                       │
│                  └────────┬────────┘                       │
│                           │                                │
├───────────────────────────┼────────────────────────────────┤
│                           │                                │
│  ┌────────────────────────▼───────────────────────┐       │
│  │         Hierarchical Tracing (3.1.5)           │       │
│  ├────────────────────────────────────────────────┤       │
│  │  • Subgraph tracking (3.1.5.1)                 │       │
│  │  • Tool call tracing (3.1.5.2)                 │       │
│  │  • Agent handoff flow (3.1.5.3)                │       │
│  └────────────────────────────────────────────────┘       │
│                           │                                │
├───────────────────────────┼────────────────────────────────┤
│                           │                                │
│  ┌────────────────────────▼───────────────────────┐       │
│  │      Prometheus Metrics (3.1.6.3)              │       │
│  ├────────────────────────────────────────────────┤       │
│  │  • Prompt version usage                        │       │
│  │  • Evaluation scores                           │       │
│  │  • A/B test variants                           │       │
│  │  • Trace depth                                 │       │
│  │  • Subgraph invocations                        │       │
│  │  • Tool calls                                  │       │
│  │  • Agent handoffs                              │       │
│  └────────────────────────────────────────────────┘       │
│                           │                                │
└───────────────────────────┼────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
         ┌──────▼──────┐         ┌─────▼──────┐
         │  Langfuse   │         │ Prometheus │
         │   Cloud     │         │  + Grafana │
         │  (Traces)   │         │ (Metrics)  │
         └─────────────┘         └────────────┘
```

### Data Flow

1. **LLM Call** → Langfuse callback captures trace
2. **Prompt Loading** → PromptRegistry tracks version usage
3. **Evaluation** → EvaluationPipeline scores output quality
4. **A/B Test** → VariantManager assigns and tracks variants
5. **Metrics** → Prometheus exporters expose metrics
6. **Visualization** → Grafana Dashboard 14 displays metrics

---

## Features Disponibles

### Phase 3.1.2 - Prompt Versioning

**Status**: ✅ Production Ready
**Coverage**: 83%
**Guide**: [prompt-versioning.md](prompt-versioning.md)

Fonctionnalités:
- ✅ Semantic versioning (v1, v2, v3, latest)
- ✅ Rollback capability (revert to previous version)
- ✅ Version comparison (performance, cost, quality)
- ✅ Automatic version tracking via Prometheus

**Use Cases**:
- Tester une nouvelle version de prompt avant déploiement
- Comparer performance entre v1 et v2
- Rollback instantané si v2 dégrade qualité

---

### Phase 3.1.3 - Evaluation Scores

**Status**: ✅ Production Ready
**Coverage**: 98%
**Guide**: [evaluators.md](evaluators.md)

Fonctionnalités:
- ✅ Relevance scoring (0.0-1.0) - Pertinence de la réponse
- ✅ Hallucination detection (0.0-1.0) - Détection d'inventions
- ✅ Correctness validation (0.0-1.0) - Exactitude factuelle
- ✅ Latency tracking - Performance temporelle
- ✅ Custom evaluators - Métriques métier custom

**Use Cases**:
- Détecter automatiquement les hallucinations en production
- Mesurer amélioration qualité après changement de prompt
- Alerter si score de pertinence < 0.7

---

### Phase 3.1.4 - A/B Testing

**Status**: ✅ Production Ready
**Coverage**: 95-97%
**Guide**: [ab-testing.md](ab-testing.md)

Fonctionnalités:
- ✅ Variant assignment (control, variant_a, variant_b)
- ✅ Deterministic hashing (même user → même variant)
- ✅ Performance comparison (latency, cost, quality)
- ✅ Statistical analysis (confidence intervals, p-values)
- ✅ Automatic traffic splitting (50/50, 80/20, etc.)

**Use Cases**:
- Comparer GPT-4 vs Claude pour router
- Tester nouveau prompt contre baseline
- Optimiser coût/qualité trade-off

---

### Phase 3.1.5 - Hierarchical Tracing

**Status**: ✅ Production Ready
**Coverage**: 70-73%
**Guide**: Intégré dans [dashboard.md](dashboard.md)

Fonctionnalités:

#### 3.1.5.1 - Subgraph Tracing
- ✅ Depth tracking (0=root, 1=subgraph, 2+=nested)
- ✅ Parent-child relationships
- ✅ Infinite recursion detection (depth > 5)

#### 3.1.5.2 - Tool Call Tracing
- ✅ Tool usage tracking (search_contacts, create_event, etc.)
- ✅ Success/failure rates
- ✅ Latency per tool

#### 3.1.5.3 - Multi-Agent Handoff
- ✅ Agent transition flow (router → planner → agent)
- ✅ Handoff duration (transition latency)
- ✅ Flow complexity analysis

**Use Cases**:
- Debugger orchestration multi-agents complexe
- Identifier quel agent est le plus lent
- Visualiser flux de conversation complet

---

### Phase 3.1.6 - Grafana Dashboard

**Status**: ✅ Production Ready
**Panels**: 24/24 (100%)
**Guide**: [dashboard.md](dashboard.md)

Dashboard 14: Langfuse LLM Observability

**Rows**:
1. Overview (calls, cost, latency)
2. Prompt Versioning (usage, performance)
3. Evaluation Scores (trends, distribution)
4. A/B Testing (variants, comparison)
5. Subgraph Tracing (depth, invocations)
6. Tool Call Tracing (success rate, usage)
7. Multi-Agent Handoff (flow, duration)
8. Cost Analysis (by model, by prompt)
9. Performance (latency, errors, cache)

**Access**: `http://localhost:3000/d/langfuse-llm-observability`

---

## Quick Start

### Step 1: Enable Langfuse

Edit `apps/api/.env`:

```bash
# Langfuse Configuration
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com  # or self-hosted

# Features (Phase 3.1)
LANGFUSE_PROMPT_VERSIONING_ENABLED=true
LANGFUSE_EVALUATION_ENABLED=true
LANGFUSE_AB_TESTING_ENABLED=true
```

**Get API Keys**:
1. Sign up at [cloud.langfuse.com](https://cloud.langfuse.com)
2. Create a new project
3. Copy Public Key and Secret Key from Settings

---

### Step 2: Start Services

```bash
# Start API with Langfuse enabled
cd apps/api
uvicorn src.main:app --reload --port 8000

# Start Prometheus (optional, for metrics)
docker-compose up prometheus -d

# Start Grafana (optional, for dashboards)
docker-compose up grafana -d
```

---

### Step 3: Verify Integration

**Check Langfuse UI**:
1. Go to [cloud.langfuse.com](https://cloud.langfuse.com)
2. Navigate to your project
3. Click "Traces" tab
4. Send a test request to LIA API
5. Verify trace appears in Langfuse UI

**Check Prometheus Metrics**:
```bash
curl http://localhost:8000/metrics | grep langfuse
```

Expected output:
```
langfuse_prompt_version_usage{prompt_id="router_system_v6",version="1"} 42.0
langfuse_evaluation_score_count{metric_name="relevance"} 15.0
langfuse_ab_test_variant{experiment="prompt_test_001",variant="control"} 25.0
...
```

**Check Grafana Dashboard**:
1. Go to `http://localhost:3000`
2. Login (admin/admin)
3. Navigate to Dashboards → Langfuse LLM Observability
4. Verify panels display data

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LANGFUSE_ENABLED` | Yes | `false` | Enable/disable Langfuse integration |
| `LANGFUSE_PUBLIC_KEY` | Yes* | - | Langfuse public API key |
| `LANGFUSE_SECRET_KEY` | Yes* | - | Langfuse secret API key |
| `LANGFUSE_HOST` | No | `https://cloud.langfuse.com` | Langfuse instance URL |
| `LANGFUSE_PROMPT_VERSIONING_ENABLED` | No | `true` | Enable prompt versioning (3.1.2) |
| `LANGFUSE_EVALUATION_ENABLED` | No | `true` | Enable evaluation pipeline (3.1.3) |
| `LANGFUSE_AB_TESTING_ENABLED` | No | `true` | Enable A/B testing (3.1.4) |

*Required if `LANGFUSE_ENABLED=true`

---

### Prompt Registry Configuration

**Location**: `apps/api/src/domains/agents/prompts/`

**Structure** (consolidée v1):
```
prompts/
├── v1/
│   ├── router_system_prompt_template.txt
│   ├── planner_system_prompt.txt
│   ├── response_system_prompt_base.txt
│   └── ... (26 prompts + 16 fewshot)
└── prompt_loader.py                  # PromptLoader
```

**Modification de Prompts**:
1. Éditer le fichier dans `v1/`
2. Mettre à jour le header changelog dans le fichier
3. Redémarrer l'API (hot reload détecte les changements)

See [prompt-versioning.md](prompt-versioning.md) for details.

---

### Evaluation Configuration

**Location**: `apps/api/src/infrastructure/llm/evaluators/`

**Available Evaluators**:
- `RelevanceEvaluator`: Measures response relevance to user query
- `HallucinationEvaluator`: Detects factual inconsistencies
- `LatencyEvaluator`: Tracks response time
- Custom evaluators: Extend `EvaluatorBase`

**Configuration**:
```python
from src.infrastructure.llm.evaluation_pipeline import EvaluationPipeline
from src.infrastructure.llm.evaluators import (
    RelevanceEvaluator,
    HallucinationEvaluator,
)

pipeline = EvaluationPipeline(
    langfuse_client=langfuse_client,
    evaluators=[
        RelevanceEvaluator(),
        HallucinationEvaluator(),
    ],
    send_to_langfuse=True,  # Send scores to Langfuse
)
```

See [evaluators.md](evaluators.md) for details.

---

### A/B Testing Configuration

**Location**: `apps/api/src/infrastructure/llm/ab_testing/`

**Example Experiment**:
```python
from src.infrastructure.llm.ab_testing.variant_manager import (
    VariantManager,
    Experiment,
    Variant,
)

# Define experiment
experiment = Experiment(
    name="prompt_optimization_001",
    description="Test new router prompt",
    variants=[
        Variant(name="control", weight=0.5, config={"prompt_version": "1"}),
        Variant(name="variant_a", weight=0.5, config={"prompt_version": "2"}),
    ],
)

# Assign variant to user
manager = VariantManager()
assignment = manager.assign_variant(experiment, user_id="user_123")
print(assignment.variant_name)  # "control" or "variant_a"
```

See [ab-testing.md](ab-testing.md) for details.

---

## Guides Utilisateurs

### Guides Disponibles (Phase 4.3 - Production Ready ✅)

1. **[GUIDE_PROMPT_VERSIONING.md](./GUIDE_PROMPT_VERSIONING.md)** (1087 lignes)
   - Pourquoi versionner les prompts?
   - Architecture LIA (router, planner, step executor)
   - Setup & Configuration
   - Usage examples (router v6 v1 vs v2, planner avec fallback)
   - Querying & Analysis (PromQL queries, Grafana dashboards)
   - Best Practices (semantic versioning, changelog, testing, rollback)
   - Troubleshooting (version not tracked, cardinality explosion)

2. **[GUIDE_EVALUATION_SCORES.md](./GUIDE_EVALUATION_SCORES.md)** (1140 lignes)
   - Pourquoi évaluer la qualité LLM?
   - Types d'évaluation (Hallucination, Relevance, Quality)
   - Setup & Configuration (evaluators, Prometheus metrics)
   - Usage examples (evaluate response, A/B test avec evaluation)
   - Grafana Dashboards (hallucination distribution, relevance time series)
   - Best Practices (sampling strategy, human-in-the-loop, caching)
   - Troubleshooting (scores always 0.5, high cost)

3. **[GUIDE_AB_TESTING.md](./GUIDE_AB_TESTING.md)** (260 lignes)
   - A/B Testing dans contexte LLM
   - Quick Start (gpt-4.1-mini-mini vs Claude-3.5-Sonnet)
   - Metrics & Analysis (PromQL success rate, statistical significance)
   - Best Practices (experiment duration, traffic allocation, success criteria)
   - Troubleshooting (cardinality explosion)

4. **[GUIDE_BEST_PRACTICES.md](./GUIDE_BEST_PRACTICES.md)** (460 lignes)
   - Cardinality Management (règles d'or, validation, limits)
   - Sampling Strategy (cost optimization, intelligent sampling)
   - Performance Optimization (async instrumentation, caching, batching)
   - Security & Privacy (PII filtering GDPR, access control)
   - Monitoring & Alerting (key alerts, production checklist)

### Documentation Complémentaire

- **[README Observability](../readme/README_OBSERVABILITY.md)** - Vue d'ensemble metrics infrastructure
- **[README Grafana Dashboards](../readme/README_GRAFANA_DASHBOARD.md)** - Dashboard 14 détails (Panel-by-panel)
- **[Runbooks](../runbooks/)** - Incident response procedures (22 runbooks)

---

## Monitoring & Dashboards

### Langfuse UI

**Access**: [cloud.langfuse.com](https://cloud.langfuse.com) (or self-hosted)

**Key Features**:
- **Traces**: Hierarchical visualization of conversations
- **Sessions**: Group traces by conversation/user
- **Prompts**: Manage prompt versions
- **Scores**: View evaluation results
- **Analytics**: Cost, latency, quality trends

**Recommended Views**:
1. Traces → Filter by session_id
2. Prompts → Compare versions
3. Scores → Track quality over time

---

### Grafana Dashboard 14

**Access**: `http://localhost:3000/d/langfuse-llm-observability`

**24 Panels**:

#### Row 1: Overview
- Total LLM Calls (counter)
- Total Cost ($)
- Average Latency (ms)

#### Row 2: Prompt Versioning
- Calls by Prompt Version (stacked graph)
- Latency by Prompt Version (heatmap)
- Prompt Version Table (top N)

#### Row 3: Evaluation Scores
- Evaluation Scores Trends (time series)
- Score Distribution Heatmap (0.0-1.0)

#### Row 4: A/B Testing
- Variant Distribution (pie chart)
- Variant Performance (comparison table)
- Variant Trends (time series)

#### Row 5: Subgraph Tracing
- Trace Depth Distribution (histogram)
- Subgraph Invocation Rate (graph)

#### Row 6: Tool Call Tracing
- Tool Call Success Rate (gauge)
- Tool Calls by Tool Name (bar chart)

#### Row 7: Multi-Agent Handoff
- Agent Handoff Flow (table)
- Handoff Duration Heatmap (matrix)
- Conversation Flow Complexity (graph)

#### Row 8: Cost Analysis
- Cost by Model (stacked graph)
- Cost by Prompt Version (table)
- Token Usage Trends (time series)

#### Row 9: Performance
- Latency Distribution (histogram)
- Error Rate (percentage)
- Cache Hit Rate (gauge)

See [dashboard.md](dashboard.md) for detailed usage guide.

---

## Troubleshooting

### Issue: Traces not appearing in Langfuse UI

**Symptoms**: API runs but no traces in Langfuse

**Root Causes**:
1. `LANGFUSE_ENABLED=false` in `.env`
2. Invalid API keys
3. Network connectivity issues

**Solutions**:
```bash
# 1. Verify .env configuration
grep LANGFUSE apps/api/.env

# 2. Test API keys
curl -X POST https://cloud.langfuse.com/api/public/ingestion \
  -H "Authorization: Bearer $LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'

# 3. Check API logs
tail -f apps/api/logs/app.log | grep langfuse
```

---

### Issue: Prometheus metrics not exported

**Symptoms**: `/metrics` endpoint empty for langfuse_* metrics

**Root Causes**:
1. Features disabled in `.env`
2. No LLM calls made yet
3. Import errors in metrics module

**Solutions**:
```bash
# 1. Verify features enabled
grep LANGFUSE_.*_ENABLED apps/api/.env

# 2. Send test request
curl -X POST http://localhost:8000/api/v1/agents/router \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'

# 3. Check metrics endpoint
curl http://localhost:8000/metrics | grep langfuse

# 4. Verify imports
cd apps/api && python -c "from src.infrastructure.observability.metrics_langfuse import *"
```

---

### Issue: Evaluation scores not sent to Langfuse

**Symptoms**: Traces appear but no scores attached

**Root Causes**:
1. `LANGFUSE_EVALUATION_ENABLED=false`
2. Evaluators not configured
3. Langfuse client not passed to pipeline

**Solutions**:
```python
# Verify evaluation pipeline setup
from src.infrastructure.llm.evaluation_pipeline import EvaluationPipeline

# Check configuration
print(pipeline.send_to_langfuse)  # Should be True
print(pipeline.langfuse_client)    # Should not be None
print(len(pipeline.evaluators))    # Should be > 0
```

---

### Issue: A/B test variants not tracking

**Symptoms**: Variants assigned but no metrics in Prometheus

**Root Causes**:
1. `LANGFUSE_AB_TESTING_ENABLED=false`
2. Prometheus metrics not instrumented
3. Variant manager not called

**Solutions**:
```bash
# Verify A/B testing enabled
grep LANGFUSE_AB_TESTING_ENABLED apps/api/.env

# Check Prometheus metrics
curl http://localhost:8000/metrics | grep langfuse_ab_test_variant

# Verify variant assignment in logs
tail -f apps/api/logs/app.log | grep variant_assigned
```

---

## Best Practices 2025

### 1. Prompt Versioning

✅ **DO**:
- Version prompts semantically (v1, v2, v3)
- Test new version with A/B test before full rollout
- Document changes in prompt comments
- Monitor performance metrics after deployment

❌ **DON'T**:
- Skip versioning and edit prompts directly
- Deploy new version without testing
- Use non-semantic versions (e.g., v1.0.2.3)

---

### 2. Evaluation

✅ **DO**:
- Run evaluations asynchronously (don't block responses)
- Set alert thresholds (e.g., relevance < 0.7)
- Review evaluation results weekly
- Create custom evaluators for business metrics

❌ **DON'T**:
- Block user response while evaluating
- Ignore evaluation scores in production
- Use only generic evaluators (relevance, hallucination)

---

### 3. A/B Testing

✅ **DO**:
- Define success metrics before starting test
- Use adequate sample size (≥100 users per variant)
- Run test for sufficient duration (≥1 week)
- Analyze statistical significance before deciding

❌ **DON'T**:
- Make decisions with <50 samples
- Stop test after 1 day
- Cherry-pick results
- Run too many experiments simultaneously

---

### 4. Monitoring

✅ **DO**:
- Set up Grafana alerts for anomalies
- Review dashboards daily in production
- Monitor cost trends proactively
- Track quality metrics (not just latency/cost)

❌ **DON'T**:
- Only check dashboards when issues arise
- Ignore cost increases
- Focus only on technical metrics (latency, errors)

---

### 5. Cost Optimization

✅ **DO**:
- Use prompt caching where possible
- Monitor cost per conversation
- Set budget alerts
- Optimize prompt length

❌ **DON'T**:
- Use GPT-4 for simple classification tasks
- Ignore token usage trends
- Skip caching implementation

---

## Resources

### Official Documentation

- **Langfuse Docs**: [langfuse.com/docs](https://langfuse.com/docs)
- **Langfuse Python SDK**: [langfuse.com/docs/sdk/python](https://langfuse.com/docs/sdk/python)
- **Langfuse Prompt Management**: [langfuse.com/docs/prompts](https://langfuse.com/docs/prompts)
- **Prometheus Docs**: [prometheus.io/docs](https://prometheus.io/docs)
- **Grafana Docs**: [grafana.com/docs](https://grafana.com/docs)

### LIA Documentation

- **Phase 3.1 Implementation**:
  - [SESSION_10_PHASE_3_1_6_2_COMPLETE.md](../optim_monitoring/SESSION_10_PHASE_3_1_6_2_COMPLETE.md)
  - [SESSION_10_PHASE_3_1_6_3_COMPLETE.md](../optim_monitoring/SESSION_10_PHASE_3_1_6_3_COMPLETE.md)
  - [SESSION_11_COMPLETE.md](../optim_monitoring/SESSION_11_COMPLETE.md)
  - [SESSION_12_COMPLETE.md](../optim_monitoring/SESSION_12_COMPLETE.md)

- **Grafana Dashboard**:
  - [14-langfuse-README.md](../../infrastructure/observability/grafana/dashboards/14-langfuse-README.md) (780 lines)

- **Tests**:
  - [test_evaluation_pipeline.py](../../apps/api/tests/unit/infrastructure/llm/test_evaluation_pipeline.py) (22 tests, 98% coverage)
  - [test_instrumentation.py](../../apps/api/tests/unit/infrastructure/llm/test_instrumentation.py) (19 tests, 70% coverage)

### Community

- **Langfuse Discord**: [discord.gg/langfuse](https://discord.gg/langfuse)
- **Langfuse GitHub**: [github.com/langfuse/langfuse](https://github.com/langfuse/langfuse)

---

## Support

### Issues & Bug Reports

For LIA-specific issues:
- Create issue in project repository
- Include error logs, configuration, steps to reproduce

For Langfuse platform issues:
- Check [Langfuse Status](https://status.langfuse.com)
- Report at [github.com/langfuse/langfuse/issues](https://github.com/langfuse/langfuse/issues)

### Feature Requests

Submit feature requests for Phase 3.2+ in project repository with:
- Use case description
- Expected behavior
- Business impact

---

## Changelog

### v1.0.0 (2025-11-23) - Phase 3.1 Complete

**Added**:
- ✅ Prompt versioning with PromptRegistry (3.1.2)
- ✅ Evaluation pipeline with 3 evaluators (3.1.3)
- ✅ A/B testing infrastructure (3.1.4)
- ✅ Hierarchical tracing (subgraph, tool, handoff) (3.1.5)
- ✅ Grafana Dashboard 14 with 24 panels (3.1.6)
- ✅ Prometheus metrics (7 metrics groups) (3.1.6.3)
- ✅ Comprehensive tests (192 tests, 87% coverage) (3.1.7)

**Coverage**:
- `evaluation_pipeline.py`: 98%
- `ab_testing/analyzer.py`: 97%
- `prompt_registry.py`: 83%
- Average Phase 3.1: 87%

**Status**: ✅ Production Ready

---

## License

© 2025 LIA. All rights reserved.
