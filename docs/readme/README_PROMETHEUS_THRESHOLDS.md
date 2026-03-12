# Prometheus Alert Thresholds - Environment Configuration

## Overview

This system enables **environment-specific alert thresholds** for Prometheus, allowing different sensitivity levels for development, staging, and production environments.

### Key Features

- **84/80 thresholds externalized** (105% coverage - some duplicates)
- **72 unique alerts configured** across all categories
- **3 environment profiles**: production (1.0x), staging (2.0x), development (5.0x)
- **Jinja2 templates** for flexible configuration
- **Automated rendering** before Docker deployment

## Architecture

```
thresholds_inventory.json          ← Master threshold inventory (80 thresholds)
        ↓
generate_threshold_envs.py         ← Generate .env files per environment
        ↓
thresholds/
  ├── production.env               ← Strict thresholds (1.0x multiplier)
  ├── staging.env                  ← Moderate thresholds (2.0x multiplier)
  └── development.env              ← Permissive thresholds (5.0x multiplier)
        ↓
convert_alerts_yaml_aware.py       ← Convert hardcoded YAML to templates
        ↓
*.yml.template files               ← Jinja2 templates with <<<VAR>>> syntax
  ├── alert_rules.yml.template
  └── alerts.yml.template
        ↓
render_alerts.py                   ← Render templates with environment vars
        ↓
*.yml files (generated)            ← Final Prometheus configuration
  ├── alert_rules.yml
  └── alerts.yml
```

## Files

### Source Files (Version Control)

- `thresholds_inventory.json` - Master inventory of all 80 thresholds
- `alert_rules.yml.template` - Jinja2 template for recording rules
- `alerts.yml.template` - Jinja2 template for alerting rules
- `thresholds/production.env` - Production threshold values (strict)
- `thresholds/staging.env` - Staging threshold values (moderate)
- `thresholds/development.env` - Development threshold values (permissive)

### Generated Files (Not in Git)

- `alert_rules.yml` - Rendered recording rules (generated before deployment)
- `alerts.yml` - Rendered alerting rules (generated before deployment)
- `*.original` - Backup files created during conversion

### Scripts

- `extract_thresholds.py` - Analyze YAML files to extract hardcoded thresholds
- `generate_threshold_envs.py` - Generate environment-specific .env files
- `convert_alerts_yaml_aware.py` - Convert hardcoded YAML to Jinja2 templates
- `render_alerts.py` - Render templates with environment variables
- `prepare_config.sh` - Automated workflow for rendering before deployment

## Usage

### Before Docker Deployment

**Option 1: Automated (Recommended)**

```bash
cd infrastructure/observability/prometheus
./prepare_config.sh [production|staging|development]
```

This script:
1. Loads thresholds from `thresholds/{environment}.env`
2. Renders `alert_rules.yml.template` → `alert_rules.yml`
3. Renders `alerts.yml.template` → `alerts.yml`
4. Validates YAML syntax

**Option 2: Manual**

```bash
cd infrastructure/observability/prometheus

# For development
python render_alerts.py --env-file thresholds/development.env \
  --template alert_rules.yml.template --output alert_rules.yml

python render_alerts.py --env-file thresholds/development.env \
  --template alerts.yml.template --output alerts.yml

# For production
python render_alerts.py --env-file thresholds/production.env \
  --template alert_rules.yml.template --output alert_rules.yml

python render_alerts.py --env-file thresholds/production.env \
  --template alerts.yml.template --output alerts.yml
```

### Start Docker Stack

```bash
docker-compose -f docker-compose.dev.yml up -d prometheus
```

Prometheus will load the pre-rendered `alert_rules.yml` and `alerts.yml` files.

### Verify Alerts

