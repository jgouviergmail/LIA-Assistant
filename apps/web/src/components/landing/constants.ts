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
 * - metrics: Prometheus metric definitions in infrastructure/observability/
 * - tests: backend pytest (~11,100) + frontend vitest
 * - adrs: docs/architecture/ ADR files (numbered up to ADR-127)
 * - releases: CHANGELOG.md release entries
 * - auditScore/auditAreas: 360° technical audit at commit 1b3a0ebc (v1.23.7,
 *   2026-07-10), 24 areas on the ISO/IEC 25010 grid. Full public report +
 *   protocol: docs/audit/ (AUDIT_REPORT_URL below). The i18n key
 *   landing.proof.audit_value carries the locale-formatted display value and
 *   must be updated in the 6 locales whenever auditScore changes.
 */

export const LANDING_STATS = {
  agents: 19,
  tools: 76,
  providers: 7,
  voiceLanguages: 99,
  metrics: 394,
  uiLanguages: 6,
  tests: 11000,
  adrs: 100,
  releases: 148,
  auditScore: '8.5/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
