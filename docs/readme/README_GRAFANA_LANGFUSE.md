# Dashboard 14 - Langfuse LLM Observability

**Version**: 1.0
**Created**: 2025-11-23
**Phase**: 3.1.6 - Advanced Langfuse Integration
**Panels**: 24 (exceeds 14 minimum requirement)

---

## 📊 Overview

Comprehensive Grafana dashboard for advanced LLM observability leveraging Langfuse capabilities implemented in Phases 3.1.2-3.1.5:

- **Phase 3.1.2**: Prompt Versioning (PromptRegistry)
- **Phase 3.1.3**: Evaluation Scores Tracking
- **Phase 3.1.4**: A/B Testing Infrastructure
- **Phase 3.1.5.1**: Subgraph Tracing (Hierarchical)
- **Phase 3.1.5.2**: Tool Call Tracing
- **Phase 3.1.5.3**: Multi-Agent Handoff Tracing

---

## 🎯 Architecture

### Data Source Strategy

**Current Implementation**: Prometheus Metrics (Phase 3.1.6 MVP)

**Rationale**:
- ✅ Infrastructure already in place
- ✅ Metrics already collected via LangfuseCallbackHandler
- ✅ No external API dependency
- ✅ Grafana Prometheus datasource pre-configured
- ✅ Real-time updates (30s refresh)

**Future Evolution**: Langfuse API datasource for advanced queries (Phase 3.2+)

### Metrics Source

All metrics are collected through:
1. **LangfuseCallbackHandler** (existing - Phase 3.1.1)
2. **Prometheus Exporters** (new - Phase 3.1.6)
   - `metrics_langgraph.py` - LangGraph framework metrics
   - `metrics_agents.py` - Agent-level metrics
   - `metrics_redis.py` - Redis rate limiting metrics

---

## 📈 Dashboard Structure - 24 Panels

### Row 1: Overview (3 panels)

#### Panel 1: Total LLM Calls (24h)
- **Type**: Stat
- **Metric**: `sum(increase(llm_calls_total[24h]))`
- **Thresholds**: Green (<1000), Yellow (1000-5000), Orange (5000-10000), Red (>10000)
- **Purpose**: High-level API call volume monitoring

#### Panel 2: Average Latency (24h)
- **Type**: Stat
- **Metric**: `avg(rate(llm_call_duration_seconds_sum[24h]) / rate(llm_call_duration_seconds_count[24h]))`
- **Thresholds**: Green (<2s), Yellow (2-5s), Orange (5-10s), Red (>10s)
- **Purpose**: Performance monitoring across all agents

#### Panel 3: Total Cost (24h)
- **Type**: Stat
- **Metric**: `sum(increase(llm_cost_total{currency="USD"}[24h]))`
- **Thresholds**: Green (<$10), Yellow ($10-$50), Orange ($50-$100), Red (>$100)
- **Purpose**: Cost tracking and budget monitoring

---

### Row 2: Prompt Performance (Phase 3.1.2) (3 panels)

#### Panel 4: Calls by Prompt Version
- **Type**: Time series
- **Metric**: `sum by (prompt_id, version) (rate(langfuse_prompt_version_usage[5m]))`
- **Purpose**: Track adoption of different prompt versions from PromptRegistry
- **Use Case**: Identify which prompts are most used, detect version rollout issues

#### Panel 5: Latency by Prompt Version (p95)
- **Type**: Heatmap
- **Metric**: `histogram_quantile(0.95, sum by (prompt_id, version, le) (rate(llm_call_duration_seconds_bucket[5m])))`
- **Purpose**: Compare performance across prompt versions
- **Use Case**: Identify slow prompts, validate optimization efforts

#### Panel 6: Success Rate by Prompt
- **Type**: Gauge
- **Metric**: `(sum(rate(llm_calls_total[5m])) - sum(rate(llm_errors_total[5m]))) / sum(rate(llm_calls_total[5m])) * 100`
- **Thresholds**: Red (<90%), Yellow (90-95%), Green (>95%)
- **Purpose**: Overall reliability monitoring
- **Use Case**: Detect prompt engineering issues, API failures

---

### Row 3: Evaluation Scores (Phase 3.1.3) (2 panels)

#### Panel 7: Evaluation Scores Trends
- **Type**: Time series
- **Metrics**:
  - `avg(langfuse_evaluation_score{metric_name="relevance"})` - Relevance
  - `avg(langfuse_evaluation_score{metric_name="hallucination"})` - Hallucination
  - `avg(langfuse_evaluation_score{metric_name="correctness"})` - Correctness
