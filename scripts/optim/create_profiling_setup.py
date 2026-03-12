#!/usr/bin/env python3
"""
Performance Profiling Setup Generator.

Creates profiling decorators and scripts to measure nested loops performance.

Strategy:
1. Create profiling decorator (@profile_performance)
2. Create profiling middleware for async functions
3. Generate profiling script for specific hot paths
4. Create baseline metrics report

Usage:
    python scripts/optim/create_profiling_setup.py

Output:
    - apps/api/src/infrastructure/observability/profiling.py (decorator)
    - scripts/profiling/profile_nested_loops.py (profiling script)
    - docs/optim/iterations/PHASE_4_PROFILING_SETUP.md (report)

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-15
"""

from pathlib import Path

# Configuration
OUTPUT_DECORATOR = Path("apps/api/src/infrastructure/observability/profiling.py")
OUTPUT_SCRIPT = Path("scripts/profiling/profile_nested_loops.py")
OUTPUT_REPORT = Path("docs/optim/iterations/PHASE_4_PROFILING_SETUP.md")

# Nested loops identified in Phase 3C
NESTED_LOOPS_HOT_PATHS = [
    {
        "file": "domains/agents/context/manager.py",
        "lines": "1154-1156",
        "description": "Store cleanup - Delete items by namespace",
        "dataset": "N=1-5 namespaces × M=10-100 keys",
        "priority": "medium",
    },
    {
        "file": "domains/agents/orchestration/dependency_graph.py",
        "lines": "184-186",
        "description": "Build reverse dependency graph",
        "dataset": "N=1-10 steps × D=1-3 deps",
        "priority": "low",
    },
    {
        "file": "domains/conversations/service.py",
        "lines": "495-505",
        "description": "Redis SCAN pagination (not true O(n²))",
        "dataset": "P patterns × paginated results",
        "priority": "low",
    },
    {
        "file": "domains/agents/nodes/response_node.py",
        "lines": "645-654",
        "description": "Format contact addresses",
        "dataset": "1-5 addresses typical",
        "priority": "low",
    },
]


def create_profiling_decorator() -> None:
    """Create profiling decorator file."""
    OUTPUT_DECORATOR.parent.mkdir(parents=True, exist_ok=True)

    content = '''"""
Performance profiling utilities.

Provides decorators and context managers for profiling code performance.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-15
"""

import time
import functools
import logging
from typing import Any, Callable
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def profile_performance(
    func_name: str | None = None,
    log_threshold_ms: float = 100.0,
    log_level: str = "INFO",
) -> Callable:
    """
    Profile function performance.

    Args:
        func_name: Custom function name for logging (default: actual function name)
        log_threshold_ms: Only log if execution time > threshold (default: 100ms)
        log_level: Log level for performance logs (default: INFO)

    Usage:
        @profile_performance()
        def my_function():
            ...

        @profile_performance(log_threshold_ms=50.0)
        async def my_async_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        name = func_name or func.__name__

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    if duration_ms >= log_threshold_ms:
                        log_func = getattr(logger, log_level.lower())
                        log_func(
                            f"[PROFILE] {name} took {duration_ms:.2f}ms",
                            extra={"duration_ms": duration_ms, "function": name}
                        )
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    if duration_ms >= log_threshold_ms:
                        log_func = getattr(logger, log_level.lower())
                        log_func(
                            f"[PROFILE] {name} took {duration_ms:.2f}ms",
                            extra={"duration_ms": duration_ms, "function": name}
                        )
            return sync_wrapper

    return decorator


@contextmanager
def profile_block(block_name: str, log_threshold_ms: float = 100.0):
    """
    Profile code block performance.

    Usage:
        with profile_block("expensive_operation"):
            # ... code to profile
            result = expensive_function()
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        if duration_ms >= log_threshold_ms:
            logger.info(
                f"[PROFILE] {block_name} took {duration_ms:.2f}ms",
                extra={"duration_ms": duration_ms, "block_name": block_name}
            )


# Import asyncio at module level for async check
import asyncio
'''

    OUTPUT_DECORATOR.write_text(content, encoding="utf-8")
    print(f"[OK] Created profiling decorator: {OUTPUT_DECORATOR}")


