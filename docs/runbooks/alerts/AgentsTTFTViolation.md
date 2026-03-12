# AgentsTTFTViolation - Runbook

**Severity**: Warning
**Component**: Agents (LangGraph)
**Impact**: Poor user experience, perceived slowness, user abandonment
**SLA Impact**: Yes - TTFT SLA violated (target: <1000ms P95)

---

## 📊 Alert Definition

**Alert Name**: `AgentsTTFTViolation`

**Prometheus Expression**:
```promql
histogram_quantile(0.95,
  sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le, intention)
) * 1000 > ${ALERT_AGENTS_TTFT_P95_MS}
```

**Threshold**:
- **Production**: P95 >1000ms (ALERT_AGENTS_TTFT_P95_MS=1000)
- **Staging**: P95 >1500ms (More relaxed for testing)
- **Development**: P95 >2000ms (Network latency acceptable)

**Firing Duration**: `for: 5m`

**Labels**:
- `severity`: warning
- `component`: agents
- `sla`: ttft
- `intention`: [user intention type]

**SLA Definition**:
TTFT (Time To First Token) = Time from user request to first streaming chunk received
- **Target**: P95 <1000ms (perceived as "instant")
- **Acceptable**: P95 <1500ms (perceived as "fast")
- **Poor**: P95 >2000ms (noticeable delay, user frustration)

---

## 🔍 Symptoms

### What Users See
- **Visible delay before response** - Blank screen for 1-3 seconds after submitting
- **Perceived unresponsiveness** - "Is it working?" uncertainty
- **Incomplete streaming UX** - Response appears "stuck" before starting
- **User abandonment** - Users refresh or re-submit request

### What Ops See
- **TTFT P95 >1000ms** in Grafana dashboard
- **Increased latency metrics** - `sse_time_to_first_token_seconds` elevated
- **Slow router decisions** - Router taking >500ms (should be <300ms)
- **LLM API latency spikes** - OpenAI/Anthropic API slow to respond
- **Large conversation context** - Too many messages in history

---

## 🎯 Possible Causes

### 1. LLM API Latency (High Likelihood - 60%)

**Description**: External LLM provider (OpenAI, Anthropic, Google) experiencing high latency or rate limiting.

**How to Verify**:
```bash
# Check LLM API latency P95
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, llm_api_duration_seconds_bucket)" | jq '.data.result[0].value[1]'

# Check LLM API failure rate
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_api_requests_total{status=\"error\"}[5m])" | jq '.data.result[0].value[1]'

# Check provider-specific latency
docker-compose logs api --since 10m | grep "LLM API" | grep -oP "duration=\K[0-9.]+" | sort -n | tail -20

# Check OpenAI status page
curl -s https://status.openai.com/api/v2/summary.json | jq '.status.description'
```

**Expected Output if This is the Cause**:
- LLM API P95 >3 seconds (normal: 1-2s)
- Errors like "rate_limit_exceeded", "service_unavailable"
- OpenAI status: "Partial Outage" or "Major Outage"

---

### 2. Router Latency (Medium-High Likelihood - 55%)

**Description**: Agent router taking too long to classify user intent, delaying LLM invocation.

**How to Verify**:
```bash
# Check router decision latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, router_decision_duration_seconds_bucket) * 1000" | jq '.data.result[0].value[1]'

# Should be <300ms, if >500ms → PROBLEM

# Check router LLM calls (router uses LLM for classification)
docker-compose logs api --since 10m | grep "router" | grep -i "llm\|openai"

# Check if router prompt is too large
docker-compose logs api --since 10m | grep "router" | grep -oP "prompt_tokens=\K[0-9]+" | sort -n | tail -10
```

**Expected Output if This is the Cause**:
- Router P95 >500ms (target: <300ms)
- Router prompt tokens >1000 (should be <500)
- Router using slower LLM model (gpt-4 instead of gpt-3.5-turbo)

---

### 3. Large Conversation Context (Medium Likelihood - 45%)

**Description**: Too many messages in conversation history sent to LLM, increasing processing time.

