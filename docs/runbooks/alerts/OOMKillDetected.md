# OOMKillDetected - Runbook

**Severity**: Warning
**Component**: Host (kernel memory)
**Impact**: One process was killed for lack of memory. A container whose main process is killed restarts by itself (`restart: unless-stopped`); what it was doing at that instant is lost
**SLA Impact**: Depends on the victim — seconds for a stateless container, the running request for the API

---

## 📊 Alert Definition

**Alert Name**: `OOMKillDetected` (core tier, `alerts-core.yml` — ADR-119)

**Prometheus Expression**:
```promql
increase(node_vmstat_oom_kill[15m]) > 0
```

`for: 0m`. No threshold to tune: one kill is the event.

`node_vmstat_oom_kill` is the kernel's own count (`/proc/vmstat`), read by node-exporter.
It covers both a container that reached its compose memory limit and the host running
out of memory as a whole. It is cumulative since boot, so a reboot resets it without
firing.

**Why not cAdvisor's `container_oom_events_total`**: that counter lives with the
container's cgroup. When the kill takes the main process, the cgroup ends before the
next scrape reads the counter. Measured on 2026-11-10 with a 32 MB container killed on
purpose: `node_vmstat_oom_kill` went from 0 to 1, and cAdvisor no longer knew the
container.

**Why this alert exists**: a container killed once restarts once.
`ContainerRestartLoop` needs three starts in 30 minutes and
`ContainerMemoryNearLimit` needs ten minutes above its threshold, so a single kill after
a fast climb reached nobody.

**Labels**:
- `severity`: warning
- `component`: host
- `tier`: core

---

## 🔍 Symptoms

- A container shows a recent start with no deployment beside it (dashboard 03, or
  `docker ps`).
- The daily report lists the alert under « ALERTES DECLENCHEES ».

---

## 🎯 Diagnosis

The counter names no victim. The kernel log does:

```bash
# Who was killed, when, and in which cgroup (the container id is in the cgroup path)
sudo journalctl -k --since "1 hour ago" --output=short-iso | grep -i -E "killed process|oom-kill"
# Map a container id prefix to its name
docker ps -a --no-trunc --format '{{.ID}} {{.Names}}' | grep <id-prefix>
```

`constraint=CONSTRAINT_MEMCG` in the kernel line means a container reached ITS limit;
`constraint=CONSTRAINT_NONE` means the host itself ran out.

For a container that is still the same one (the kill took a child process):

```bash
docker inspect <name> --format 'OOMKilled={{.State.OOMKilled}} restarts={{.RestartCount}}'
CG=/sys/fs/cgroup/system.slice/docker-$(docker inspect -f '{{.Id}}' <name>).scope
cat $CG/memory.events          # oom, oom_kill, max
grep -E "^(anon|file|active_file|inactive_file|shmem) " $CG/memory.stat
```

`docker inspect` describes the CURRENT container only: after a restart it reads
`OOMKilled=false`.

---

## 🛠️ Resolution

1. **A container at its limit** — read what it held: `anon` is what the process
   allocated, `file` is page cache the kernel drops by itself. Anonymous memory near the
   limit is a real need or a leak: compare with the previous days on dashboard 03 before
   raising the limit in `docker-compose.prod.yml`. See
   [ContainerMemoryNearLimit](./ContainerMemoryNearLimit.md) for the per-service causes
   and [ApiWorkerMemoryHigh](./ApiWorkerMemoryHigh.md) for the API workers.
2. **The host as a whole** — a build during a deployment is the usual moment (the
   images are built on the host). Read `node_memory_MemAvailable_bytes` and
   `node_memory_SwapFree_bytes` around the kill.
3. **The sandbox** — a skill or a script killed inside its sandbox container is the
   limit doing its job; the run reports its own failure.

---

## 📚 Related

- [ContainerMemoryNearLimit](./ContainerMemoryNearLimit.md) — the slow approach to a limit
- [ContainerDown](./ContainerDown.md) — the restart loop
- [ADR-119](../../architecture/ADR-119-Alerting-Reactivation-Minimal-Core.md) — the alerting core