- **Purpose**: Track LLM output quality over time
- **Use Case**: Detect quality degradation, validate improvements

#### Panel 8: Score Distribution Heatmap
- **Type**: Heatmap
- **Metric**: `sum by (metric_name, score_bucket) (langfuse_evaluation_score_bucket)`
- **Purpose**: Visualize score distribution across buckets (0-0.2, 0.2-0.4, ..., 0.8-1.0)
- **Use Case**: Identify score clustering, detect bimodal distributions

---

### Row 4: A/B Testing (Phase 3.1.4) (3 panels)

#### Panel 9: Variant Distribution
- **Type**: Pie chart
- **Metric**: `sum by (variant) (langfuse_ab_test_variant)`
- **Purpose**: Verify A/B test traffic split
- **Use Case**: Confirm 50/50 split, detect assignment bias

#### Panel 10: Variant Performance Comparison
- **Type**: Bar gauge
- **Metrics**:
  - Latency: `avg by (variant) (llm_call_duration_seconds)`
  - Success Rate: `(sum by (variant) (llm_calls_total) - sum by (variant) (llm_errors_total)) / sum by (variant) (llm_calls_total)`
  - Cost: `sum by (variant) (llm_cost_total)`
- **Purpose**: Compare variants across key metrics
- **Use Case**: Data-driven variant selection, ROI analysis

#### Panel 11: Variant Trends Over Time
- **Type**: Time series (stacked)
- **Metric**: `sum by (variant) (rate(langfuse_ab_test_variant[5m]))`
- **Purpose**: Track variant assignment rate evolution
- **Use Case**: Detect assignment algorithm issues, verify ramp-up

---

### Row 5: Trace Hierarchy (Phase 3.1.5.1) (2 panels)

#### Panel 12: Trace Depth Distribution
- **Type**: Bar chart
- **Metric**: `sum by (depth_level) (langfuse_trace_depth)`
- **Purpose**: Visualize nesting levels (0=root, 1=subgraph, 2+=nested)
- **Use Case**: Understand orchestration complexity, detect infinite loops

#### Panel 13: Subgraph Invocation Rate
- **Type**: Time series
- **Metric**: `sum by (subgraph_name) (rate(langfuse_subgraph_invocations[5m]))`
- **Purpose**: Track agent-level activity (contacts_agent, emails_agent, etc.)
- **Use Case**: Identify most-used agents, detect bottlenecks

---

### Row 6: Tool Call Metrics (Phase 3.1.5.2) (2 panels)

#### Panel 14: Tool Call Success Rate
- **Type**: Stat
- **Metric**: `sum(langfuse_tool_calls{success="true"}) / sum(langfuse_tool_calls) * 100`
- **Thresholds**: Red (<80%), Yellow (80-90%), Green (>90%)
- **Purpose**: Monitor tool integration reliability
- **Use Case**: Detect broken integrations, API failures

#### Panel 15: Tool Calls by Tool Name
- **Type**: Time series (stacked)
- **Metric**: `sum by (tool_name) (rate(langfuse_tool_calls[5m]))`
- **Purpose**: Track usage of each tool (search_contacts, send_email, etc.)
- **Use Case**: Identify most-used tools, optimize caching

---

### Row 7: Multi-Agent Handoffs (Phase 3.1.5.3) (3 panels)

#### Panel 16: Agent Handoff Flow
- **Type**: Table
- **Metric**: `sum by (source_agent, target_agent) (langfuse_agent_handoffs)`
- **Purpose**: Visualize agent transition matrix (router → contacts_agent, etc.)
- **Use Case**: Understand conversation flow patterns, detect routing issues

#### Panel 17: Handoff Duration by Agent Pair
- **Type**: Heatmap
- **Metric**: `avg by (source_agent, target_agent) (langfuse_handoff_duration_seconds)`
- **Purpose**: Identify slow handoffs (Green = fast, Red = slow)
- **Use Case**: Optimize agent orchestration, reduce latency

#### Panel 18: Conversation Flow Complexity
- **Type**: Time series
- **Metric**: `count by (conversation_id) (langfuse_agent_handoffs)`
- **Purpose**: Track number of agents involved per conversation
- **Use Case**: Detect overly complex flows, validate simplification efforts

---

### Row 8: Cost Analysis (2 panels)

#### Panel 19: Cost by Model (24h)
- **Type**: Bar chart (horizontal)
- **Metric**: `sum by (model) (increase(llm_cost_total[24h]))`
- **Purpose**: Identify most expensive models
- **Use Case**: Optimize model selection, switch to cheaper alternatives

