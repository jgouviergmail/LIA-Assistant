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
 *   (v1.27.3): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 463,
 *   including the two ADR-182 counters (peer_domain_correction_total,
 *   oauth_health_notification_skipped_total).
 * - tests: SUM of both suites, rounded DOWN (the landing renders it as "N+").
 *   Re-measured at v1.27.3: backend 17,025 collected (+217 over v1.27.2 —
 *   ADR-182 peer routing/summaries/owner-defaults, the honest-failure
 *   directive, and the ADR-183 catalogue-closure suites), frontend 4,269
 *   (+19, connector-health banner and shortcut editing) = 21,294 → 21,000
 *   (the rounded display is unchanged since v1.27.2).
 *   Re-measure every release: the value carried the backend count alone
 *   until v1.25.9.
 * - adrs: docs/architecture/ ADR files (182 files, numbered up to ADR-183 —
 *   ADR-008 has no separate file, so 183 numbers map to 182 files).
 * - releases: CHANGELOG.md release entries — `grep -c '^## \['` MINUS the
 *   `## [Unreleased]` heading when one is present (it is not a release).
 *   190 headings at v1.27.3, no Unreleased pending.
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
  metrics: 463,
  uiLanguages: 6,
  tests: 21000,
  adrs: 182,
  releases: 190,
  auditScore: '8.3/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
