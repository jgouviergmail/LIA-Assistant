# ADR-361 — The egress probe names the failing step and confirms a cut before calling it one

**Status:** Accepted — 2026-10-22, owner request after recurring « Self-check
critical: platform_egress » notifications in production, approved with « ok +
ADR » once the root cause was established from the production logs.

**Amends:** ADR-247 (decision 1: `platform_egress`, « one bounded TCP connect
per tick »).

## Context

Measured on production (v3.3.0), read-only, before the change:

1. **The incidents were almost all one tick long.** 18 `platform_egress`
   incidents since 2026-09-02, 16 of them opened and resolved five minutes
   later, at the next tick; 8 on 2026-10-20 alone. Over the 30 days of snapshot
   retention, about 8,000 probes: 15 critical (13 `TimeoutError`, 2
   `gaierror`), the successes clustered around 14 ms — and a second cluster
   between 4,010 and 4,030 ms.
2. **The 4-second cluster is Docker's embedded DNS resolver.** A container
   resolves through `127.0.0.11`, which forwards to the servers of the host's
   `resolv.conf` and waits 4 s for an answer before failing over to the next
   one. The Docker daemon logs every such failover (`[resolver] failed to query
   external DNS server … i/o timeout`), and for every probe sampled the timeout
   of the probe's own query is logged exactly 4.00 s after it started (9 of 9
   checked). In the five `TimeoutError` incidents checked this way, the first
   server timed out at 4.00 s and the probe gave up at 5 s while the resolver
   was still asking the next one: **the connection was never attempted**, yet
   each incident read « api.openai.com:443 unreachable (TimeoutError) » and
   pointed at the provider.
3. **What lost the packets was outside LIA.** Every incident within the host
   journal's retention was explained: 3 coincided with the host's Wi-Fi
   association dropping, 8 with DNS queries lost upstream while the link held —
   the home Internet access was disrupted on 2026-10-20 (the owner's report;
   the public-site probe recorded 198 lookups slower than 2 s that day, against
   1 to 3 on an ordinary one). No LLM call failed on the network from 16 to
   21 October: the calls paid the latency.
4. **The probe decided on one attempt** whose 5-second budget covered both the
   resolution and the connect, while one resolver failover alone costs 4 s. The
   other way round, a success at 4 s — a resolver that had to fail over — read
   OK beside a 14 ms normal: the thirteen hours of 2026-10-20 during which every
   outbound lookup risked 4 s were visible only as eight critical pages.
5. **The docstring promised « one bounded TCP connect »**, which the code was
   not: `asyncio.open_connection(host, port)` resolved inside the measured
   window.

## Decision

1. **Two named phases.** Each attempt resolves the target through the running
   loop's resolver — the one every outbound call of the process uses — then
   connects to the resolved addresses in the resolver's order, as
   `open_connection` itself would. A failure names its phase and its exception
   class: `name resolution timed out`, `name resolution failed (gaierror)`,
   `connect timed out (name resolution took N ms)`, `connect failed (OSError,
   name resolution took N ms)` — a connect starved by a slow resolution says so.
   The message of an exception is never recorded: it can carry hosts.
2. **A loss is confirmed over paced attempts.** Up to
   `DIAGNOSTICS_EGRESS_PROBE_ATTEMPTS` attempts per tick (default 3, bounds
   1–5), one per `DIAGNOSTICS_EGRESS_PROBE_TIMEOUT_SECONDS` slot: an attempt that
   fails fast waits out its slot, so a loss must outlast (attempts − 1) slots —
   10 s by default — to be critical. The first success ends the tick.
3. **Three verdicts.**
   - **OK**: the first attempt succeeded faster than
     `DIAGNOSTICS_EGRESS_PROBE_SLOW_SECONDS` (default 2 s).
   - **DEGRADED**: reached after a failed attempt, or slower than that
     threshold. Visible on the health page with the phase durations; no
     incident, no notification — incident synchronisation is unchanged
     (degraded neither opens nor resolves).
   - **CRITICAL**: every attempt failed. The incident and the notification of
     ADR-247, now naming the failing phase and the number of attempts.
4. **The slow threshold stays below the attempt budget**, refused at boot
   otherwise (`DiagnosticsSettings.egress_slow_threshold_below_attempt_budget`):
   a success never outlasts its attempt, so a threshold at or above the budget
   would silence the degraded verdict for good. Only a configured probe is held
   to it: without a target the check does not exist, and thresholds that decide
   nothing must not stop an instance from booting after an upgrade.
5. **The reported value is unchanged in meaning**: the duration of the
   successful attempt in milliseconds, resolution included, so the stored series
   stays comparable; the detail of a degraded result carries both phase
   durations.

## Consequences

- On a day like 2026-10-20 the health page reads « degraded » and names the slow
  or recovered resolution, where it used to page the administrator eight times;
  only a loss that outlasts every attempt of a tick still pages. An outage like
  2026-08-28 (`ip_forward = 0`, every connect failing for hours) is still
  critical at the first tick, and a real cut of a minute or more still opens an
  incident — naming the step that failed.
- A failing tick lasts at most attempts × timeout (15 s by default) instead of
  one timeout; the self-check job runs every interval with `max_instances=1`.
- A resolution cancelled by its timeout keeps its executor thread until the
  system resolver gives up. Attempts are sequential, so at most one such thread
  per attempt.
- An open egress incident closes on the first clean tick only: degraded ticks
  keep it open, the doctrine every check already follows.
- `healthy_probes` (the engine tests' fixture) now patches the egress probe
  too: run through the Taskfile, the root `.env` injects a real target, and the
  engine's unit tests used to open a real connection whose speed decided their
  verdicts.

## Alternatives rejected

- **Raising the timeout alone**, to cover one or two resolver failovers: it
  would have absorbed most of these incidents without code, but kept a single
  sample, kept blaming the target for a DNS failure, kept a 4-second failover
  reading OK, and tied the verdict to Docker's internal timings.
- **Confirmation across ticks** (critical only after two consecutive critical
  ticks): it delays a real cut by a whole interval and needs state the
  in-process checks do not keep. Confirming inside the tick is enough to tell a
  hiccup from a cut.
- **A separate `platform_dns` check**: a second correlation key, recipe and set
  of labels for what is one question — can the platform reach the outside —
  whose answer only needed the failing step named.
- **A DNS cache on the host, or Prometheus watching the host's network link**:
  both would serve every outbound call, not only the probe, but they are
  infrastructure decisions of their own and are left for a later lot.

## Implementation references

- `apps/api/src/domains/diagnostics/engine.py` — `_probe_platform_egress`,
  `_egress_attempt`, `_connect_first`, `_egress_success`.
- `apps/api/src/core/config/diagnostics.py` — the two settings and the boot
  refusal; defaults in `apps/api/src/core/constants.py`.
- `apps/api/tests/unit/domains/diagnostics/test_engine.py` —
  `TestPlatformEgressProbe`, `TestIpv6BracketStripping`.
- `docs/technical/DIAGNOSTICS_DOMAIN.md` — « Naming the cause, not only the
  consequence ».
