# HighConversationResetRate - Runbook

**Severity**: Warning
**Component**: Agents
**Impact**: Users losing conversation context frequently, poor UX
**SLA Impact**: Potential - Affects user experience quality

---

## 1. Alert Definition

**Alert Name**: `HighConversationResetRate`

**PromQL Query**:
```promql
(rate(conversation_resets_total[5m]) / rate(conversation_messages_total[5m])) * 100 > <<<ALERT_CONVERSATION_RESET_RATE_PERCENT>>>
```

**Thresholds**:
- **Production**: >10% reset rate (Warning - should be <5%)
- **Staging**: >15%
- **Development**: >20%

**Duration**: For 5 minutes

**Labels**:
```yaml
severity: warning
component: agents
alert_type: data_quality
impact: context_loss
```

**Annotations**:
```yaml
summary: "High conversation reset rate: {{ $value }}%"
description: "Conversations being reset at {{ $value }}% rate (threshold: <<<ALERT_CONVERSATION_RESET_RATE_PERCENT>>>%)"
```

---

## 2. Symptoms

### What Users See
- Agent "forgets" previous conversation context
- User has to re-explain context repeatedly
- "Start new conversation" triggered unintentionally
- Conversation history missing after refresh

### What Ops See
- `conversation_resets_total` metric increasing
- Database checkpoint deletions high
- User complaints about "forgetting" behavior

---

## 3. Possible Causes

### Cause 1: Automatic Reset on Error/Timeout (High Likelihood)
**Likelihood**: High (50%)

**Verification**:
```bash
# Check correlation between errors and resets
docker-compose logs api | grep -E "conversation_reset|ConversationError" | tail -50

# Check reset reasons in metrics
curl -s "http://localhost:9090/api/v1/query?query=sum by (reason) (rate(conversation_resets_total[5m]))" | jq -r '.data.result[] | "\(.metric.reason): \(.value[1])"'
```

---

### Cause 2: Session/Cookie Expiration (Medium Likelihood)
**Likelihood**: Medium (30%)

**Verification**:
```bash
# Check session duration
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.5,rate(session_duration_seconds_bucket[1h]))" | jq '.data.result[0].value[1]'

# Check cookie settings
grep -n "SESSION_TTL\|COOKIE_MAX_AGE" apps/api/.env
```

---

### Cause 3: Checkpoint Recovery Failures (Medium Likelihood)
**Likelihood**: Medium (25%)

**Verification**:
```bash
# Check checkpoint load errors
docker-compose logs api | grep -i "checkpoint.*load.*error\|checkpoint.*not found"

# Check database checkpoint integrity
docker-compose exec postgres psql -U lia -c "
SELECT COUNT(*) as invalid_checkpoints
FROM checkpoints
WHERE checkpoint_data IS NULL OR checkpoint_data = 'null'::jsonb;
"
```

---

## 4. Resolution Steps

### Immediate Mitigation

**Option 1: Increase session/checkpoint TTL**

**File**: `apps/api/.env`
```bash
SESSION_TTL_SECONDS=86400  # 24 hours instead of 1 hour
CHECKPOINT_RETENTION_DAYS=7  # Keep checkpoints longer
```

---

**Option 2: Disable automatic reset on errors**

**File**: `apps/api/src/domains/agents/services/conversation_orchestrator.py`
```python
async def handle_agent_error(conversation_id: str, error: Exception):
    """Handle errors without resetting conversation"""
    logger.error(f"Agent error in conversation {conversation_id}: {error}")

    # Don't reset, return error to user for retry
    # await reset_conversation(conversation_id)  # REMOVED

    return {
        "error": str(error),
        "retry": True,
        "conversation_preserved": True
    }
```

---

### Root Cause Fix

**Fix 1: Implement graceful degradation**

```python
async def load_conversation_state(conversation_id: str):
    """Load state with fallback to partial recovery"""
    try:
        # Try full checkpoint load
        return await checkpointer.aget(conversation_id)
    except CheckpointNotFoundError:
        logger.warning(f"Checkpoint not found for {conversation_id}, loading from messages")
        # Rebuild state from database messages
        messages = await get_conversation_messages(conversation_id)
        return rebuild_state_from_messages(messages)
    except Exception as e:
        logger.error(f"Checkpoint load failed for {conversation_id}: {e}")
        # Last resort: Return minimal valid state
        return {
            "conversation_id": conversation_id,
            "messages": [],
            "status": "recovered_partial"
        }
```

---

**Fix 2: Add conversation state persistence verification**

```python
async def save_checkpoint_with_verification(state, config):
    """Save and verify checkpoint"""
    await checkpointer.aput(state, config)

    # Verify saved correctly
    loaded = await checkpointer.aget(config)
    if loaded != state:
        logger.error(f"Checkpoint verification failed for {config['conversation_id']}")
        # Retry save
        await checkpointer.aput(state, config)
```

---

## 5. Related Dashboards & Queries

**Conversation reset rate**:
```promql
(rate(conversation_resets_total[5m]) / rate(conversation_messages_total[5m])) * 100
```

**Resets by reason**:
```promql
sum by (reason) (rate(conversation_resets_total[5m]))
```

---

## 6. Related Runbooks
- [CheckpointSaveSlowCritical.md](./CheckpointSaveSlowCritical.md) - Checkpoint persistence
- [HighErrorRate.md](./HighErrorRate.md) - Errors triggering resets

---

## 7. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
