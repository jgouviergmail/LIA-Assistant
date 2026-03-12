# LLMAPIFailureRateHigh - Runbook

**Severity**: critical
**Component**: llm
**Impact**: Agents ne peuvent pas générer réponses, fonctionnalité core indisponible pour utilisateurs
**SLA Impact**: Yes - Breaches availability + functionality SLA, agents complètement hors service

---

## 📊 Alert Definition

**Alert Name**: `LLMAPIFailureRateHigh`

**Prometheus Expression**:
```promql
sum(rate(llm_api_calls_total{status="error"}[5m]))
/
sum(rate(llm_api_calls_total[5m])) > <<< ALERT_LLM_API_FAILURE_RATE_PERCENT >>>
```

**Threshold**:
- **Production**: 0.03 (3% - stricter than default for core functionality)
- **Staging**: 0.08 (8% - relaxed for testing)
- **Development**: 0.30 (30% - very relaxed for experimentation)

**Firing Duration**: `for: 5m`

**Labels**:
- `severity`: critical
- `component`: llm
- `type`: availability

**Related Alerts**:
- `LLMAPISuccessRateLow` (inverse metric, success <95%)
- `HighErrorRate` (cascading effect - LLM failures → API errors)

---

## 🔍 Symptoms

### What Users See
- Agents ne répondent pas aux questions
- Messages "Sorry, I'm having trouble generating a response"
- Chat conversations bloquent à "Thinking..."
- Timeouts après 30-60 secondes d'attente
- Fonctionnalités contacts/emails search ne fonctionnent pas (agents-powered)
- Erreurs "Service temporarily unavailable"

### What Ops See
- Métrique `llm_api_calls_total{status="error"}` en spike
- Alert `LLMAPIFailureRateHigh` firing dans AlertManager
- Souvent co-firing avec `HighErrorRate` (LLM errors → API 500)
- Logs API: `AnthropicAPIError: 429 Too Many Requests` ou `503 Service Unavailable`
- Logs API: `httpx.TimeoutException: Request timeout`
- Grafana panel "LLM API Errors" rouge
- Panel "Agent Response Success Rate" chute brutalement

---

## 🎯 Possible Causes

### 1. Anthropic API Outage / Degradation

**Likelihood**: **Medium** (external dependency, hors de notre contrôle)

**Description**:
Anthropic Claude API connaît outage ou dégradation performance. Leur infrastructure est généralement très fiable (99.9%+ uptime) mais incidents arrivent. Souvent annoncés sur status page.

**How to Verify**:
```bash
# 1. Check Anthropic status page
curl -s https://status.anthropic.com/api/v2/status.json | jq '{status: .status.description, updated: .page.updated_at}'

# 2. Vérifier si incident actif
curl -s https://status.anthropic.com/api/v2/incidents/unresolved.json | jq '.incidents[] | {name, status, impact, created_at}'

# 3. Test direct API Anthropic (hors de notre app)
curl -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-3-sonnet-20240229",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "test"}]
  }'

# 4. Vérifier latency API dans nos métriques
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(llm_api_latency_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'
```

**Expected Output if This is the Cause**:
```json
// Status page montre problème
{
  "status": "Partial Outage",
  "updated": "2025-11-22T10:30:00Z"
}

// Incident actif
{
  "name": "Elevated Error Rates",
  "status": "investigating",
  "impact": "major",
  "created_at": "2025-11-22T10:15:00Z"
}

// Test direct API échoue
{"error": {"type": "internal_server_error", "message": "Service temporarily unavailable"}}

// Latency élevée (>10s)
"12.5"
```

---

### 2. Rate Limiting / Quota Exceeded

