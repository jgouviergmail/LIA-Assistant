/**
 * Centralized landing page statistics.
 * Single source of truth consumed by HeroSection (trust badges), ProofSection
 * (animated counters + engineering proof) and JsonLd (SEO feature list).
 *
 * Verified against the codebase (2026-07):
 * - agents: 18 statically registered domain agents (infrastructure/startup/
 *   agents.py, ADR-123) + MCP iterative agent + sub-agents = 20. Re-measured
 *   2026-07-25: `grep -c 'register_agent(' agents.py` — the telephony agent
 *   had landed without this counter following it.
 * - tools: ToolManifest entries across src/domains/agents/{domain}/catalogue_manifests.py.
 *   Re-measured 2026-07-27 (v1.25.27) = 82, and corrected DOWN from 85 at v1.25.26: this tile
 *   renders the raw number with no "+", so an over-count is a false claim.
 *   Cross-checked against runtime rather than grep alone — production logs
 *   328 `catalogue_tool_registered` events across 4 uvicorn workers = 82 per
 *   worker, which matches `grep -rcE '^[A-Za-z_]+ = ToolManifest\(' src/domains/agents/`.
 * - providers: ProviderType Literal in infrastructure/llm/providers/adapter.py
 *   (openai, anthropic, deepseek, perplexity, ollama, gemini, qwen)
 * - metrics: Prometheus metric definitions across src/ — re-measured 2026-07-27
 *   (v1.25.27): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 444.
 * - tests: SUM of both suites, rounded DOWN (the landing renders it as "N+").
 *   Measured 2026-07-27 (v1.25.27): backend pytest 16,159 collected (854 files)
 *   + frontend vitest 3,473 (296 files) = 19,632. Re-measure both suites every
 *   release: the value carried the backend count alone until v1.25.9, while its
 *   comment already claimed both.
 * - adrs: docs/architecture/ ADR files (162 files, numbered up to ADR-163 —
 *   ADR-008 has no separate file, so 163 numbers map to 162 files).
 * - releases: CHANGELOG.md release entries — `grep -c '^## \['` MINUS the
 *   `## [Unreleased]` heading when one is present (it is not a release).
 *   175 headings, no Unreleased pending.
 * - auditScore/auditAreas: technical audit V11 of the 2026-07-16 snapshot
 *   (released as v1.25.0) — 24 normalized areas mapped to ISO/IEC 25010:2023,
 *   arithmetic mean 199/240 = 8.3/10, security out of scope. Full public
 *   report + protocol: docs/audit/ (AUDIT_REPORT_URL below). The i18n key
 *   landing.transparency.p2_t carries the locale-formatted display value and
 *   must be updated in the 6 locales whenever auditScore changes.
 */

export const LANDING_STATS = {
  agents: 20,
  tools: 82,
  providers: 7,
  voiceLanguages: 99,
  metrics: 444,
  uiLanguages: 6,
  tests: 19000,
  adrs: 162,
  releases: 175,
  auditScore: '8.3/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
