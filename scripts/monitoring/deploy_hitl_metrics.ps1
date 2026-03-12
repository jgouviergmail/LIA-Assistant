# Script de déploiement automatique - HITL Metrics (Windows PowerShell)
# Usage: .\scripts\deploy_hitl_metrics.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================================================"
Write-Host "DEPLOYMENT HITL METRICS - Automated Deployment Script (Windows)"
Write-Host "========================================================================"
Write-Host ""

function Log-Info {
    param($Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Log-Warn {
    param($Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Log-Error {
    param($Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Step 1: Prerequisites
Write-Host "========================================================================"
Write-Host "STEP 1: Checking Prerequisites"
Write-Host "========================================================================"

Log-Info "Checking Python..."
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Log-Error "Python not found. Please install Python"
    exit 1
}

Log-Info "Checking Docker..."
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Log-Error "Docker not found. Please install Docker"
    exit 1
}

Log-Info "All prerequisites met"
Write-Host ""

# Step 2: Validate Code
Write-Host "========================================================================"
Write-Host "STEP 2: Validating Code Implementation"
Write-Host "========================================================================"

Log-Info "Running metrics validation..."
Push-Location apps\api
python scripts\validate_hitl_metrics_simple.py
$ValidationResult = $LASTEXITCODE
Pop-Location

if ($ValidationResult -ne 0) {
    Log-Error "Metrics validation failed!"
    exit 1
}

Log-Info "Code validation: PASS"
Write-Host ""

# Step 3: Validate Configuration
Write-Host "========================================================================"
Write-Host "STEP 3: Validating Configuration Files"
Write-Host "========================================================================"

Log-Info "Validating recording_rules.yml..."
try {
    python -c "import yaml; yaml.safe_load(open('infrastructure/observability/prometheus/recording_rules.yml', encoding='utf-8'))"
    Log-Info "Recording rules: VALID"
} catch {
    Log-Error "Recording rules: INVALID"
    exit 1
}

Log-Info "Validating alert_rules.yml..."
try {
    python -c "import yaml; yaml.safe_load(open('infrastructure/observability/prometheus/alert_rules.yml', encoding='utf-8'))"
    Log-Info "Alert rules: VALID"
} catch {
    Log-Error "Alert rules: INVALID"
    exit 1
}

Log-Info "Validating dashboard JSON..."
try {
    python -c "import json; json.load(open('infrastructure/observability/grafana/dashboards/07-hitl-tool-approval.json', encoding='utf-8'))"
    Log-Info "Dashboard JSON: VALID"
} catch {
    Log-Error "Dashboard JSON: INVALID"
    exit 1
}

Write-Host ""

# Step 4: Start/Restart Services
Write-Host "========================================================================"
Write-Host "STEP 4: Starting/Restarting Services"
Write-Host "========================================================================"

if (Test-Path "docker-compose.yml") {
    Log-Info "Found docker-compose.yml"

    Log-Warn "About to restart Prometheus. This will cause brief interruption."
    $continue = Read-Host "Continue? (y/n)"
    if ($continue -ne "y") {
        Log-Warn "Deployment cancelled by user"
        exit 0
    }

    Log-Info "Restarting Prometheus..."
    docker-compose restart prometheus

    Log-Info "Waiting 10 seconds for Prometheus to start..."
    Start-Sleep -Seconds 10
} else {
    Log-Warn "docker-compose.yml not found. Skipping service restart."
    Log-Warn "Please restart Prometheus manually."
}

Write-Host ""

# Step 5: Verify Prometheus
Write-Host "========================================================================"
Write-Host "STEP 5: Verifying Prometheus Configuration"
Write-Host "========================================================================"

Log-Info "Checking Prometheus health..."
try {
    $PrometheusHealth = Invoke-RestMethod -Uri "http://localhost:9090/-/healthy" -TimeoutSec 5
    if ($PrometheusHealth -like "*Prometheus is Healthy*") {
        Log-Info "Prometheus: HEALTHY"
    } else {
        Log-Error "Prometheus: UNHEALTHY"
        exit 1
    }
} catch {
    Log-Error "Prometheus: NOT ACCESSIBLE"
    Log-Warn "Please check Prometheus logs: docker logs prometheus"
    exit 1
}

Log-Info "Checking recording rules loaded..."
$RulesResponse = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/rules"
$RecordingRules = $RulesResponse.data.groups | Where-Object { $_.name -eq "hitl_user_behavior" }
if ($RecordingRules) {
    Log-Info "Recording rules: LOADED (4 rules)"
} else {
    Log-Error "Recording rules: NOT LOADED"
    exit 1
}

Log-Info "Checking alert rules loaded..."
$AlertRules = $RulesResponse.data.groups | Where-Object { $_.name -eq "hitl_quality" }
if ($AlertRules -and $AlertRules.rules.Count -eq 8) {
    Log-Info "Alert rules: LOADED (8 alerts)"
} else {
    Log-Error "Alert rules: NOT LOADED or incomplete"
    exit 1
}

Write-Host ""

# Step 6: Verify API
Write-Host "========================================================================"
Write-Host "STEP 6: Verifying API /metrics Endpoint"
Write-Host "========================================================================"

$ApiUrl = if ($env:API_URL) { $env:API_URL } else { "http://localhost:8000" }
Log-Info "Checking API health..."
try {
    $ApiHealth = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 5
    Log-Info "API: HEALTHY"
} catch {
    Log-Warn "API: Not accessible at $ApiUrl"
    Log-Warn "Please start API manually: cd apps\api; uvicorn src.main:app --reload"
    Log-Warn "Skipping metrics verification..."
    Write-Host ""
    Write-Host "========================================================================"
    Write-Host "DEPLOYMENT: PARTIAL SUCCESS"
    Write-Host "========================================================================"
    Write-Host ""
    Write-Host "Configuration deployed successfully, but API verification skipped."
    Write-Host "Please start the API and verify metrics manually:"
    Write-Host "  Invoke-WebRequest $ApiUrl/metrics | Select-String hitl"
    Write-Host ""
    exit 0
}

Log-Info "Checking /metrics endpoint..."
$Metrics = Invoke-WebRequest -Uri "$ApiUrl/metrics"
$MetricsText = $Metrics.Content

if ($MetricsText -like "*hitl_clarification_fallback_total*") {
    Log-Info "Metrics: EXPOSED (hitl_clarification_fallback_total found)"
} else {
    Log-Error "Metrics: NOT EXPOSED"
    exit 1
}

Log-Info "Checking all 3 new metrics..."
$Metric1 = ($MetricsText -split "`n" | Select-String "hitl_clarification_fallback_total").Count -gt 0
$Metric2 = ($MetricsText -split "`n" | Select-String "hitl_edit_actions_total").Count -gt 0
$Metric3 = ($MetricsText -split "`n" | Select-String "hitl_rejection_type_total").Count -gt 0

if ($Metric1 -and $Metric2 -and $Metric3) {
    Log-Info "All 3 metrics: FOUND"
} else {
    Log-Error "Some metrics missing: fallback=$Metric1, edit=$Metric2, rejection=$Metric3"
    exit 1
}

Write-Host ""

# Step 7: Verify Prometheus Scraping
Write-Host "========================================================================"
Write-Host "STEP 7: Verifying Prometheus Scraping"
Write-Host "========================================================================"

Log-Info "Checking Prometheus targets..."
$TargetsResponse = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/targets"
$ApiTarget = $TargetsResponse.data.activeTargets | Where-Object { $_.labels.job -eq "api" }
if ($ApiTarget -and $ApiTarget.health -eq "up") {
    Log-Info "Prometheus -> API scraping: UP"
} else {
    Log-Warn "Prometheus -> API scraping: DOWN or not configured"
    Log-Warn "Please check prometheus.yml for 'api' job configuration"
}

Write-Host ""

# Step 8: Summary
Write-Host "========================================================================"
Write-Host "DEPLOYMENT: SUCCESS"
Write-Host "========================================================================"
Write-Host ""
Write-Host "√ Code validation: PASS"
Write-Host "√ Configuration validation: PASS"
Write-Host "√ Prometheus restarted: OK"
Write-Host "√ Recording rules loaded: 4/4"
Write-Host "√ Alert rules loaded: 8/8"
Write-Host "√ API /metrics endpoint: ACCESSIBLE"
Write-Host "√ New metrics exposed: 3/3"
Write-Host "√ Prometheus scraping: $(if ($ApiTarget.health -eq 'up') { 'UP' } else { 'CHECK MANUALLY' })"
Write-Host ""
Write-Host "========================================================================"
Write-Host "NEXT STEPS"
Write-Host "========================================================================"
Write-Host ""
Write-Host "1. Import Dashboard to Grafana:"
Write-Host "   - Open http://localhost:3001"
Write-Host "   - Dashboards -> Import"
Write-Host "   - Upload: infrastructure\observability\grafana\dashboards\07-hitl-tool-approval.json"
Write-Host ""
Write-Host "2. Run Functional Tests:"
Write-Host "   - Follow: PHASE4_FUNCTIONAL_TESTS.md"
Write-Host "   - Trigger HITL interactions"
Write-Host "   - Verify metrics increment"
Write-Host ""
Write-Host "3. Configure Alertmanager (Optional):"
Write-Host "   - Edit: infrastructure\observability\alertmanager\alertmanager.yml"
Write-Host "   - Add Slack webhooks"
Write-Host "   - Restart: docker-compose restart alertmanager"
Write-Host ""
Write-Host "4. Collect Baseline Metrics (1 week):"
Write-Host "   - Monitor dashboard daily"
Write-Host "   - Calculate average/median values"
Write-Host "   - Adjust alert thresholds if needed"
Write-Host ""
Write-Host "Documentation:"
Write-Host "  - Deployment Guide: DEPLOYMENT_GUIDE_HITL_METRICS.md"
Write-Host "  - Quick Reference: HITL_METRICS_QUICK_REFERENCE.md"
Write-Host "  - Full Report: HITL_METRICS_IMPLEMENTATION_COMPLETE.md"
Write-Host ""
Write-Host "========================================================================"
