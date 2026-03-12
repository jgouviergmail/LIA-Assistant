# HITL Streaming Load Testing Guide

> **Version**: 5.5 | **Status**: Active | **Dernière mise à jour**: 2025-01

## Overview

This guide explains how to use the load testing script to measure HITL (Human-in-the-Loop) streaming performance under realistic load conditions.

**Key Metrics Measured:**
- **TTFT (Time To First Token)**: Critical UX metric - target < 300ms
- **Throughput**: Requests per second
- **Latency Percentiles**: p50, p95, p99
- **Error Rates**: Success/failure breakdown
- **Token Metrics**: Tokens generated per request

## Quick Start

### Prerequisites

```bash
# Install dependencies
pip install httpx asyncio aiohttp

# Ensure API is running
docker-compose -f docker-compose.dev.yml up -d api
```

### Basic Usage

```bash
# Run with default settings (10 users, 100 requests)
python scripts/load_test_hitl_streaming.py

# Run with custom load profile
python scripts/load_test_hitl_streaming.py --users 50 --requests 500

# Run for fixed duration (300 seconds)
python scripts/load_test_hitl_streaming.py --duration 300

# Export results to JSON
python scripts/load_test_hitl_streaming.py --output results.json
```

## Load Testing Scenarios

### Scenario 1: Smoke Test (Low Load)

Verify basic functionality with minimal load.

```bash
python scripts/load_test_hitl_streaming.py --users 1 --requests 10
```

**Expected Results:**
- Success rate: 100%
- TTFT p95: < 300ms
- No errors

### Scenario 2: Normal Load (Production Simulation)

Simulate typical production traffic with 10 concurrent users.

```bash
python scripts/load_test_hitl_streaming.py --users 10 --requests 100 --output normal_load.json
```

**Expected Results:**
- Success rate: > 99%
- TTFT p95: < 300ms
- TTFT p99: < 500ms
- Throughput: > 5 req/s

### Scenario 3: Stress Test (High Load)

Test system limits with high concurrent load.

```bash
python scripts/load_test_hitl_streaming.py --users 50 --requests 500 --output stress_test.json
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

### Scenario 4: Soak Test (Endurance)

Run for extended duration to detect memory leaks and resource exhaustion.

```bash
python scripts/load_test_hitl_streaming.py --users 20 --duration 3600 --output soak_test.json
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

### Scenario 5: Spike Test (Burst Traffic)

Simulate sudden traffic spike (e.g., viral event).

```bash
# Baseline load
python scripts/load_test_hitl_streaming.py --users 10 --duration 60 &

# Wait 30s, then spike to 100 users
sleep 30 && python scripts/load_test_hitl_streaming.py --users 100 --duration 30
```

**Expected Results:**
- System handles spike gracefully
- TTFT degrades temporarily but recovers
- No cascading failures

## Interpreting Results

### TTFT Metrics (Critical for UX)

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

### Throughput Metrics

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

### Error Analysis

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

## Performance Benchmarks

### Target Performance (Production)

| Metric | Target | Acceptable | Critical |
|--------|--------|-----------|----------|
| TTFT P95 | < 300ms | < 500ms | > 1000ms |
| TTFT P99 | < 500ms | < 1000ms | > 2000ms |
| Success Rate | > 99.9% | > 99% | < 95% |
| Throughput | > 10 req/s | > 5 req/s | < 1 req/s |
| Error Rate | < 0.1% | < 1% | > 5% |

### Baseline Measurements (Development)

**Environment:** Docker Compose Dev, M1 Mac, 16GB RAM

| Scenario | Users | TTFT P95 | Throughput | Success Rate |
|----------|-------|----------|------------|--------------|
| Smoke Test | 1 | 180ms | 3.2 req/s | 100% |
| Normal Load | 10 | 280ms | 5.8 req/s | 99.5% |
| Stress Test | 50 | 450ms | 22.1 req/s | 96.2% |
| Soak Test | 20 | 310ms | 8.5 req/s | 98.8% |

## Troubleshooting

### Issue: High TTFT (> 500ms)

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

### Issue: Low Throughput (< 5 req/s)

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

### Issue: High Error Rate (> 5%)

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

## CI/CD Integration

### GitHub Actions Example

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
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install httpx aiohttp

      - name: Start services
        run: |
          docker-compose -f docker-compose.dev.yml up -d api redis
          sleep 10  # Wait for services to be ready

      - name: Run load test
        run: |
          python scripts/load_test_hitl_streaming.py \
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

### Grafana Dashboard Integration

Import load test results into Grafana for visualization:

```bash
# Run load test and export to InfluxDB format
python scripts/load_test_hitl_streaming.py --output results.json

# Convert to InfluxDB line protocol
python scripts/convert_to_influxdb.py results.json | \
  curl -XPOST 'http://localhost:8086/write?db=load_tests' --data-binary @-
```

## Best Practices

### 1. Run Baseline Tests Before Changes

```bash
# Before making changes
python scripts/load_test_hitl_streaming.py --output baseline.json

# After making changes
python scripts/load_test_hitl_streaming.py --output after_changes.json

# Compare results
python scripts/compare_load_tests.py baseline.json after_changes.json
```

### 2. Test with Realistic Data

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

### 3. Monitor System Resources

Run load test with monitoring:

```bash
# Terminal 1: Run load test
python scripts/load_test_hitl_streaming.py --users 50 --duration 300

# Terminal 2: Monitor Docker stats
docker stats lia-api-dev lia-redis-dev

# Terminal 3: Monitor Prometheus
watch -n 5 'curl -s http://localhost:9090/api/v1/query?query=hitl_question_ttft_seconds | jq .'
```

### 4. Test in Staging Environment

Always test in staging before production:

```bash
# Production-like load test in staging
python scripts/load_test_hitl_streaming.py \
  --base-url https://staging-api.lia.ai/api/v1 \
  --users 100 \
  --duration 600 \
  --output staging_load_test.json
```

## References

- [HITL Streaming Architecture](../docs/agents/MESSAGE_WINDOWING_STRATEGY.md)
- [Prometheus Metrics](../monitoring/prometheus/alerts/hitl_cache_alerts.yml)
- [Grafana Dashboard](../monitoring/grafana/dashboards/llm_observability_v2.json)
- [ADR 012: Message Windowing](../docs/adr/012-message-windowing-latency-optimization.md)
