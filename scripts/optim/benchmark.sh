#!/bin/bash
# Benchmark SSE Streaming Performance
# Usage: ./scripts/benchmark.sh

set -e

echo "🚀 SSE Streaming Performance Benchmark"
echo "========================================"
echo ""

# Check if API is running
if ! docker compose -f docker-compose.dev.yml ps | grep -q "api.*Up"; then
    echo "❌ API container is not running!"
    echo "   Start with: docker compose -f docker-compose.dev.yml up -d"
    exit 1
fi

echo "✅ API container is running"
echo ""

# Run benchmark with test user
echo "📊 Running benchmarks (this may take 30-60 seconds)..."
echo ""

docker compose -f docker-compose.dev.yml exec api python scripts/run_benchmark.py --test-user

echo ""
echo "✅ Benchmark complete!"
echo ""
echo "💡 Tips:"
echo "   - Target SLA: TTFT < 1000ms, Tokens/sec > 20"
echo "   - Run multiple times for consistent results"
echo "   - Compare before/after code changes"
echo ""
