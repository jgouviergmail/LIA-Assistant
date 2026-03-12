# AgentsRouterLowConfidenceHigh - Runbook

**Severity**: Warning
**Component**: Agents (LangGraph Router)
**Impact**: Poor routing quality, incorrect intent classification, suboptimal agent selection
**SLA Impact**: No (warning level) - Quality degradation but not service outage

---

## 📊 Alert Definition

**Alert Name**: `AgentsRouterLowConfidenceHigh`

**Prometheus Expression**:
```promql
(
  sum(rate(router_decisions_total{confidence_bucket="low"}[10m]))
  /
  sum(rate(router_decisions_total[10m]))
) * 100 > ${ALERT_AGENTS_ROUTER_LOW_CONFIDENCE_PERCENT}
```

**Threshold**:
- **Production**: >10% low confidence (ALERT_AGENTS_ROUTER_LOW_CONFIDENCE_PERCENT=10)
- **Staging**: >20% low confidence
- **Development**: >30% low confidence

**Confidence Bucket Definition**:
- **High confidence**: ≥0.8 (80%+) - Router is very certain
- **Medium confidence**: 0.6-0.8 (60-80%) - Router is reasonably certain
- **Low confidence**: <0.6 (<60%) - Router is uncertain, may misroute

**Firing Duration**: `for: 10m`

**Labels**:
- `severity`: warning
- `component`: agents
- `sla`: quality

---

## 🔍 Symptoms

### What Users See
- **Incorrect agent responses** - Email agent when user asks about calendar
- **Generic fallback responses** - Router defaults to general assistant
- **Repetitive clarification requests** - "Could you clarify what you need?"
- **Context misunderstanding** - Agent doesn't grasp user intent

### What Ops See
- **High low-confidence rate** - >10% router decisions with confidence <0.6
- **Increased fallback routing** - `router_fallback_total` metric elevated
- **Router reasoning unclear** - Logs show ambiguous reasoning
- **Intent distribution skewed** - Too many requests routed to "general"

---

## 🎯 Possible Causes

### 1. Ambiguous User Queries (High Likelihood - 65%)

**Description**: User queries lack clear intent signals, making classification difficult.

**How to Verify**:
```bash
# Check recent low-confidence router decisions
docker-compose logs api --since 30m | grep "router.*low.*confidence" | tail -20

# Extract user queries with low confidence
docker-compose logs api --since 30m | grep -E "router.*confidence.*0\.[0-5]" -B 5 | grep "user_message" | head -10

# Look for patterns:
# - Very short queries: "help", "yes", "ok"
# - Vague queries: "I need something", "can you assist?"
# - Multi-intent queries: "Send email and schedule meeting"
```

**Expected Output if This is the Cause**:
- Queries <5 words or <30 characters
- No clear action verbs (send, schedule, search, etc.)
- Mixed intents in single query

---

### 2. Insufficient Router Training / Prompt Context (Medium-High Likelihood - 55%)

**Description**: Router prompt lacks examples, clear intent definitions, or decision criteria.

**How to Verify**:
```bash
# Check router prompt size
grep -A 100 "ROUTER_SYSTEM_PROMPT" apps/api/src/domains/agents/context/prompts.py | wc -l

# Check if few-shot examples exist
grep -c "Example:" apps/api/src/domains/agents/context/prompts.py

# Analyze router prompt quality
cat apps/api/src/domains/agents/context/prompts.py | grep -A 50 "ROUTER_SYSTEM_PROMPT"

# Look for:
# - <5 examples per intention → Insufficient
# - No decision criteria → Vague instructions
# - Missing edge case handling
```

**Expected Output if This is the Cause**:
- Prompt <200 lines (should be 300-500 for quality routing)
- <3 examples per intent (should be 5-10)
- No explicit confidence threshold guidance

---

### 3. New/Unanticipated Use Cases (Medium Likelihood - 45%)

**Description**: Users requesting functionality not covered by existing intentions.

**How to Verify**:
```bash
# Check intent distribution
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(router_decisions_total[1h])) by (intention)" | jq '.data.result[] | "\(.metric.intention): \(.value[1])"'

# Check for high "general" or "unknown" routing
curl -s "http://localhost:9090/api/v1/query?query=rate(router_decisions_total{intention=\"general\"}[1h])" | jq '.data.result[0].value[1]'

# Analyze low-confidence router reasoning
docker-compose logs api --since 1h | grep -E "router.*reasoning" | grep -i "low\|uncertain\|unclear" | head -20
```