#### Panel 20: Cost Trend (7 days)
- **Type**: Time series
- **Metric**: `sum(increase(llm_cost_total[1d]))`
- **Purpose**: Daily cost evolution over the last week
- **Use Case**: Detect cost spikes, forecast budget

---

### Row 9: Error Analysis (2 panels)

#### Panel 21: Errors by Type
- **Type**: Pie chart
- **Metric**: `sum by (error_type) (increase(llm_errors_total[24h]))`
- **Purpose**: Distribution of error types (rate_limit, timeout, invalid_request, etc.)
- **Use Case**: Identify common failure patterns, prioritize fixes

#### Panel 22: Error Rate Trend
- **Type**: Time series
- **Metric**: `rate(llm_errors_total[5m])`
- **Purpose**: Error rate over time (errors/sec)
- **Alert**: Red threshold line at 0.1 errors/s
- **Use Case**: Detect error spikes, validate fixes

---

### Row 10: Token Usage (2 panels)

#### Panel 23: Token Consumption by Type
- **Type**: Time series (stacked area)
- **Metrics**:
  - `sum by (token_type) (rate(llm_tokens_consumed_total{token_type="prompt"}[5m]))` - Prompt
  - `sum by (token_type) (rate(llm_tokens_consumed_total{token_type="completion"}[5m]))` - Completion
  - `sum by (token_type) (rate(llm_tokens_consumed_total{token_type="cached"}[5m]))` - Cached
- **Purpose**: Breakdown of token types
- **Use Case**: Optimize prompt caching, reduce completion tokens

#### Panel 24: Tokens per Model (24h)
- **Type**: Bar gauge (horizontal)
- **Metric**: `sum by (model) (increase(llm_tokens_consumed_total[24h]))`
- **Purpose**: Total token consumption per model
- **Use Case**: Identify token-heavy models, optimize usage

---

## 🔧 Dashboard Variables

### 1. $datasource
- **Type**: Datasource
- **Query**: `prometheus`
- **Purpose**: Select Prometheus datasource

### 2. $interval
- **Type**: Interval
- **Options**: `30s, 1m, 5m, 10m, 30m, 1h`
- **Default**: `5m`
- **Purpose**: Aggregation interval for rate() queries

### 3. $llm_type
- **Type**: Query (multi-select)
- **Query**: `label_values(llm_calls_total, llm_type)`
- **Options**: `router, planner, contacts_agent, emails_agent, response, orchestrator`
- **Purpose**: Filter by agent node type

### 4. $model
- **Type**: Query (multi-select)
- **Query**: `label_values(llm_calls_total, model)`
- **Options**: `gpt-4.1-mini, gpt-4.1-mini-mini, claude-3-5-sonnet, etc.`
- **Purpose**: Filter by LLM model

### 5. $prompt_id
- **Type**: Query (multi-select)
- **Query**: `label_values(langfuse_prompt_version_usage, prompt_id)`
- **Options**: All prompt IDs from PromptRegistry
- **Purpose**: Filter by prompt ID (Phase 3.1.2)

### 6. $experiment
- **Type**: Query (multi-select)
- **Query**: `label_values(langfuse_ab_test_variant, experiment)`
- **Options**: Active A/B test experiments
- **Purpose**: Filter by experiment name (Phase 3.1.4)

---

## 📦 Required Prometheus Metrics

### Existing Metrics (Phase 3.1.1)
These metrics are already collected via LangfuseCallbackHandler:

```python
# LLM Calls
llm_calls_total{llm_type, model, session_id}
llm_call_duration_seconds{llm_type, model}
llm_tokens_consumed_total{llm_type, model, token_type}
llm_cost_total{llm_type, model, currency}

# Errors
llm_errors_total{llm_type, model, error_type}
```

### New Metrics (Phase 3.1.6)
These metrics need to be instrumented in Phase 3.1.6.3:

