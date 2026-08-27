# Guide : mesurer les performances (latence SSE et charge HITL)

Deux questions distinctes, deux outils, un seul dossier de scripts
(`apps/api/scripts/benchmark/`) — et un seul guide, parce que la réponse à
l'une conditionne la lecture de l'autre :

| Question | Partie | Script |
|---|---|---|
| « Combien de temps pour le premier token, pour un utilisateur seul ? » | [Partie 1](#partie-1--benchmark-de-latence-sse) | `benchmark_sse_streaming.py`, `run_benchmark.py` |
| « Que se passe-t-il à 10, 50, 100 utilisateurs simultanés ? » | [Partie 2](#partie-2--test-de-charge-du-streaming-hitl) | `load_test_hitl_streaming.py` |

Mesurer la latence sous charge nulle et en déduire le comportement sous charge
est l'erreur classique : la partie 2 existe précisément parce que les deux
courbes divergent. Ces mesures sont des **instruments**, pas des seuils : ce qui
fait autorité en CI, ce sont les gates de `task lint` et les suites de tests.

---

## Partie 1 — Benchmark de latence SSE


Scripts pour mesurer et analyser les performances du streaming SSE des agents LangGraph.

### 🎯 Objectifs

Mesurer les métriques de performance critiques :
- **Time to First Token (TTFT)** : Latence avant le premier token
- **Time to Last Token (TTLT)** : Temps total de génération
- **Tokens per Second** : Débit de génération
- **Router Latency** : Temps de décision du router
- **Total Response Time** : Temps total end-to-end

### 🚀 Utilisation Rapide

#### Option 1 : Script Wrapper (Recommandé)

Depuis la racine du projet :

```bash
./scripts/optim/benchmark.sh
```

**Ce script fait automatiquement** :
1. Vérifie que l'API tourne
2. Crée un utilisateur de test si nécessaire
3. S'authentifie automatiquement
4. Exécute les 4 benchmarks
5. Affiche les résultats agrégés

#### Option 2 : Exécution Manuelle

Depuis le container API :

```bash
# Avec utilisateur de test (créé automatiquement)
docker compose -f docker-compose.dev.yml exec api python apps/api/scripts/benchmark/run_benchmark.py --test-user

# Avec vos propres credentials
docker compose -f docker-compose.dev.yml exec api python apps/api/scripts/benchmark/run_benchmark.py \
  --email votre@email.com \
  --password VotrePassword
```

### 📊 Interprétation des Résultats

#### Exemple de Sortie

```
========================================
SSE STREAMING PERFORMANCE BENCHMARK
========================================

[1/4] Testing: Bonjour...
  ✅ Router Latency: 245ms
  ✅ Time to First Token: 389ms
  ✅ Time to Last Token: 1456ms
  ✅ Total Tokens: 87
  ✅ Tokens/sec: 82.3
  ✅ Total Time: 1502ms

...

========================================
AGGREGATE RESULTS
========================================

Successful Requests: 4/4
Average Router Latency: 267ms
Average Time to First Token: 412ms
Average Time to Last Token: 1823ms
Average Tokens: 124
Average Tokens/sec: 67.8
Average Total Time: 1891ms

--------------------------------------------------------------------------------
SLA ANALYSIS (Target: TTFT < 1000ms, Tokens/sec > 20)
--------------------------------------------------------------------------------
TTFT < 1000ms: 4/4 (100.0%)
Tokens/sec > 20: 4/4 (100.0%)

========================================
✅ VERDICT: ALL SLA TARGETS MET
========================================
```

#### Métriques Clés

| Métrique | Cible | Description | Impact Utilisateur |
|----------|-------|-------------|--------------------|
| **TTFT** | < 1000ms | Latence avant 1er token | Perception réactivité |
| **Tokens/sec** | > 20 | Vitesse génération | Fluidité lecture |
| **Router Latency** | < 500ms | Temps décision routing | Latence initiale |
| **Total Time** | Variable | Temps complet réponse | Satisfaction globale |

#### Verdicts

- ✅ **ALL SLA TARGETS MET** : Performances optimales
- ⚠️ **MOST SLA TARGETS MET (>80%)** : Performances acceptables, à surveiller
- ❌ **SLA TARGETS NOT MET** : Investigation requise

### 🔍 Cas d'Usage

#### 1. Validation Avant Déploiement

```bash
# Avant merge
./scripts/optim/benchmark.sh > baseline.txt

# Après modifications code
./scripts/optim/benchmark.sh > after_changes.txt

# Comparer
diff baseline.txt after_changes.txt
```

**Objectif** : S'assurer qu'aucune régression de performance.

#### 2. Optimisation LLM Config

```bash
# Test 1 : Config actuelle
./scripts/optim/benchmark.sh

# Modifier .env (ex: RESPONSE_LLM_TEMPERATURE=0.5)
docker compose -f docker-compose.dev.yml restart api

# Test 2 : Nouvelle config
./scripts/optim/benchmark.sh
```

**Objectif** : Trouver le meilleur compromis vitesse/qualité.

#### 3. Load Testing (Simple)

```bash
# Exécuter 10 fois
for i in {1..10}; do
  echo "=== RUN $i ==="
  ./scripts/optim/benchmark.sh
  sleep 5
done
```

**Objectif** : Vérifier stabilité sous charge répétée.

#### 4. Comparaison Modèles

```bash
# Test gpt-4.1-mini
RESPONSE_LLM_MODEL=gpt-4.1-mini ./scripts/optim/benchmark.sh > mini.txt

# Test gpt-4.1-mini
RESPONSE_LLM_MODEL=gpt-4.1-mini ./scripts/optim/benchmark.sh > gpt4o.txt

# Comparer
diff mini.txt gpt4o.txt
```

**Objectif** : Évaluer trade-off coût/performance.

### 🛠️ Personnalisation

#### Modifier les Messages de Test

Éditer `apps/api/scripts/benchmark/benchmark_sse_streaming.py` :

```python
TEST_MESSAGES = [
    "Bonjour",
    "Quel temps fait-il?",
    "Explique-moi la photosynthèse",
    "Rédige un email professionnel",
    # Ajoutez vos messages ici
]
```

#### Ajuster les SLA Cibles

Modifier les seuils dans `apps/api/scripts/benchmark/run_benchmark.py` :

```python
# SLA Analysis
ttft_sla_met = sum(1 for m in successful_metrics if m.time_to_first_token_ms < 1000)  # Modifier 1000
tokens_sla_met = sum(1 for m in successful_metrics if m.tokens_per_second > 20)       # Modifier 20
```

#### Tester Endpoint Différent

```bash
docker compose -f docker-compose.dev.yml exec api python apps/api/scripts/benchmark/run_benchmark.py \
  --test-user \
  --api-url http://autre-api:8000
```

### 📈 Intégration CI/CD

Ajouter job GitHub Actions pour tracking automatique :

```yaml
benchmark-performance:
  name: Performance Benchmark
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Start services
      run: docker compose -f docker-compose.dev.yml up -d

    - name: Wait for API
      run: sleep 10

    - name: Run benchmark
      run: |
        docker compose -f docker-compose.dev.yml exec -T api \
          python apps/api/scripts/benchmark/run_benchmark.py --test-user > benchmark.txt

    - name: Check SLA
      run: |
        if grep -q "ALL SLA TARGETS MET" benchmark.txt; then
          echo "✅ Performance SLA met"
        else
          echo "❌ Performance SLA not met"
          exit 1
        fi

    - name: Upload results
      uses: actions/upload-artifact@v4
      with:
        name: benchmark-results
        path: benchmark.txt
```

### 🐛 Troubleshooting

#### Erreur "API container is not running"

```bash
# Démarrer l'API
docker compose -f docker-compose.dev.yml up -d

# Vérifier statut
docker compose -f docker-compose.dev.yml ps
```

#### Erreur "Failed to create test user"

```bash
# Vérifier logs PostgreSQL
docker compose -f docker-compose.dev.yml logs postgres

# Vérifier migration DB
docker compose -f docker-compose.dev.yml exec api alembic current
```

#### Erreur "HTTP 401 Unauthorized"

```bash
# Vérifier Redis (sessions)
docker compose -f docker-compose.dev.yml logs redis

# Nettoyer sessions Redis
docker compose -f docker-compose.dev.yml exec redis redis-cli FLUSHDB
```

#### Résultats incohérents

Causes possibles :
- Cache réseau : Attendre 30s entre tests
- Load variable : Redémarrer containers
- OpenAI API throttling : Utiliser API key avec quota

### 📚 Ressources

- ADR-009: LangGraph Event Filtering
- PROMPTOPS Documentation
- [OpenAI Performance Best Practices](https://platform.openai.com/docs/guides/production-best-practices/improving-latencies)

---

**Dernière mise à jour** : 2025-10-20

---

## Partie 2 — Test de charge du streaming HITL


### Overview

This guide explains how to use the load testing script to measure HITL (Human-in-the-Loop) streaming performance under realistic load conditions.

**Key Metrics Measured:**
- **TTFT (Time To First Token)**: Critical UX metric - target < 300ms
- **Throughput**: Requests per second
- **Latency Percentiles**: p50, p95, p99
- **Error Rates**: Success/failure breakdown
- **Token Metrics**: Tokens generated per request

### Quick Start

#### Prerequisites

```bash
# Install dependencies
pip install httpx asyncio aiohttp

# Ensure API is running
docker-compose -f docker-compose.dev.yml up -d api
```

#### Basic Usage

```bash
# Run with default settings (10 users, 100 requests)
python apps/api/scripts/benchmark/load_test_hitl_streaming.py

# Run with custom load profile
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --users 50 --requests 500

# Run for fixed duration (300 seconds)
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --duration 300

# Export results to JSON
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --output results.json
```

### Load Testing Scenarios

#### Scenario 1: Smoke Test (Low Load)

Verify basic functionality with minimal load.

```bash
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --users 1 --requests 10
```

**Expected Results:**
- Success rate: 100%
- TTFT p95: < 300ms
- No errors

#### Scenario 2: Normal Load (Production Simulation)

Simulate typical production traffic with 10 concurrent users.

```bash
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --users 10 --requests 100 --output normal_load.json
```

**Expected Results:**
- Success rate: > 99%
- TTFT p95: < 300ms
- TTFT p99: < 500ms
- Throughput: > 5 req/s

#### Scenario 3: Stress Test (High Load)

Test system limits with high concurrent load.

```bash
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --users 50 --requests 500 --output stress_test.json
```

**Expected Results:**
- Success rate: > 95%
- TTFT p95: < 500ms (degradation acceptable)
- TTFT p99: < 1000ms
- Throughput: > 20 req/s

**Watch for:**
- Redis connection pool exhaustion
- LLM API rate limits
- Database connection limits
- Memory leaks

#### Scenario 4: Soak Test (Endurance)

Run for extended duration to detect memory leaks and resource exhaustion.

```bash
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --users 20 --duration 3600 --output soak_test.json
```

**Duration:** 1 hour (3600 seconds)

**Expected Results:**
- Consistent TTFT over time (no degradation)
- Stable memory usage (no leaks)
- No connection pool exhaustion

**Monitor:**
```bash
# Watch Docker stats
docker stats lia-api-dev lia-redis-dev

# Watch Prometheus metrics
curl http://localhost:9090/api/v1/query?query=hitl_question_ttft_seconds
```

#### Scenario 5: Spike Test (Burst Traffic)

Simulate sudden traffic spike (e.g., viral event).

```bash
# Baseline load
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --users 10 --duration 60 &

# Wait 30s, then spike to 100 users
sleep 30 && python apps/api/scripts/benchmark/load_test_hitl_streaming.py --users 100 --duration 30
```

**Expected Results:**
- System handles spike gracefully
- TTFT degrades temporarily but recovers
- No cascading failures

### Interpreting Results

#### TTFT Metrics (Critical for UX)

```
🎯 Time To First Token (TTFT) - Critical UX Metric:
   Min: 120ms
   Mean: 250ms
   Median: 240ms
   P95: 290ms ✅ (target: <300ms)
   P99: 450ms
   Max: 800ms
   Samples: 100
```

**Analysis:**
- ✅ **P95 < 300ms**: Excellent - 95% of users see first token in < 300ms
- ⚠️ **P95 > 300ms**: Needs optimization - UX degraded for 5% of users
- ❌ **P95 > 500ms**: Critical - unacceptable user experience

**Optimization Targets:**
- **Min**: ~100-150ms (network + LLM API latency)
- **P95**: < 300ms (UX target)
- **P99**: < 500ms (acceptable tail latency)

#### Throughput Metrics

```
⚡ Execution Summary:
   Duration: 45.23s
   Requests Completed: 100
   Requests Failed: 0
   Success Rate: 100.00%
   Throughput: 2.21 req/s
```

**Analysis:**
- **Low throughput (< 1 req/s)**: Bottleneck in API or LLM
- **Normal throughput (5-10 req/s)**: Healthy for 10 concurrent users
- **High throughput (> 20 req/s)**: Excellent scalability

#### Error Analysis

```
❌ Errors:
   TimeoutException: 5
   ConnectionError: 2
   ValidationError: 1
```

**Common Errors:**
- **TimeoutException**: LLM API slow or overloaded
- **ConnectionError**: Redis/DB connection pool exhausted
- **ValidationError**: Invalid data in request/response
- **HTTPException 429**: Rate limit exceeded

### Performance Benchmarks

#### Target Performance (Production)

| Metric | Target | Acceptable | Critical |
|--------|--------|-----------|----------|
| TTFT P95 | < 300ms | < 500ms | > 1000ms |
| TTFT P99 | < 500ms | < 1000ms | > 2000ms |
| Success Rate | > 99.9% | > 99% | < 95% |
| Throughput | > 10 req/s | > 5 req/s | < 1 req/s |
| Error Rate | < 0.1% | < 1% | > 5% |

#### Baseline Measurements (Development)

**Environment:** Docker Compose Dev, M1 Mac, 16GB RAM

| Scenario | Users | TTFT P95 | Throughput | Success Rate |
|----------|-------|----------|------------|--------------|
| Smoke Test | 1 | 180ms | 3.2 req/s | 100% |
| Normal Load | 10 | 280ms | 5.8 req/s | 99.5% |
| Stress Test | 50 | 450ms | 22.1 req/s | 96.2% |
| Soak Test | 20 | 310ms | 8.5 req/s | 98.8% |

### Troubleshooting

#### Issue: High TTFT (> 500ms)

**Possible Causes:**
1. LLM API latency (OpenAI/Anthropic)
2. Redis cache miss (cold cache)
3. Database query slow
4. Network latency

**Diagnosis:**
```bash
# Check Prometheus metrics
curl 'http://localhost:9090/api/v1/query?query=hitl_question_ttft_seconds'

# Check Redis latency
docker exec lia-redis-dev redis-cli --latency

# Check API logs
docker logs lia-api-dev | grep hitl_question_ttft
```

**Fixes:**
- Enable LLM cache (already implemented)
- Use faster LLM model (gpt-4.1-mini-mini vs gpt-4)
- Warm up cache before load test
- Check network latency to LLM API

#### Issue: Low Throughput (< 5 req/s)

**Possible Causes:**
1. Sequential processing (missing async/await)
2. Connection pool exhausted
3. CPU/memory bottleneck

**Diagnosis:**
```bash
# Check resource usage
docker stats lia-api-dev

# Check connection pools
docker logs lia-api-dev | grep "pool exhausted"

# Check Python async tasks
docker exec lia-api-dev ps aux | grep python
```

**Fixes:**
- Increase Redis connection pool size
- Increase DB connection pool size
- Scale API horizontally (multiple containers)
- Optimize async/await usage

#### Issue: High Error Rate (> 5%)

**Possible Causes:**
1. Rate limit exceeded (LLM API)
2. Redis connection timeout
3. Database deadlock
4. Memory exhaustion

**Diagnosis:**
```bash
# Check error logs
docker logs lia-api-dev | grep ERROR

# Check rate limits
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/rate_limits

# Check Redis connection
docker exec lia-redis-dev redis-cli INFO clients
```

**Fixes:**
- Implement exponential backoff retry
- Increase rate limits (upgrade LLM API tier)
- Increase Redis max connections
- Add circuit breaker pattern

### CI/CD Integration

#### GitHub Actions Example

```yaml
name: HITL Streaming Load Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.14'

      - name: Install dependencies
        run: |
          pip install httpx aiohttp

      - name: Start services
        run: |
          docker-compose -f docker-compose.dev.yml up -d api redis
          sleep 10  # Wait for services to be ready

      - name: Run load test
        run: |
          python apps/api/scripts/benchmark/load_test_hitl_streaming.py \
            --users 10 \
            --requests 50 \
            --output load_test_results.json

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: load-test-results
          path: load_test_results.json

      - name: Check performance thresholds
        run: |
          # Fail if TTFT P95 > 500ms (CI threshold)
          python -c "
          import json
          with open('load_test_results.json') as f:
              results = json.load(f)
          ttft_p95 = results['ttft_metrics']['p95_ms']
          assert ttft_p95 < 500, f'TTFT P95 too high: {ttft_p95}ms'
          "
```

#### Grafana Dashboard Integration

Import load test results into Grafana for visualization:

```bash
# Run load test and export to InfluxDB format
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --output results.json

# Convert to InfluxDB line protocol (exemple — script non commité)
python scripts/convert_to_influxdb.py results.json | \
  curl -XPOST 'http://localhost:8086/write?db=load_tests' --data-binary @-
```

### Best Practices

#### 1. Run Baseline Tests Before Changes

```bash
# Before making changes
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --output baseline.json

# After making changes
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --output after_changes.json

# Compare results (exemple — script non commité)
python scripts/compare_load_tests.py baseline.json after_changes.json
```

#### 2. Test with Realistic Data

Modify the script to use realistic user queries instead of static "Recherche jean":

```python
# In load_test_hitl_streaming.py, replace:
"message": f"Recherche jean",

# With:
REALISTIC_QUERIES = [
    "Recherche jean",
    "Recherche jean",
    "Cherche Jean Dupont",
    "Trouve Marie Martin",
]
"message": random.choice(REALISTIC_QUERIES),
```

#### 3. Monitor System Resources

Run load test with monitoring:

```bash
# Terminal 1: Run load test
python apps/api/scripts/benchmark/load_test_hitl_streaming.py --users 50 --duration 300

# Terminal 2: Monitor Docker stats
docker stats lia-api-dev lia-redis-dev

# Terminal 3: Monitor Prometheus
watch -n 5 'curl -s http://localhost:9090/api/v1/query?query=hitl_question_ttft_seconds | jq .'
```

#### 4. Test in Staging Environment

Always test in staging before production:

```bash
# Production-like load test in staging
python apps/api/scripts/benchmark/load_test_hitl_streaming.py \
  --base-url https://staging-api.lia.ai/api/v1 \
  --users 100 \
  --duration 600 \
  --output staging_load_test.json
```

### References

- [HITL Streaming Architecture](../technical/MESSAGE_WINDOWING_STRATEGY.md)
- [Prometheus Metrics](../../infrastructure/observability/prometheus/alerts/hitl_cache_alerts.yml)
- Grafana Dashboard
- ADR 012: Message Windowing

---