**Expected Output if This is the Cause**:
- "general" intent >40% of total (should be <20%)
- Router reasoning: "Does not match existing intentions clearly"
- Emerging patterns in user queries not covered by intents

---

### 4. Router Model Quality Degradation (Medium Likelihood - 40%)

**Description**: LLM model used for routing producing less confident classifications.

**How to Verify**:
```bash
# Check router model configuration
grep "ROUTER_MODEL\|ROUTER_LLM" apps/api/.env apps/api/src/

# Check if model recently changed
git log --since="7 days ago" --oneline -- apps/api/.env apps/api/src/domains/agents/nodes/router_node_v3.py | head -10

# Check LLM API error rate for router
docker-compose logs api --since 1h | grep "router.*llm.*error" | wc -l

# Check router response format issues
docker-compose logs api --since 1h | grep -E "router.*(parse|format|json)" | tail -20
```

**Expected Output if This is the Cause**:
- Recent model change (e.g., GPT-4 → GPT-3.5-turbo)
- LLM API errors during routing (>5%)
- JSON parsing failures (malformed router responses)

---

### 5. Conversation Context Confusion (Low-Medium Likelihood - 30%)

**Description**: Router receives conversation history causing confusion between current and past intents.

**How to Verify**:
```bash
# Check if router uses conversation context
grep -n "conversation\|history\|context" apps/api/src/domains/agents/nodes/router_node_v3.py | head -10

# Check message count sent to router
docker-compose logs api --since 30m | grep "router.*messages" | grep -oP "count=\K[0-9]+" | sort -n | tail -20

# Analyze context impact
docker-compose logs api --since 30m | grep -E "router.*(previous|last|earlier)" | head -10
```

**Expected Output if This is the Cause**:
- Router receives >5 messages (should only need current message)
- Logs mention "previous conversation" in reasoning
- Low confidence after context added

---

### 6. Edge Case / Multi-Intent Queries (Low Likelihood - 25%)

**Description**: User queries span multiple intentions or are genuinely ambiguous.

**How to Verify**:
```bash
# Find multi-intent patterns
docker-compose logs api --since 1h | grep -E "router.*confidence.*0\.[0-5]" -B 5 | grep "user_message" | grep -E "and|also|then|after"

# Examples:
# - "Send email and schedule meeting" → 2 intents
# - "Search docs then compose summary" → 2 intents

# Check router multi-intent handling
grep -A 20 "multi.*intent\|multiple.*intent" apps/api/src/domains/agents/nodes/router_node_v3.py
```

**Expected Output if This is the Cause**:
- Queries with "and", "also", "then" connectors
- No multi-intent decomposition logic in router

---

## 🔧 Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Check current low-confidence rate**
```bash
# Low confidence percentage
curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(router_decisions_total{confidence_bucket=\"low\"}[10m])) / sum(rate(router_decisions_total[10m]))) * 100" | jq '.data.result[0].value[1]'

# If >10% → ALERT threshold violated
```

**Step 2: Check intent distribution**
```bash
# Top intents by volume
curl -s "http://localhost:9090/api/v1/query?query=topk(5, sum(rate(router_decisions_total[10m])) by (intention))" | jq '.data.result[] | "\(.metric.intention): \(.value[1])"'

# Check if "general" dominates (should be <20%)
```

**Step 3: Sample low-confidence decisions**
```bash
# Recent low-confidence router logs
docker-compose logs api --since 10m | grep -E "router.*confidence.*0\.[0-5]" | tail -10

# Extract user queries
docker-compose logs api --since 10m | grep -E "router.*confidence.*0\.[0-5]" -B 3 | grep "user_message" | tail -10
```

---

### Deep Dive Investigation (5-10 minutes)

**Step 4: Analyze router reasoning**
```bash
# Get detailed router decisions with reasoning
docker-compose logs api --since 30m | grep "router_decision" | jq '.reasoning' | head -20

# Look for patterns:
# - "Unclear intent"
# - "Multiple possible intentions"
# - "Insufficient context"
# - "No matching intention"
```