```python
# Phase 3.1.2 - Prompt Versioning
langfuse_prompt_version_usage{prompt_id, version}  # Counter
# Increment in: src/domains/agents/prompts/registry.py::get_prompt()

# Phase 3.1.3 - Evaluation Scores
langfuse_evaluation_score{metric_name}  # Histogram
langfuse_evaluation_score_bucket{metric_name, score_bucket, le}  # Histogram buckets
# Collect in: src/domains/agents/evaluation/pipeline.py::evaluate()

# Phase 3.1.4 - A/B Testing
langfuse_ab_test_variant{experiment, variant}  # Counter
# Increment in: src/domains/agents/ab_testing/variant_manager.py::assign_variant()

# Phase 3.1.5.1 - Subgraph Tracing
langfuse_trace_depth{depth_level}  # Histogram
langfuse_subgraph_invocations{subgraph_name}  # Counter
# Collect in: src/infrastructure/llm/instrumentation.py::create_instrumented_config()

# Phase 3.1.5.2 - Tool Call Tracing
langfuse_tool_calls{tool_name, success}  # Counter
# Increment in: src/infrastructure/llm/tool_tracing.py::trace_tool_call()

# Phase 3.1.5.3 - Multi-Agent Tracing
langfuse_agent_handoffs{source_agent, target_agent}  # Counter
langfuse_handoff_duration_seconds{source_agent, target_agent}  # Histogram
# Collect in: src/infrastructure/llm/agent_handoff_tracing.py::trace_agent_handoff()
```

---

## 🚀 Installation & Setup

### 1. Copy Dashboard to Grafana

```bash
# Option A: Manual import (Grafana UI)
# 1. Open Grafana → Dashboards → New → Import
# 2. Upload `14-langfuse-llm-observability.json`
# 3. Select Prometheus datasource
# 4. Click "Import"

# Option B: Provisioning (automated)
cp infrastructure/observability/grafana/dashboards/14-langfuse-llm-observability.json \
   /etc/grafana/provisioning/dashboards/
```

### 2. Verify Prometheus Datasource

Ensure Prometheus is configured in Grafana:

```yaml
# /etc/grafana/provisioning/datasources/prometheus.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

### 3. Instrument Missing Metrics

See **Phase 3.1.6.3 - Metrics Instrumentation** for implementation details.

---

## 📊 Usage Scenarios

### Scenario 1: Prompt Performance Optimization

**Goal**: Identify slow prompts and optimize them

**Steps**:
1. Open **Panel 5: Latency by Prompt Version (p95)**
2. Filter by `$prompt_id` to focus on specific prompts
3. Identify red/orange areas (slow prompts)
4. Cross-reference with **Panel 4: Calls by Prompt Version** to check usage
5. Optimize high-usage slow prompts first
6. Deploy new version, monitor latency improvement

**Metrics**:
- Latency reduction: Target <2s p95
- Success rate: Maintain >95%

---

### Scenario 2: A/B Test Evaluation

**Goal**: Determine winning variant in A/B test

**Steps**:
1. Open **Panel 10: Variant Performance Comparison**
2. Select experiment using `$experiment` variable
3. Compare variants across:
   - Latency (lower is better)
   - Success Rate (higher is better)
   - Cost (lower is better)
4. Check **Panel 9: Variant Distribution** to verify traffic split
5. Monitor **Panel 11: Variant Trends** for ramp-up issues
6. Make data-driven decision to promote winner

**Decision Criteria**:
- Variant A: 1.5s latency, 98% success, $0.05/call
- Variant B: 2.0s latency, 96% success, $0.03/call
- **Winner**: Variant A (better UX despite higher cost)

---

### Scenario 3: Cost Optimization

**Goal**: Reduce LLM costs without sacrificing quality

**Steps**:
1. Check **Panel 3: Total Cost (24h)** for current spending
2. Open **Panel 19: Cost by Model (24h)** to identify expensive models
3. Cross-reference with **Panel 24: Tokens per Model (24h)** for token usage
4. Identify candidates for model downgrade (e.g., gpt-4.1-mini → gpt-4.1-mini-mini)
5. Run A/B test (Phase 3.1.4) to validate quality
6. Monitor **Panel 20: Cost Trend (7 days)** for savings

**Example**:
- gpt-4.1-mini: $50/day (router agent)
- Switch to gpt-4.1-mini-mini: $5/day
- **Savings**: $45/day = $1,350/month

---

### Scenario 4: Multi-Agent Debugging

**Goal**: Diagnose slow conversation flows

**Steps**:
1. Open **Panel 18: Conversation Flow Complexity** to identify complex flows
2. Check **Panel 16: Agent Handoff Flow** to see transition matrix
3. Identify bottleneck agent pair in **Panel 17: Handoff Duration**
4. Cross-reference with **Panel 13: Subgraph Invocation Rate** for load
5. Optimize slow agent or parallelize handoffs
6. Verify improvement in **Panel 2: Average Latency (24h)**

**Common Issues**:
- router → planner: 5s handoff (excessive planning time)
- contacts_agent → response: 3s handoff (large context transfer)

---

## 🔍 Troubleshooting

### Issue 1: No Data in Panels

**Symptoms**:
- All panels show "No data"
- Empty graphs

**Root Causes**:
1. **Prometheus not scraping metrics**
   - Check Prometheus targets: http://prometheus:9090/targets
   - Verify `/metrics` endpoint is accessible
2. **Metrics not instrumented**
   - Phase 3.1.6.3 not completed
   - Missing Prometheus exporters
3. **Wrong datasource**
   - Dashboard variable `$datasource` not set to Prometheus

**Fix**:
```bash
# Verify Prometheus scraping
curl http://localhost:8000/metrics | grep llm_calls_total

