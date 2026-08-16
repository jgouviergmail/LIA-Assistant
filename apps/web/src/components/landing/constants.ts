/**
 * Centralized landing page statistics.
 * Single source of truth consumed by CosmosHero (trust badges), ProofSection
 * (animated counters + engineering proof) and JsonLd (SEO feature list).
 *
 * Verified against the codebase (2026-07):
 * - agents: 18 statically registered domain agents (infrastructure/startup/
 *   agents.py, ADR-123) + MCP iterative agent + sub-agents = 20. Re-measured
 *   2026-07-25: `grep -c 'register_agent(' agents.py` — the telephony agent
 *   had landed without this counter following it.
 * - tools: tool manifests the running catalogue actually EXPOSES, not the count
 *   of `X = ToolManifest(` declarations. Re-measured 2026-08-05 (v1.27.14) = 88,
 *   down from the 89 carried since v1.27.6 — the grep and the runtime had drifted
 *   apart and stopped measuring the same thing: production registers 88, while
 *   the grep returns 89 by counting five browser manifests that no call site in
 *   catalogue_loader.py ever registers, and missing four skill tools built by a
 *   factory rather than assigned at module level. The tile renders a raw number
 *   with no "+", so the runtime figure is the only one that cannot over-claim.
 *   Historical note — Re-measured 2026-08-02 (v1.27.6) = 89: the three CRM read capabilities
 *   (get_calls, get_open_loops, get_peer_messages), each registered in the
 *   domain whose catalogue had none (ADR-193).
 *   Previous measurement 2026-07-31 (v1.27.3) = 86. This tile renders the raw number
 *   with no "+", so an over-count is a false claim — hence the runtime
 *   cross-check rather than grep alone: production logs 344
 *   `catalogue_tool_registered` events across 4 uvicorn workers = 86 per
 *   worker, matching `grep -rcE '^[A-Za-z_]+ = ToolManifest\(' src/domains/agents/`.
 *   The +4 over the v1.25.27 measurement of 82 is the peer tool family shipped
 *   in v1.27.0 (list_peer_connections, get_peer_availability, get_peer_tasks,
 *   send_peer_message), which had never been carried into this tile.
 * - providers: ProviderType Literal in infrastructure/llm/providers/adapter.py
 *   (openai, anthropic, deepseek, perplexity, ollama, gemini, qwen)
 * - metrics: Prometheus metric definitions across src/ — re-measured 2026-08-08
 *   (v1.29.0): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 471,
 *   the five counters of the instance ceiling, the administrable capabilities
 *   and the demonstrator envelope (ADR-216/217/218) over the 466 of v1.27.7.
 *   Previous measurement 2026-08-02 (v1.27.7) = 466.
 * - tests: SUM of both suites, rounded DOWN (the landing renders it as "N+").
 *   Re-measured at v1.30.0: backend 18,254 collected across 990 files
 *   (`pytest tests/unit tests/agents --collect-only -q --no-cov`) + frontend
 *   5,475 (vitest, 441 files) = 23,729 → 23,700.
 *   Previous measurement at v1.29.0: backend 18,206 collected across 987 files
 *   + frontend 5,448 (440 files) = 23,654 → 23,600. The backend figure is LOWER
 *   than v1.28.0's 18,276 and that is correct, not a regression: the isolated
 *   agentic-demonstrator prototype (44 modules, 35 unit suites, 244 tests) was
 *   deleted in favour of running the STANDARD image inside an isolated Compose
 *   envelope — the product demonstrates itself rather than a reduction of
 *   itself. Two POSIX-only suites do not collect on the Windows measurement
 *   host (989 files exist, 987 yield tests), so CI collects marginally more.
 *   Re-measured at v1.27.10: backend 18,016 collected (+14 over v1.27.9 —
 *   the hub-count probes and their gate-keeper, the two repository
 *   counters now sharing ONE filter, and the provenance route guards),
 *   frontend 4,830 (+22 — the status-tone module, the priority density
 *   oracle, the tinted count pill and the clickable memories) = 22,846 →
 *   22,800, a strict round-DOWN to the hundred.
 *   Re-measured at v1.27.14: backend 18,128 (pytest --collect-only) +
 *   frontend 5,018 (vitest) = 23,146 → 23100 (rounded down, the only stat
 *   where "+" stays legitimate by contract).
 *   Previous re-measure at v1.27.12: backend 18,041 (985 files) + frontend
 *   4,987 = 23,028.
 *   Previous re-measure at v1.27.8: backend 17,925, frontend 4,690 = 22,615.
 *   Re-measure every release: the value carried the backend count alone
 *   until v1.25.9.
 * - adrs: docs/architecture/ ADR files — recount every release, never carry it
 *   over (it was stranded at 183 from v1.27.0 to v1.27.4). 218 files at
 *   v1.30.0, numbered up to ADR-219: ADR-008 has no separate file, so the
 *   highest number is always one above the file count.
 * - releases: CHANGELOG.md release entries — `grep -c '^## \['` MINUS the
 *   `## [Unreleased]` heading when one is present (it is not a release).
 *   204 headings at v1.30.0, no Unreleased pending.
 * - auditScore/auditAreas: technical audit V11 of the 2026-07-16 snapshot
 *   (released as v1.25.0) — 24 normalized areas mapped to ISO/IEC 25010:2023,
 *   arithmetic mean 199/240 = 8.3/10, security out of scope. Full public
 *   report + protocol: docs/audit/ (AUDIT_REPORT_URL below). The i18n key
 *   landing.transparency.p2_t carries the locale-formatted display value and
 *   must be updated in the 6 locales whenever auditScore changes.
 */

export const LANDING_STATS = {
  agents: 20,
  tools: 88,
  providers: 7,
  voiceLanguages: 99,
  metrics: 471,
  uiLanguages: 6,
  tests: 23700,
  adrs: 218,
  releases: 204,
  auditScore: '8.3/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