**Step 5: Check confidence distribution**
```bash
# Confidence bucket distribution
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(router_decisions_total[1h])) by (confidence_bucket)" | jq '.data.result[] | "\(.metric.confidence_bucket): \(.value[1])"'

# Healthy distribution:
# high (>0.8): 70-80%
# medium (0.6-0.8): 15-25%
# low (<0.6): <10%
```

**Step 6: Test router directly**
```bash
# Test router with sample queries
docker-compose exec api python -c "
import asyncio
from src.domains.agents.nodes.router_node import RouterNode

async def test():
    router = RouterNode()

    test_queries = [
        'Send email to John about meeting',  # Should be high confidence → email
        'Schedule dentist appointment',       # Should be high confidence → calendar
        'help me',                           # Low confidence (ambiguous)
    ]

    for query in test_queries:
        messages = [{'role': 'user', 'content': query}]
        result = await router.route(messages)
        print(f'{query[:40]:40} → {result[\"intention\"]:15} (confidence: {result[\"confidence\"]:.2f})')

asyncio.run(test())
"
```

**Step 7: Check for emerging patterns**
```bash
# Group low-confidence queries by pattern
docker-compose logs api --since 1h | grep -E "router.*confidence.*0\.[0-5]" -B 3 | grep "user_message" | sort | uniq -c | sort -rn | head -10

# Identifies frequent low-confidence query types
```

---

## ✅ Resolution Steps

### Immediate Mitigation (<10 minutes)

**Option 1: Fallback to general assistant (safe default)**
```bash
# Configure router to use general assistant when confidence <0.6
nano apps/api/src/domains/agents/nodes/router_node_v3.py

# Add fallback logic:
# if result['confidence'] < 0.6:
#     logger.warning(f"Low confidence ({result['confidence']:.2f}), falling back to general")
#     return {'intention': 'general_assistant', 'confidence': result['confidence']}

# Restart API
docker-compose restart api

# When to use: Prevent incorrect routing
# Expected impact: Low-confidence rate metric improves (routes go to general)
# Downside: Doesn't fix root cause, general agent may not be optimal
```

**Option 2: Enable router debugging/explanation**
```bash
# Add detailed logging to understand low-confidence causes
nano apps/api/src/domains/agents/nodes/router_node_v3.py

# Add debug logging:
# if result['confidence'] < 0.7:
#     logger.warning(f"Router low confidence: {result}")
#     logger.debug(f"User query: {messages[-1]['content']}")
#     logger.debug(f"Reasoning: {result.get('reasoning', 'N/A')}")

# Restart API
docker-compose restart api

# When to use: Gather data for root cause analysis
# Expected impact: Better visibility into router decisions
```

**Option 3: Temporarily lower alert threshold (if false alarm)**
```bash
# If investigation shows low-confidence decisions are acceptable, adjust threshold
nano apps/api/.env.alerting.production

# Change:
# ALERT_AGENTS_ROUTER_LOW_CONFIDENCE_PERCENT=10 → ALERT_AGENTS_ROUTER_LOW_CONFIDENCE_PERCENT=15

# Reload AlertManager configuration
docker-compose restart prometheus

# When to use: ONLY if low confidence is acceptable for use case
# Expected impact: Alert stops firing
# Downside: May mask real quality issues
```

---

### Verification After Mitigation

```bash
# 1. Verify low-confidence rate normalized
curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(router_decisions_total{confidence_bucket=\"low\"}[10m])) / sum(rate(router_decisions_total[10m]))) * 100" | jq '.data.result[0].value[1]'
# Expected: <10%

# 2. Verify alert stopped firing
curl -s "http://localhost:9093/api/v2/alerts" | jq '.[] | select(.labels.alertname=="AgentsRouterLowConfidenceHigh") | .status.state'
# Expected: "inactive"

# 3. Check fallback rate not excessive
curl -s "http://localhost:9090/api/v1/query?query=rate(router_fallback_total[10m])" | jq '.data.result[0].value[1]'
# Expected: <0.05 (5% fallback rate)

# 4. Test sample queries
# Verify high-confidence for clear queries
```

---

### Root Cause Fix (Permanent Solution - 2-6 hours)

**Fix 1: Enhance router prompt with better examples and criteria**

**File**: `apps/api/src/domains/agents/context/prompts.py`