**How to Verify**:
```bash
# Check conversation message count distribution
docker-compose exec postgres psql -U lia -c "
SELECT
  CASE
    WHEN jsonb_array_length(checkpoint_data->'messages') < 10 THEN '<10'
    WHEN jsonb_array_length(checkpoint_data->'messages') < 50 THEN '10-50'
    WHEN jsonb_array_length(checkpoint_data->'messages') < 100 THEN '50-100'
    ELSE '>100'
  END AS message_count_bucket,
  COUNT(*) AS conversations
FROM checkpoints
WHERE updated_at > NOW() - INTERVAL '1 hour'
GROUP BY message_count_bucket
ORDER BY message_count_bucket;
"

# Check prompt token counts
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, llm_prompt_tokens_bucket)" | jq '.data.result[0].value[1]'

# Check if context pruning is working
docker-compose logs api --since 10m | grep -i "context\|prune\|trim"
```

**Expected Output if This is the Cause**:
- Many conversations with >50 messages
- Prompt tokens P95 >4000 (models like GPT-3.5 start slowing down)
- No evidence of context pruning in logs

---

### 4. Network Latency to LLM Provider (Medium Likelihood - 40%)

**Description**: Network path to OpenAI/Anthropic degraded, adding RTT latency.

**How to Verify**:
```bash
# Ping OpenAI API
ping -c 10 api.openai.com

# Check DNS resolution time
time nslookup api.openai.com

# Traceroute to LLM provider
traceroute -m 15 api.openai.com

# Check for packet loss
mtr -r -c 100 api.openai.com

# Check if using proxy/VPN (can add latency)
env | grep -i "proxy\|http"
```

**Expected Output if This is the Cause**:
- Ping latency >100ms (good: <50ms)
- DNS resolution >500ms (good: <100ms)
- Traceroute shows high latency hops (>100ms)
- Packet loss >1%

---

### 5. Database Query Latency (Low-Medium Likelihood - 30%)

**Description**: Slow database queries fetching conversation history before LLM call.

**How to Verify**:
```bash
# Check slow database queries
docker-compose exec postgres psql -U lia -c "
SELECT
  substring(query, 1, 100) AS query_preview,
  calls,
  mean_exec_time / 1000 AS mean_seconds,
  max_exec_time / 1000 AS max_seconds
FROM pg_stat_statements
WHERE query LIKE '%checkpoints%' OR query LIKE '%messages%'
ORDER BY mean_exec_time DESC
LIMIT 10;
"

# Check checkpoint load latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, checkpoint_load_duration_seconds_bucket) * 1000" | jq '.data.result[0].value[1]'

# Check database connection pool
curl -s "http://localhost:9090/api/v1/query?query=db_connection_pool_in_use" | jq '.data.result[0].value[1]'
```

**Expected Output if This is the Cause**:
- Checkpoint load P95 >200ms (target: <50ms)
- Slow queries fetching conversation history (>100ms)
- Connection pool saturated (>80% in use)

---

### 6. Cold Start / Model Loading (Low Likelihood - 20%)

**Description**: First request after deployment or idle period slower due to model/prompt loading.

**How to Verify**:
```bash
# Check container uptime
docker inspect lia_api_1 | jq '.[0].State.StartedAt'

# Check if TTFT correlates with container restarts
docker-compose ps | grep api

# Check for lazy loading in logs
docker-compose logs api --since 10m | grep -i "load\|init\|cache\|warm"

# Check if using prompt caching
docker-compose logs api | grep -i "prompt.*cache"
```

**Expected Output if This is the Cause**:
- Container recently restarted (<10 minutes ago)
- First few requests slow, then normalize
- Logs show "Loading model", "Initializing prompt cache"

---

## 🔧 Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Check current TTFT metrics**
```bash
# P95 TTFT overall
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le)) * 1000" | jq '.data.result[0].value[1]'

# P95 TTFT by intention
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le, intention)) * 1000" | jq '.data.result[] | "\(.metric.intention): \(.value[1])ms"'

# If >1000ms → SLA violated
```

**Step 2: Check LLM API health**
```bash
# LLM API latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, llm_api_duration_seconds_bucket) * 1000" | jq '.data.result[0].value[1]'

# LLM API error rate
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_api_requests_total{status=\"error\"}[5m]) * 100" | jq '.data.result[0].value[1]'

# If latency >3000ms OR error rate >5% → LLM API issue
```

