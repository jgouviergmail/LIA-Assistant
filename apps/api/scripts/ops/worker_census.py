"""Census of ONE live API worker: what it holds, by type and by allocator — numbers only.

Injected into a running worker through ``sys.remote_exec`` (PEP 768, Python
3.14), from the API container (the default seccomp profile refuses
``process_vm_writev`` without ``CAP_SYS_PTRACE``, hence ``--privileged``)::

    docker cp apps/api/scripts/ops/worker_census.py lia-api-prod:/tmp/census.py
    docker exec -u 0 --privileged lia-api-prod \\
        python -c "import sys; sys.remote_exec(<worker pid>, '/tmp/census.py')"
    docker exec lia-api-prod cat /tmp/census_<worker pid>.json

The script runs in the worker's main thread at its next bytecode boundary and
pauses it for a few seconds (about six on a Raspberry Pi 5 for 1.7 million
objects). It reads ``/proc/self/status``, glibc's ``mallinfo2``, pymalloc's
``sys._debugmallocstats`` (to a sibling text file), counts the objects the
cyclic collector tracks by type and shallow size, lists the largest containers
and the largest ``functools.lru_cache`` wrappers, then runs one ``gc.collect()``
and one ``malloc_trim(0)`` — both things the process does anyway — and reads
the memory again. Only type names, counts, sizes and attribute names leave the
process: no object content, no string value, nothing a person wrote.

What it must NEVER do: walk the referrers of thousands of objects. That
variant (``gc.get_referrers`` per vector) killed a production worker on
2026-10-12 (ADR-283, amendment). Since the startup heap is frozen,
``gc.get_objects()`` lists only what the worker allocated after its boot; the
frozen part is ``gc.get_freeze_count()`` — and it is the former that grows.
"""

import collections
import ctypes
import functools
import gc
import json
import os
import sys
import time

t0 = time.monotonic()
out: dict[str, object] = {
    "pid": os.getpid(),
    "started_at": time.time(),
    "python": sys.version.split()[0],
}


def rss() -> dict[str, int]:
    d: dict[str, int] = {}
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith(("VmRSS", "RssAnon", "RssFile", "RssShmem", "VmSwap", "VmHWM")):
                k, v = line.split(":")
                d[k] = int(v.split()[0]) // 1024
    return d


out["rss_before_MB"] = rss()

libc = ctypes.CDLL("libc.so.6")


class MallInfo2(ctypes.Structure):
    _fields_ = [
        (n, ctypes.c_size_t)
        for n in (
            "arena",
            "ordblks",
            "smblks",
            "hblks",
            "hblkhd",
            "usmblks",
            "fsmblks",
            "uordblks",
            "fordblks",
            "keepcost",
        )
    ]


libc.mallinfo2.restype = MallInfo2


def mallinfo() -> dict[str, float]:
    mi = libc.mallinfo2()
    return {
        "arena_MB": round(mi.arena / 1048576, 1),
        "mmapped_hblkhd_MB": round(mi.hblkhd / 1048576, 1),
        "in_use_uordblks_MB": round(mi.uordblks / 1048576, 1),
        "free_fordblks_MB": round(mi.fordblks / 1048576, 1),
        "trimmable_top_keepcost_MB": round(mi.keepcost / 1048576, 1),
    }


out["glibc_before"] = mallinfo()

pm_path = f"/tmp/census_pymalloc_{os.getpid()}.txt"
saved = os.dup(2)
try:
    with open(pm_path, "w") as f:
        os.dup2(f.fileno(), 2)
        try:
            sys._debugmallocstats()
        finally:
            os.dup2(saved, 2)
finally:
    os.close(saved)
out["allocated_blocks"] = sys.getallocatedblocks()
out["gc_stats"] = gc.get_stats()
out["gc_frozen"] = gc.get_freeze_count()

t1 = time.monotonic()
objs = gc.get_objects()
out["gc_tracked_objects"] = len(objs)
by_type: collections.Counter[str] = collections.Counter()
size_by_type: collections.Counter[str] = collections.Counter()
big: list[tuple[int, str]] = []
lru: list[tuple[int, int | None, str]] = []
model_classes = 0
for o in objs:
    t = type(o)
    tn = f"{getattr(t, '__module__', '?')}.{getattr(t, '__qualname__', '?')}"
    by_type[tn] += 1
    try:
        size_by_type[tn] += sys.getsizeof(o)
    except Exception:  # noqa: BLE001 - a census never fails on one object
        pass
    try:
        if isinstance(o, (dict, list, set, frozenset, tuple)):
            n = len(o)
            if n >= 5000:
                big.append((n, t.__name__))
        elif isinstance(o, functools._lru_cache_wrapper):
            ci = o.cache_info()
            if ci.currsize >= 50:
                fn = getattr(o, "__wrapped__", o)
                lru.append(
                    (
                        ci.currsize,
                        ci.maxsize,
                        f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', '?')}",
                    )
                )
        elif isinstance(o, type) and any(b.__name__ == "BaseModel" for b in o.__mro__):
            model_classes += 1
    except Exception:  # noqa: BLE001 - another thread may mutate a container meanwhile
        continue
out["top_types_by_count"] = by_type.most_common(50)
out["top_types_by_shallow_size_MB"] = [
    (k, round(v / 1048576, 2)) for k, v in size_by_type.most_common(40)
]
out["sum_shallow_size_tracked_MB"] = round(sum(size_by_type.values()) / 1048576, 1)
out["pydantic_model_classes"] = model_classes
big.sort(reverse=True)
out["big_containers_len_type"] = big[:30]
lru.sort(key=lambda x: x[0], reverse=True)
out["lru_caches_currsize_maxsize_fn"] = lru[:30]
del objs
out["census_seconds"] = round(time.monotonic() - t1, 2)
out["modules_loaded"] = len(sys.modules)

out["gc_collect_freed"] = gc.collect()
out["rss_after_gc_MB"] = rss()
out["malloc_trim_result"] = libc.malloc_trim(0)
out["rss_after_trim_MB"] = rss()
out["glibc_after_trim"] = mallinfo()
out["total_seconds"] = round(time.monotonic() - t0, 2)
with open(f"/tmp/census_{os.getpid()}.json", "w") as f:
    json.dump(out, f, indent=1, default=str)