```python
# BEFORE (insufficient examples):
ROUTER_SYSTEM_PROMPT = """
You are a router. Classify user intent.

Intentions:
- email: Email operations
- calendar: Calendar operations
- general: Everything else

Return JSON: {"intention": "email", "confidence": 0.95}
"""

# AFTER (comprehensive with examples and criteria):
ROUTER_SYSTEM_PROMPT = """
You are an intelligent routing system. Analyze the user's query and classify their intention with high confidence.

# Available Intentions

## 1. EMAIL (email_compose, email_send, email_manage)
**Triggers**: compose, write, send, draft, reply, forward, email, message
**Examples**:
- "Send an email to John about the meeting"  → email_send (confidence: 0.98)
- "Draft a message to the team"              → email_compose (confidence: 0.95)
- "Reply to Sarah's email"                   → email_send (confidence: 0.92)
- "Show my unread emails"                    → email_manage (confidence: 0.90)

## 2. CALENDAR (calendar_schedule, calendar_view, calendar_manage)
**Triggers**: schedule, meeting, appointment, calendar, event, book, reschedule
**Examples**:
- "Schedule dentist appointment tomorrow"    → calendar_schedule (confidence: 0.97)
- "Show my calendar for next week"           → calendar_view (confidence: 0.94)
- "Cancel my 3pm meeting"                    → calendar_manage (confidence: 0.91)
- "When is my next appointment?"             → calendar_view (confidence: 0.89)

## 3. DOCUMENT_SEARCH (docs_search, docs_retrieve)
**Triggers**: search, find, lookup, document, file, retrieve, locate
**Examples**:
- "Find the Q4 budget document"              → docs_search (confidence: 0.96)
- "Search for contracts from last year"      → docs_search (confidence: 0.93)
- "Retrieve the project proposal"            → docs_retrieve (confidence: 0.90)

## 4. GENERAL_ASSISTANT (general)
**Use when**: Query doesn't clearly match above intentions
**Examples**:
- "What's the weather today?"                → general (confidence: 0.85)
- "Help me brainstorm ideas"                 → general (confidence: 0.80)
- "Explain machine learning"                 → general (confidence: 0.88)

# Confidence Guidelines

**High Confidence (≥0.8)**:
- Clear action verb matching intention triggers
- Specific object (email, meeting, document)
- Single, unambiguous intent

**Medium Confidence (0.6-0.8)**:
- Intent implied but not explicit
- Multiple possible interpretations
- Requires slight assumption

**Low Confidence (<0.6)**:
- Vague query ("help", "yes", "okay")
- Multiple intents in one query
- No clear action verb
- Ambiguous context

# Output Format

ALWAYS return valid JSON:
{
  "intention": "[intention_name]",
  "confidence": [0.0-1.0],
  "reasoning": "Brief explanation of decision"
}

# Special Cases

**Multi-Intent Queries**: Route to primary intent, note others in reasoning
Example: "Send email and schedule meeting" → email_send (primary), note calendar in reasoning

**Ambiguous Queries**: Route to general with low confidence (<0.6)
Example: "help me" → general (confidence: 0.3)

**Follow-up Context**: Consider if this is a follow-up (e.g., "yes" after question)
Use conversation context sparingly - focus on current message.
"""
```

**Testing**:
```bash
# Test enhanced prompt
docker-compose exec api python -c "
import asyncio
from src.domains.agents.nodes.router_node import RouterNode

async def test():
    router = RouterNode()

    test_cases = [
        ('Send email to John', 'email', 0.9),
        ('Schedule meeting tomorrow', 'calendar', 0.9),
        ('help', 'general', 0.4),  # Should have low confidence
    ]

    for query, expected_intent, expected_conf_min in test_cases:
        messages = [{'role': 'user', 'content': query}]
        result = await router.route(messages)
        actual_intent = result['intention']
        actual_conf = result['confidence']

        status = '✓' if actual_intent.startswith(expected_intent) and actual_conf >= expected_conf_min else '✗'
        print(f'{status} {query[:30]:30} → {actual_intent:15} (conf: {actual_conf:.2f}, expected: {expected_intent} ≥{expected_conf_min})')

asyncio.run(test())
"
```

---

**Fix 2: Implement multi-intent decomposition**

**File**: `apps/api/src/domains/agents/services/intent_decomposer.py` (create new)