**Step 3: Check router performance**
```bash
# Router decision latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, router_decision_duration_seconds_bucket) * 1000" | jq '.data.result[0].value[1]'

# If >500ms → Router bottleneck
```

---

### Deep Dive Investigation (5-10 minutes)

**Step 4: Analyze TTFT breakdown**
```bash
# Breakdown: Router + LLM TTFT + Network
# Total TTFT = Router Decision + LLM API Latency

# Router contribution
ROUTER_P95=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, router_decision_duration_seconds_bucket) * 1000" | jq -r '.data.result[0].value[1]')

# LLM contribution
LLM_P95=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, llm_api_duration_seconds_bucket) * 1000" | jq -r '.data.result[0].value[1]')

echo "Router P95: ${ROUTER_P95}ms"
echo "LLM API P95: ${LLM_P95}ms"
echo "Total (approx): $((${ROUTER_P95%.*} + ${LLM_P95%.*}))ms"

# If Router >30% of total → Optimize router
# If LLM >70% of total → External API issue or large context
```

**Step 5: Check conversation context sizes**
```bash
# Distribution of prompt tokens
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.50, llm_prompt_tokens_bucket)" | jq '.data.result[0].value[1]'
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, llm_prompt_tokens_bucket)" | jq '.data.result[0].value[1]'
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99, llm_prompt_tokens_bucket)" | jq '.data.result[0].value[1]'

# If P95 >4000 tokens → Context too large
# If P99 >8000 tokens → VERY large contexts

# Check message count in active conversations
docker-compose exec postgres psql -U lia -c "
SELECT
  AVG(jsonb_array_length(checkpoint_data->'messages')) AS avg_messages,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY jsonb_array_length(checkpoint_data->'messages')) AS p95_messages
FROM checkpoints
WHERE updated_at > NOW() - INTERVAL '1 hour';
"
```

**Step 6: Test direct LLM API latency**
```bash
# Bypass router, call LLM directly to isolate latency
time curl -X POST https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10,
    "stream": true
  }' --no-buffer | head -1

# If <500ms → Router or application overhead is issue
# If >2000ms → LLM provider issue
```

**Step 7: Check for streaming issues**
```bash
# SSE streaming errors
curl -s "http://localhost:9090/api/v1/query?query=rate(sse_streaming_errors_total[5m])" | jq '.data.result[0].value[1]'

# Check if streaming properly configured
docker-compose logs api --since 10m | grep -i "stream" | tail -50

# Verify SSE headers
curl -N http://localhost:8000/api/agents/chat -X POST -H "Content-Type: application/json" -d '{"message":"test"}' -v 2>&1 | grep -i "transfer-encoding\|content-type"
# Should show: Content-Type: text/event-stream
```

---

## ✅ Resolution Steps

### Immediate Mitigation (<5 minutes)

**Option 1: Switch to faster LLM model (if using GPT-4)**
```bash
# Check current model
grep "OPENAI_MODEL\|DEFAULT_MODEL" apps/api/.env

# If using gpt-4, temporarily switch to gpt-3.5-turbo (5-10x faster TTFT)
nano apps/api/.env
# Change: OPENAI_MODEL=gpt-4 → OPENAI_MODEL=gpt-3.5-turbo

# Restart API
docker-compose restart api

# Verify TTFT improved
sleep 60
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le)) * 1000" | jq '.data.result[0].value[1]'

# When to use: Urgent SLA violation, quality trade-off acceptable
# Expected impact: TTFT reduces 50-70% (2000ms → 600-1000ms)
# Downside: Lower response quality
```

**Option 2: Reduce conversation context window**
```bash
# Edit context pruning configuration
nano apps/api/.env
# Add or modify:
# MAX_CONVERSATION_MESSAGES=20  # Keep only last 20 messages (default: 50)
# MAX_PROMPT_TOKENS=2000        # Limit prompt size

# Restart API
docker-compose restart api

# When to use: Large conversation contexts identified
# Expected impact: TTFT reduces 20-40%
# Downside: Less conversation history context
```

