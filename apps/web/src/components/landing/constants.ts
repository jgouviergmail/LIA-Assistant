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
 * - tools: ToolManifest entries across src/domains/agents/{domain}/catalogue_manifests.py.
 *   Re-measured 2026-07-31 (v1.27.3) = 86. This tile renders the raw number
 *   with no "+", so an over-count is a false claim — hence the runtime
 *   cross-check rather than grep alone: production logs 344
 *   `catalogue_tool_registered` events across 4 uvicorn workers = 86 per
 *   worker, matching `grep -rcE '^[A-Za-z_]+ = ToolManifest\(' src/domains/agents/`.
 *   The +4 over the v1.25.27 measurement of 82 is the peer tool family shipped
 *   in v1.27.0 (list_peer_connections, get_peer_availability, get_peer_tasks,
 *   send_peer_message), which had never been carried into this tile.
 * - providers: ProviderType Literal in infrastructure/llm/providers/adapter.py
 *   (openai, anthropic, deepseek, perplexity, ollama, gemini, qwen)
 * - metrics: Prometheus metric definitions across src/ — re-measured 2026-07-31
 *   (v1.27.4): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 464,
 *   the ADR-184 counter (planner_parameter_bounds_corrections_total) over the
 *   463 of v1.27.3.
 * - tests: SUM of both suites, rounded DOWN (the landing renders it as "N+").
 *   Re-measured at v1.27.5: backend 17,415 collected across 933 files (+326
 *   over v1.27.4 — the full contact card, the 360° scope model and routes,
 *   the catalogue/registry parity guard, the tool's honesty matrix, plus the
 *   ADR-191 cross-domain reachability and capability-directive oracles),
 *   frontend 4,447 (+178) = 21,862 → 21,000 (the rounded display is unchanged
 *   since v1.27.2).
 *   Re-measure every release: the value carried the backend count alone
 *   until v1.25.9.
 * - adrs: docs/architecture/ ADR files (190 files, numbered up to ADR-191 —
 *   ADR-008 has no separate file, so 191 numbers map to 190 files). Was
 *   stranded at 183 from v1.27.0 to v1.27.4: recount it, never carry it over.
 * - releases: CHANGELOG.md release entries — `grep -c '^## \['` MINUS the
 *   `## [Unreleased]` heading when one is present (it is not a release).
 *   192 headings at v1.27.5, no Unreleased pending.
 * - auditScore/auditAreas: technical audit V11 of the 2026-07-16 snapshot
 *   (released as v1.25.0) — 24 normalized areas mapped to ISO/IEC 25010:2023,
 *   arithmetic mean 199/240 = 8.3/10, security out of scope. Full public
 *   report + protocol: docs/audit/ (AUDIT_REPORT_URL below). The i18n key
 *   landing.transparency.p2_t carries the locale-formatted display value and
 *   must be updated in the 6 locales whenever auditScore changes.
 */

export const LANDING_STATS = {
  agents: 20,
  tools: 86,
  providers: 7,
  voiceLanguages: 99,
  metrics: 464,
  uiLanguages: 6,
  tests: 21000,
  adrs: 190,
  releases: 192,
  auditScore: '8.3/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