```python
from typing import List, Dict
from src.infrastructure.llm import get_llm

class IntentDecomposer:
    """Handles queries with multiple intents"""

    async def decompose(self, query: str) -> List[Dict]:
        """
        Decompose multi-intent query into separate sub-queries.

        Example:
            Input: "Send email to John and schedule meeting tomorrow"
            Output: [
                {"query": "Send email to John", "intention": "email_send"},
                {"query": "Schedule meeting tomorrow", "intention": "calendar_schedule"}
            ]
        """
        # Check if multi-intent (heuristic: contains "and", "then", "also")
        multi_intent_indicators = [' and ', ' then ', ' also ', ' after that ']
        if not any(indicator in query.lower() for indicator in multi_intent_indicators):
            return [{"query": query, "intention": None}]  # Single intent

        # Use LLM to decompose
        llm = await get_llm()
        decompose_prompt = f"""
Decompose this multi-intent query into separate sub-queries:

Query: "{query}"

Return JSON array:
[
  {{"sub_query": "...", "intent_hint": "..."}},
  {{"sub_query": "...", "intent_hint": "..."}}
]
"""
        response = await llm.ainvoke([{"role": "user", "content": decompose_prompt}])
        sub_queries = json.loads(response.content)

        return sub_queries
```

**Integration**:
```python
# apps/api/src/domains/agents/nodes/router_node_v3.py
from src.domains.agents.services.intent_decomposer import IntentDecomposer

class RouterNode:
    def __init__(self):
        self.decomposer = IntentDecomposer()

    async def route(self, messages: List[Dict]) -> Dict:
        user_query = messages[-1]['content']

        # Check for multi-intent
        sub_queries = await self.decomposer.decompose(user_query)

        if len(sub_queries) > 1:
            # Multi-intent detected
            logger.info(f"Multi-intent query decomposed into {len(sub_queries)} sub-queries")
            # Route first sub-query, store others for sequential execution
            primary_intent = await self._classify(sub_queries[0]['sub_query'])
            primary_intent['multi_intent'] = True
            primary_intent['remaining_queries'] = sub_queries[1:]
            return primary_intent
        else:
            # Single intent
            return await self._classify(user_query)
```

---

**Fix 3: Add router confidence boosting with context**

**File**: `apps/api/src/domains/agents/nodes/router_node_v3.py`

```python
class RouterNode:
    async def route_with_context(self, messages: List[Dict], user_profile: Dict = None) -> Dict:
        """
        Route with additional context to boost confidence.

        Context sources:
        - User profile (preferences, history)
        - Conversation state (recent intentions)
        - Temporal context (time of day, day of week)
        """
        base_result = await self._classify(messages[-1]['content'])

        # Boost confidence with context signals
        confidence_boost = 0.0

        # 1. User profile signals
        if user_profile:
            # Example: User frequently uses email → boost email confidence
            if base_result['intention'].startswith('email'):
                email_frequency = user_profile.get('email_usage_frequency', 0)
                if email_frequency > 0.5:  # User uses email >50% of time
                    confidence_boost += 0.1

        # 2. Conversation context signals
        if len(messages) > 1:
            # Check if previous message was same intention
            # (likely continuation)
            prev_intention = messages[-2].get('intention')
            if prev_intention == base_result['intention']:
                confidence_boost += 0.15

        # 3. Temporal signals
        from datetime import datetime
        hour = datetime.now().hour
        if 9 <= hour <= 17:  # Business hours
            # Email/calendar more likely during work hours
            if base_result['intention'] in ['email', 'calendar']:
                confidence_boost += 0.05

        # Apply boost (cap at 0.98 to avoid overconfidence)
        base_result['confidence'] = min(base_result['confidence'] + confidence_boost, 0.98)
        base_result['confidence_boost'] = confidence_boost

        return base_result
```

---

**Fix 4: Implement router performance monitoring and A/B testing**

**File**: `apps/api/src/infrastructure/observability/metrics_router.py` (enhance)

```python
from prometheus_client import Histogram, Counter

# Add detailed confidence distribution
router_confidence_distribution = Histogram(
    'router_confidence_distribution',
    'Distribution of router confidence scores',
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
)

# Track router performance by query type
router_performance_by_query_length = Histogram(
    'router_performance_by_query_length',
    'Router confidence by query length',
    labelnames=['query_length_bucket'],  # <10 words, 10-30, >30
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Track router version for A/B testing
router_decisions_by_version = Counter(
    'router_decisions_by_version',
    'Router decisions by model version',
    labelnames=['version', 'intention', 'confidence_bucket']
)
```

