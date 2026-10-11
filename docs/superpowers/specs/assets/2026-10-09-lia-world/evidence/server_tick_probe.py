"""Bounded CPU-only characterization, no files, sockets or application data."""

import json
import math
import platform
import resource
import statistics
import time

rows = []
deadline = time.perf_counter() + 3
for population in (5, 10):
    actors = [{'id': i, 'x': 20.0 + i, 'y': 20.0, 'sequence': 0}
              for i in range(population)]
    obstacles = {(x, 4) for x in range(4, 24)} | {(8, y) for y in range(5, 20)}
    durations, bytes_by_tick = [], []
    for tick in range(2000):
        if time.perf_counter() > deadline:
            break
        started = time.perf_counter_ns()
        for actor in actors:
            angle = (tick + actor['id']) * .013
            x = min(63.0, max(0.0, actor['x'] + math.cos(angle) * .03))
            y = min(63.0, max(0.0, actor['y'] + math.sin(angle) * .03))
            if (int(x), int(y)) not in obstacles:
                actor['x'], actor['y'] = x, y
            actor['sequence'] += 1
        payloads = [json.dumps({'epoch': 1, 'sequence': tick,
                                'actors': [a for a in actors if a['id'] != recipient]},
                               separators=(',', ':')).encode('utf-8')
                    for recipient in range(population)]
        durations.append((time.perf_counter_ns() - started) / 1_000_000)
        bytes_by_tick.append(sum(len(p) for p in payloads))
    ordered = sorted(durations)
    rows.append({'population': population, 'iterations': len(ordered),
                 'median_tick_ms': statistics.median(ordered),
                 'p95_tick_ms': ordered[int(len(ordered) * .95)],
                 'mean_payload_bytes_per_tick': statistics.mean(bytes_by_tick),
                 'approx_cpu_fraction_one_core_at_10hz': statistics.mean(ordered) * 10 / 1000})
print(json.dumps({'architecture': platform.machine(), 'python': platform.python_version(),
                  'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  'samples': rows,
                  'limits': 'Synthetic floor update and per-recipient JSON only. No Redis, authentication, WebSocket, real assets, HITL, providers or concurrent application workload measured.'}, indent=2))