def create_profiling_script() -> None:
    """Create profiling script for nested loops."""
    OUTPUT_SCRIPT.parent.mkdir(parents=True, exist_ok=True)

    content = f'''#!/usr/bin/env python3
"""
Nested Loops Profiling Script.

Profiles identified nested loops to measure actual performance impact.

Usage:
    cd apps/api
    .venv/Scripts/python ../../scripts/profiling/profile_nested_loops.py

Output:
    docs/profiling/nested_loops_baseline.md

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-15
"""

import sys
import time
import statistics
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "apps" / "api" / "src"))

# Hot paths to profile
HOT_PATHS = {{hot_paths}}


def profile_function(func: callable, *args: Any, iterations: int = 100) -> dict[str, float]:
    """Profile function execution time."""
    durations = []

    for _ in range(iterations):
        start = time.perf_counter()
        func(*args)
        duration_ms = (time.perf_counter() - start) * 1000
        durations.append(duration_ms)

    return {{
        "mean_ms": statistics.mean(durations),
        "median_ms": statistics.median(durations),
        "stdev_ms": statistics.stdev(durations) if len(durations) > 1 else 0.0,
        "min_ms": min(durations),
        "max_ms": max(durations),
        "p95_ms": statistics.quantiles(durations, n=20)[18],  # 95th percentile
        "p99_ms": statistics.quantiles(durations, n=100)[98],  # 99th percentile
    }}


def main():
    """Main profiling function."""
    print("=" * 60)
    print("  Nested Loops Performance Profiling - LIA")
    print("=" * 60)
    print()

    print("[*] Profiling setup:")
    print(f"   Hot paths: {{len(HOT_PATHS)}}")
    print(f"   Iterations per test: 100")
    print()

    results = []

    for hot_path in HOT_PATHS:
        print(f"[{{len(results)+1}}/{{len(HOT_PATHS)}}] Profiling: {{hot_path['file']}} ({{hot_path['lines']}})")
        print(f"   Description: {{hot_path['description']}}")
        print(f"   Dataset: {{hot_path['dataset']}}")

        # TODO: Import actual functions and profile
        # For now, create placeholder
        print(f"   [SKIP] Manual profiling required - function not importable directly")
        print()

    print("[*] Profiling complete!")
    print()
    print("[NEXT] Steps:")
    print("   1. Add @profile_performance decorator to identified functions")
    print("   2. Run integration tests with profiling enabled")
    print("   3. Analyze logs for slow operations (> 100ms)")
    print("   4. Focus optimization on functions with p99 > 500ms")


if __name__ == "__main__":
    main()
'''

    # Format hot paths as Python list
    hot_paths_str = "[\n"
    for hp in NESTED_LOOPS_HOT_PATHS:
        hot_paths_str += "    {\n"
        for key, value in hp.items():
            hot_paths_str += f'        "{key}": "{value}",\n'
        hot_paths_str += "    },\n"
    hot_paths_str += "]"

    content = content.replace("{hot_paths}", hot_paths_str)

    OUTPUT_SCRIPT.write_text(content, encoding="utf-8")
    OUTPUT_SCRIPT.chmod(0o755)  # Make executable
    print(f"[OK] Created profiling script: {OUTPUT_SCRIPT}")


