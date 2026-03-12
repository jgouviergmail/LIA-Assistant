# PKCEValidationFailures - Runbook

**Severity**: Warning
**Component**: Authentication
**Impact**: User authentication failures, potential security breach attempts
**SLA Impact**: Yes - Affects user login/authorization

---

## 1. Alert Definition

**Alert Name**: `PKCEValidationFailures`

**PromQL Query**:
```promql
(rate(pkce_validation_failures_total[5m]) / rate(pkce_validation_attempts_total[5m])) * 100 > <<<ALERT_PKCE_VALIDATION_FAILURE_RATE_PERCENT>>>
```

**Thresholds**:
- **Production**: >5% failure rate (Warning - should be <1%)
- **Staging**: >10% failure rate
- **Development**: >20% failure rate

**Duration**: For 5 minutes

**Labels**:
```yaml
severity: warning
component: authentication
alert_type: security
impact: auth_failures
```

**Annotations**:
```yaml
summary: "PKCE validation failures high: {{ $value }}%"
description: "PKCE validation failing at {{ $value }}% (threshold: <<<ALERT_PKCE_VALIDATION_FAILURE_RATE_PERCENT>>>%)"
```

---

## 2. Symptoms

### What Users See
- "Invalid authorization code" error during OAuth flow
- Repeated redirects to Google login without success
- "Authentication failed, please try again" messages
- Unable to connect Google services (Gmail, Contacts, Calendar)

### What Ops See
- `pkce_validation_failures_total` metric increasing
- OAuth callback errors in API logs
- `code_verifier` mismatch errors
- Redis cache misses for PKCE state

---

## 3. Possible Causes

### Cause 1: PKCE State Not Persisted (Redis/Session Issue) (High Likelihood)
**Description**: `code_verifier` stored in Redis/session expires or is lost before OAuth callback.

**Likelihood**: High (50%) - Common with session/cache issues

**Verification**:
```bash
# Check Redis connectivity
docker-compose exec redis redis-cli ping

# Check Redis memory usage (eviction policy)
docker-compose exec redis redis-cli info memory | grep -E "used_memory|maxmemory|evicted_keys"

# Check PKCE state TTL in Redis
docker-compose exec redis redis-cli --scan --pattern "pkce:*" | head -5
docker-compose exec redis redis-cli ttl "pkce:[state_value]"

# Should be >300 seconds (5 minutes), not expired

# Check logs for state storage
docker-compose logs api | grep "pkce" | grep -i "store\|save"
```

---

### Cause 2: Clock Skew Between Client and Server (Medium Likelihood)
**Description**: Client/server time mismatch causes state expiration or timestamp validation failures.

**Likelihood**: Medium (30%)

**Verification**:
```bash
# Check server time
docker-compose exec api date -u

# Compare to NTP server
ntpdate -q pool.ntp.org

# Check time difference (should be <10 seconds)

# Check OAuth state expiration logic
grep -n "expires_at\|created_at" apps/api/src/domains/auth/ -r
```

---

### Cause 3: Multiple Concurrent OAuth Flows (Race Condition) (Medium Likelihood)
**Description**: User opens multiple tabs, starts multiple OAuth flows, code_verifier gets overwritten.

**Likelihood**: Medium (25%)

**Verification**:
```bash
# Check for duplicate state values
docker-compose logs api | grep "pkce_validation" | grep -o "state=[a-zA-Z0-9]*" | sort | uniq -d

# Check if state is uniquely keyed
grep -n "state.*code_verifier" apps/api/src/domains/auth/ -r
```

---

### Cause 4: Malicious/Invalid Authorization Attempts (Low-Medium Likelihood)
**Description**: Attackers attempting to replay authorization codes or brute-force PKCE challenges.

**Likelihood**: Low-Medium (20%) - Security concern

**Verification**:
```bash
# Check for repeated failures from same IP
docker-compose logs api | grep "pkce_validation_failed" | grep -o "ip=[0-9.]*" | sort | uniq -c | sort -nr | head -10

# Suspicious: >10 failures from single IP in short time

# Check for invalid code_verifier patterns
docker-compose logs api | grep "pkce.*invalid" | tail -20
```

---

## 4. Diagnostic Steps

### Quick Health Check (<2 minutes)

**Step 1: Check current failure rate**
```bash
# Calculate failure rate
curl -s "http://localhost:9090/api/v1/query?query=(rate(pkce_validation_failures_total[5m])/rate(pkce_validation_attempts_total[5m]))*100" | jq '.data.result[0].value[1]'

# >5% = Warning, >10% = Critical
```

