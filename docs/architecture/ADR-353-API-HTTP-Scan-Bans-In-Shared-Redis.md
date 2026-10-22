# ADR-353: API HTTP Scan Bans in Shared Redis

**Status:** Accepted

**Date:** 2026-10-19

## Context

Unknown-route scans and repeated credential rejections need a response that
survives a change of API worker. A blanket rule on HTTP 401 or 404 would also
punish expired sessions, concurrent page requests and legitimate missing
resources. The existing global request ceiling and endpoint limits remain
useful, but measure a different signal; their architecture is recorded in
[ADR-017](ADR-017-Rate-Limiting-Architecture.md).

Behind Cloudflare Tunnel, a local firewall sees the tunnel connection rather
than an independently reachable visitor. A local Fail2Ban firewall action
cannot be assumed to block an HTTP visitor merely because a log names that
visitor. Enforcement must happen where the canonical caller can be used in an
admission decision, or at the trusted edge.

## Decision

### Qualify failures at the API boundary

Install the pure-ASGI
[`ScanProtectionMiddleware`](../../apps/api/src/core/http_scan.py) in the
[shared middleware chain](../../apps/api/src/core/middleware.py), outside the
global request limiter and inside CORS, logging and security headers. Check
the existing ban before handing the request to the application. Inspect only
the first response-start message when recording a qualified failure:

| Response | Qualification |
|---|---|
| Unknown-route 404 | No route matched (`scope.get("route") is None`). Count distinct path digests in the scan window; repeating a path or changing its query does not add another distinct member. |
| Resource 404 | A route matched. Do not count it, including a handler reporting that a record does not exist. |
| Credential 401 | Only a POST to the configured API prefix's `/auth/login` or `/auth/mfa/verify`. Give each rejected attempt a fresh fingerprint without inspecting or storing credentials. |
| Other 401 | Do not count it. Expired sessions and ordinary authenticated page requests cannot accumulate scan strikes. |

The qualifying response keeps its original status. Once it creates a ban,
subsequent admitted checks for that address return HTTP 429 with
`error="http_scan_blocked"`, a localized message and the remaining lifetime in
both the JSON body and `Retry-After`. CORS exposes that header to an allowed
browser origin. Outer logging uses the common 429 trace described in
[ADR-354](ADR-354-Canonical-Client-IP-In-Every-HTTP-429.md).

Reuse [`resolve_client_ip`](../../apps/api/src/core/client_ip.py): a parsed
`CF-Connecting-IP` takes precedence, with the existing peer fallback. Redis
keys use the canonical IP representation. The Cloudflare header is trustworthy
only while the deployment prevents untrusted access that bypasses the trusted
proxy chain; this middleware does not establish that network boundary.

Only resolved addresses for which `ip_address(...).is_global` is true are
eligible. Unknown, malformed, loopback, private and other non-global callers
are exempt, as are OPTIONS, non-HTTP scopes and the probe paths declared by
`RATE_LIMIT_GLOBAL_EXEMPT_PATHS`. This preserves internal SSR, health checks
and monitoring. The middleware forwards request and response streams without
buffering bodies or introducing a task group. Recording can delay response
start only within its bounded Redis operation.

### Share atomic windows and fixed bans

[`RedisHTTPScanGuard`](../../apps/api/src/infrastructure/rate_limiting/http_scan.py)
reuses the existing
[`get_redis_cache` pool](../../apps/api/src/infrastructure/cache/redis.py) and
owns no additional connection lifecycle or dependency. All workers consult the
same ban key. Unknown paths and credential attempts have separate rolling
sorted sets and independently configured windows and limits; either reason
can create the common ban for that address.

One Lua EVAL uses Redis TIME to remove expired members, add or refresh the
fingerprint, expire the rolling state and evaluate the threshold atomically.
The transition uses `SET NX EX` for a fixed ban lifetime and clears the
triggering reason's rolling set. It first checks for an existing ban, so
concurrent workers have one creation winner and continued activity cannot
renew that ban. Sorted-set membership is bounded by the configured threshold
and all owned state expires. Admission reads the remaining TTL, rounded up
for the HTTP response; it does not extend it.

Each lookup and each record operation has its own deadline covering pool
access and the Redis command. An error or timeout fails open for that
operation. A timed-out write may already have completed in Redis: degradation
means the result could not be confirmed, not that the write was absent.
Requests already in flight are not cancelled when another request creates a
ban.

The parameter authority is
[`SecuritySettings`](../../apps/api/src/core/config/security.py), backed by
[`HTTP_SCAN_*_DEFAULT` constants](../../apps/api/src/core/constants.py). The
[environment template](../../.env.example) exposes the operator contract:

| Environment setting | Purpose |
|---|---|
| `HTTP_SCAN_PROTECTION_ENABLED` | Enable API scan admission and recording. |
| `HTTP_SCAN_WINDOW_SECONDS` | Rolling window for distinct unknown paths. |
| `HTTP_SCAN_NOT_FOUND_LIMIT` | Distinct unknown paths required for a ban. |
| `HTTP_SCAN_AUTH_WINDOW_SECONDS` | Rolling window for credential rejections. |
| `HTTP_SCAN_AUTH_FAILURE_LIMIT` | Credential rejections required for a ban. |
| `HTTP_SCAN_BAN_SECONDS` | Fixed ban lifetime. |
| `HTTP_SCAN_REDIS_TIMEOUT_SECONDS` | Maximum wait for each Redis guard operation. |

Defaults and validation bounds stay in those sources. The guard supplements
the existing global and endpoint limits; disabling it does not disable them.

### Make degraded protection observable

[`metrics_http_scan.py`](../../apps/api/src/infrastructure/observability/metrics_http_scan.py)
counts new bans by reason, refused requests, and degraded operations by
`check` or `record`. IPs and paths never become metric labels. Redis stores
the address in expiring keys and path digests as members; it stores no query,
username or request body. A ban event identifies the caller in structured
logs, while a degraded event records the operation and exception type.

The [HTTP/API dashboard](../../infrastructure/observability/grafana/dashboards/04-http-api.json)
separates bans, blocked requests and failed guard operations. The existing
[`GlobalRateLimitDegraded` alert](../../infrastructure/observability/prometheus/alerts-core.yml.template)
adds the scan guard's degraded counter to the global limiter's counter, with
an absent series treated as zero on either side. Its existing threshold and
firing duration are preserved. It counts failed operations, not unique
requests, since one request may encounter several degraded guards.

The [diagnostic recipe](../../apps/api/src/domains/diagnostics/evidence_recipes.py)
includes `http_scan_check_failed` and retains the shared dependency query and
existing evidence sanitation. The
[runbook](../runbooks/alerts/GlobalRateLimitDegraded.md) distinguishes failed
ban lookup from an unconfirmed record operation and gives targeted read-only
checks. Repair Redis reachability or latency; a global purge is not a repair.

## Alternatives considered

| Option | Assessment |
|---|---|
| Cloudflare edge controls | Complementary protection can cover web traffic and every exposed hostname before traffic reaches the origin. It needs deployment-specific policy and access; API middleware alone cannot provide that scope. |
| Local Fail2Ban firewall actions | Useful for directly reachable services such as SSH. Behind a tunnel, a visitor IP in a log does not make that visitor the origin connection's peer; firewall bans can miss the visitor or disrupt the shared tunnel. A dedicated edge integration would need separate qualification. |
| Counters in each API worker | Avoid Redis calls, but distribute the budget across workers, lose state on restart and cannot make the ban transition atomic across instances. |

Shared Redis provides a bounded API-level decision using the same caller
identity as the existing limiters. Failing open favors API availability during
a Redis incident and requires the degradation signal to remain actionable.

## Consequences and verification

This protects requests reaching the API. It does not protect frontend-only
hostnames or assets, stop traffic at the edge, or cover every form of abuse.
Slow scans, distributed sources and activity below the configured thresholds
can remain admitted. A public address shared by multiple people also shares
its ban. Normal session and resource errors are excluded, but repeated
credential failures on a shared address can still affect other callers.

Eligible public API requests add a bounded Redis lookup; qualified failures
also add a bounded record operation. A Redis outage weakens enforcement,
including lookup of existing bans. Eviction or loss of the cache database can
remove protection state. Edge controls remain the complementary option when
the origin must be shielded or all hostnames must be covered.

[Middleware unit tests](../../apps/api/tests/unit/core/test_http_scan_protection.py)
cover route/session exclusions, credential failures, public address handling,
canonical identity, CORS/security headers, disablement and bounded fail-open
behavior. [Real Redis tests](../../apps/api/tests/integration/infrastructure/rate_limiting/test_http_scan.py)
cover concurrent guard instances, a single ban creation winner, path
deduplication, independent reasons and addresses, rolling expiry and a ban
lifetime that does not renew. The
[PromQL tests](../../infrastructure/observability/prometheus/tests/alerts_core_test.yml)
cover scan-only degradation and combined signals; the
[diagnostics tests](../../apps/api/tests/unit/domains/diagnostics/test_evidence_recipes.py)
exercise recipe coverage and evidence contracts.

An isolated AMD64 Docker qualification exercised the real middleware on a
minimal FastAPI application with uvicorn, HTTP requests and dedicated Redis.
It checked legitimate errors, unknown-route bans, exemptions, warning traces
and expiring Redis state using probe-specific thresholds. This is not a full
production application or production-threshold qualification. At acceptance,
the production API image had not yet received the patch. This decision records
the implemented contract; activation and verification of the actual production
image, environment and proxy envelope are separate deployment work.

Deployment follow-up, 2026-10-19: the derivative of the current production API
image also passed an isolated native ARM64 probe using the configured production
thresholds for both unknown routes and credential failures. That probe retained
deduplication, admission exemptions, a non-renewing ban lifetime and warning
traces, with its own disposable Redis and network. The API-only activation then
passed readiness and source-hash verification; the other containers were not
recreated. This adds native image and deployment evidence without turning the
minimal probe into a full application or external Cloudflare journey.