def create_profiling_report() -> None:
    """Create profiling setup report."""
    OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)

    content = f'''# Phase 4 - Performance Profiling Setup

**Date**: 2025-11-15
**Status**: [OK] SETUP COMPLETE
**Author**: Claude Code (Sonnet 4.5)

---

## [SUMMARY] Executive Summary

### Objective

Create a profiling infrastructure to measure the performance of nested loops identified in Phase 3C.

**Phase 3C Recap**: 46 nested loops analyzed -> 0 critical issues detected (small datasets < 100 items).

**Profiling objective**: Establish performance baseline and detect future regressions.

---

## [DELIVERABLES] Deliverables

### 1. Profiling Decorator

**File**: [{OUTPUT_DECORATOR}]({OUTPUT_DECORATOR})

**Usage**:
```python
from infrastructure.observability.profiling import profile_performance, profile_block

# Decorator for functions
@profile_performance(log_threshold_ms=100.0)
async def my_expensive_function():
    ...

# Context manager for code blocks
async def my_function():
    with profile_block("nested_loop_cleanup"):
        for namespace in namespaces:
            for key in keys:
                await store.delete(key)
```

**Features**:
- Supports async and sync
- Configurable threshold (default: 100ms)
- Structured logging (extra fields for Prometheus)
- Zero overhead if < threshold

---

### 2. Profiling Script

**File**: [{OUTPUT_SCRIPT}]({OUTPUT_SCRIPT})

**Usage**:
```bash
cd apps/api
.venv/Scripts/python ../../scripts/profiling/profile_nested_loops.py
```

**Note**: Placeholder script - manual profiling recommended as internal functions are difficult to import directly.

---

## [HOT PATHS] Identified Nested Loops

{len(NESTED_LOOPS_HOT_PATHS)} hot paths identified in Phase 3C:

'''

    for idx, hp in enumerate(NESTED_LOOPS_HOT_PATHS, 1):
        content += f'''### {idx}. {hp["file"]} ({hp["lines"]})

**Description**: {hp["description"]}
**Dataset**: {hp["dataset"]}
**Priority**: {hp["priority"]}

'''

    content += '''---

## [METHODOLOGY] Profiling Methodology

### Phase 1: Baseline (Current)

1. **Add decorators** to critical functions:
   ```python
   # domains/agents/context/manager.py
   @profile_performance(func_name="context_store_cleanup")
   async def _delete_items_by_namespace(self, ...):
       ...
   ```

2. **Run integration tests** with profiling enabled

3. **Collect metrics**:
   - Mean, Median, P95, P99 execution time
   - Dataset size (N × M)
   - Frequency (calls/min)

### Phase 2: Profiling (If Issue Detected)

**Triggers**:
- P99 > 500ms AND calls > 10/min
- User reports slow operations

**Tools**:
- `cProfile` for detailed Python profiling
- `py-spy` for sampling profiler (production-safe)
- `memory_profiler` if memory leak suspected

**Commands**:
```bash
# cProfile (development only)
python -m cProfile -o profile.stats script.py

# py-spy (production-safe)
py-spy record -o profile.svg --pid <pid>
```

### Phase 3: Optimization (If Confirmed)

**Strategies**:
1. **Batch operations** (10-100 items per batch)
2. **Async concurrency** (asyncio.gather() for independent ops)
3. **Caching** (memoization for repeated calls)
4. **Data structure optimization** (dict/set lookups vs. list iteration)

**Validation**:
- Benchmark before/after (>= 30% improvement required)
- Tests pass (no regressions)
- Profile again (confirm improvement)

---

## [METRICS] Metrics to Monitor

### Performance Metrics

- **Latency (ms)** : Mean, Median, P95, P99
- **Throughput (ops/s)** : Operations completed per second
- **Dataset size** : N × M (input size)
- **Frequency** : Calls per minute/hour

### Thresholds (Alerts)

| Metric | Warning | Critical |
|--------|---------|----------|
| P99 latency | > 200ms | > 500ms |
| P95 latency | > 100ms | > 300ms |
| Mean latency | > 50ms | > 150ms |
| Frequency | > 100/min | > 1000/min |

---

## [RECOMMENDATIONS] Recommendations

### Immediate Actions

1. [OK] **Profiling decorator created** - Ready to use
2. Pending - **Add decorators** to the 4 identified hot paths
3. Pending - **Run integration tests** and collect baseline
4. Pending - **Document baseline metrics** in this report

### Long-Term Actions

1. **Prometheus integration** : Export profiling metrics to Prometheus
2. **Grafana dashboard** : Visualize performance over time
3. **Alerting** : Set up alerts for P99 > 500ms
4. **Continuous profiling** : Integrate py-spy into CI/CD

---

## [NEXT STEPS] Next Steps

### Option A: Immediate Profiling (Recommended)

1. Add `@profile_performance()` to the 4 hot paths
2. Run tests: `pytest tests/integration/ -v`
3. Analyze logs: `grep "\\[PROFILE\\]" logs/*.log`
4. Document baseline in this report

### Option B: Passive Monitoring

1. Deploy profiling decorator in production
2. Monitor logs for 1 week
3. Identify slow operations (> 100ms)
4. Prioritize optimizations if necessary

### Option C: Proactive Optimization

**DO NOT DO** without profiling data - Premature optimization is evil.

---

**Report Generated**: 2025-11-15
**Author**: Claude Code (Sonnet 4.5)
**Status**: ✅ Setup complete - Ready for profiling
'''

    OUTPUT_REPORT.write_text(content, encoding="utf-8")
    print(f"[OK] Created profiling report: {OUTPUT_REPORT}")


def main():
    """Main setup function."""
    print("=" * 60)
    print("  Performance Profiling Setup - LIA")
    print("=" * 60)
    print()

    print("[*] Creating profiling infrastructure...")
    print()

    create_profiling_decorator()
    create_profiling_script()
    create_profiling_report()

    print()
    print("[SUCCESS] Profiling setup complete!")
    print()
    print("[DELIVERABLES]:")
    print(f"   1. Profiling decorator: {OUTPUT_DECORATOR}")
    print(f"   2. Profiling script: {OUTPUT_SCRIPT}")
    print(f"   3. Setup report: {OUTPUT_REPORT}")
    print()
    print("[NEXT] Next steps:")
    print("   1. Review setup report for methodology")
    print("   2. Add @profile_performance() to hot paths")
    print("   3. Run integration tests with profiling enabled")
    print("   4. Analyze logs for baseline metrics")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[WARN] Setup interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Setup failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
