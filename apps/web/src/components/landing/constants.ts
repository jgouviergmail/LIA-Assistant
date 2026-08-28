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
 *   CORRECTED at v1.32.0: 102, down from the 105 published since v1.31.1.
 *   That 105 was 102 MEASURED plus 3 PREDICTED — three manifests a release
 *   was expected to register unconditionally (write_spreadsheet,
 *   append_document_text, create_email_filter). Measured on the v1.32.0
 *   production runtime, they are not there: `"tool_manifests": 102` on all
 *   four workers, and no `catalogue_tool_registered` event names any of the
 *   three. They are declared in `drive/catalogue_manifests.py` and
 *   `emails/settings_catalogue_manifests.py` but registered conditionally, so
 *   the running catalogue does not expose them — the same trap this comment
 *   already recorded for five browser manifests. A prediction is not a
 *   measurement, and this tile renders a raw number with no "+".
 *   The v1.31.1 note read: 102 runtime + 3 expected. The +15 over v1.30.11 is the Google API ecosystem
 *   programme: contact groups (3), availability (1), Gmail settings (3),
 *   workspace docs read+write (4), air quality / pollen (2), plus the two
 *   above. Runtime figure, never the grep — the tile renders a raw number.
 *   Previous re-measure at v1.30.11: 90 (the two peer-facing manifests added
 *   since v1.27.0 had never been carried into this tile).
 *   The +4 over the v1.25.27 measurement of 82 is the peer tool family shipped
 *   in v1.27.0 (list_peer_connections, get_peer_availability, get_peer_tasks,
 *   send_peer_message), which had never been carried into this tile.
 * - providers: ProviderType Literal in infrastructure/llm/providers/adapter.py
 *   (openai, anthropic, deepseek, perplexity, ollama, gemini, qwen)
 * - metrics: Prometheus metric definitions across src/ — re-measured 2026-08-27
 *   (v1.32.0): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 486,
 *   the three series of `observability/metrics_llm_config.py` — capability
 *   mismatch, unmapped agent (ADR-244) and reasoning coercion (ADR-245).
 *   Previous re-measure 2026-08-21
 *   (v1.31.1): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 483
 *   (+3: the two push-channel counters and the Web Risk screening counter).
 *   Previous re-measure 2026-08-20
 *   (v1.30.14): `grep -rhE '= (Counter|Gauge|Histogram|Summary)\(' src` = 480
 *   (adaptive candidate evidence, consolidation census + the ADR-232/233
 *   funnels). Previous re-measure 2026-08-16 (v1.30.1): 473,
 *   the no-usage accounting counter and the cache write-skip counter (ADR-220)
 *   over the 471 of v1.29.0 (instance ceiling, administrable capabilities and
 *   demonstrator envelope, ADR-216/217/218; 466 at v1.27.7).
 * - tests: SUM of both suites, rounded DOWN (the landing renders it as "N+").
 *   Re-measured at v1.35.0: backend 20,741 (`pytest tests/unit tests/agents
 *   --collect-only --no-cov`) + frontend 6,344 (`vitest list`) = 27,085
 *   -> 27,000 (unchanged: the ADR-248 suites did not cross the next
 *   thousand, and the figure is rounded DOWN by contract).
 *   Re-measured at v1.34.1: backend 20,698 (`pytest tests/unit tests/agents
 *   --collect-only --no-cov`) + frontend 6,344 (`vitest list`) = 27,042
 *   -> 27,000. The figure goes DOWN from the 27,600 stamped at v1.34.0, which
 *   over-claimed by 558: the number was not re-measured with the documented
 *   commands. A count shown to a visitor is exact or it does not exist, and
 *   correcting it downward costs nothing next to stating it wrong.
 *   Re-measured at v1.33.0: backend 20,409 (`pytest tests/unit tests/agents
 *   --collect-only --no-cov`; +251 — the native-shells programme: the wake
 *   relay's seal/client/service/router, the APNs client, the native OAuth
 *   return across connectors AND MCP, the shell pages/plugin-surface/deep-link
 *   guards) + frontend 6,318 (`vitest list`) = 26,727 → 26,700.
 *   Re-measured at v1.32.0: backend 20,158 (`pytest tests/unit tests/agents
 *   --collect-only --no-cov`) + frontend 6,258 vitest (489 files) = 26,416
 *   -> 26,400. The figure goes DOWN by 400 and that is the point (zero
 *   oversell): ADR-245 replaced a cross-product of four stored reasoning
 *   shapes against four widget values with one shape, and the catalogue
 *   deletion took the widget-conditional suites with it. What replaced them
 *   is fewer tests asserting more — the golden equivalence over the live
 *   configuration, the published-vs-enforced contract, and the invariant that
 *   the identity sentinel never reaches a provider.
 *   Previous re-measure at v1.30.15: backend 19,335 (pytest tests/unit tests/agents,
 *   1,076 files — the prod-log remediation: SSE stream registry + eviction
 *   wiring, GraphInterrupt carve-outs, Brave clamp, OWM 404 verdicts,
 *   event_type capacity guard, web-research timeout family, catalogue
 *   registration order) + frontend 5,869 vitest (468 files) = 25,204
 *   -> 25200.
 *   Previous re-measure at v1.30.14: backend 19,291 (pytest, 1,073 files — the
 *   ADR-233 ontology purge removed more collected items than the evolution
 *   program added; ~155 new: activity timeline, memory supersession,
 *   procedural memory, prosody/readout, proposals inbox, adaptive ReAct) +
 *   frontend 5,859 vitest = 25,150 -> 25,100 (the honest figure goes DOWN
 *   this release; zero oversell doctrine).
 *   Previous re-measure at v1.30.13: backend 19,894 (pytest, 1,131 files) +
 *   frontend 5,816 vitest = 25,710.
 *   Re-measured at v1.30.11: backend 19,100 (1,042 files;
 *   `pytest tests/unit tests/agents --collect-only --no-cov`; +342 — the
 *   tabular import/export foundation (ADR-228): workbook writer/reader and
 *   their OOXML pins, the column-coverage guard against the live schema,
 *   the change-plan engine, the transactional applier, the deterministic
 *   pricing read paths and the unique-active-tariff migration) + frontend
 *   5,812 (463 files — the sheet hook, the import state machine and the
 *   preview dialog with its issue/diff/apply oracles) = 24,912 -> 24,900.
 *   Previous re-measure at v1.30.10: backend 18,758 (1,028 files)
 *   + frontend 5,733
 *   (455 files — the capability↔section table and its derived reverse, the
 *   settings-hub status line with its four silences, the landing release band,
 *   the shared changelog key builders, and the single-form SettingsSection
 *   contract) = 24,491 → 24,400 (the rounded value does not move this time).
 *   Previous re-measure at v1.30.9: backend 18,705
 *   (`pytest tests/unit tests/agents --collect-only --no-cov`; the master-detail
 *   settings program (ADR-227) is frontend-only, and the per-user
 *   document-generation opt-in removal trimmed a few backend suites) +
 *   frontend 5,710 (453 files — shell model, rail, overview, pane with its
 *   honest-absence and focus-ratchet contracts, integrated page journeys, the
 *   two compile-complete registries proven against each section's source, and
 *   the 15 admin sections joining search and deep links) = 24,415 → 24,400.
 *   Previous at v1.30.8: backend 18,710
 *   (`pytest tests/unit tests/agents --collect-only --no-cov`; +92 — the
 *   Document Generation domain (ADR-226): content schemas, sanitization
 *   incl. the proven formula-injection cases, the seven pure renderers
 *   round-tripped through the RAG readers, the pending store, the service
 *   and tool guard chains, catalogue/taxonomy/timeout wiring and the
 *   PDF-inline serving rule) + frontend 5,537 (446 files — the document
 *   cards, reducer/history mapping and the settings opt-in) = 24,247 →
 *   24,200.
 *   Previous at v1.30.7: backend 18,618
 *   (`pytest tests/unit tests/agents --collect-only --no-cov`; +189 — the
 *   Agent Plugins domain: spec-driven manifest and mcp.json validation
 *   against the standard's own examples, staging guards, the
 *   install/update/uninstall orchestrator, provenance invariants on both
 *   the skills and MCP sides, and the account-deletion purge extensions)
 *   + frontend 5,522 (444 files — the Plugins settings section, its
 *   import-report dialog and the two delete-lock guards) = 24,140 → 24,100.
 *   Previous at v1.30.5: backend 18,429
 *   (`pytest tests/unit tests/agents --collect-only --no-cov`; +72 — the
 *   time-slot tariff suites: resolution/overlap/round-trip, admin schema and
 *   service inheritance contracts, both cost chokepoints, Redis blob
 *   compatibility, plus the modal scroll-architecture pin) + frontend 5,501
 *   (442 files — the slot editor helpers and modal journeys) = 23,930 → 23,900.
 *   Previous at v1.30.4: backend 18,357
 *   (`pytest tests/unit tests/agents --collect-only -q --no-cov`; +36 — the
 *   executor failure-propagation contract, the peers manifest pins, the
 *   oversize-clarification i18n and the FOR_EACH measured-claims suites) +
 *   frontend 5,479 = 23,836 → 23,800.
 *   Previous at v1.30.3: backend 18,321 (997 yielding files) + frontend
 *   5,479 (vitest, 442 files — the self-hosted-fonts guards) = 23,800.
 *   Previous at v1.30.2: 18,321 + 5,476 = 23,797 → 23,700; the backend drop
 *   from v1.30.1's 18,369 was ADR-222 deleting ~50 dead-code tests while the
 *   upgrade lots added ~30 behavioral ones.
 *   Previous measurement at v1.30.1: backend 18,369 (997 files) + frontend
 *   5,476 = 23,845 → 23,800.
 *   Previous measurement at v1.30.0: backend 18,254 (990 files) + frontend
 *   5,475 = 23,729 → 23,700.
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
 *   Re-measured at v1.31.2: backend 20,565 (pytest --collect-only, 1,202 files)
 *   + frontend 6,088 (vitest list) = 26,653 → 26,600, a strict round-DOWN to the
 *   hundred. The +91 backend is the RAG-fusion lot (ADR-242: the fusion contract
 *   and its shared harness, the six-language BM25 tokenizer guards, the Gemini
 *   adapter's token/cost contract, the embedding boot guard) and the +12 frontend
 *   is the shared retrieval-settings bar and the recalibrated relevance tiers.
 *   Previous re-measure at v1.31.1: backend 20,474 (pytest --collect-only) + frontend
 *   6,076 (vitest list) = 26,550 → 26,500, a strict round-DOWN to the hundred.
 *   The +1,096 backend is the Google API ecosystem programme landing whole
 *   (11 lots: Places SKU + field masks, Meet, contact groups, Web Risk,
 *   freeBusy, Street View, Gmail history delta, Weather/AQ/Pollen, Sheets/Docs
 *   read+write, Gmail settings, push channels) plus this release's air-quality
 *   enrichment and admin-coverage guards.
 *   Previous re-measure at v1.31.0: backend 19,378 (pytest --collect-only; +43 — the
 *   Python 3.14 migration guards (version-surface guard, native-wheel import
 *   smoke, hermetic Telegram audio pipeline, ADR-241), the rate-limiter
 *   request-id collision pins and the __main__ loop-branch pins) + frontend
 *   6,066 (475 files, vitest; the eyes idle-engine wave and the data-driven
 *   changelog surfaces iterating the new key) = 25,444 → 25,400.
 *   Previous re-measure at v1.30.16: backend 19,335 (1,076 files, pytest
 *   --collect-only, unchanged — frontend-only release) + frontend 6,035
 *   (475 files, vitest; the expressive-eyes wave) = 25,370 → 25,300.
 *   Previous re-measure at v1.30.12: backend 19,844 (1,119 files, pytest
 *   --collect-only) + frontend 5,815 (463 files, vitest) = 25,659 → 25,600.
 *   Previous re-measure at v1.27.14: backend 18,128 (pytest --collect-only) +
 *   frontend 5,018 (vitest) = 23,146 → 23100 (rounded down, the only stat
 *   where "+" stays legitimate by contract).
 *   Previous re-measure at v1.27.12: backend 18,041 (985 files) + frontend
 *   4,987 = 23,028.
 *   Previous re-measure at v1.27.8: backend 17,925, frontend 4,690 = 22,615.
 *   Re-measure every release: the value carried the backend count alone
 *   until v1.25.9.
 * - adrs: docs/architecture/ ADR files — recount every release, never carry it
 *   over (it was stranded at 183 from v1.27.0 to v1.27.4). 241 files at
 *   v1.31.2, numbered up to ADR-242: ADR-008 has no separate file, so the
 *   highest number runs one above the file count.
 * - releases: CHANGELOG.md release entries — `grep -c '^## \['` MINUS the
 *   `## [Unreleased]` heading when one is present (it is not a release).
 *   223 headings at v1.31.2, no Unreleased pending.
 * - auditScore/auditAreas: technical audit V11 of the 2026-07-16 snapshot
 *   (released as v1.25.0) — 24 normalized areas mapped to ISO/IEC 25010:2023,
 *   arithmetic mean 199/240 = 8.3/10, security out of scope. Full public
 *   report + protocol: docs/audit/ (AUDIT_REPORT_URL below). The i18n key
 *   landing.transparency.p2_t carries the locale-formatted display value and
 *   must be updated in the 6 locales whenever auditScore changes.
 */

export const LANDING_STATS = {
  agents: 20,
  tools: 102,
  providers: 7,
  voiceLanguages: 99,
  metrics: 486,
  uiLanguages: 6,
  tests: 27000,
  adrs: 247,
  releases: 231,
  auditScore: '8.3/10',
  auditAreas: 24,
} as const;

/** Public audit report — target of the ProofSection audit tile. */
export const AUDIT_REPORT_URL =
  'https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md';
