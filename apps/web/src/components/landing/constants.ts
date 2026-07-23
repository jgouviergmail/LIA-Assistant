/**
 * Centralized landing page statistics.
 * Single source of truth consumed by HeroSection (trust badges), ProofSection
 * (animated counters + engineering proof) and JsonLd (SEO feature list).
 *
 * Verified against the codebase (2026-07):
 * - agents: 17 statically registered domain agents (infrastructure/startup/
 *   agents.py, ADR-123) + MCP iterative agent + sub-agents → "19+" is the
 *   defensible public claim
 * - tools: ToolManifest entries across src/domains/agents/{domain}/catalogue_manifests.py
 * - providers: ProviderType Literal in infrastructure/llm/providers/adapter.py
 *   (openai, anthropic, deepseek, perplexity, ollama, gemini, qwen)
 * - metrics: Prometheus metric definitions across src/ — measured 2026-07-22
 *   (v1.25.12): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 428
 *   (the observability/ folder alone holds 413; helpers define the rest)
 * - tests: SUM of both suites, rounded DOWN (the landing renders it as "N+").
 *   Measured 2026-07-22 (v1.25.15): backend pytest 12,717 collected
 *   + frontend vitest 2,324 (233 files) = 15,041. Re-measure both suites every
 *   release: the value carried the backend count alone until v1.25.9, while its
 *   comment already claimed both.
 * - adrs: docs/architecture/ ADR files (141 files, numbered up to ADR-142 —
 *   the six founding ADRs were reconstituted in this cycle, so files and
 *   numbering now agree).
 * - releases: CHANGELOG.md release entries — `grep -c '^## \['` MINUS the
 *   `## [Unreleased]` heading when one is present (it is not a release).
 *   164 headings, no Unreleased pending.
 * - auditScore/auditAreas: technical audit V11 of the 2026-07-16 snapshot
 *   (released as v1.25.0) — 24 normalized areas mapped to ISO/IEC 25010:2023,
 *   arithmetic mean 199/240 = 8.3/10, security out of scope. Full public
 *   report + protocol: docs/audit/ (AUDIT_REPORT_URL below). The i18n key
 *   landing.transparency.p2_t carries the locale-formatted display value and
 *   must be updated in the 6 locales whenever auditScore changes.
 */

export const LANDING_STATS = {
  agents: 19,
  tools: 76,
  providers: 7,
  voiceLanguages: 99,
  metrics: 431,
  uiLanguages: 6,
  tests: 15000,
  adrs: 141,
  releases: 164,
  auditScore: '8.3/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