**Likelihood**: **High** (cause #1 si pas d'outage Anthropic)

**Description**:
Dépassement limites Anthropic:
- **Tier-based rate limits**: 50-5000 requests/min selon tier
- **Token quotas**: Budget tokens/jour
- **Concurrent requests**: Max connections simultanées

LIA peut spike requests lors de pics trafic (marketing campaigns, batch jobs).

**How to Verify**:
```bash
# 1. Vérifier logs pour rate limit errors
docker-compose logs api --since=15m | grep -i "anthropic" | grep -i "rate\|429\|quota"

# 2. Vérifier métriques request rate
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_api_calls_total[1m])*60" | jq '.data.result[0].value[1]'

# 3. Comparer avec tier limits (check Anthropic console)
# Tier 1: 50 req/min
# Tier 2: 1000 req/min
# Tier 3: 2000 req/min
# Enterprise: 5000+ req/min

# 4. Vérifier token consumption rate
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_tokens_consumed_total[5m])*60" | jq '.data.result[0].value[1]'

# 5. Check Anthropic console pour usage actuel
# https://console.anthropic.com/settings/usage
```

**Expected Output if This is the Cause**:
```
# Logs montrent 429 errors
2025-11-22 10:30:15 ERROR AnthropicAPIError: 429 Too Many Requests
Response headers: {'retry-after': '60', 'x-ratelimit-remaining': '0'}

# Request rate dépasse tier limit
"65.3"  # >50 req/min (Tier 1 limit)

# Token consumption rate très élevé
"150000"  # 150K tokens/min
```

---

### 3. API Key Invalid / Expired

**Likelihood**: **Low** (sauf rotation récente)

**Description**:
API key Anthropic invalide, expirée, ou révoquée. Peut arriver après:
- Rotation manuelle keys (nouveau key pas déployé)
- Key révoquée pour sécurité (leak détecté)
- Billing issue (payment failed → key suspended)

**How to Verify**:
```bash
# 1. Vérifier logs pour auth errors
docker-compose logs api --since=30m | grep -i "anthropic" | grep -i "401\|unauthorized\|authentication\|invalid.*key"

# 2. Test API key actuelle
ANTHROPIC_API_KEY=$(docker-compose exec api printenv ANTHROPIC_API_KEY)
curl -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model": "claude-3-sonnet-20240229", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}'

# 3. Vérifier env var chargée correctement
docker-compose exec api printenv | grep ANTHROPIC

# 4. Check Anthropic console billing status
# https://console.anthropic.com/settings/billing
```

**Expected Output if This is the Cause**:
```
# Logs 401 Unauthorized
ERROR: AnthropicAPIError: 401 Unauthorized - Invalid API key

# Test direct échoue
{"error": {"type": "authentication_error", "message": "Invalid API key"}}

# Env var manquante ou incorrecte
ANTHROPIC_API_KEY=sk-ant-api03-... # Verify starts with sk-ant-
```

---

### 4. Network / Connectivity Issues

**Likelihood**: **Low-Medium**

**Description**:
Problèmes réseau entre notre infra et Anthropic:
- DNS resolution failure
- Firewall blocking outbound HTTPS
- Proxy misconfiguration
- SSL certificate issues
- Network partition

**How to Verify**:
```bash
# 1. Test DNS resolution
docker-compose exec api nslookup api.anthropic.com

# 2. Test HTTPS connectivity
docker-compose exec api curl -I https://api.anthropic.com

# 3. Vérifier logs network errors
docker-compose logs api --since=15m | grep -i "connection\|timeout\|network\|dns"

# 4. Test depuis host (hors container)
curl -I https://api.anthropic.com

# 5. Vérifier firewall rules
# (dépend de l'infrastructure - cloud provider, VPC, etc.)
```

**Expected Output if This is the Cause**:
```
# DNS fail
;; connection timed out; no servers could be reached

# Connection refused
curl: (7) Failed to connect to api.anthropic.com port 443: Connection refused

# Logs timeout
httpx.TimeoutException: timed out waiting for server response
```

---

### 5. Client-Side Timeout Configuration Too Aggressive

**Likelihood**: **Medium**

**Description**:
Timeout configuré dans notre client Anthropic trop court. Anthropic peut prendre 10-30s pour réponses longues (streaming, large context). Si timeout client = 5s → faux positifs.

**How to Verify**:
```bash
# 1. Vérifier timeout config dans code
grep -r "timeout\|Timeout" apps/api/src/infrastructure/llm/ --include="*.py" -A 2 -B 2

# 2. Vérifier métriques latency réelle API
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(llm_api_latency_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'

# 3. Comparer avec timeout configuré
# Si P99 latency ≈ timeout → timeout trop court

# 4. Vérifier logs pour timeout vs real errors
docker-compose logs api --since=30m | grep -c "TimeoutError"
docker-compose logs api --since=30m | grep -c "AnthropicAPIError.*50"
```

**Expected Output if This is the Cause**:
```python
# Code shows aggressive timeout
client = Anthropic(
    api_key=settings.ANTHROPIC_API_KEY,
    timeout=5.0  # ← Trop court!
)

# P99 latency proche de timeout
"4.8"  # seconds (presque 5s timeout)

# Beaucoup de TimeoutError
25  # timeout errors
3   # real 5xx errors
```

---

## 🔧 Diagnostic Steps

### Quick Health Check (< 2 minutes)

**Objectif**: Identifier rapidement si Anthropic down ou notre problème.

```bash
# 1. Check Anthropic status page
curl -s https://status.anthropic.com/api/v2/status.json | jq '.status.description'

# 2. Vérifier error rate actuel
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(llm_api_calls_total{status=\"error\"}[5m]))/sum(rate(llm_api_calls_total[5m]))" | jq '.data.result[0].value[1]'

# 3. Vérifier logs récents pour error type
docker-compose logs api --tail=100 | grep "AnthropicAPIError" | tail -10

# 4. Test rapide API Anthropic direct
curl -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $(docker-compose exec api printenv ANTHROPIC_API_KEY | tr -d '\r')" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-sonnet-20240229","max_tokens":10,"messages":[{"role":"user","content":"test"}]}'

# 5. Check si co-firing avec HighErrorRate
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.labels.alertname=="HighErrorRate") | .status.state'
```

**Interprétation**:
- Status = "All Systems Operational" + test API succeed → Pas Anthropic, notre problème
- Status = "Partial/Major Outage" → Outage Anthropic, pas de fix rapide possible
- Error 429 dans logs → Rate limiting
- Error 401 → API key issue
- Timeout → Network ou timeout config

---

### Deep Dive Investigation (5-10 minutes)

#### Step 1: Analyser Distribution Erreurs par Type
```bash
# Extraire error types et counts
docker-compose logs api --since=30m | grep "AnthropicAPIError" | \
  sed 's/.*AnthropicAPIError: \([0-9]*\).*/\1/' | \
  sort | uniq -c | sort -rn

# 401: Auth error (API key)
# 429: Rate limit
# 500/503: Anthropic server error
# timeout: Network ou timeout config
```

---

#### Step 2: Vérifier Request Rate vs Limits
```bash
# Request rate current
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_api_calls_total[1m])*60" | jq '.data.result[0].value[1]'

# Request rate max dans dernière heure
curl -s "http://localhost:9090/api/v1/query?query=max_over_time(rate(llm_api_calls_total[1m])[1h:1m])*60" | jq '.data.result[0].value[1]'

# Comparer avec tier limit (vérifier Anthropic console)
echo "Current tier limit: [check console.anthropic.com/settings/limits]"

# Token consumption rate
curl -s "http://localhost:9090/api/v1/query?query=rate(llm_tokens_consumed_total[5m])*60" | jq '.data.result[0].value[1]'
```

---

#### Step 3: Analyser Latency Patterns
```bash
# Latency percentiles
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.50,sum(rate(llm_api_latency_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'  # P50
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum(rate(llm_api_latency_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'  # P95
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(llm_api_latency_seconds_bucket[5m]))by(le))" | jq '.data.result[0].value[1]'  # P99

# Si P99 proche de timeout config → timeout trop court
```

---

#### Step 4: Vérifier Traffic Patterns
```bash
# Spike de trafic récent?
curl -s "http://localhost:9090/api/v1/query?query=rate(http_requests_total{path=~\"/api/agents/.*\"}[5m])" | jq '.data.result'

# Users actifs
curl -s "http://localhost:9090/api/v1/query?query=conversation_active_users_total" | jq '.data.result[0].value[1]'

# Comparer avec baseline
curl -s "http://localhost:9090/api/v1/query?query=avg_over_time(conversation_active_users_total[24h])" | jq '.data.result[0].value[1]'
```

---

### Automated Diagnostic Script

```bash
infrastructure/observability/scripts/diagnose_llm_api.sh
```

---

## ✅ Resolution Steps

### Immediate Mitigation (Stop the Bleeding)

#### Option A: Implement Retry Logic with Backoff (si pas déjà fait)

**Use When**: Anthropic outage temporaire ou rate limits temporaires.

```python
# apps/api/src/infrastructure/llm/anthropic_client.py

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, anthropic.RateLimitError)),
    wait=wait_exponential(multiplier=1, min=4, max=30),  # Backoff exponentiel
    stop=stop_after_attempt(3),  # Max 3 tentatives
    reraise=True
)
async def call_anthropic_api(prompt: str, **kwargs):
    response = await client.messages.create(
        model="claude-3-sonnet-20240229",
        messages=[{"role": "user", "content": prompt}],
        **kwargs
    )
    return response
```

**Deploy**:
```bash
# Apply fix et rebuild
docker-compose build api
docker-compose restart api

# Vérifier logs retry working
docker-compose logs -f api | grep -i "retry\|attempt"
```

**Pros**: Résout transient failures automatiquement
**Cons**: Augmente latency (retries), ne résout pas quota issues
**Duration**: 5 minutes (code + deploy)

---

#### Option B: Switch to Fallback Model / Provider (si configuré)

**Use When**: Anthropic outage prolongée confirmée.

```python
# Fallback to smaller/faster model
if anthropic_failing:
    model = "claude-3-haiku-20240307"  # Faster, cheaper fallback
else:
    model = "claude-3-sonnet-20240229"  # Normal model
```

**Ou fallback to OpenAI** (si implémenté):
```python
try:
    response = await anthropic_client.call(prompt)
except AnthropicAPIError:
    logger.warning("Anthropic failed, falling back to OpenAI")
    response = await openai_client.call(prompt)
```

**Pros**: Maintient service disponible
**Cons**: Qualité réponses peut être inférieure, coûts différents
**Duration**: Immediate si code exists, sinon N/A

---

#### Option C: Enable Rate Limiting / Request Queue

**Use When**: Rate limit dépassé identifié.

```python
# apps/api/src/infrastructure/llm/rate_limiter.py
from aiolimiter import AsyncLimiter

# Configure limiter basé sur tier
# Tier 1: 50 req/min = 0.83 req/sec
limiter = AsyncLimiter(max_rate=45, time_period=60)  # 10% buffer

async def call_anthropic_with_limit(prompt: str):
    async with limiter:
        return await call_anthropic_api(prompt)
```

**Deploy**:
```bash
docker-compose build api
docker-compose restart api
```

**Pros**: Prévient rate limit errors, smooth traffic
**Cons**: Augmente latency (queueing), peut causer user timeouts
**Duration**: 10 minutes (code + test + deploy)

---

#### Option D: Increase Timeout Configuration

**Use When**: Timeouts identifiés comme cause, pas d'outage Anthropic.

```python
# Avant
client = Anthropic(timeout=5.0)

# Après
client = Anthropic(timeout=30.0)  # 6x augmentation

# Ou timeout adaptatif
timeout = 10.0 if len(prompt) < 1000 else 30.0
```

**Pros**: Résout faux positifs timeout
**Cons**: Requests lentes bloquent plus longtemps
**Duration**: 2 minutes

---

### Verification After Mitigation

```bash
# 1. Vérifier alert cleared
watch -n 10 'curl -s http://localhost:9093/api/v2/alerts | jq ".[] | select(.labels.alertname==\"LLMAPIFailureRateHigh\") | .status.state"'

# 2. Vérifier error rate diminue
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(llm_api_calls_total{status=\"error\"}[5m]))/sum(rate(llm_api_calls_total[5m]))" | jq '.data.result[0].value[1]'

# 3. Vérifier logs ne montrent plus errors
docker-compose logs api --tail=50 | grep -c "AnthropicAPIError"

# 4. Test fonctionnel agent
curl -X POST http://localhost:8000/api/agents/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "Hello, can you help me?"}'

# 5. Vérifier success rate remonte
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(llm_api_calls_total{status=\"success\"}[5m]))/sum(rate(llm_api_calls_total[5m]))" | jq '.data.result[0].value[1]'
```

**Expected After Success**:
- Error rate < 1%
- Alert inactive
- Agent répond correctement
- Success rate > 97%

---

### Root Cause Fix (Permanent Solution)

#### If Cause = Rate Limiting

**Permanent Fix**: Upgrade Anthropic tier OU implement request queueing.

**Option 1 - Upgrade Tier** (recommandé si budget permet):
```
Tier 1: 50 req/min, $10/month
Tier 2: 1000 req/min, $50/month
Tier 3: 2000 req/min, $200/month
Enterprise: 5000+ req/min, custom pricing
```

Action: Contact Anthropic sales, upgrade via console.anthropic.com

**Option 2 - Implement Smart Queueing**:
```python
# Priority queue basé sur user tier
class LLMRequestQueue:
    def __init__(self):
        self.high_priority = asyncio.Queue()
        self.normal_priority = asyncio.Queue()

    async def enqueue(self, request, priority="normal"):
        if priority == "high":
            await self.high_priority.put(request)
        else:
            await self.normal_priority.put(request)

    async def process_with_rate_limit(self):
        while True:
            # High priority first
            if not self.high_priority.empty():
                request = await self.high_priority.get()
            else:
                request = await self.normal_priority.get()

            async with rate_limiter:
                await process_request(request)
```

---

#### If Cause = Timeout Too Short

**Fix**: Implement adaptive timeout.

```python
def calculate_timeout(prompt_length: int, max_tokens: int) -> float:
    """Calculate appropriate timeout based on request size."""
    base_timeout = 10.0
    length_factor = min(prompt_length / 1000, 5.0)  # +1s per 1K chars, max +5s
    tokens_factor = min(max_tokens / 1000, 10.0)    # +1s per 1K tokens, max +10s
    return base_timeout + length_factor + tokens_factor

# Usage
timeout = calculate_timeout(len(prompt), max_tokens=2000)
client = Anthropic(timeout=timeout)
```

---

#### If Cause = No Retry Logic

**Fix**: Implement comprehensive retry with circuit breaker.

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
@retry(wait=wait_exponential(min=4, max=60), stop=stop_after_attempt(3))
async def call_anthropic_resilient(prompt: str):
    """Call Anthropic with retries and circuit breaker."""
    try:
        response = await anthropic_client.call(prompt)
        metrics.llm_api_calls.labels(status="success").inc()
        return response
    except anthropic.RateLimitError as e:
        metrics.llm_api_calls.labels(status="rate_limited").inc()
        raise  # Retry via decorator
    except anthropic.APIError as e:
        if e.status_code >= 500:
            metrics.llm_api_calls.labels(status="server_error").inc()
            raise  # Retry server errors
        else:
            metrics.llm_api_calls.labels(status="client_error").inc()
            raise  # Don't retry client errors
```

---

#### Monitoring Post-Fix

**Surveiller 48h**:
- Error rate reste <1%
- Success rate >99%
- Latency stable (P99 <15s)
- Pas de circuit breaker trips
- Rate limit buffer >20%

```bash
# Dashboard Grafana: LLM API Health
# Monitor:
# - Success/failure rate
# - Latency percentiles
# - Request rate vs tier limit
# - Retry rate
# - Circuit breaker state
```

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **LLM API Health**: `http://localhost:3000/d/llm-api`
  - Panel: "API Call Success Rate"
  - Panel: "Error Rate by Type (429, 5xx, timeout)"
  - Panel: "Latency Percentiles"
- **Agents Performance**: `http://localhost:3000/d/agents`
  - Panel: "Response Success Rate"

### Prometheus Queries
```promql
# Error rate percentage
(sum(rate(llm_api_calls_total{status="error"}[5m])) /
 sum(rate(llm_api_calls_total[5m]))) * 100

# Errors by type
sum(rate(llm_api_calls_total{status="error"}[5m])) by (error_type)

# Success rate
sum(rate(llm_api_calls_total{status="success"}[5m])) /
sum(rate(llm_api_calls_total[5m]))

# Request rate
rate(llm_api_calls_total[1m]) * 60
```

### External Status Checks
```bash
# Anthropic status API
curl https://status.anthropic.com/api/v2/status.json | jq .

# Subscribe to status updates
# https://status.anthropic.com/ → Subscribe
```

---

## 📚 Related Runbooks

- **[HighErrorRate](./HighErrorRate.md)** - Souvent co-fire (LLM errors → API errors)
- **[AgentsRouterLatencyHigh](./AgentsRouterLatencyHigh.md)** - Latency corrélée
- **[DailyCostBudgetExceeded](./DailyCostBudgetExceeded.md)** - Si workaround = plus de calls

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: Monday Morning Spike
**Description**: Weekend → low usage → lundi 9h spike → rate limit hit
**Resolution**: Pre-warm cache dimanche soir, rate limiter progressive
**Prevention**: Predictive scaling basé sur calendrier

### Pattern 2: Viral Feature Launch
**Description**: Nouvelle feature populaire → 10x requests → quota exhausted
**Resolution**: Temporary tier upgrade, feature flag throttling
**Prevention**: Gradual rollout, capacity planning pre-launch

### Known Issue 1: Streaming Timeout False Positives
**Symptom**: Streaming responses timeout même si data arrive
**Workaround**: Increase timeout for streaming, implement heartbeat
**Tracking**: GitHub issue #[TODO]

### Known Issue 2: Retry Storm Under Outage
**Symptom**: Anthropic outage → tous clients retry → amplifie load
**Workaround**: Circuit breaker, jittered backoff
**Tracking**: GitHub issue #[TODO]

---

## 🆘 Escalation

### When to Escalate

Escalader si:
- [ ] Anthropic outage >30min sans ETA
- [ ] Rate limit hit et upgrade tier impossible immédiatement
- [ ] Error rate >20% pendant 10+ minutes
- [ ] Business impact critique (demo client, deadline)
- [ ] Suspicion data leak (API key compromis)

### Escalation Path

**Level 1 - Senior Backend Engineer** (0-15min):
- **Contact**: Backend Lead
- **Slack**: #backend-critical

**Level 2 - Architect / Tech Lead** (15-30min):
- **Contact**: Tech Lead
- **Slack**: #incidents-critical
- **Decision needed**: Fallback provider, tier upgrade approval

**Level 3 - CTO + Product** (30min+):
- **Contact**: CTO
- **Decision needed**: Business continuity, budget for tier upgrade, communicate to users

**Anthropic Support**:
- **Email**: support@anthropic.com
- **Priority Support**: (if Enterprise tier)

---

## 📝 Post-Incident Actions

### Immediate (<1h)
- [ ] Create incident report
- [ ] Notify users si impact >50 users
- [ ] Document Anthropic status page state
- [ ] Capture error logs/metrics

### Short-Term (<24h)
- [ ] Update runbook
- [ ] Implement retry logic si manquant
- [ ] Review tier adequacy
- [ ] Add monitoring gaps (circuit breaker, queue depth)

### Long-Term (<1 week)
- [ ] Post-mortem
- [ ] Implement fallback provider si critique
- [ ] Capacity planning review
- [ ] Consider multi-provider strategy

---

## 🔗 Additional Resources

### Documentation
- [Anthropic API Reference](https://docs.anthropic.com/claude/reference)
- [Rate Limits](https://docs.anthropic.com/claude/reference/rate-limits)
- [Error Codes](https://docs.anthropic.com/claude/reference/errors)

### Code References
- LLM Client: `apps/api/src/infrastructure/llm/anthropic_client.py`
- Retry Logic: `apps/api/src/infrastructure/llm/retry.py`
- Metrics: `apps/api/src/infrastructure/observability/metrics_agents.py`

### External Resources
- [Anthropic Status Page](https://status.anthropic.com/)
- [Anthropic Console](https://console.anthropic.com/)
- [Best Practices - API Resilience](https://docs.anthropic.com/claude/docs/api-resilience)

---

## 📅 Runbook Metadata

**Created**: 2025-11-22
**Last Updated**: 2025-11-22
**Maintainer**: Backend Team + AI/ML Team
**Version**: 1.0
**Related GitHub Issues**: #31

**Changelog**:
- **2025-11-22**: Initial creation

---

## ✅ Runbook Validation Checklist

- [x] Alert definition verified
- [ ] Anthropic API tested (**TODO**)
- [ ] Retry logic reviewed (**TODO**)
- [ ] Status page monitoring setup (**TODO**)
- [ ] Escalation to Anthropic support tested (**TODO**)
- [ ] Fallback provider considered (**TODO**)

---

**Note**: Critical de monitorer Anthropic status page ET implémenter retry robust. API externe = hors de notre contrôle.