# Check Prometheus targets
curl http://prometheus:9090/api/v1/targets

# Verify datasource in Grafana
curl http://grafana:3000/api/datasources
```

---

### Issue 2: Metrics Missing Labels

**Symptoms**:
- Panel shows data but cannot filter by `$llm_type` or `$model`
- Variables have no options

**Root Causes**:
1. **Labels not added to metrics**
   - LangfuseCallbackHandler not passing labels
2. **Label cardinality explosion**
   - Too many unique label values (e.g., session_id)

**Fix**:
```python
# Correct label usage (low cardinality)
llm_calls_total.labels(
    llm_type="router",  # 5-10 unique values
    model="gpt-4.1-mini",     # 5-10 unique values
).inc()

# Avoid high cardinality
# ❌ BAD: llm_calls_total.labels(session_id="sess_12345")
# ✅ GOOD: Store session_id in metadata, not labels
```

---

### Issue 3: Heatmaps Not Rendering

**Symptoms**:
- Panels 5, 8, 17 show error or blank heatmap

**Root Causes**:
1. **Histogram metrics not configured**
   - Missing `_bucket`, `_sum`, `_count` metrics
2. **Wrong query format**
   - `format: "heatmap"` not set in target

**Fix**:
```python
# Ensure histogram metrics exist
from prometheus_client import Histogram

llm_call_duration = Histogram(
    'llm_call_duration_seconds',
    'LLM call latency',
    ['llm_type', 'model'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
```

---

## 📚 References

### Related Documentation
- [Session 10 - Phase 3.1.6 Complete](../../../docs/optim_monitoring/SESSION_10_PHASE_3_1_6_COMPLETE.md)
- [Dashboard Design Document](../../../docs/optim_monitoring/SESSION_10_PHASE_3_1_6_DASHBOARD_DESIGN.md)
- [Phase 3.1.2 - Prompt Versioning](../../../docs/optim_monitoring/SESSION_10_PHASE_3_1_2_COMPLETE.md)
- [Phase 3.1.3 - Evaluation Scores](../../../docs/optim_monitoring/SESSION_10_PHASE_3_1_3_COMPLETE.md)
- [Phase 3.1.4 - A/B Testing](../../../docs/optim_monitoring/SESSION_10_PHASE_3_1_4_COMPLETE.md)
- [Phase 3.1.5.1 - Subgraph Tracing](../../../docs/optim_monitoring/SESSION_10_PHASE_3_1_5_1_COMPLETE.md)
- [Phase 3.1.5.2 - Tool Call Tracing](../../../docs/optim_monitoring/SESSION_10_PHASE_3_1_5_2_COMPLETE.md)
- [Phase 3.1.5.3 - Multi-Agent Tracing](../../../docs/optim_monitoring/SESSION_10_PHASE_3_1_5_3_COMPLETE.md)

### External Resources
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)
- [Prometheus Query Examples](https://prometheus.io/docs/prometheus/latest/querying/examples/)
- [Langfuse Observability Guide](https://langfuse.com/docs/observability)

---

## ✅ Validation Checklist

Phase 3.1.6.2 - Dashboard Implementation:

- [x] Dashboard JSON created (14-langfuse-llm-observability.json)
- [x] 24 panels implemented (exceeds 14 minimum)
- [x] 6 dashboard variables configured (datasource, interval, llm_type, model, prompt_id, experiment)
- [x] Global settings configured (refresh 30s, timezone browser, time range 24h)
- [x] Panel descriptions added (all 24 panels documented)
- [x] Grafana schema version 38 compliance
- [x] README documentation created
- [ ] Metrics instrumentation (Phase 3.1.6.3 - PENDING)
- [ ] Dashboard tested with real data (Phase 3.1.6.3 - PENDING)
- [ ] Screenshots captured (Phase 3.1.6.3 - PENDING)

---

**Next Phase**: 3.1.6.3 - Metrics Instrumentation + Langfuse Datasource Configuration