**A/B Testing Framework**:
```python
# apps/api/src/domains/agents/nodes/router_node_v3.py
import random

class RouterNode:
    def __init__(self):
        self.router_versions = {
            'v1': self._route_v1,  # Current production router
            'v2': self._route_v2,  # Experimental enhanced router
        }

    async def route(self, messages: List[Dict]) -> Dict:
        # A/B test: 10% traffic to v2
        version = 'v2' if random.random() < 0.10 else 'v1'

        result = await self.router_versions[version](messages)
        result['router_version'] = version

        # Track metrics by version
        router_decisions_by_version.labels(
            version=version,
            intention=result['intention'],
            confidence_bucket=self._bucket_confidence(result['confidence'])
        ).inc()

        return result
```

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **LangGraph Agents Observability** - `http://localhost:3000/d/agents-langgraph`
  - Panel: "Router Confidence Distribution" - Histogram of confidence scores
  - Panel: "Low Confidence Rate" - Percentage <0.6
  - Panel: "Router Decisions by Intention" - Intent distribution

### Prometheus Queries

**Low confidence rate**:
```promql
(sum(rate(router_decisions_total{confidence_bucket="low"}[10m])) /
 sum(rate(router_decisions_total[10m]))) * 100
```

**Confidence distribution**:
```promql
sum(rate(router_decisions_total[10m])) by (confidence_bucket)
```

**Intent distribution**:
```promql
topk(10, sum(rate(router_decisions_total[10m])) by (intention))
```

---

## 📚 Related Runbooks

- **[AgentsRouterLatencyHigh.md](./AgentsRouterLatencyHigh.md)** - Router performance issues
- **[AgentsTTFTViolation.md](./AgentsTTFTViolation.md)** - Router latency impacts TTFT

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Ambiguous "Help" Queries
**Scenario**: Users ask "help" without context → Low confidence.

**Prevention**: Implement clarification prompts, ask follow-up questions.

---

### Pattern 2: New Feature Requests
**Scenario**: Users ask for features not yet implemented → Router uncertain.

**Prevention**: Add "feature_request" intention, route to feedback collection.

---

### Known Issue 1: GPT-3.5-turbo Confidence Scores
**Problem**: GPT-3.5-turbo returns lower confidence than GPT-4 for same queries.

**Workaround**: Calibrate confidence thresholds per model, or use GPT-4 for routing.

---

## 🆘 Escalation

### When to Escalate

- [ ] Low confidence >20% for >1 hour (severe quality issue)
- [ ] Router performance degradation after deployment
- [ ] Requires new intentions (product decision)

### Escalation Path

**Level 1 - ML/AI Team Lead** (0-15 minutes)
**Level 2 - Product Manager** (15-30 minutes) - for new intention discussions

---

## 📝 Post-Incident Actions

- [ ] Create incident report
- [ ] Analyze low-confidence query patterns
- [ ] Enhance router prompt with examples
- [ ] Consider new intentions if needed
- [ ] Implement router A/B testing framework

---

## 📋 Incident Report Template

```markdown
# Incident: Router Low Confidence High

**Date**: [YYYY-MM-DD]
**Duration**: [HH:MM]

## Root Cause
[Ambiguous queries / Insufficient examples / New use cases]

## Impact
- Low confidence rate: [XX]%
- Intentions affected: [list]
- User experience: [description]

## Resolution
[Prompt enhancement / Fallback logic / New intentions]

## Action Items
- [ ] Enhance router prompt
- [ ] Add monitoring for query patterns
- [ ] A/B test router improvements
```

---

## 🔗 Additional Resources

- [LangChain Router Patterns](https://python.langchain.com/docs/how_to/routing)
- [OpenAI Function Calling Best Practices](https://platform.openai.com/docs/guides/function-calling)

---

## 📅 Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-23
**Author**: ML Team

---

## ✅ Validation Checklist

- [x] Alert definition verified
- [x] Confidence thresholds documented
- [x] Mitigation steps tested
- [ ] Peer review completed

---

**End of Runbook**