**Option 3: Enable prompt caching (if not already enabled)**
```bash
# Check if prompt caching enabled
grep "PROMPT_CACHE" apps/api/.env

# If not enabled, add:
nano apps/api/.env
# Add:
# ENABLE_PROMPT_CACHE=true
# PROMPT_CACHE_TTL=3600  # 1 hour cache

# Restart API
docker-compose restart api

# When to use: Repetitive system prompts
# Expected impact: TTFT reduces 10-30% for cached prompts
# Downside: Stale prompts if changed frequently
```

**Option 4: Bypass router for critical intentions (emergency)**
```bash
# If router latency is bottleneck, temporarily use direct LLM routing
# This bypasses intelligent routing but ensures fast response

# Edit router configuration
nano apps/api/src/domains/agents/nodes/router_node_v3.py

# Add bypass logic:
# if intention in ["email_compose", "quick_question"]:  # Critical paths
#     return "general_assistant"  # Skip LLM-based routing

# Restart API
docker-compose restart api

# When to use: Router >50% of TTFT, emergency only
# Expected impact: Removes 300-500ms router latency
# Downside: Less accurate routing, potential quality issues
```

---

### Verification After Mitigation

```bash
# 1. Verify TTFT normalized
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le)) * 1000" | jq '.data.result[0].value[1]'
# Expected: <1000ms

# 2. Verify alert stopped firing
curl -s "http://localhost:9093/api/v2/alerts" | jq '.[] | select(.labels.alertname=="AgentsTTFTViolation") | .status.state'
# Expected: "inactive"

# 3. Test user-facing latency
time curl -N http://localhost:8000/api/agents/chat -X POST -H "Content-Type: application/json" -d '{"message":"Hello"}' --no-buffer | head -1
# Should show first chunk within 1 second

# 4. Check by intention (ensure all intentions improved)
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le, intention)) * 1000" | jq '.data.result[] | "\(.metric.intention): \(.value[1])ms"'
```

---

### Root Cause Fix (Permanent Solution - 1-4 hours)

**Fix 1: Optimize router prompt and model**

**File**: `apps/api/src/domains/agents/context/prompts.py`
```python
# BEFORE (verbose router prompt - 800 tokens):
ROUTER_SYSTEM_PROMPT = """
You are an intelligent routing system...
[300 lines of detailed instructions]
Available intentions: email_compose, calendar_manage, document_search...
[Detailed descriptions of each intention]
"""

# AFTER (optimized - 300 tokens):
ROUTER_SYSTEM_PROMPT = """
Route user queries to intentions:
- email: Email compose/send
- calendar: Schedule/event management
- docs: Document search/retrieval
- general: Other queries

Format: {"intention": "email", "confidence": 0.95}
"""
```

**Switch to faster model for router**:
```python
# apps/api/src/domains/agents/nodes/router_node_v3.py
class RouterNode:
    def __init__(self):
        # BEFORE: Using GPT-4 (slow but accurate)
        self.model = "gpt-4"

        # AFTER: Using GPT-3.5-turbo (fast, sufficient for routing)
        self.model = "gpt-3.5-turbo"
        # OR even better: Use fine-tuned model for routing
        # self.model = "ft:gpt-3.5-turbo:lia:router:abc123"
```

**Testing**:
```bash
# Load test router
docker-compose exec api python -c "
import asyncio
from src.domains.agents.nodes.router_node import RouterNode

async def test():
    router = RouterNode()
    messages = [{'role': 'user', 'content': 'Send email to John'}]
    start = asyncio.get_event_loop().time()
    result = await router.route(messages)
    duration = (asyncio.get_event_loop().time() - start) * 1000
    print(f'Router decision: {result} in {duration:.0f}ms')

asyncio.run(test())
"
# Target: <300ms
```

---

**Fix 2: Implement conversation context pruning**

