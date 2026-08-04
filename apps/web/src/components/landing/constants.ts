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
 *   Re-measured 2026-08-02 (v1.27.6) = 89: the three CRM read capabilities
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
 * - metrics: Prometheus metric definitions across src/ — re-measured 2026-08-02
 *   (v1.27.7): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 466,
 *   the two ADR-194/195 counters (planner_fabricated_parameters_restored_total,
 *   semantic_validation_for_each_demand_dropped_total) over the 464 of v1.27.4.
 * - tests: SUM of both suites, rounded DOWN (the landing renders it as "N+").
 *   Re-measured at v1.27.10: backend 18,016 collected (+14 over v1.27.9 —
 *   the hub-count probes and their gate-keeper, the two repository
 *   counters now sharing ONE filter, and the provenance route guards),
 *   frontend 4,830 (+22 — the status-tone module, the priority density
 *   oracle, the tinted count pill and the clickable memories) = 22,846 →
 *   22,800, a strict round-DOWN to the hundred.
 *   Previous re-measure at v1.27.8: backend 17,925, frontend 4,690 = 22,615.
 *   Re-measure every release: the value carried the backend count alone
 *   until v1.25.9.
 * - adrs: docs/architecture/ ADR files (204 files, numbered up to ADR-205 —
 *   ADR-008 has no separate file, so 205 numbers map to 204 files). Was
 *   stranded at 183 from v1.27.0 to v1.27.4: recount it, never carry it over.
 * - releases: CHANGELOG.md release entries — `grep -c '^## \['` MINUS the
 *   `## [Unreleased]` heading when one is present (it is not a release).
 *   197 headings at v1.27.10, no Unreleased pending.
 * - auditScore/auditAreas: technical audit V11 of the 2026-07-16 snapshot
 *   (released as v1.25.0) — 24 normalized areas mapped to ISO/IEC 25010:2023,
 *   arithmetic mean 199/240 = 8.3/10, security out of scope. Full public
 *   report + protocol: docs/audit/ (AUDIT_REPORT_URL below). The i18n key
 *   landing.transparency.p2_t carries the locale-formatted display value and
 *   must be updated in the 6 locales whenever auditScore changes.
 */

export const LANDING_STATS = {
  agents: 20,
  tools: 89,
  providers: 7,
  voiceLanguages: 99,
  metrics: 466,
  uiLanguages: 6,
  tests: 22800,
  adrs: 204,
  releases: 197,
  auditScore: '8.3/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
