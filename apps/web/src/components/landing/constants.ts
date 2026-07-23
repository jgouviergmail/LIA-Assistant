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
 * - metrics: Prometheus metric definitions across src/ — measured 2026-07-23
 *   (v1.25.17): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 437
 *   (MFA/session/export families added by the security program)
 * - tests: SUM of both suites, rounded DOWN (the landing renders it as "N+").
 *   Measured 2026-07-23 (v1.25.17): backend pytest 12,906 collected (760 files)
 *   + frontend vitest 2,533 (259 files) = 15,439. Re-measure both suites every
 *   release: the value carried the backend count alone until v1.25.9, while its
 *   comment already claimed both.
 * - adrs: docs/architecture/ ADR files (145 files, numbered up to ADR-146 —
 *   the six founding ADRs were reconstituted in this cycle, so files and
 *   numbering now agree).
 * - releases: CHANGELOG.md release entries — `grep -c '^## \['` MINUS the
 *   `## [Unreleased]` heading when one is present (it is not a release).
 *   165 headings, no Unreleased pending.
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
  metrics: 437,
  uiLanguages: 6,
  tests: 15400,
  adrs: 145,
  releases: 165,
  auditScore: '8.3/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