**File**: `apps/api/src/domains/conversations/services/context_manager.py`
```python
from typing import List, Dict
import tiktoken

class ConversationContextManager:
    def __init__(self, max_tokens: int = 2000, max_messages: int = 20):
        self.max_tokens = max_tokens
        self.max_messages = max_messages
        self.encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")

    def prune_context(self, messages: List[Dict]) -> List[Dict]:
        """
        Prune conversation context to stay within token limits.
        Strategy: Keep system message + recent messages + summarize middle.
        """
        if len(messages) <= self.max_messages:
            # Check token count
            total_tokens = sum(len(self.encoder.encode(m['content'])) for m in messages)
            if total_tokens <= self.max_tokens:
                return messages  # Within limits, no pruning

        # Always keep system message (first message)
        system_message = messages[0] if messages[0]['role'] == 'system' else None
        user_assistant_messages = messages[1:] if system_message else messages

        # Keep most recent N messages
        recent_messages = user_assistant_messages[-self.max_messages:]

        # If still too many tokens, summarize older messages
        total_tokens = sum(len(self.encoder.encode(m['content'])) for m in recent_messages)
        if total_tokens > self.max_tokens:
            # Keep only last 10 messages (most relevant)
            recent_messages = recent_messages[-10:]

            # Add summary of pruned messages
            pruned_count = len(user_assistant_messages) - 10
            if pruned_count > 0:
                summary_message = {
                    'role': 'system',
                    'content': f'[{pruned_count} earlier messages summarized for context length]'
                }
                recent_messages.insert(0, summary_message)

        # Rebuild context
        pruned_context = []
        if system_message:
            pruned_context.append(system_message)
        pruned_context.extend(recent_messages)

        return pruned_context
```

**Integration**:
```python
# apps/api/src/domains/agents/nodes/planner_node_v3.py
from src.domains.conversations.services.context_manager import ConversationContextManager

class PlannerNode:
    def __init__(self):
        self.context_manager = ConversationContextManager(max_tokens=2000, max_messages=20)

    async def plan(self, state: AgentState):
        # Prune context before sending to LLM
        pruned_messages = self.context_manager.prune_context(state['messages'])

        # Call LLM with pruned context
        response = await self.llm.ainvoke(pruned_messages)
        ...
```

**Testing**:
```bash
# Test with long conversation
docker-compose exec api python -c "
from src.domains.conversations.services.context_manager import ConversationContextManager

manager = ConversationContextManager(max_tokens=2000, max_messages=20)
messages = [
    {'role': 'system', 'content': 'You are a helpful assistant'},
    *[{'role': 'user', 'content': f'Message {i}'} for i in range(100)]
]

pruned = manager.prune_context(messages)
print(f'Original: {len(messages)} messages')
print(f'Pruned: {len(pruned)} messages')
"
# Should show: Pruned: ~21 messages (system + 20 recent)
```

---

**Fix 3: Implement parallel router + LLM call (advanced)**

**Optimization**: Call router LLM and main LLM in parallel for certain queries.

**File**: `apps/api/src/domains/agents/graph.py`
```python
import asyncio

async def route_and_invoke_parallel(state: AgentState):
    """
    For simple queries, route and invoke LLM in parallel.
    Router result used for metrics/logging, LLM result sent to user.
    """
    # Check if query is simple (heuristic: <50 tokens, no context needed)
    if len(state['messages'][-1]['content']) < 200:
        # Parallel execution
        router_task = asyncio.create_task(router_node.route(state))
        llm_task = asyncio.create_task(general_assistant_node.invoke(state))

        # Await both
        router_result, llm_result = await asyncio.gather(router_task, llm_task)

        # Log router decision (for analytics)
        logger.info(f"Router: {router_result} (parallel mode)")

        return llm_result
    else:
        # Sequential (normal path for complex queries)
        router_result = await router_node.route(state)
        return await route_to_node(router_result, state)
```

**When to use**: After confirming router is bottleneck, for simple queries only.

**Expected impact**: TTFT reduces by router latency (300-500ms) for eligible queries.

---

**Fix 4: Use streaming-optimized LLM models**

**Recent models with better TTFT**:
- **GPT-3.5-turbo-16k** (2024): Improved streaming performance
- **Claude-3-Haiku** (Anthropic): Optimized for low latency (<500ms TTFT)
- **Gemini-1.5-Flash** (Google): Fast streaming (<400ms TTFT)

**Configuration**:
```bash
# apps/api/.env
OPENAI_MODEL=gpt-3.5-turbo-16k  # or
ANTHROPIC_MODEL=claude-3-haiku-20240307  # or
GOOGLE_MODEL=gemini-1.5-flash
```

