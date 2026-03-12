# AgentsStreamingErrorRateHigh - Runbook

**Severity**: Warning
**Component**: Agents
**Impact**: Degraded streaming UX, users see incomplete/broken responses
**SLA Impact**: Potential - Affects user experience quality

---

## 1. Alert Definition

**Alert Name**: `AgentsStreamingErrorRateHigh`

**PromQL Query**:
```promql
(rate(agent_streaming_errors_total[5m]) / rate(agent_streaming_requests_total[5m])) * 100 > <<<ALERT_AGENTS_STREAMING_ERROR_RATE_PERCENT>>>
```

**Thresholds**:
- **Production**: >3% error rate (Warning)
- **Staging**: >5%
- **Development**: >10%

**Duration**: For 5 minutes

**Labels**:
```yaml
severity: warning
component: agents
alert_type: streaming
impact: ux_degradation
```

**Annotations**:
```yaml
summary: "Agent streaming error rate high: {{ $value }}%"
description: "Streaming errors at {{ $value }}% (threshold: <<<ALERT_AGENTS_STREAMING_ERROR_RATE_PERCENT>>>%)"
```

---

## 2. Symptoms

### What Users See
- Responses stop mid-sentence
- "Connection lost" or "Streaming error" messages
- Page shows loading indicator indefinitely
- Partial responses without completion

### What Ops See
- `agent_streaming_errors_total` metric increasing
- WebSocket/SSE connection failures in logs
- Client timeouts in streaming endpoints

---

## 3. Possible Causes

### Cause 1: LLM API Streaming Interruption (High Likelihood)
**Likelihood**: High (50%)

**Verification**:
```bash
# Check LLM streaming errors
docker-compose logs api | grep -i "streaming.*error\|anthropic.*stream"

# Check LLM API latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(llm_api_latency_seconds_bucket[5m]))" | jq '.data.result[0].value[1]'
```

---

### Cause 2: Client Connection Timeout (Medium Likelihood)
**Likelihood**: Medium (30%)

**Verification**:
```bash
# Check streaming request duration
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket{path=~\".*stream.*\"}[5m]))" | jq '.data.result[0].value[1]'

# >30s indicates slow streaming
```

---

### Cause 3: Network Instability (Low-Medium Likelihood)
**Likelihood**: Low-Medium (20%)

**Verification**:
```bash
# Check container network errors
docker stats lia_api_1 --no-stream --format "table {{.Container}}\t{{.NetIO}}"
```

---

## 4. Resolution Steps

### Immediate Mitigation

**Option 1: Implement streaming error recovery**

**File**: `apps/api/src/domains/agents/services/streaming_handler.py`
```python
async def stream_with_retry(messages):
    """Retry streaming on failure"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with client.messages.stream(
                model="claude-3-sonnet-20240229",
                messages=messages,
                max_tokens=2000
            ) as stream:
                async for text in stream.text_stream:
                    yield text
            break  # Success
        except Exception as e:
            logger.warning(f"Streaming error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                yield "\n\n[Error: Unable to complete response. Please try again.]"
                raise
            await asyncio.sleep(1)  # Brief pause before retry
```

---

**Option 2: Increase client timeout**

**File**: `apps/api/src/infrastructure/llm/client.py`
```python
client = Anthropic(
    api_key=settings.anthropic_api_key,
    timeout=httpx.Timeout(60.0, read=120.0)  # Increase read timeout for streaming
)
```

---

### Root Cause Fix

**Fix 1: Add heartbeat/keepalive to streaming**

**File**: `apps/api/src/domains/agents/api/router.py`
```python
from fastapi.responses import StreamingResponse

async def stream_agent_response(conversation_id: str):
    async def generate():
        last_chunk_time = time.time()

        async for chunk in agent_stream(conversation_id):
            yield f"data: {chunk}\n\n"
            last_chunk_time = time.time()

            # Send keepalive every 15s if no data
            if time.time() - last_chunk_time > 15:
                yield ": keepalive\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## 5. Related Dashboards & Queries

**Streaming error rate**:
```promql
(rate(agent_streaming_errors_total[5m]) / rate(agent_streaming_requests_total[5m])) * 100
```

---

## 6. Related Runbooks
- [LLMAPIFailureRateHigh.md](./LLMAPIFailureRateHigh.md) - LLM API issues
- [CriticalLatencyP99.md](./CriticalLatencyP99.md) - Slow responses

---

## 7. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