1. Open Prometheus: [http://localhost:9090/alerts](http://localhost:9090/alerts)
2. Check that all alerts are loaded
3. Verify threshold values match your environment

## Threshold Categories

| Category | Count | Examples |
|----------|-------|----------|
| Infrastructure | 17 | Redis connections, database connections, disk space |
| HITL Quality | 11 | Clarification fallback rate, rejection rate, approval rate |
| Reliability | 9 | Error rates, OAuth failures, tool failures |
| Checkpoint Persistence | 7 | Save latency, load latency, checkpoint size |
| Business Metrics | 4 | Conversation abandonment rate |
| Performance | 4 | API latency P95/P99, router latency |
| LLM Costs | 3 | Daily budget, hourly cost, model budget |
| Other | 25 | Container health, conversation creation, tokens |

**Total**: 80 thresholds

## Environment Multipliers

Thresholds are adjusted per environment to reduce alert noise in non-production:

| Environment | Multiplier | Use Case | Example Alert |
|-------------|-----------|----------|---------------|
| **Production** | `1.0x` | Strict monitoring for customer-facing services | Error rate > 5% (base: 0.05) |
| **Staging** | `2.0x` | Moderate for pre-production testing | Error rate > 10% (0.05 × 2) |
| **Development** | `5.0x` | Permissive for local/CI environments | Error rate > 25% (0.05 × 5) |

### Multiplier Logic

```python
# For "greater_than" operators (e.g., error_rate > threshold)
adjusted = base_value * multiplier

# For "less_than" operators (e.g., tokens_per_sec < threshold)
adjusted = base_value / multiplier

# For percentage values (0-1 range), cap at 0.99
if 0 < adjusted < 1.0:
    adjusted = min(adjusted, 0.99)
```

## Modifying Thresholds

### 1. Edit Master Inventory

Edit `thresholds_inventory.json` to change base thresholds.

### 2. Regenerate Environment Files

```bash
python generate_threshold_envs.py
```

This creates new `.env` files in `thresholds/` directory.

### 3. Re-render YAML Files

```bash
./prepare_config.sh production  # or staging/development
```

### 4. Reload Prometheus

```bash
# Hot reload (no downtime)
curl -X POST http://localhost:9090/-/reload

# Or restart container
docker-compose restart prometheus
```

## Adding New Alerts

### 1. Add Alert to YAML Template

Edit `alert_rules.yml.template` or `alerts.yml.template`:

```yaml
- alert: MyNewAlert
  expr: |
    my_metric > <<<ALERT_MY_NEW_ALERT_THRESHOLD>>>
  for: 5m
  labels:
    severity: warning
```

### 2. Add Threshold to Inventory

Edit `thresholds_inventory.json`:

```json
{
  "alert": "MyNewAlert",
  "value": 100.0,
  "operator": "greater_than",
  "category": "performance",
  "source_file": "alerts.yml",
  "line": 123
}
```

### 3. Regenerate and Deploy

```bash
python generate_threshold_envs.py
./prepare_config.sh production
docker-compose restart prometheus
```

## Template Syntax

Templates use Jinja2 with custom delimiters `<<<` and `>>>` to avoid conflicts with Prometheus `{{ }}` templating.

### Examples

```yaml
# Greater than
expr: error_rate > <<<ALERT_ERROR_RATE_THRESHOLD>>>

# Less than
expr: tokens_per_sec < <<<ALERT_MIN_TOKENS_THRESHOLD>>>

# Equal
expr: service_up == <<<ALERT_SERVICE_UP_THRESHOLD>>>

# In complex expressions
expr: |
  histogram_quantile(0.95, rate(latency_bucket[5m]))
  > <<<ALERT_LATENCY_P95_THRESHOLD>>>
```

## Troubleshooting

### Issue: Variables not substituted

**Symptom**: YAML contains `<<<VAR_NAME>>>` after rendering

**Cause**: Variable not found in `.env` file

**Fix**:
1. Check variable name in template matches `.env` file
2. Verify `.env` file is loaded correctly
3. Re-run `generate_threshold_envs.py`

### Issue: YAML syntax error

**Symptom**: Prometheus fails to load config

**Cause**: Invalid YAML after rendering

**Fix**:
```bash
# Validate YAML
python -c "import yaml; yaml.safe_load(open('alerts.yml'))"

# Check for unsubstituted variables
grep "<<<" alerts.yml
```

### Issue: Alerts not firing as expected

**Symptom**: Production alerts too sensitive or not firing

**Cause**: Wrong environment file used

**Fix**:
```bash
# Verify which .env was used
grep "ALERT_HIGH_ERROR_RATE_THRESHOLD" alerts.yml
# Production should be ~0.05, Development ~0.25
```

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Render Prometheus alerts
  run: |
    cd infrastructure/observability/prometheus
    ./prepare_config.sh ${{ env.ENVIRONMENT }}
  env:
    ENVIRONMENT: ${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}

- name: Validate Prometheus config
  run: |
    docker run --rm -v $(pwd)/infrastructure/observability/prometheus:/prometheus \
      prom/prometheus:latest \
      promtool check config /prometheus/prometheus.yml
```

## References

- [Prometheus Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Jinja2 Template Documentation](https://jinja.palletsprojects.com/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/alerting/)

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2025-11-23 | 1.0.0 | Initial implementation - 84/80 thresholds externalized |