**Step 2: Check Redis availability**
```bash
docker-compose ps redis
docker-compose exec redis redis-cli ping
# Should return "PONG"
```

**Step 3: Check recent failure logs**
```bash
docker-compose logs api --tail=50 | grep -i "pkce\|oauth\|authorization"
```

---

### Deep Dive Analysis (5-10 minutes)

**Step 4: Analyze failure patterns**
```bash
# Extract failure reasons
docker-compose logs api | grep "pkce_validation_failed" | jq -r '.reason' | sort | uniq -c | sort -nr

# Common reasons:
# - "state_not_found" → Redis expiration
# - "verifier_mismatch" → Storage corruption or attack
# - "expired" → TTL too short or clock skew
```

**Step 5: Inspect Redis PKCE state**
```bash
# List all PKCE states
docker-compose exec redis redis-cli --scan --pattern "pkce:*"

# Check a specific state
docker-compose exec redis redis-cli get "pkce:[state_value]"

# Should contain JSON with code_verifier, created_at, expires_at

# Check eviction policy
docker-compose exec redis redis-cli config get maxmemory-policy
# Should be "allkeys-lru" or "volatile-ttl", NOT "noeviction"
```

**Step 6: Test OAuth flow manually**
```bash
# Initiate OAuth flow
curl -v "http://localhost:8000/api/auth/google/authorize"
# Extract state parameter from redirect URL

# Check if state exists in Redis
docker-compose exec redis redis-cli get "pkce:[state_from_url]"

# Simulate callback (use valid authorization code from Google)
curl -v "http://localhost:8000/api/auth/google/callback?code=[auth_code]&state=[state]"
```

---

## 5. Resolution Steps

### Immediate Mitigation

**Option 1: Increase PKCE state TTL (Fastest - 1 minute)**

**File**: `apps/api/.env`
```bash
# Increase from 300 to 600 seconds (10 minutes)
PKCE_STATE_TTL_SECONDS=600
```

**Restart**:
```bash
docker-compose restart api
```

**When to use**: If failures correlate with slow OAuth flows (users taking >5min to authorize).

---

**Option 2: Fix Redis eviction policy (Fast - 2 minutes)**

```bash
# Change to volatile-ttl (only evict keys with TTL)
docker-compose exec redis redis-cli config set maxmemory-policy volatile-ttl

# Persist configuration
docker-compose exec redis redis-cli config rewrite
```

**When to use**: If Redis is evicting PKCE state keys due to memory pressure.

---

**Option 3: Rate limit OAuth attempts per IP (Medium - 5 minutes)**

**File**: `apps/api/src/domains/auth/router.py`
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.get("/google/authorize")
@limiter.limit("5/minute")  # Max 5 OAuth flows per IP per minute
async def google_authorize(request: Request):
    # ... existing code
```

**When to use**: If seeing repeated failures from same IPs (potential attack).

---

### Root Cause Fix

**Fix 1: Use database-backed session storage (instead of Redis)**

**File**: `apps/api/src/infrastructure/auth/pkce_store.py`
```python
from sqlalchemy import Column, String, DateTime, Text
from src.infrastructure.database import Base

class PKCEState(Base):
    __tablename__ = "pkce_states"

    state = Column(String(255), primary_key=True)
    code_verifier = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    user_ip = Column(String(45))  # For audit

class DatabasePKCEStore:
    async def save_state(self, state: str, code_verifier: str, ttl: int):
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        pkce_state = PKCEState(
            state=state,
            code_verifier=code_verifier,
            created_at=datetime.utcnow(),
            expires_at=expires_at
        )
        session.add(pkce_state)
        await session.commit()

    async def get_verifier(self, state: str) -> Optional[str]:
        result = await session.execute(
            select(PKCEState).where(
                PKCEState.state == state,
                PKCEState.expires_at > datetime.utcnow()
            )
        )
        pkce_state = result.scalar_one_or_none()
        if pkce_state:
            # Delete after retrieval (one-time use)
            await session.delete(pkce_state)
            await session.commit()
            return pkce_state.code_verifier
        return None
```

**Migration**:
```bash
docker-compose exec api alembic revision --autogenerate -m "Add PKCE state table"
docker-compose exec api alembic upgrade head
```

---

**Fix 2: Implement state uniqueness per session**

**File**: `apps/api/src/domains/auth/oauth_flow_handler.py`
```python
import secrets

def generate_pkce_state(session_id: str) -> str:
    """Generate unique state per user session"""
    random_part = secrets.token_urlsafe(32)
    # Include session_id to prevent cross-session attacks
    state = f"{session_id}:{random_part}"
    return state