**A/B Testing**:
```python
# Test different models
models_to_test = [
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k",
    "claude-3-haiku-20240307",
]

for model in models_to_test:
    # Measure TTFT for each model
    # Select fastest with acceptable quality
```

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **LangGraph Agents Observability** - `http://localhost:3000/d/agents-langgraph`
  - Panel: "Time to First Token (P50/P95/P99)" - TTFT distribution
  - Panel: "TTFT by Intention" - Breakdown by user intent
  - Panel: "Router Latency" - Router decision time

- **LLM Tokens & Cost** - `http://localhost:3000/d/llm-tokens-cost`
  - Panel: "Prompt Tokens Distribution" - Context size impact
  - Panel: "LLM API Latency" - External API performance

### Prometheus Queries

**TTFT P95 overall**:
```promql
histogram_quantile(0.95,
  sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le)
) * 1000
```

**TTFT P95 by intention**:
```promql
histogram_quantile(0.95,
  sum(rate(sse_time_to_first_token_seconds_bucket[5m])) by (le, intention)
) * 1000
```

**Router latency contribution**:
```promql
(histogram_quantile(0.95, router_decision_duration_seconds_bucket) /
 histogram_quantile(0.95, sse_time_to_first_token_seconds_bucket)) * 100
```

**LLM API latency**:
```promql
histogram_quantile(0.95, llm_api_duration_seconds_bucket) * 1000
```

---

## 📚 Related Runbooks

- **[AgentsRouterLatencyHigh.md](./AgentsRouterLatencyHigh.md)** - Router-specific latency issues
- **[LLMAPIFailureRateHigh.md](./LLMAPIFailureRateHigh.md)** - External LLM API issues
- **[AgentsStreamingErrorRateHigh.md](./AgentsStreamingErrorRateHigh.md)** - SSE streaming failures

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Cold Start Penalty
**Scenario**: First request after deployment has 2-3x higher TTFT.

**Prevention**: Implement warmup requests on deployment, pre-load models.

---

### Pattern 2: GPT-4 TTFT Degradation
**Scenario**: GPT-4 TTFT increases during peak hours (OpenAI congestion).

**Prevention**: Use GPT-3.5-turbo as fallback, monitor OpenAI status.

---

### Known Issue 1: Anthropic Claude Streaming Delay
**Problem**: Claude-3 has initial buffering delay (~500ms) before first token.

**Workaround**: Use Claude-3-Haiku (optimized for streaming) or add progress indicator.

---

## 🆘 Escalation

### When to Escalate

- [ ] TTFT >2000ms for >30 minutes (severe user impact)
- [ ] External LLM provider outage (no control)
- [ ] Architectural change needed (move to different LLM)
- [ ] SLA breach affecting >50% requests

### Escalation Path

**Level 1 - ML/AI Team Lead** (0-15 minutes)
**Level 2 - CTO** (15-30 minutes)

---

## 📝 Post-Incident Actions

- [ ] Create incident report
- [ ] Update TTFT monitoring dashboards
- [ ] Optimize router prompt (reduce tokens)
- [ ] Implement context pruning
- [ ] A/B test faster models
- [ ] Add TTFT SLA to service contract

---

## 📋 Incident Report Template

```markdown
# Incident: TTFT SLA Violation

**Date**: [YYYY-MM-DD]
**Duration**: [HH:MM]
**Severity**: Warning

## Root Cause
[LLM API latency / Router slow / Large context]

## Impact
- TTFT P95: [XXX]ms (target: <1000ms)
- Intentions affected: [list]
- User complaints: [count]

## Resolution
[Immediate: Model switch | Permanent: Context pruning]

## Action Items
- [ ] Optimize router prompt
- [ ] Implement context pruning
- [ ] Monitor TTFT by model
```

---

## 🔗 Additional Resources

- [OpenAI Streaming Best Practices](https://platform.openai.com/docs/guides/streaming)
- [Anthropic Claude Latency Optimization](https://docs.anthropic.com/claude/docs/streaming)
- [LangChain Streaming Guide](https://python.langchain.com/docs/how_to/streaming)

---

## 📅 Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-23
**Author**: ML/SRE Team

---

## ✅ Validation Checklist

- [x] Alert definition verified
- [x] TTFT measurement methodology confirmed
- [x] Mitigation steps tested
- [ ] Peer review completed

---

**End of Runbook**
