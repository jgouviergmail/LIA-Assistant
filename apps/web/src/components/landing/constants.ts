/**
 * Centralized landing page statistics.
 * Single source of truth consumed by HeroSection (trust badges), ProofSection
 * (animated counters + engineering proof) and JsonLd (SEO feature list).
 *
 * Verified against the codebase (2026-07):
 * - agents: 17 statically registered domain agents (main.py) + MCP iterative
 *   agent + sub-agents → "19+" is the defensible public claim
 * - tools: ToolManifest entries across src/domains/agents/{domain}/catalogue_manifests.py
 * - providers: ProviderType Literal in infrastructure/llm/providers/adapter.py
 *   (openai, anthropic, deepseek, perplexity, ollama, gemini, qwen)
 * - metrics: Prometheus metric definitions in infrastructure/observability/
 * - tests: backend pytest (~11,100) + frontend vitest
 * - adrs: docs/architecture/ ADR files (numbered up to ADR-117)
 * - releases: CHANGELOG.md release entries
 * - auditScore: 360° technical audit, 20 areas, July 2026 (docs/audit/)
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
  releases: 133,
  auditScore: '8.0/10',
} as const;