def validate_pkce_state(state: str, session_id: str) -> bool:
    """Validate state belongs to current session"""
    if ":" not in state:
        return False
    state_session_id, _ = state.split(":", 1)
    return state_session_id == session_id
```

---

**Fix 3: Add comprehensive PKCE validation logging**

**File**: `apps/api/src/infrastructure/observability/metrics.py`
```python
from prometheus_client import Counter

pkce_validation_failures = Counter(
    'pkce_validation_failures_total',
    'PKCE validation failures',
    ['reason', 'user_agent', 'ip_prefix']  # Labels for debugging
)

# In validation code
def validate_pkce(state, code_verifier):
    try:
        stored_verifier = get_verifier_from_redis(state)
        if not stored_verifier:
            pkce_validation_failures.labels(
                reason='state_not_found',
                user_agent=request.headers.get('User-Agent', 'unknown')[:50],
                ip_prefix=get_ip_prefix(request.client.host)
            ).inc()
            raise PKCEValidationError("State not found")

        if stored_verifier != code_verifier:
            pkce_validation_failures.labels(
                reason='verifier_mismatch',
                user_agent=request.headers.get('User-Agent', 'unknown')[:50],
                ip_prefix=get_ip_prefix(request.client.host)
            ).inc()
            raise PKCEValidationError("Verifier mismatch")

        return True
    except Exception as e:
        logger.error("PKCE validation failed", extra={
            "state": state[:10] + "...",  # Partial for privacy
            "error": str(e),
            "user_agent": request.headers.get('User-Agent'),
            "ip": request.client.host
        })
        raise
```

---

**Fix 4: Implement automatic cleanup of expired states**

**File**: `infrastructure/observability/scripts/cleanup_expired_pkce.sh`
```bash
#!/bin/bash
# Cron job to clean expired PKCE states (if using database storage)

docker-compose exec -T postgres psql -U lia -c "
DELETE FROM pkce_states WHERE expires_at < NOW();
"

echo "[$(date)] Cleaned expired PKCE states"
```

**Crontab**:
```bash
# Run every hour
0 * * * * /path/to/cleanup_expired_pkce.sh
```

---

## 6. Related Dashboards & Queries

### Prometheus Queries

**PKCE validation failure rate**:
```promql
(rate(pkce_validation_failures_total[5m]) / rate(pkce_validation_attempts_total[5m])) * 100
```

**Failures by reason**:
```promql
sum by (reason) (rate(pkce_validation_failures_total[5m]))
```

**Failures by IP prefix**:
```promql
topk(10, sum by (ip_prefix) (rate(pkce_validation_failures_total[1h])))
```

---

## 7. Related Runbooks
- [HighErrorRate.md](./HighErrorRate.md) - May include auth errors
- None specific (authentication is isolated domain)

---

## 8. Common Patterns

### Pattern 1: Mobile App OAuth Timeout
**Scenario**: Mobile users get distracted, return >5min later, PKCE state expired.

**Detection**: Failures spike at 5min intervals after authorization initiation.

**Fix**: Increase PKCE_STATE_TTL to 15 minutes for mobile clients.

---

### Pattern 2: Browser Extension Interference
**Scenario**: Privacy extensions block cookies/storage, state not persisted.

**Detection**: Failures from specific user agents (Firefox+Privacy Badger).

**Fix**: Provide clear error message instructing users to allow cookies for auth flow.

---

## 9. Security Considerations

**IMPORTANT**: PKCE is a security mechanism (RFC 7636). Do not:
- Disable PKCE validation to "fix" high failure rate
- Log full `code_verifier` values (security risk)
- Increase TTL beyond 15 minutes (replay attack window)
- Allow same state to be reused (one-time use only)

**Monitoring for attacks**:
```bash
# Alert if >100 failures from single IP in 5min
(sum by (ip_prefix) (rate(pkce_validation_failures_total[5m])) > 20)
```

---

## 10. Escalation

### When to Escalate
- Failure rate >20% (indicates systemic issue)
- Evidence of coordinated attack (many IPs, same pattern)
- Production auth completely broken (>50% failure)

### Escalation Path
1. **Level 1 - Security Team** (0-15min) - For potential security incidents
2. **Level 2 - Infrastructure Lead** (15-30min) - For Redis/database issues
3. **Level 3 - CTO** (30min+) - For business impact decisions

---

## 11. Runbook Metadata

**Version**: 1.0
**Last Updated**: 2025-11-22
**Author**: SRE Team
