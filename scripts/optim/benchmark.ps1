# SSE Streaming Performance Benchmark (PowerShell)
# Usage: .\scripts\benchmark.ps1

Write-Host "🚀 SSE Streaming Performance Benchmark" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if API is running
$apiStatus = docker compose -f docker-compose.dev.yml ps api 2>&1
if ($apiStatus -notmatch "Up") {
    Write-Host "❌ API container is not running!" -ForegroundColor Red
    Write-Host "   Start with: docker compose -f docker-compose.dev.yml up -d" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ API container is running" -ForegroundColor Green
Write-Host ""

# Run benchmark with test user
Write-Host "📊 Running benchmarks (this may take 30-60 seconds)..." -ForegroundColor Yellow
Write-Host ""

docker compose -f docker-compose.dev.yml exec api python scripts/run_benchmark.py --test-user

Write-Host ""
Write-Host "✅ Benchmark complete!" -ForegroundColor Green
Write-Host ""
Write-Host "💡 Tips:" -ForegroundColor Cyan
Write-Host "   - Target SLA: TTFT < 1000ms, Tokens/sec > 20"
Write-Host "   - Run multiple times for consistent results"
Write-Host "   - Compare before/after code changes"
Write-Host ""
