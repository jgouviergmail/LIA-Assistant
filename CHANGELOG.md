# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.13.9] - 2026-04-01

### Added

- **Admin Pagination — Page Size Selector** — All 5 admin tables (Users, Usage Limits, LLM Pricing, Google API Pricing, Image Generation Pricing) now feature a page size selector (10/20/50/100, default 20) with total items count display. Shared `<Pagination>` component enriched with `pageSize`, `onPageSizeChange`, `totalItems`, and `loading` props. (`pagination.tsx`, all Admin*Section components)
- **Admin Users — Full Column Sorting** — All 23 data columns in the admin users table are now sortable, including statistics (messages, tokens, cost), resource counts (connectors, skills, MCP servers, scheduled actions, RAG spaces), preferences (language, voice, memory, tokens display), usage blocked status, and last message date. Backend `getattr()` sorting replaced with a 3-tier mapping: User model fields, COALESCE-wrapped UserStatistics expressions, and labeled subquery columns. (`repository.py`, `AdminUsersSection.tsx`)
- **Admin Users — Memories & Interests Sortable** — Memory count and interest count moved from service-layer batch queries to SQL subqueries in the repository, enabling server-side sorting. Previously unsortable icon columns now clickable. (`repository.py`, `service.py`)
- **Image Generation Pricing — gpt-image-1.5 & gpt-image-1-mini** — Added 18 pricing entries (9 per model: 3 qualities × 3 sizes) for OpenAI's new image models. Applied to both DEV and PROD databases. Seed file already contained the data. (`image_generation_pricing_seed.sql`)

### Fixed

- **Admin Users Sort Consistency** — Fixed inconsistent sort order on statistics columns where NULL values (users without UserStatistics row from LEFT JOIN) appeared mixed with zero values. All statistics sort expressions now wrapped with `func.coalesce(..., 0)` and `nulls_last()` applied to all ORDER BY directions. (`repository.py`)
- **CodeQL — 4 Path Injection Alerts** — `_cleanup_attachment_files()` and `_cleanup_rag_files()` in account deletion service now validate resolved paths with `Path.resolve()` + `is_relative_to()` to block path traversal. (`account_deletion_service.py`)
- **CodeQL — 2 Empty Except Alerts** — Added `logger.debug()` to `except ValueError` and `except json.JSONDecodeError` blocks in memory extractor instead of silent `pass`. (`memory_extractor.py`)

### Changed

- **Admin Pagination UX** — Admin users pagination changed from centered variant (no total) to justified layout with total count, matching usage limits pattern. Default page size reduced from 100 to 20 for all admin tables. (`AdminUsersSection.tsx`, `constants.ts`)

### Documentation

- Updated 16 guide files (why, how, privacy, terms — 6 languages) with v1.13.9 version reference.

## [1.13.8] - 2026-03-31

### Fixed

- **28 CI Test Failures** — Updated unit tests for v1.13.7 account lifecycle changes: mock `_get_memory_counts_batch`/`_get_interests_counts_batch` in search tests, set `deleted_at` on mock users for GDPR soft-delete prerequisite, add `is_deleted=False` to session dependency mocks, update prompt assertion for rewritten journal introspection prompt, fix memory extractor `_parse_items` to reject create actions with missing content/category.
- **4 CodeQL Alerts** — Fixed 3 empty-except blocks (calendar_tools, runtime_helpers, devops_ssh_service) with structured logging. Fixed incomplete URL substring sanitization in event_card.py — replaced `"meet.google.com" in location` with `_is_meet_url()` using `urlparse` for proper domain validation.
- **3 Dependency Vulnerabilities** — Fixed brace-expansion CVE-2024-4068 (medium, zero-step sequence DoS) and CVE-2025-5889 (low, ReDoS) via pnpm override pinned to 2.0.2. Fixed cryptography DNS constraint enforcement (low) via PR #75 bump to 46.0.6.

### Documentation

- **docs/technical/CI_CD.md** — New "Dependency Vulnerability Remediation (pnpm Overrides)" section with rules and override table
- **docs/technical/SECURITY.md** — New "Dependency Vulnerability Management" section covering strategy, CodeQL remediation patterns, URL validation best practice. Revision date updated.

## [1.13.7] - 2026-03-31

### Added

- **Account Lifecycle (4-State Model)** — New account lifecycle: Active → Deactivated → Deleted → Erased (GDPR). Soft-delete purges all personal data (22 tables, LangGraph store/checkpoints, Redis caches, physical files) while preserving billing history (token_usage_logs, user_statistics, google_api_usage_logs). User row kept with email/name for billing contact. ADR-067 documented. (`src/domains/users/account_deletion_service.py`, `src/domains/auth/models.py`)
- **Account Deletion API** — New `DELETE /api/v1/users/admin/{user_id}/delete-account` endpoint for admin soft-delete with precondition enforcement (must be deactivated first). Returns purge counts per table. (`src/domains/users/router.py`)
- **Admin Panel Delete/Erase Buttons** — Deactivated users show "Delete" button (soft-delete), deleted users show "Erase (GDPR)" button (hard-delete). Status badge distinguishes Active/Inactive/Deleted with distinct colors. (`AdminUsersSection.tsx`)
- **Centralized Usage Limit Pre-Check** — New `is_user_blocked_for_llm()` static method combines usage limit check + Prometheus metrics + structured logging in one call. Applied to all LLM-consuming background jobs. (`src/domains/usage_limits/service.py`)
- **Account Status in Usage Limit Enforcement** — `_compute_status()` now checks `is_active` and `deleted_at` as priority 0 (before manual blocks and usage limits). New `BLOCKED_ACCOUNT` status in `UsageLimitStatus` enum. Integrated into `check_user_allowed()` at all 3 code paths (cache hit, DB with limits, DB without limits).

### Changed

- **Background Task Protection (7 jobs)** — All LLM-consuming and connector-related background jobs now filter out inactive/deleted/blocked users: ProactiveTaskRunner (SQL filter), scheduled_action_executor (+is_active check + is_user_blocked_for_llm), reminder_notification (+is_active check), journal_consolidation (+deleted_at filter), token_refresh (JOIN User filter), OAuth health check (+deleted_at filter), session_dependencies (+is_deleted rejection).
- **GDPR Hard-Delete Precondition** — `delete_user_gdpr()` now requires user to be soft-deleted first (`deleted_at IS NOT NULL`). Enforces sequential lifecycle.
- **Usage Limit Cache Invalidation on Deactivation** — `update_user_activation()` now invalidates usage limit Redis cache immediately when deactivating a user, preventing stale cache from allowing LLM calls during the TTL window.
- **LLM Config Auto-Clean reasoning_effort** — When admin changes an LLM type's model to a non-reasoning model (gpt-4.1-*), `reasoning_effort` is automatically cleared. Validator returns `None` instead of warning for non-reasoning OpenAI models. 29 stale `reasoning_effort` values cleaned from LLM_DEFAULTS constants.
- **OAuth Health Check Filtering** — Now excludes deactivated users (`is_active=False`), deleted users (`deleted_at IS NOT NULL`), and usage-blocked users (`is_usage_blocked=True`) from health check queries.

### Fixed

- **philips_hue Enum Mismatch** — Fixed `LookupError: 'philips_hue' is not among the defined enum values` in `GET /api/v1/connectors/admin/global-config`. Migration had inserted lowercase value; corrected to uppercase `PHILIPS_HUE` in production DB.
- **Journal Consolidation UsageLimitExceeded** — Added pre-check before expensive DB queries and prompt building. Previously, the limit was only checked inside `invoke_with_instrumentation()` after all preparatory work was done.
- **Scheduled Action Executor Unprotected** — Was the only LLM-consuming background job with no user status check and no usage limit pre-check. Now has both.
- **admin_broadcasts FK Constraint** — Added `ondelete="SET NULL"` to `sent_by` FK (was missing, would cause FK violation on GDPR hard-delete).
- **google_api_usage_logs FK Preservation** — Changed FK from `CASCADE` to `SET NULL` to preserve billing history when user row is hard-deleted.
- **ConversationMessage.user_id Bug** — Fixed incorrect `DELETE WHERE user_id` on `conversation_messages` table which has no `user_id` column (only `conversation_id`). Now uses subquery via conversation_id.

### Documentation

- **ADR-067** — Account Lifecycle (Active / Deactivated / Deleted / Erased)
- **docs/INDEX.md**, **docs/architecture/ADR_INDEX.md** — Cross-referenced

## [1.13.6] - 2026-03-30

### Added

- **Centralized User Message Embedding Service** — Computes the user message embedding once per conversation turn and caches by text hash. Shared across memory injection, journal injection, memory extraction, and journal extraction. Reduces from 5 redundant embedding API calls to 1 per turn. Includes triviality filter that skips extraction entirely on trivial messages ("ok", "merci", "👍"). (`src/infrastructure/llm/user_message_embedding.py`)
- **Memory PostgreSQL Migration** — Migrated long-term memory storage from LangGraph AsyncPostgresStore to a dedicated SQLAlchemy model (`Memory`) with pgvector HNSW index. Unified with journal's PostgreSQL + pgvector pattern. Full CRUD via `MemoryRepository` and `MemoryService`. Alembic migration + data migration script. ADR-066 documented. (`src/domains/memories/models.py`, `repository.py`, `service.py`)
- **Memory Extraction Create/Update/Delete** — Memory extraction can now update or delete existing memories (micro-consolidation), not just create. LLM sees existing memories with UUIDs and decides actions. Anti-hallucination ID validation. Pinned memories protected from extraction modifications.
- **Interest Extraction Create/Update/Delete** — Interest extraction aligned on the same create/update/delete pattern as memory and journal. LLM can update topics or delete interests the user no longer cares about. Updated prompt, schema, parser, and debug panel.
- **Journal Extraction Semantic Pre-filter** — Replaces `get_all_active()` (all entries) with semantic top-10 + 3 recent. Reduces input tokens from ~7,500 to ~2,500 per extraction call.
- **Debug Panel Reorganization** — Sections reorganized into "Context Injection" (memory, RAG, knowledge, journal) and "Background Extraction" (memory, journal, interest) groups. New `JournalExtractionSection` as separate accordion. Shared `ActionBadge` component for consistent CREATE/UPDATE/DELETE display across all extraction sections.

### Changed

- **Prompt Optimization** — Memory extraction prompt reduced by 65% (1,784→620 tokens), journal introspection by 60% (1,280→508), journal analyst persona by 63% (305→113). Same directives, denser format. Interest extraction prompt rewritten with create/update/delete actions.
- **Emotional State Computation** — Migrated from `semantic_store.py` (LangGraph Items) to `emotional_state.py` (Memory ORM objects). Same DANGER/COMFORT/NEUTRAL algorithm.
- **Memory Cleanup Scheduler** — Rewritten to use `MemoryRepository` instead of LangGraph store. Same retention algorithm (usage + importance + recency).
- **Memory Router** — Rewritten from LangGraph store operations to `MemoryService`. Memory IDs changed from `mem_<12hex>` to UUID format (frontend compatible — uses opaque strings).

### Fixed

- **Journal Third-Party Projection** — Added anti-pattern directive preventing the journal from attributing traits to the user based on third-party subjects ("son's exam postponed" ≠ user procrastinating).
- **Journal Dedup Guard Removed** — Redundant post-extraction LLM merge call removed. The LLM now sees entries with IDs via semantic pre-filter and handles update/delete directly, eliminating unnecessary embedding + LLM calls.
- **Debug Panel Memory Detection Crash** — Fixed `Cannot read properties of undefined (reading 'toFixed')` error when extraction returned update/delete actions without importance/emotional_weight fields.
- **Interest Extraction Confidence Filter** — Fixed confidence threshold blocking delete/update actions (confidence is N/A for non-create actions).

### Documentation

- **ADR-066** — Memory Storage Migration from LangGraph Store to PostgreSQL Custom
- **docs/INDEX.md**, **docs/architecture/ADR_INDEX.md** — Cross-referenced
- **PromptName Literal** — Added 5 missing prompt names (memory + planner prompts)

## [1.13.5] - 2026-03-29

### Added

- **Debug Panel — Memory Detection Section** — New debug panel section showing memories extracted and stored in long-term memory from each user message. Displays: extracted memories with category, emotional weight (-10/+10), importance score, trigger topic, and storage status (success/failure); existing similar memories found during deduplication with semantic similarity scores; LLM metadata (model, input/output/cached tokens). Header badge shows `stored/extracted` count and dedup matches. Mirrors the Interest Detection pattern. (`apps/api/src/domains/agents/services/memory_extractor.py`, `apps/web/src/components/debug/components/sections/MemoryDetectionSection.tsx`)
- **Memory Extraction Debug Cache** — Module-level TTL cache (`_memory_extraction_debug_cache`) in `memory_extractor.py` captures debug data from `extract_memories_background()` keyed by `parent_run_id`. Consumed by `streaming_service.py` via `get_memory_extraction_debug(run_id)` after `await_run_id_tasks` completes. TTL 120s, max 100 entries, lazy eviction on read. 5 unit tests for cache/consume/TTL/size semantics.

### Changed

- **DRY — `getEmotionalLabel` Factorized** — Emotional weight label helper (TRAUMA/NEG/NEU/POS/TRES+) extracted from `MemoryInjectionSection.tsx` and `MemoryDetectionSection.tsx` into shared `formatters.ts`. Both sections now import from the centralized utility.

### Fixed

- **Conversation Deletion — Nested Transaction Error** — `ConversationService.delete_conversation()` wrapped store cleanup SQL in a redundant `async with db.begin()` block, causing `InvalidRequestError` ("A transaction is already begun on this Session") when the session already had an active implicit transaction. Removed the nested `begin()` and executed raw SQL directly on the existing session. (`apps/api/src/domains/conversations/service.py`)

### Documentation

- **6 files updated** — `DEBUG_PANEL_ARCHITECTURE.md` (Memory Detection cache mechanism), `LONG_TERM_MEMORY.md` (troubleshooting point 5: Memory Detection section), `CHANGELOG.md`, `README.md`, version bumps in 16 guide files.

## [1.13.4] - 2026-03-29

### Changed

- **Memory Optimization — E5 → OpenAI Embeddings** — Replaced local E5 model (intfloat/multilingual-e5-small, 384 dims) with OpenAI text-embedding-3-small (1536 dims) for memory search, tool routing, and interest deduplication. Eliminates sentence-transformers + PyTorch CPU from each worker, saving ~1 GB RAM per worker. New `memory_embeddings.py` singleton follows journal/RAG embedding pattern. Alembic migration drops `store_vectors` (auto-recreated by LangGraph with new dimensions) and nulls interest embeddings. Reindex script (`scripts/reindex_embeddings.py`) for post-deploy re-embedding.
- **Memory Optimization — Playwright Lazy Init** — Browser agent Chromium instances no longer launched at startup. Pool initialized on first browser tool call, saving ~1.5 GB RAM at boot (24 Chromium processes eliminated). Cleanup job uses safe no-op function compatible with scheduler leader election pattern.
- **Memory Optimization — Uvicorn Worker Recycling** — Added `--limit-max-requests 10000 --limit-max-requests-jitter 1000` to prevent Python memory fragmentation accumulation across workers.
- **API RAM Usage** — Reduced from 6.73 GB (84% of 8 GB limit) to 2.64 GB (33%) on Raspberry Pi 5 production server. Combined savings: ~4 GB.
- **Embedding Similarity Thresholds** — All E5-calibrated thresholds recalibrated for OpenAI embeddings (more discriminative score distribution). Memory search: 0.88→0.45, hybrid: 0.5→0.4, interest dedup: 0.90→0.75, content dedup: 0.85→0.70. No more hardcoded magic numbers — all thresholds use settings or centralized constants.
- **LLM Configuration Defaults** — `LLM_DEFAULTS` in code aligned with production-tuned settings (44 entries). Strategy: gpt-4.1-nano (domain agents), gpt-4.1-mini (routing), claude-sonnet-4-6 (extraction), qwen3.5-plus (planning), gpt-5.4 (advanced). New SQL seed `llm_config_seed.sql` for fresh installations.
- **Docker Compose** — Removed `HF_HOME`, `TRANSFORMERS_CACHE` env vars and `huggingface_cache` volume from both dev and prod compose files.
- **Dockerfile** — Removed PyTorch CPU override install (no longer needed without sentence-transformers).

### Fixed

- **WebSearchCard Synthesis Border** — Removed left border on AI synthesis block (`with_border=False`) per design intent.
- **WebSearchCard Source Badge Icons** — Source indicator icons (Perplexity, Brave, Wikipedia) now inherit white color in active state instead of being overridden by `lia-icon` default color.
- **networkx Dependency** — Added explicit `networkx==3.6.1` to requirements.txt (was a transitive dependency of sentence-transformers/torch, now needed directly by SemanticIntentDetector type registry).

### Removed

- **sentence-transformers** — Removed from requirements.txt (was pulling PyTorch + ~700 MB in Docker image).
- **Local E5 Embeddings** — `LocalE5Embeddings` class, `get_local_embeddings()`, `preload_embedding_model()` removed from `local_embeddings.py`. File retained for `cosine_similarity()` utility only.
- **HuggingFace Cache** — `huggingface_cache` Docker volume removed (E5 model no longer downloaded at runtime).

### Documentation

- **52 files updated** — All references to E5/local embeddings replaced across README, CLAUDE.md, 6 locale files, 12 landing guides, 20+ technical docs, 8 ADRs. ADR-049 marked as SUPERSEDED. `LOCAL_EMBEDDINGS.md` rewritten as migration notice.

## [1.13.3] - 2026-03-29

### Added

- **Skills Guide Redesign** — Complete rewrite of the in-app skill creation guide with 3 tabbed sections: Fundamentals (3 archetypes, L1/L2/L3 activation model, best practices), Create (SKILL.md format, frontmatter fields, Prompt Expert & Advisory examples, folder structure, references/scripts/assets usage, import process), Advanced (plan templates with auto-trigger, complete agent & tool catalogue with parameters and types organized by category via accordion, Python scripts, internal skill tools). 210 translation keys across 6 languages. (`apps/web/src/components/settings/SkillGuideModal.tsx`)
- **Skills Guide Button Enhancement** — Guide button promoted from subtle text link to prominent outlined Button with primary color, repositioned alongside Import for responsive smartphone layout (stacks vertically on mobile). (`apps/web/src/components/settings/SkillsSettings.tsx`)
- **Admin Users — New Columns** — 5 new columns in user administration: Skills count (user-imported), MCP servers count, Scheduled actions count, RAG spaces count, and Usage blocked status. All counts fetched via efficient correlated subqueries in a single SQL statement. (`apps/api/src/domains/users/repository.py`, `apps/api/src/domains/users/schemas.py`, `apps/web/src/components/settings/AdminUsersSection.tsx`)
- **Admin Limits — Sortable Columns** — Email and Blocked columns now support click-to-sort (asc/desc) with arrow indicators. Backend `GET /usage-limits/admin/users` endpoint extended with `sort_by` and `sort_order` query parameters. (`apps/api/src/domains/usage_limits/router.py`, `apps/api/src/domains/usage_limits/repository.py`, `apps/web/src/components/settings/AdminUsageLimitsSection.tsx`)

### Changed

- **Multi-Provider Naming** — Domain taxonomy display names and descriptions updated from Google-specific ("Google Calendar", "Gmail", "Google Contacts", "Google Drive", "Google Tasks") to provider-agnostic ("Calendar", "Email", "Contacts", "Drive / Files", "Tasks") reflecting the multi-provider connector abstraction (Google, Microsoft, Apple). Updated in: domain taxonomy, skill guide tool catalogue, skill-generator references. (`apps/api/src/domains/agents/registry/domain_taxonomy.py`, `data/skills/system/skill-generator/references/tool-catalogue.md`, `data/skills/system/skill-generator/references/format-specification.md`)

### Fixed

- **PlaceCard Crash Fix** — `_get_next_open_time` method signature was accidentally removed during dead code cleanup, causing `AttributeError` and silent render failure for all place cards. Restored method definition. (`apps/api/src/domains/agents/display/components/place_card.py`)
- **EmailCard Layout** — Sender name `font-weight: 400` (was 500). Date + status icons displayed above sender name. Labels + attachments + thread count merged on same chip line above subject. `chip-row` `margin-bottom` added for spacing below badges.
- **EventCard Polish** — Removed separator line under chips. Year stripped from date chip. Extra vertical margin before location.
- **RouteCard Map Full-Width** — Reverted to original `lia-route__map-link` / `lia-route__map-image` CSS classes instead of generic `lia-card-hero` (which didn't compensate border-left properly). Removed `max-height` constraint on hero images.
- **RouteCard Badges Reorder** — Line 1: arrival + suggested departure. Line 2: traffic + duration + distance. Removed separator under badges. Departure chip shows time only (strips day name).
- **PlaceCard Badges Reorder** — Type + price + distance + stars on same line. Open/closed + opening/closing time on separate line. Added `_get_closing_time()` method + `V3Messages.get_closes_at()` i18n (6 languages). 16px space before address.
- **CSS Card-Top Spacing** — `margin-bottom` increased from `sm` (8px) to `md` (12px) for uniform spacing between title separator and badges across all cards.
- **CSS Card Hero** — Added `overflow: hidden` via `:has(.lia-card-hero)` on parent card. Removed `max-height` on `lia-card-hero img` for natural aspect ratio.
- **DST-Aware Heartbeat Test** — `test_today_event_shows_time_only` now uses dynamic UTC offset for the test date instead of hardcoded `+01:00`, fixing CET→CEST transition failures.

## [1.13.2] - 2026-03-28

### Added

- **Design System v4 — Standardized HTML Card Components** — Complete visual redesign of all 14 HTML cards using a unified component library. 19 reusable CSS components (`lia-card-top`, `lia-illus`, `lia-chip`, `lia-chip-row`, `lia-sec`, `lia-d-row`, `lia-d-item`, `lia-desc-block`, `lia-card-hero`, `lia-tbadge`, `lia-att-row`, `lia-att-av`, `lia-part-list`, `lia-src-link`, `lia-kv-rows`, `lia-review`, `lia-raw-block`, `lia-file-meta`, `lia-illus-sm`). 17 Python helper functions in `base.py`. Every card now uses the same building blocks — zero domain-specific CSS classes. (`apps/web/src/styles/lia-components.css`, `apps/api/src/domains/agents/display/components/base.py`)
- **42px Illustration Vignettes** — Each card header features a colored square-rounded icon (9 color variants: green, red, amber, blue, indigo, purple, teal, orange, gray) with gradient backgrounds and filled Material Symbols icons. Dark mode uses `rgba()` backgrounds.
- **Chip System** — New inline metadata tags with borders and icons (9 variants: green, amber, red, indigo, time, stars, thread, attach, allday). Replaces inconsistent badge usage across cards.
- **Section Headers with Mini-Vignettes** — Collapsible "Voir plus" sections now use 28px mini-illustrations for each section (hours, reviews, services, participants, sources, etc.).
- **Attendee Avatars** — Stacked colored circle avatars showing participant initials with "+N" overflow indicator.
- **Participant Lists with Emails** — Event and email collapsible sections now show each participant with status icon + name + email (mailto: link).
- **Design System Guide** — Comprehensive documentation covering all components, color variants, responsive rules, Python helpers, and how to create new cards. (`docs/guides/GUIDE_DESIGN_SYSTEM.md`)

### Changed

- **All 14 HTML Cards Migrated** — EventCard, EmailCard, ContactCard, PlaceCard, WeatherCard (3 variants), RouteCard, TaskItem, ReminderCard, FileItem, ArticleCard, WebSearchCard, SearchResultCard, McpResultCard — all now use v4 components.
- **Card Layout Normalization** — All cards with `display: flex` (email, event, task, file, article) corrected to `flex-direction: column` for proper v4 vertical layout.
- **Contact Card** — Type badges colored by category (work=indigo, home=green, mobile=amber). Details aligned left. Collapsible uses same `render_d_row` + `render_type_badge` as main card.
- **Place Card** — Photo hero preserved. Chips organized in 3 rows (stars / type+status / price+distance). Collapsible sections with mini-vignettes (hours as KV grid, reviews, services, accessibility, payment).
- **Weather Card** — French weather descriptions added to icon mapping (~20 terms: ciel dégagé, nuageux, pluie, orage, neige, brouillard). Label "Min / Max" changed to "Températures" (6 languages). Sunrise/sunset icon alignment fixed.
- **Route Card** — Title simplified to "→ Destination". ETA displayed as indigo chip. Chips split into 2 rows (arrival+traffic / duration+distance). "Voiture" badge removed (redundant with illustration icon).
- **Task Card** — Unified mobile/desktop rendering (was 2 separate methods). Notes shown directly without "Voir plus".
- **Reminder Card** — Badge + title on same line. "Créé le" prefix added to creation date.
- **File Card** — Type-colored illustration (doc=blue, sheet=green, pdf=red, folder=amber). Chips with separator below.
- **Email Card** — Square-rounded initials avatar. Full-width separator under header. Recipients with emails in collapsible.
- **Article Card** — Wikipedia badge above title. Separator above categories.
- **WebSearch Card** — Source chips above title. Results web with spacing. Sources as icon+link per line.
- **MCP Card** — KV rows for structured data. Raw block for JSON.
- **Event Organizer Email Filter** — Calendar group emails (`@group.calendar.google.com`, `@resource.calendar.google.com`) no longer displayed as organizer email.
- **`render_collapsible()` Enhancement** — New `with_separator` parameter (default `True`). Cards pass `False` when the preceding element already provides a separator.
- **i18n Labels** — Added `get_accessibility_title()` and `get_payment_title()` to V3Messages (6 languages).

### Fixed

- **Email Card Crash** — `V3Messages.get_messages()` and `get_files()` were called but didn't exist, causing silent render failure. Fixed by using numeric-only chip labels.
- **22 Dead Methods Removed** — Cleaned up legacy rendering methods no longer called after v4 migration across 8 card files.

## [1.13.1] - 2026-03-28

### Fixed

- **Calendar/Reminder/Task Timezone DST Bug** — When creating events for dates across DST boundaries (e.g. March 29 during CET→CEST transition), the LLM sent the current offset (+01:00) instead of the target date's offset (+02:00), causing events to be scheduled 1 hour late. `normalize_user_datetime()` now always strips and re-localizes to the correct offset for the target date. Applied to: create/update event, create/update task (due dates), create reminder (trigger_datetime), and event search (time_min/max). (`src/core/time_utils.py`, `src/domains/agents/tools/calendar_tools.py`, `src/domains/agents/tools/tasks_tools.py`, `src/domains/agents/tools/reminder_tools.py`)
- **Context Resolver Cross-Domain Contamination** — Queries like "show me the last email" after viewing calendar events were incorrectly routed to the event domain instead of email. Root cause: the reference resolver detected "the last" as a contextual reference to the previous turn's domain. Fix: context references can only confirm domains already detected by the query analyzer, or fill in when no domain was detected — never override with an unrelated domain. (`src/domains/agents/services/query_analyzer_service.py`)
- **DevOps Semantic Keywords Overmatch** — DevOps tool keywords were too generic ("check server logs", "vérifier les logs"), causing the briefing skill and other requests to be routed to devops. Replaced with Docker-specific prefixed keywords ("devops check docker container logs"). Removed French keywords (English-only convention). (`src/domains/agents/devops/catalogue_manifests.py`)
- **Prod Docker Socket Permissions** — Deploy scripts now auto-detect the host Docker group GID and inject `DOCKER_GID` into `.env` before running `docker compose up`, ensuring `appuser` has socket access on first deploy. (`scripts/deploy/deploy-prod.ps1`, `scripts/deploy/deploy.sh`)
- **Personal Data in Documentation** — Removed personal email addresses and private IP addresses from public documentation files. (`docs/technical/HITL.md`, `docs/guides/GUIDE_DEVOPS_CLAUDE_CLI.md`, `CHANGELOG.md`)

### Changed

- **Prod Memory Optimization** — Replaced PyTorch CUDA with CPU-only version in Dockerfile.prod (~700MB saved per worker on ARM64). Reventilated container RAM limits: Tempo 512M→768M, Web/Prometheus/Grafana/Loki 512M→256M, Redis/Portainer 256M→128M. API stays at 8GB with ~78% usage (was 94%). (`Dockerfile.prod`, `docker-compose.prod.yml`)
- **DomainConfig Priority Removed** — Removed unused `priority` field from `DomainConfig` dataclass and `get_domains_by_priority()` function. Domain selection is handled by LLM intelligence, not numeric priority. (`src/domains/agents/registry/domain_taxonomy.py`)
- **Blog & Guides Enriched** — Added self-enriching anti-hallucination registry documentation to "Execution Plans" blog article (6 languages) and technical guide section 6.4. (`apps/web/locales/`, `apps/web/src/data/guides/how.*.md`)

## [1.13.0] - 2026-03-28

### Added

- **DevOps Claude CLI Integration (Admin-only)** — New `devops` domain with `claude_server_task_tool` that allows administrators to interact with Claude Code CLI installed inside the API Docker containers. Claude CLI independently inspects logs, diagnoses issues, checks container health, and manages Docker services — all through natural language via the LIA assistant. Features: local subprocess execution (no SSH needed), real-time streaming progress via SSE `execution_step` events, session persistence for multi-turn investigations (`--resume`), configurable `--allowedTools`/`--disallowedTools` per server profile (dev: full access, prod: read-only investigation). Access controlled by `is_superuser` DB check with default-deny. (`src/domains/agents/devops/`, `src/domains/agents/tools/devops_tools.py`, `src/domains/agents/services/devops_ssh_service.py`)
- **Claude CLI in Docker Images** — Node.js 22 + Claude Code CLI + Docker CLI installed in both `Dockerfile.dev` and `Dockerfile.prod`. Docker socket mounted for container management. Auth credentials mounted read-only from host. (`Dockerfile.dev`, `Dockerfile.prod`, `docker-compose.dev.yml`, `docker-compose.prod.yml`)
- **DevOps Documentation** — Comprehensive guide covering architecture, prerequisites, deployment, security model, and troubleshooting. (`docs/guides/GUIDE_DEVOPS_CLAUDE_CLI.md`, `docs/INDEX.md`)
- **Alertmanager Email-Only Template** — Simplified template for environments without Slack/PagerDuty. Auto-selected by entrypoint when webhooks are not configured. (`apps/api/monitoring/alertmanager/alertmanager-email-only.yml.template`)

### Changed

- **DevOps Tool Timeout** — `claude_server_task_tool` added to high-latency tools list in parallel executor with 120s timeout (default 30s was causing CancelledError). (`src/domains/agents/orchestration/parallel_executor.py`)
- **Alertmanager Entrypoint** — Rewritten to gracefully handle missing SMTP (minimal log-only config), missing Slack/PagerDuty (email-only template), and inline env comment parsing bug. (`apps/api/monitoring/alertmanager/docker-entrypoint.sh`)

### Fixed

- **PostgreSQL Health Check FATAL Spam** — `pg_isready` health check was missing `-d ${POSTGRES_DB}`, causing PostgreSQL to attempt connection to a database named after the user (~720 FATAL/hour). Fixed in `compose.services.yml`, `docker-compose.dev.yml`, and `docker-compose.prod.yml`.
- **Philips Hue ConnectorType LookupError (Prod)** — Alembic migration inserted `philips_hue` (enum `.value`, lowercase) but SQLAlchemy expects `PHILIPS_HUE` (enum `.name`, uppercase). Fixed migration to use `.name` and added UPDATE for existing data. (`alembic/versions/2026_03_20_0001-add_philips_hue_global_config.py`)
- **Heartbeat ForeignKeyViolation (Prod)** — Proactive heartbeat used a nil UUID (`00000000-...`) as `conversation_id` fallback instead of `None`, violating the FK constraint on `message_token_summary`. Fixed to pass `None` (column is nullable). (`src/infrastructure/proactive/tracking.py`)
- **Heartbeat Journal Embedding Dimension Mismatch (Prod)** — Heartbeat used `get_local_embeddings()` (E5-small, 384 dim) to search journals indexed with OpenAI embeddings (1536 dim). Fixed to use `get_journal_embeddings()`. (`src/domains/heartbeat/context_aggregator.py`)
- **Missing LLM Pricing: claude-3-5-haiku-latest** — Added alias to pricing seed. (`infrastructure/database/seeds/llm_pricing_seed.sql`)
- **Alertmanager Config Error** — `.env` inline comments (`SLACK_WEBHOOK=  # comment`) were parsed as non-empty values, causing `unsupported scheme "" for URL`. Fixed by commenting out unused webhook variables. (`.env`)

## [1.12.4] - 2026-03-27

### Added

- **IoT Discovery-before-Planning** — When controlling Philips Hue lights, the planner now performs a lightweight discovery call to the Hue Bridge before generating the execution plan. Light and room names are injected into the planner context, enabling the LLM to resolve user descriptions (e.g., "plafond du salon") to exact device names ("Plafond salon"). Follows the same pattern as MCP reference discovery. (`src/domains/agents/services/smart_planner_service.py`)

### Changed

- **Landing Page Hero Subtitle** — Reworked hero subtitle into 3 concise lines: personality, orchestration, simplicity. Updated all 6 locale files. (`apps/web/locales/`)
- **Landing Page Image Generation Description** — Updated to cover all 3 use cases: generate from text, refine generated images, edit photos sent as attachments. Updated all 6 locale files. (`apps/web/locales/`)
- **Hue Semantic Keywords** — Aligned with codebase convention: English-only keywords (was the only multilingual outlier across 20 agent catalogues). (`src/domains/agents/hue/catalogue_manifests.py`)

### Fixed

- **Hue Light vs Room Control** — When asking to control a specific light in a room (e.g., "éteins le plafond du salon"), LIA now correctly targets the individual light instead of turning off the entire room. Root cause: semantic keywords in `control_hue_room_tool` contained room names ("salon") causing higher match scores, and `_find_resource_by_name()` used bidirectional partial matching. Fixed via: specificity rule in Hue agent prompt, strict exact-match in `_find_resource_by_name()`, and IoT discovery context injection. (`src/domains/agents/tools/hue_tools.py`, `src/domains/agents/prompts/v1/hue_agent_prompt.txt`, `src/domains/agents/prompts/v1/smart_planner_prompt.txt`)

## [1.12.3] - 2026-03-26

### Added

- **Image Download Button** — Discrete download button on generated images and browser screenshots in the chat. Visible on hover (desktop) or always semi-visible (mobile). Also available in the full-screen lightbox with loading spinner. Uses `fetch` + Blob to bypass cross-origin `<a download>` restrictions. Shared utility `downloadImage()` in `apps/web/src/lib/utils/download-image.ts` with robust MIME extension parsing (`jpeg→jpg`, `svg+xml→svg`), Unicode-safe filename sanitisation, and `response.ok` guard against error blob downloads. (`apps/web/src/components/chat/ChatMessage.tsx`, `apps/web/src/components/ui/image-lightbox.tsx`)

### Fixed

- **Mobile Long-Press "Save Image"** — Native browser context menu ("Save Image") now works on generated images and browser screenshots on iOS Safari and Android Chrome. Root cause: Starlette `FileResponse` defaulted to `Content-Disposition: attachment` when `filename` was provided, which prevented mobile browsers from recognising the resource as a displayable image. Fixed by using `content_disposition_type="inline"` for image MIME types, while keeping `attachment` for non-image files (PDF). (`apps/api/src/domains/attachments/router.py`)

## [1.12.2] - 2026-03-26

### Added

- **Progressive Browser Screenshots** — During browser navigation, screenshots are streamed in real-time via an SSE side-channel to the frontend, displayed as inline overlays in the chat flow. Thumbnails (640px, JPEG q60, ~30KB) provide lightweight visual feedback without LLM processing. Five capture points: navigate, click, fill, press_key, and the new `browser_snapshot_tool`. (`src/infrastructure/browser/session.py`, `src/domains/agents/tools/browser_tools.py`, `apps/web/src/components/chat/BrowserScreenshotOverlay.tsx`)
- **Final Browser Screenshot Card** — Last screenshot from each browsing session saved as an Attachment (full-res 1280px, JPEG q80) and displayed inside the assistant message bubble before markdown content. Persists on page reload via `loadConversationMessages` metadata extraction. Supports lightbox click-to-expand. (`apps/web/src/components/chat/ChatMessage.tsx`, `src/domains/agents/api/service.py`)
- **Generic Side-Channel Queue** — New `__side_channel_queue` in `RunnableConfig.configurable`, a generic `asyncio.Queue` mechanism for any tool to emit SSE events directly to the frontend without going through the LLM response. Fire-and-forget with graceful degradation. (`src/domains/agents/tools/runtime_helpers.py`)
- **`emit_side_channel_chunk()` Helper** — Generic helper in `runtime_helpers.py` for putting `ChatStreamChunk` instances into the side-channel queue. None-safe, never raises, silently drops chunks if queue unavailable. Reusable by any tool domain. (`src/domains/agents/tools/runtime_helpers.py`)
- **`browser_snapshot_tool`** — Fifth screenshot capture point added to the browser ReAct agent, providing a dedicated tool for explicit page snapshots alongside the implicit captures on navigate/click/fill/press_key. (`src/domains/agents/tools/browser_tools.py`)

### Changed

- **Side-Channel Interleaving** — `_interleave_side_channel()` in `service.py` polls the queue every 300ms even during long graph node executions (ReAct browser loop), ensuring real-time screenshot delivery regardless of graph stream timing. (`src/domains/agents/api/service.py`)

### Removed

- **`BROWSER_SCREENSHOT_ENABLED`** — Removed the legacy setting and `browser_screenshot_tool` that sent screenshots to the LLM as base64 text. The LLM cannot analyze images visually, making this tool useless. Replaced by progressive screenshots which stream directly to the user. (`src/core/config/browser.py`, `src/domains/agents/tools/browser_tools.py`)

## [1.12.1] - 2026-03-26

### Added

- **Image Pricing Admin Panel** — New admin section "LLM Image Pricing" under Settings → Administration. Full CRUD for managing per-image pricing by (model, quality, size). Follows the same pattern as LLM Text Pricing: paginated table with search and sorting, create/edit modal, soft-delete with temporal versioning, audit logging, and cache reload. React 19 `useOptimistic` + `useTransition` for instant UI feedback. 5 backend endpoints at `/admin/image-pricing/pricing` (list, create, update, delete, reload-cache). i18n in 6 languages. (`src/domains/image_generation/router.py`, `src/domains/image_generation/schemas.py`, `apps/web/src/components/settings/AdminImagePricingSection.tsx`)

### Changed

- **Admin Section Naming** — Standardized administration section titles across all 6 languages: "Administration des LLM" → "Tarification LLM Texte", "Administration des API Google" → "Tarification API Google", "Tarification génération d'images" → "Tarification LLM Image".

- **Journal Semantic Dedup Guard** — New programmatic guard in journal extraction that prevents duplicate entries. When the LLM proposes a new entry semantically similar to existing ones (cosine similarity ≥ configurable threshold), the system calls a merge LLM to fuse all matching entries into a single enriched directive instead of creating a duplicate. Supports N→1 consolidation: if multiple existing entries match, they are all merged into the primary and the secondaries are deleted. Configurable via `JOURNAL_DEDUP_SIMILARITY_THRESHOLD` (default: 0.72). New `journal_merge_prompt.txt` for LLM-driven entry fusion. Graceful degradation on any failure (embedding, search, or merge). (`src/domains/journals/extraction_service.py`, `prompts/v1/journal_merge_prompt.txt`)

### Changed

- **Admin Section Naming** — Standardized administration section titles across all 6 languages: "Administration des LLM" → "Tarification LLM Texte", "Administration des API Google" → "Tarification API Google", "Tarification génération d'images" → "Tarification LLM Image".
- **Journal Introspection Prompt Rebalanced** — Replaced the hard "prioritize learnings above all" directive with a neutral theme selection guide. Each theme now has multiple non-exhaustive examples and a classification decision tree. Added thematic diversity directive to avoid over-concentration in a single theme. Result: entries are now distributed across `learnings`, `user_observations`, `self_reflection`, and `ideas_analyses` instead of 87% learnings. (`prompts/v1/journal_introspection_prompt.txt`)

### Fixed

- **Image Edit Auto-Resolution** — `edit_image` tool no longer requires a valid UUID for `source_attachment_id`. When the planner passes a textual description instead of a UUID, the tool automatically resolves the most recent image attachment from the database. (`src/domains/agents/tools/image_generation_tools.py`)
- **UnifiedToolOutput.failure Signature** — All 23 `failure()` calls in image generation tools were missing the required `error_code` positional argument, causing `TypeError` on any error path in production. Fixed with appropriate codes (`TOOL_ERROR`, `NOT_FOUND`, `AUTH_ERROR`). (`src/domains/agents/tools/image_generation_tools.py`)
- **Image Generation Timeout on High Quality** — gpt-image-1 in high quality takes 40-90 seconds. The parallel executor now enforces a minimum 90-second timeout for image tools, overriding the planner's default 30s. (`src/domains/agents/orchestration/parallel_executor.py`)
- **Journal Consolidation Prompt Contradiction** — The consolidation prompt contained contradictory instructions: "most runs should produce few actions" vs "dedup is always mandatory." Removed the inhibiting phrase and strengthened STEP 1 (MANDATORY DEDUP) with explicit semantic similarity guidance (same topic from different angles = duplicate). (`prompts/v1/journal_consolidation_prompt.txt`)

### Security

- **Dependency Vulnerability Fix** — Pinned `picomatch@4.0.4` (was 4.0.3 + 2.3.1) to fix 4 Dependabot alerts: 2 high-severity ReDoS via extglob quantifiers and 2 medium-severity method injection in POSIX character classes. Pinned `flatted@3.4.2` for consistency. All overrides use exact versions. (`package.json`)

## [1.12.0] - 2026-03-26

### Added

- **AI Image Generation** — New domain `image_generation` with multi-provider abstract architecture (`ImageGenerationClient` → `OpenAIImageClient` factory). Users can generate images from text prompts via the `generate_image` tool, with results displayed as cards below the assistant response. Supports gpt-image-1 (low/medium/high quality, 3 size presets). Images saved as attachments on disk with ownership tracking. Cost tracking integrated into `TrackingContext` → `MessageTokenSummary` → `UserStatistics` → `UsageLimits`. Pricing loaded at startup with class-level in-memory cache and cross-worker Redis Pub/Sub invalidation. (`src/domains/image_generation/`, `src/domains/agents/tools/image_generation_tools.py`)
- **AI Image Editing** — New `edit_image` tool for modifying existing images via text instructions using the OpenAI Responses API (`images.generate` with `image` parameter). Auto-resolves the most recent image attachment when no UUID is provided — the planner never needs to know attachment IDs. Includes intelligent resize to the nearest supported dimension (1024×1024, 1024×1536, 1536×1024) preserving aspect ratio, with size-aware cost calculation. (`src/domains/agents/tools/image_generation_tools.py`, `src/domains/image_generation/resize.py`)
- **Image Generation User Preferences** — Per-user settings for quality (low/medium/high), size (square/portrait/landscape), and output format (png/webp). Defaults: enabled, low quality, portrait, PNG. Configurable in Settings → Preferences. Tools always use user preferences for cost control — planner cannot override. (`src/domains/auth/models.py`, `apps/web/src/components/settings/ImageGenerationSettings.tsx`)
- **Image Generation Admin Configuration** — `image_generation` LLM type added to `LLM_TYPES_REGISTRY` (category: specialized). Administrators can select model and provider in the LLM Configuration panel. Pricing seed data for gpt-image-1 (9 combinations: 3 qualities × 3 sizes). (`src/domains/llm_config/constants.py`, `infrastructure/database/seeds/image_generation_pricing_seed.sql`)
- **Image Generation Debug Panel** — Image generation calls appear in LLM Pipeline, LLM Calls, and Execution Times sections of the debug panel. Synthetic node record with model, quality, size, image count, and cost. (`src/domains/agents/api/service.py`)
- **Image Generation Catalogue & Domain** — `image_generation` domain registered in `domain_taxonomy.py` with `image_generation_agent` containing `generate_image` and `edit_image` tools. Full catalogue manifests with semantic keywords, cost profiles, and parameter schemas. 120-second agent timeout to accommodate high-quality generation latency. (`src/domains/agents/image_generation/catalogue_manifests.py`, `src/domains/agents/registry/domain_taxonomy.py`)
- **Generated Image Persistence** — Images stored as attachments with conversation-scoped metadata (`generated_images` array in message metadata). Survive page reload via `loadConversationMessages` metadata extraction. SSE `done` chunk includes `generated_images` for real-time display. Cascade deletion on conversation delete via existing attachment cleanup. (`apps/web/src/components/chat/ChatMessage.tsx`, `apps/web/src/hooks/useConversation.ts`)

### Fixed

- **Image Generation Tool Timeout on High Quality** — gpt-image-1 in high quality takes 40-90 seconds, but the parallel executor imposed a 30-second timeout (from planner LLM or default). Added minimum timeout enforcement for image tools: `max(step_timeout, 90s)` capped at 120s. (`src/domains/agents/orchestration/parallel_executor.py`)
- **Adaptive Replanner Marking Image Results as Empty** — `generate_image` returned a plain string, which the adaptive replanner classified as `empty_results`, triggering an unnecessary replan. Fixed by returning `UnifiedToolOutput.action_success()` with structured data. (`src/domains/agents/tools/image_generation_tools.py`, `src/domains/agents/orchestration/adaptive_replanner.py`)
- **UnifiedToolOutput.failure Missing error_code** — All 23 `failure()` calls in image generation tools were missing the required `error_code` positional argument, causing `TypeError` on any error path. Fixed with appropriate error codes (`TOOL_ERROR`, `NOT_FOUND`, `AUTH_ERROR`). (`src/domains/agents/tools/image_generation_tools.py`)
- **Edit Image Auto-Resolution** — Planner passed textual descriptions (e.g., "the photo of the black and white cat") instead of UUIDs for `source_attachment_id`. Fixed by making the parameter optional and auto-resolving the most recent image attachment from the database when no valid UUID is provided. (`src/domains/agents/tools/image_generation_tools.py`)

### Changed

- **Settings Layout Reorganization** — Moved Channels, Voice Mode, and Image Generation from Features tab to Preferences tab for better UX grouping. (`apps/web/src/app/[lng]/dashboard/settings/page.tsx`)

## [1.11.5] - 2026-03-25

### Fixed

- **Chat Message Bubble Content Truncation** — Markdown tables (and occasionally other long content) caused the assistant's response bubble to visually cut off. Root cause: `overflow: hidden` on `.message-bubble` and `.message-bubble-assistant` created an implicit scroll container that miscalculated intrinsic height when nested elements (like `table-wrapper`) had their own overflow. Fixed by replacing `overflow: hidden` with `overflow-x: clip; overflow-y: visible` — clips horizontal overflow without creating a scroll container, allowing the bubble to size correctly to its content. (`apps/web/src/styles/globals.css`)
- **76-Second Latency Spike After Response (Currency API Timeout Storm)** — After each assistant response, a ~76-second delay blocked the debug panel and new messages. Root cause: `CurrencyRateService` was instantiated fresh on every call in `business_metrics`, losing its in-memory cache each time. When the frankfurter.app currency API became unreachable from Docker, each instance retried 3 times × 5s timeout + exponential backoff = ~19s per call × 4 sequential calls = 76s blocking in `response_node`. Fixed with three changes: (1) cache promoted from instance-level to class-level (`_rate_cache` class dict shared across all instances); (2) negative-result cache (`_negative_cache`, 5-minute TTL) prevents retries after API failure; (3) retry policy reduced from 3 attempts to 2, with shorter backoff (`min=1, max=3` instead of `min=2, max=10`). Worst case drops from ~76s to ~6s on first failure, then 0s for 5 minutes. (`src/infrastructure/external/currency_api.py`, `tests/unit/test_currency_api.py`)
- **Route Arrival/Departure Time Off by 1 Hour (Naive Datetime Treated as UTC)** — When the user asked "arrive at 21h", the LLM passed `2026-03-26T21:00:00` (naive, no timezone) to the route tool. `parse_datetime()` defaulted naive datetimes to UTC, then `convert_to_user_timezone()` converted UTC 21:00 → Paris 22:00. The map and response showed 22h instead of 21h. Fixed by adding `normalize_user_datetime()` utility in `time_utils.py` that detects naive datetime strings (no `Z` or `+/-` offset) and attaches the user's timezone offset directly, without UTC conversion. Applied to both `arrival_time` and `departure_time` in `get_route_tool`. Datetimes with explicit timezone (from calendar events, APIs) are left unchanged. (`src/core/time_utils.py`, `src/domains/agents/tools/routes_tools.py`)

## [1.11.4] - 2026-03-25

### Fixed

- **HITL Draft Recipient Modification Ignored by LLM** — When a user requested a recipient change during draft critique (e.g., "non envoi à user@example.com"), the HITL classifier correctly detected `REPLAN` (converted to `EDIT`), and the `DraftModificationService` called the LLM, but the LLM consistently returned the original recipients unchanged. Root cause: the draft modifier prompt rule 2 ("Respect existing context (recipient, structure, etc.)") contradicted recipient change instructions, and rule 6 only covered contact references (`@carven`) — not direct email addresses. Fixed with a three-layer approach: (1) prompt rule 2 reworded to not protect recipients, rule 6 expanded to cover direct email addresses; (2) `_build_context_info()` now labels recipients as "modifiable" instead of presenting them as fixed context; (3) new `_apply_explicit_recipient_override()` post-processing extracts email addresses from instructions via regex and applies them directly when the LLM fails to change the `to`/`cc` fields. Also resolves contact names from instructions against the contact context as fallback. (`src/domains/agents/services/hitl/draft_modifier.py`, `src/domains/agents/prompts/v1/draft_modifier_prompt.txt`)

### Changed

- **Docker Dev Log Level Set to DEBUG** — `docker-compose.dev.yml` now overrides `LOG_LEVEL=DEBUG` for the API container, ensuring all debug-level logs (including LLM prompts, raw responses, and detailed state transitions) are visible during development without requiring `.env` changes. (`docker-compose.dev.yml`)
- **Draft Modifier Debug Observability** — Added 3 debug-level logs to `DraftModificationService`: `draft_modification_prompt_built` (system prompt preview), `draft_modification_llm_raw_response` (LLM raw output), and `actual_changes` field in `draft_modification_completed` (lists only fields that actually changed vs. all fields returned). Enables rapid diagnosis of LLM modification failures. (`src/domains/agents/services/hitl/draft_modifier.py`)

## [1.11.3] - 2026-03-25

### Security

- **SSRF Prevention in Profile Image Proxy** — `GET /profile-image-proxy` validated the initial URL hostname against `ALLOWED_IMAGE_DOMAINS` but used `follow_redirects=True` without post-redirect validation. An authenticated attacker could craft a Google CDN URL that redirects to internal services (metadata endpoints, private network). Fixed by validating the final response URL hostname after redirects. Reuses the same allowlist pattern as the pre-fetch check. (`src/domains/auth/router.py`)
- **SSRF Prevention in Philips Hue Pairing** — `POST /connectors/philips-hue/pair` accepted an unvalidated `bridge_ip` string parameter, allowing requests to arbitrary hosts (including cloud metadata endpoints, internal services). Added `_HueBridgeIpValidatorMixin` Pydantic validator enforcing private IPv4 addresses only (RFC 1918), rejecting loopback, public IPs, and IPv6. Applied to both `HuePairingRequest` and `HueLocalActivationRequest` schemas. (`src/domains/connectors/schemas.py`)
- **OAuth Redirect Parameter Injection** — Hue OAuth callback embedded the raw `error` query parameter from the OAuth provider directly into the redirect URL without sanitization. This was the only OAuth callback (out of 10) that bypassed the centralized `handle_oauth_callback_error_redirect()` handler. Fixed by aligning with the pattern used by all 9 other callbacks (Gmail, Google Contacts/Calendar/Drive/Tasks, Microsoft x4), which classifies errors via `OAuthCallbackErrorCode` enum values. Also aligned success redirect path to `/dashboard/settings` for consistency. (`src/domains/connectors/router.py`)
- **Incomplete URL Substring Sanitization** — `MarkdownContent.tsx` used `src.includes('googleusercontent.com')` to detect Google profile photos, which could match substrings in unrelated hostnames (e.g., `evil-googleusercontent.com`). Fixed by using `new URL(src).hostname` with exact match against the existing `GOOGLE_IMAGE_DOMAINS` array (exported from `utils.ts`). (`apps/web/src/components/chat/MarkdownContent.tsx`, `apps/web/src/lib/utils.ts`)

### Fixed

- **Journal Size Warning Logic** — `if usage_pct > 80` / `elif usage_pct > 100` conditions were ordered incorrectly: the first branch captured all values above 80 (including >100), making the "CRITICAL: exceeded limit" message unreachable. Users exceeding 100% saw the softer "approaching limit" warning instead. Fixed by reversing condition order (>100 first, then >80). (`src/domains/journals/extraction_service.py`)
- **Duplicate Constant Definition** — `MAX_AGENT_RESULTS_DEFAULT` was defined twice in `constants.py` (lines 1687 and 1891) with identical value. Removed the duplicate at line 1891 (misplaced in the observability section). (`src/core/constants.py`)
- **Implicit String Concatenation in List** — Adjacent string literals in `context_builder.py` list were implicitly concatenated without parentheses, creating a fragile pattern where a missing comma could silently change behavior. Wrapped in explicit parentheses. (`src/domains/journals/context_builder.py`)
- **Empty Except Blocks (10 alerts)** — Added explanatory comments to 6 justified cleanup/fallback `except` blocks (browser session close, pool memory probe, leader elector task cancel, Hue color parsing). Added `logger.debug()` to 2 parsing fallbacks (JSON recovery, UUID validation) and `logger.warning()` to 1 service load failure (personality service in journal extraction). 1 alert was a false positive (browser_tools.py except block was not actually empty). (`src/infrastructure/browser/session.py`, `src/infrastructure/browser/pool.py`, `src/infrastructure/scheduler/leader_elector.py`, `src/domains/journals/extraction_service.py`, `src/domains/connectors/clients/philips_hue_client.py`)
- **TLS Certificate Validation Comment** — Added explicit justification comment for `verify=False` in Hue bridge pairing (bridges use self-signed certificates by design). (`src/domains/connectors/clients/philips_hue_client.py`)

## [1.11.2] - 2026-03-25

### Changed

- **Complete Environment Configuration Overhaul** — All 8 `.env` files reorganized into 73 numbered sections with Table of Contents, standardized English comments (usage, impact, valid values), and full cross-file consistency. Files: `.env`, `.env.example`, `.env.prod`, `.env.prod.example`, `.env.min.prod`, `apps/web/.env.local.example`, `apps/web/.env.local.prod`, `apps/api/.env.test`. Section numbering is consistent across dev and prod files (prod skips `[07] SSL`). All comments are succinct inline format with column-aligned padding.
- **98 Missing Settings Keys Added** — Audit of all 18 Pydantic config modules (645 total fields) against `.env.example` revealed 98 non-LLM Settings fields that had no `.env` entry. All added with default values from `constants.py`, organized in their correct sections. Categories: scoring thresholds (18), HITL (9), context resolution (6), planner/orchestration (11), memory extraction (5), browser (7), RAG (6), and more.

### Fixed

- **`PLACE_CAROUSEL_ENABLED` Settings Violation** — Was read directly via `os.environ.get()` in `constants.py`, bypassing the Settings system. Migrated to `ConnectorsSettings.place_carousel_enabled` field with `PLACE_CAROUSEL_ENABLED_DEFAULT` constant. Removed orphan `import os` from `constants.py`. Updated both usages in `places_tools.py` to read from `settings.place_carousel_enabled`. (`src/core/constants.py`, `src/core/config/connectors.py`, `src/domains/agents/tools/places_tools.py`)
- **`RATE_LIMITING_ENABLED` Typo in `.env.test`** — Was `RATE_LIMITING_ENABLED=false` (non-existent field), corrected to `RATE_LIMIT_ENABLED=false` (actual `ConnectorsSettings.rate_limit_enabled` field).
- **`list[str]` Fields JSON Format** — `APPROVAL_AUTO_APPROVE_ROLES` and `APPROVAL_SENSITIVE_CLASSIFICATIONS` were added with comma-separated format (`admin,power_user`) which Pydantic-settings cannot parse for `list[str]` fields. Fixed to JSON format (`["admin","power_user"]`).
- **`ASSISTANT_NAME` Removed from `.env.min.prod`** — Was present as an env var but is actually a hardcoded constant in `constants.py` (not a Settings field). Removed to prevent confusion.
- **`.env.prod.example` Section Numbering** — SSL section removal caused all subsequent sections to be renumbered `[07]-[72]` instead of keeping `[08]-[73]`. Fixed to maintain consistent numbering with `.env.example`. Also fixed em-dash `—` replaced by `--` in section headers.

### Documentation

- Updated `docs/technical/MCP_INTEGRATION.md` with MCP settings completeness
- Updated `docs/technical/LLM_CONFIG_ADMIN.md` with note about LLM per-agent keys not in `.env`
- Updated `docs/knowledge/11_mcp_servers.md` with new MCP config keys

## [1.11.1] - 2026-03-25

### Added

- **ADR-063: Cross-Worker Cache Invalidation via Redis Pub/Sub** — When running with `uvicorn --workers N`, in-memory caches (class/module-level variables) are per-process. Modifying a config via the admin API only reloaded one worker — the other N-1 workers kept stale data. New centralized `invalidation.py` module uses Redis Pub/Sub to broadcast invalidation events. Each cache exposes `load_*()` (startup/subscriber) and `invalidate_and_reload()` (runtime = load + publish). Publisher includes `os.getpid()` to skip self-reload. `verify_registry_completeness()` at startup detects missing registrations. Applied to 4 caches: `LLMConfigOverrideCache`, `SkillsCache`, `PricingCacheService`, `GoogleApiPricingService`. (`src/infrastructure/cache/invalidation.py`, `src/core/constants.py`)
- **Calendar Tool Semantic Keywords** — Added 5 appointment-lookup keywords to `get_events_tool` catalogue manifest to fix semantic tool selection misranking read queries as update/create operations. Keywords: "which appointment do I have on Saturday", "what appointments this week", "do I have any appointments on that day", "what is on my calendar this weekend", "any events planned for Saturday". (`src/domains/agents/calendar/catalogue_manifests.py`)

### Fixed

- **Initiative Node Per-Turn State Reset** — `initiative_iteration` was never reset between conversation turns. Since LangGraph state is checkpointed to PostgreSQL, after the first turn (which increments `initiative_iteration` to 1), all subsequent turns arrived with `iteration >= max_iterations` (default 1), causing the initiative node to be systematically skipped with `reason: max_iterations`. Fixed by resetting all 4 initiative state fields (`initiative_iteration`, `initiative_results`, `initiative_skipped_reason`, `initiative_suggestion`) in the router node's per-turn state clearing block, alongside the existing `planner_iteration` reset. (`src/domains/agents/nodes/router_node_v3.py`)
- **Calendar Event Tool Selection Misranking** — Asking "quel rdv samedi ?" (which appointment Saturday?) caused the semantic tool selector to rank `update_event_tool` (0.656) and `create_event_tool` (0.341) above `get_events_tool` (0.002). The correct read-only tool was excluded by the catalogue score threshold (0.07), forcing the planner to delegate to a sub-agent, which triggered an unnecessary HITL approval prompt. Root cause: `get_events_tool` lacked appointment-lookup keywords while update/create tools had "change appointment time" and "schedule appointment" keywords that matched better. Fixed by adding targeted read-only appointment keywords. (`src/domains/agents/calendar/catalogue_manifests.py`)
- **Skills Cache Cross-Worker Invalidation** — All skill CRUD endpoints (`import`, `delete`, `update_description`, `translate`) now use `SkillsCache.invalidate_and_reload()` instead of local-only `load_from_disk()`. Reload endpoint explicitly publishes after `sync_from_disk()` commit. (`src/domains/skills/router.py`, `src/domains/skills/cache.py`)
- **LLM Config Cache Cross-Worker Invalidation** — `LLMConfigOverrideCache.invalidate_and_reload()` now publishes to Redis Pub/Sub after local reload. Previously, config changes (e.g., switching Initiative LLM model) were only effective on ~25% of requests (1 worker out of 4). (`src/domains/llm_config/cache.py`)
- **Google API Pricing Cache Cross-Worker Invalidation** — `GoogleApiPricingService.invalidate_and_reload()` added and wired to admin pricing reload endpoint. (`src/domains/google_api/pricing_service.py`, `src/domains/google_api/router.py`)
- **Pricing Cache Cross-Worker Invalidation** — `PricingCacheService.invalidate_and_refresh()` added for future runtime pricing modifications. (`src/infrastructure/cache/pricing_cache.py`)

## [1.11.0] - 2026-03-24

### Added

- **ADR-062: Agent Initiative Phase** — Post-execution enrichment node in the LangGraph pipeline. After the task orchestrator executes the user's request, the initiative node analyzes results, detects cross-domain signals, and proactively performs read-only verifications to enrich the response. Example: weather forecast shows rain → initiative checks calendar for outdoor events → response warns the user. Fully prompt-driven (no hardcoded logic), configurable via `INITIATIVE_ENABLED`, `INITIATIVE_MAX_ITERATIONS`, `INITIATIVE_MAX_ACTIONS`. Uses structured output with `InitiativeDecision` schema (OpenAI strict mode compatible). Includes pre-filter (skips when no adjacent read-only tools), memory/interests injection, and suggestion field for write-action proposals. (`src/domains/agents/nodes/initiative_node.py`, `src/domains/agents/prompts/v1/initiative_prompt.txt`, `src/domains/agents/registry/domain_taxonomy.py`)
- **MCP Iterative Mode (ReAct Sub-Agent)** — MCP servers with `iterative_mode: true` are now handled by a ReAct agent loop instead of the static planner. The agent interacts with the MCP server iteratively (reads documentation, then calls tools with correct parameters), solving the fundamental limitation where the planner pre-generated all parameters without understanding the server's API. Powered by a generic `ReactSubAgentRunner` (also used by browser agent). Configurable via `MCP_REACT_ENABLED`, `MCP_REACT_MAX_ITERATIONS`. Per-server activation via `iterative_mode` attribute on admin and user MCP configs. (`src/domains/agents/tools/react_runner.py`, `src/domains/agents/tools/mcp_react_tools.py`, `src/domains/agents/prompts/v1/mcp_react_agent_prompt.txt`)
- **ReactSubAgentRunner** — Generic, reusable runner for LangGraph ReAct sub-agents. Handles LLM creation, prompt loading, tool wrapping, MCP App registry propagation, and graceful error handling. Used by both browser agent and MCP iterative mode. Replaces 60+ lines of duplicated code in browser_tools.py. (`src/domains/agents/tools/react_runner.py`)
- **Domain Taxonomy Enrichment** — `related_domains` updated across all domain configs to enable richer cross-domain initiative detection: weather↔event (bidirectional), email↔contact↔event, task↔event↔contact, place↔weather↔route, file↔contact, reminder↔contact↔event. (`src/domains/agents/registry/domain_taxonomy.py`)
- **User MCP `iterative_mode`** — New boolean attribute on user MCP server configuration. Users can enable iterative mode per-server via the Settings UI. Includes Alembic migration, Pydantic schema update, frontend toggle with cost warning tooltip, and i18n in 6 languages. (`src/domains/user_mcp/models.py`, `src/domains/user_mcp/schemas.py`, `apps/web/src/components/settings/MCPServersSettings.tsx`)
- **Token Tracking `node_name_override`** — `TokenTrackingCallback` now supports a `node_name_override` in config metadata, allowing sub-agents to display meaningful names in the debug panel instead of internal graph node names. (`src/infrastructure/observability/callbacks.py`)
- **Initiative Prometheus Metrics** — 3 new metrics: `initiative_evaluations_total` (by decision: skip/act/error), `initiative_actions_executed_total`, `initiative_duration_seconds_histogram`. (`src/infrastructure/observability/metrics_agents.py`)
- **MCP ReAct Prometheus Metrics** — 2 new metrics: `mcp_react_invocations_total` (by server/status), `mcp_react_iterations_histogram`. (`src/infrastructure/observability/metrics_agents.py`)

### Changed

- **Browser Agent Refactoring** — `browser_task_tool` now uses `ReactSubAgentRunner` instead of inline ReAct agent creation. Removes ~60 lines of duplicated code. Functionally identical. (`src/domains/agents/tools/browser_tools.py`)
- **Excalidraw Cleanup** — Removed `SPATIAL_SUFFIX` override, `iterative_builder.py`, and `position_corrector.py`. Excalidraw now uses the generic MCP iterative mode (ReAct agent) which handles `read_me` → `create_view` flow naturally. (`src/infrastructure/mcp/excalidraw/overrides.py`, `src/infrastructure/mcp/tool_adapter.py`)
- **Smart Planner MCP Reference Filtering** — When a server uses `iterative_mode`, its `reference_content` is no longer injected into the planner prompt (the ReAct agent reads it itself via `read_me`). Saves ~27K tokens per Excalidraw request. (`src/domains/agents/services/smart_planner_service.py`)
- **OpenAI Strict Mode Compatibility** — Added `ConfigDict(extra="forbid")` to `ParameterValue`, `ParameterItem`, `InitiativeAction`, and `InitiativeDecision` to ensure `additionalProperties: false` in JSON schemas. Required for OpenAI structured output mode. (`src/domains/agents/orchestration/plan_schemas.py`, `src/domains/agents/nodes/initiative_node.py`)

### Fixed

- **Excalidraw Incoherent Diagrams** — Diagrams generated by the static planner were spatially incoherent (texts and arrows scattered randomly). Root cause: the planner is not specialized for Excalidraw JSON format and the 27K-char cheat sheet was being ignored in the complex planning context. Fix: MCP iterative mode lets a dedicated ReAct agent read the documentation and generate elements correctly.

## [1.10.2] - 2026-03-24

### Fixed

- **HITL Draft CC/BCC Modification** — CC and BCC fields were not modifiable during HITL draft review (EDIT action). When a user requested to add, change, or remove CC/BCC recipients on an email draft, the modification was silently ignored. Root cause: `cc` and `bcc` were in `PRESERVED_FIELDS` (immutable) instead of `CONTENT_FIELDS` (LLM-modifiable). Same pattern as the `to` field fix from 2026-01-11, but `cc`/`bcc` were missed. Additionally, `_parse_modification_response()` now supports `clearable_fields` (`cc`, `bcc`) so that returning an empty string explicitly removes recipients instead of preserving originals. (`src/domains/agents/services/hitl/draft_modifier.py`)
- **HITL Draft Field Configuration Audit** — Comprehensive audit and correction of `PRESERVED_FIELDS` and `CONTENT_FIELDS` across all 9 draft types to align with actual Pydantic models and connector protocol signatures:
  - `email_reply`: `in_reply_to` renamed to `message_id` (matching `EmailReplyDraftInput`); `cc`/`bcc`/`subject` excluded from `CONTENT_FIELDS` (not supported by `reply_email` protocol across Google/Apple/Microsoft connectors)
  - `email_forward`: `original_message_id` renamed to `message_id` (matching `EmailForwardDraftInput`); `bcc`/`subject` excluded (not supported by `forward_email` protocol); `cc` confirmed as supported
  - `event`/`event_update`: added `timezone` to `PRESERVED_FIELDS` (prevents LLM from inadvertently changing timezone during content edits)
  - `contact_update`: added `address` to `CONTENT_FIELDS` (field existed in `ContactUpdateDraftInput` but was not modifiable)
  - `task`/`task_update`: fixed `tasklist_id` → `task_list_id` (matching actual field name in `TaskDraftInput`/`TaskUpdateDraftInput`)
  (`src/domains/agents/services/hitl/draft_modifier.py`)

## [1.10.1] - 2026-03-24

### Added

- **ADR-061: Centralized Component Activation** — Three-layer defense system for component enable/disable control. Layer 1: domain gate-keeper validates LLM-output domains against `available_domains` (strips hallucinated/disabled domains post-LLM and post-expansion in `query_analyzer_service.py`). Layer 2: per-request `request_tool_manifests_ctx` ContextVar built once at request start, combining registry manifests minus admin MCP disabled plus user MCP tools — all consumers read filtered manifests from a single source instead of 7+ scattered filter sites. Layer 3: API guard returns 403 on admin MCP proxy endpoints (`call-tool`, `read-resource`) for disabled servers, with defense-in-depth in `MCPClientManager`. (`src/core/context.py`, `src/domains/agents/services/query_analyzer_service.py`, `src/domains/agents/api/service.py`, `src/domains/user_mcp/admin_router.py`, `src/infrastructure/mcp/client_manager.py`)
- **GPT-5.4 Model Support** — Added `gpt-5.4` and `gpt-5.4-mini` model profiles with full capabilities (reasoning, vision, structured output, streaming). Pricing seeded in `llm_pricing_seed.sql` (117 models). (`src/infrastructure/llm/model_profiles.py`, `infrastructure/database/seeds/llm_pricing_seed.sql`)
- **Run-Level Token Tracking** — All `TrackingContext` instances sharing the same `run_id` now publish their committed records to a module-level collector (`_run_records`, `_run_google_api_records`). The debug panel shows EVERY LLM call (pipeline + background tasks like memory/interest/journal extraction) in a single unified view. `cleanup_run_records(run_id)` prevents memory leaks after the debug panel is emitted. (`src/domains/chat/service.py`, `src/domains/agents/services/streaming/service.py`)
- **Debug Metrics sessionStorage Persistence** — Debug metrics history is persisted to `sessionStorage` so it survives page navigation within the same tab. Hydrated on `createInitialState()`, updated via `useEffect`. Capped at 50 entries to stay within the 5 MB storage limit. (`apps/web/src/reducers/chat-reducer.ts`, `apps/web/src/hooks/useChat.ts`)
- **Onboarding Pages Overhaul** — Complete redesign of the onboarding flow: Page 1 adds a 4-line intro explaining what makes LIA different from ChatGPT/Claude/Gemini. Page 2 replaces Google-specific connector options with 5 essential external connectors (Brave Search, Wikipedia, Google Places, OpenWeatherMap, Browser) with descriptions and provider mixing note. Page 4 adds autonomous memory description and settings management tip. Page 7 adds a feature discovery list (Skills, MCPs, RAG, Scheduled Actions, Voice Mode) before the example categories. All 6 locale files updated (en, fr, de, es, it, zh). (`apps/web/src/components/onboarding/pages/Page1Welcome.tsx`, `Page2Connectors.tsx`, `Page4Memory.tsx`, `Page7Examples.tsx`)
- **Background Task Token Awaiting** — Debug panel now awaits background tasks (memory, interest, journal extraction) up to 15s before reading DB-aggregated totals, ensuring the debug panel shows the same cost as the chat bubble. (`src/domains/agents/services/streaming/service.py`)

### Changed

- **Responses API Pattern-Based Eligibility** — Replaced hardcoded `RESPONSES_API_ELIGIBLE_MODELS` set (30+ entries) with a single regex pattern `^(gpt-4\.1|gpt-5|o[1-9])`. Auto-extensible for future GPT-5.x and o-series models. (`src/infrastructure/llm/providers/responses_adapter.py`)
- **Tool Conversion via `convert_to_openai_function`** — `ResponsesLLM._convert_tools()` and `_format_tools_for_binding()` now delegate to LangChain's `convert_to_openai_function()` instead of manual `model_json_schema()` calls. Fixes crash on tools with `InjectedToolArg` annotations (non-serializable `CallableSchema`). (`src/infrastructure/llm/providers/responses_adapter.py`)
- **Excalidraw Intent-Only Mode** — Removed `position_corrector.py` (384 lines) and its test file. The tool adapter no longer has a fallback path for raw Excalidraw elements — only structured intent objects are processed through the iterative builder. Simplified `_prepare_excalidraw()`, updated documentation strings and prompt override. (`src/infrastructure/mcp/tool_adapter.py`, `src/infrastructure/mcp/excalidraw/`)
- **Centralized Tool Manifest Access** — Router node, normal/panic filtering strategies, and expansion service now read from `get_request_tool_manifests()` instead of `registry.list_tool_manifests()` + manual per-consumer filtering. Eliminates duplicate filtering logic across 7+ locations. (`src/domains/agents/nodes/router_node_v3.py`, `src/domains/agents/services/catalogue/strategies/`, `src/domains/agents/semantic/expansion_service.py`)
- **Query Analyzer Domain Builder Extraction** — Extracted `_build_available_domains()` helper from inline code in `analyze_query()`. Called once per request and reused for both LLM prompt construction and post-expansion domain validation. (`src/domains/agents/services/query_analyzer_service.py`)
- **HeroSection Responsive Subtitle** — Removed `whitespace-nowrap` from hero subtitle for proper text wrapping on mobile. (`apps/web/src/components/landing/HeroSection.tsx`)

### Fixed

- **Disabled MCP Server Tool Execution** — When a user disabled an admin MCP app (e.g., Excalidraw), the system continued routing queries to that domain and executing its tools. Root cause: LLM-output domains were never validated against `available_domains`, and semantic expansion could re-introduce disabled domains. Fixed by ADR-061 three-layer defense. (`src/domains/agents/services/query_analyzer_service.py`, `src/core/context.py`)
- **GPT-5.4 reasoning_effort + Tools Incompatibility** — `gpt-5.4` and later models do not support `reasoning_effort` parameter simultaneously with function tools in `/v1/chat/completions`. Fixed by omitting `reasoning_effort` when tools are present. Applied to both `_generate()` and `_stream()` paths. (`src/infrastructure/llm/providers/responses_adapter.py`)
- **Browser Tool Store Propagation** — `browser_task_tool` nested ReAct agent was missing the parent graph's `InMemoryStore`, causing `validate_runtime_config` failures. Fixed by passing `runtime.store` to `create_react_agent()`. (`src/domains/agents/tools/browser_tools.py`)
- **AdminLLMConfigSection Loading Flicker** — Loading spinner was shown during refetches (not just initial load), causing the entire content to unmount and lose focus. Fixed by conditioning spinner on `loading && configs.length === 0`. (`apps/web/src/components/settings/AdminLLMConfigSection.tsx`)
- **Debug Panel Missing Background Task Costs** — The debug panel displayed token costs only from the main pipeline, missing memory/interest/journal extraction costs. Fixed by run-level token aggregation and background task awaiting. (`src/domains/chat/service.py`, `src/domains/agents/services/streaming/service.py`)

### Removed

- **Excalidraw Position Corrector** — Deleted `position_corrector.py` and `test_excalidraw_position_corrector.py`. The module corrected text centering and shape overlaps in raw LLM-generated Excalidraw elements, but is no longer needed since the system now exclusively uses intent-based diagram generation via the iterative builder.

## [1.10.0] - 2026-03-23

### Added

- **Push-to-Talk Mobile Fix** — Comprehensive fix for push-to-talk on smartphones. CSS anti-long-press (`select-none`, `-webkit-touch-callout:none`, `onContextMenu`), handlers always attached (eliminates race condition when `showSendMode` changes mid-touch), `onTouchCancel` for system interruptions, `onTouchMove` for finger-slide cancellation. `e.preventDefault()` now conditional: only called during actual push-to-talk, preserving form submit on mobile. (`apps/web/src/components/chat/ChatInput.tsx`)
- **Push-to-Talk Cancel Support** — Users can release the button during the async setup phase (state 'connecting') to cancel. `cancelledRef` flag checked after `Promise.allSettled` completes. `stopRecording()` extended to handle 'connecting' state. (`apps/web/src/hooks/useVoiceInput.ts`)
- **Push-to-Talk Latency Optimization** — `getUserMedia` + WS connect parallelized via `Promise.allSettled` (saves ~100-500ms). Worklet Blob URL cached across recordings. WebSocket pre-warmed in background during idle state. Setup timeout (10s) prevents indefinite blocking on slow networks. (`apps/web/src/hooks/useVoiceInput.ts`, `apps/web/src/lib/constants.ts`)
- **Voice Mode Latency Optimization** — KWS microphone stream reused for recording (eliminates `getUserMedia` call, saves ~200-800ms). WebSocket pre-connected during listening state. Recording worklet URL cached. VAD silence threshold reduced from 1000ms to 750ms for faster end-of-speech detection. (`apps/web/src/hooks/useVoiceMode.ts`)
- **Ready Chime** — Short synthesized audio cue (ascending C5→E5 major third, ~250ms) plays when recording starts after wake word detection, providing auditory feedback that the app is ready. Uses Web Audio API oscillators, no external audio file. (`apps/web/src/lib/audio/ready-chime.ts`)
- **Per-User STT Language** — User's preferred language (from DB `user.language` column) is now included in the WebSocket ticket and passed to the backend STT service. `SherpaSttService` maintains a thread-safe cache of `OfflineRecognizer` instances keyed by language code, biasing Whisper transcription to the user's language instead of auto-detection. (`apps/api/src/domains/voice/ticket_store.py`, `apps/api/src/domains/voice/stt/sherpa_stt.py`, `apps/api/src/domains/voice/router.py`)
- **Send Button Loading State** — Send icon remains visible (at 30% opacity) with a spinning overlay when disabled, instead of being replaced by a spinner. Preserves visual landmark. Uses `text-primary-foreground` for correct light/dark mode rendering. (`apps/web/src/components/chat/ChatInput.tsx`)
- **Sherpa WASM Setup Script** — New `scripts/download-sherpa-wasm.sh` downloads the pre-built sherpa-onnx WASM runtime (VAD + ASR + Whisper Tiny.en bundled, ~111MB) from GitHub releases. Integrated into `scripts/setup-dev.sh` as step 3/3 and `Dockerfile.prod` model-downloader stage. (`scripts/download-sherpa-wasm.sh`, `scripts/setup-dev.sh`, `apps/web/Dockerfile.prod`)
- **Safari iOS Voice Mode Support** — Changed `Cross-Origin-Embedder-Policy` from `credentialless` to `require-corp`, enabling `crossOriginIsolated` (and thus `SharedArrayBuffer` for Sherpa WASM) on Safari iOS. Google Fonts `crossOrigin="anonymous"` attribute added. Google profile images already proxied via existing endpoint. (`apps/web/next.config.ts`, `apps/web/src/app/[lng]/layout.tsx`)
- **VoiceInputService.updateCallbacks()** — Allows re-wiring callbacks on a pre-warmed service instance without creating a new connection. Used by both push-to-talk and voice mode pre-warm flows. (`apps/web/src/lib/voice-input-service.ts`)

### Fixed

- **Sherpa WASM Script Loading** — Browser `class` declarations at top-level of `<script>` tags don't become `window` properties in strict mode. Fixed by fetching script content, appending a shim that explicitly assigns `createVad`, `CircularBuffer`, and `OfflineRecognizer` to `window`, then executing via Blob `<script>` tag. (`apps/web/src/lib/audio/sherpaKws.ts`)
- **VoiceModeBadge Stuck Initializing** — Badge remained in "Initializing..." state forever on browsers where KWS is not supported (missing `SharedArrayBuffer`). Fixed by checking `isKwsSupported` in the `isInitializing` condition. (`apps/web/src/components/voice/VoiceModeBadge.tsx`)
- **handleSubmit Guard Incomplete** — Form submit was not blocked during push-to-talk 'connecting' state. Added `voiceState !== 'connecting'` to the guard. (`apps/web/src/components/chat/ChatInput.tsx`)

## [1.9.6] - 2026-03-23

### Added

- **Unified LLM + Embedding Tracking** — Embedding calls (journal context, memory search, RAG retrieval via `TrackedOpenAIEmbeddings`) are now recorded in the conversation's main `TrackingContext` instead of a separate standalone tracker. This makes embedding token usage visible in the debug panel alongside chat completions and TTS. Dual-strategy approach: (1) when a conversation tracker is active (via `current_tracker` ContextVar), record directly into it; (2) fallback to standalone `TrackingContext` for background operations (RAG indexing, scheduled tasks). Graceful degradation with try/except ensures embedding calls never break on tracking failures. (`apps/api/src/infrastructure/llm/embedding_context.py`, `apps/api/src/infrastructure/llm/tracked_embeddings.py`)
- **TokenUsageRecord call_type & sequence** — Two new fields on `TokenUsageRecord` NamedTuple: `call_type` (`"chat"` | `"embedding"`, default `"chat"`) distinguishes LLM call categories, and `sequence` (monotonic counter under asyncio lock) provides chronological ordering. Both fields are backward-compatible (keyword defaults). `get_llm_calls_breakdown()` now returns these fields for the debug panel. (`apps/api/src/domains/chat/service.py`)
- **Debug Panel: LLM Pipeline Section** — New `LLMPipelineSection` component showing ALL LLM calls (chat + embedding) in chronological execution order. Each row displays: sequence number, type badge (CHAT/EMB), node badge with color, model name, duration, tokens IN/CACHE/OUT, and cost. Summary header shows total calls (split by type), duration, tokens, and cost. (`apps/web/src/components/debug/components/sections/LLMPipelineSection.tsx`)
- **Debug Panel: Embedding Visibility** — Embedding calls now appear in existing debug sections: LLM Calls section shows `EMB` badge (teal) with `—` for tokens_out; Request Lifecycle section includes embedding nodes; Token Budget totals include embedding tokens; LLM Summary aggregates all call types. (`apps/web/src/components/debug/components/sections/LLMCallsSection.tsx`, `apps/web/src/components/debug/DebugPanel.tsx`)
- **Embedding Duration Tracking** — `TrackedOpenAIEmbeddings` now passes `duration_ms` (latency in milliseconds) to `persist_embedding_tokens()`, enabling timing display in the debug panel. (`apps/api/src/infrastructure/llm/tracked_embeddings.py`)

### Fixed

- **Embedding ContextVar Overwrite Bug** — `persist_embedding_tokens()` previously created `async with TrackingContext(...)` which temporarily overwrote the `current_tracker` ContextVar, potentially corrupting concurrent access to the conversation tracker. The new approach avoids creating a new `TrackingContext` when a conversation tracker is already active. (`apps/api/src/infrastructure/llm/embedding_context.py`)
- **LLMCallsSection Hardcoded Node Colors** — Node color determination in `LLMCallsSection` used inline `includes()` checks instead of the centralized `getNodeColor()` helper, causing new node types (like embedding) to always fall back to default color. Refactored to use `getNodeColor()`. (`apps/web/src/components/debug/components/sections/LLMCallsSection.tsx`)
- **Zod Schema Gaps (v3.2 debt)** — `LLMCallSchema` was missing `duration_ms`, `LifecycleNodeSchema` was missing `duration_ms`, and `RequestLifecycleSchema` was missing `total_duration_ms`. Added as optional fields. (`apps/web/src/components/debug/validation/schemas.ts`)

## [1.9.5] - 2026-03-23

### Added

- **ToolManifest.context_save_mode** — New `context_save_mode: ContextSaveMode | None` field on `ToolManifest` dataclass enables explicit LIST/DETAILS override for context auto-save classification, bypassing the name-based heuristic in `classify_save_mode()`. Propagated through both parallel_executor and `@connector_tool`/`@auto_save_context` decorator chains. Set to `ContextSaveMode.LIST` on all 4 unified tools (get_events, get_emails, get_contacts, get_tasks). (`apps/api/src/domains/agents/registry/catalogue.py`, `apps/api/src/domains/agents/context/manager.py`, `apps/api/src/domains/agents/orchestration/parallel_executor.py`, `apps/api/src/domains/agents/context/decorators.py`, `apps/api/src/domains/agents/tools/decorators.py`)
- **Email Reply/Forward HITL Domains** — Separate `email_reply` and `email_forward` insufficient content domains with domain-specific required fields (reply: body only; forward: recipient + optional body). Includes i18n questions (6 languages), field questions, detection patterns, DRAFT_TYPE_EMOJIS, and DRAFT_SUMMARIES. (`apps/api/src/core/constants.py`, `apps/api/src/core/i18n_hitl.py`)
- **Task Update current_task Fetch** — `UpdateTaskDraftTool` now fetches the current task before creating the draft, enabling before/after comparison in HITL critique (consistent with calendar and contact update patterns). Due date converted from UTC to user timezone. (`apps/api/src/domains/agents/tools/tasks_tools.py`)
- **Rich HITL Draft Critique Prompt** — Redesigned `hitl_draft_critique_prompt.txt` with domain-specific markdown templates (email, event, contact, task), emoji field prefixes, before/after strikethrough for updates, irreversibility warnings for deletions. (`apps/api/src/domains/agents/prompts/v1/hitl_draft_critique_prompt.txt`)
- **Rich Post-HITL Result Display** — `_format_draft_execution_result` now shows all draft attributes with i18n labels, domain emojis, formatted dates, and clickable links. Intermediate search results (`[search] N event(s):...`) are replaced by the execution result instead of being concatenated. Module-level `_DRAFT_RESULT_FIELD_CONFIG` defines field rendering per domain. (`apps/api/src/domains/agents/nodes/response_node.py`)
- **Enriched HITL Fallback Summaries** — `_generate_fallback_critique` now produces multi-line structured summaries with extra fields (body for emails, location/attendees for events, phone/org for contacts, due/notes for tasks) and `---` separator before action buttons. (`apps/api/src/domains/agents/services/hitl/interactions/draft_critique.py`)

### Fixed

- **Calendar 404 on Non-Primary Calendar** — `update_event_tool` and `delete_event_tool` failed with 404 when modifying events on shared calendars (e.g., "Famille"). Root cause: `calendar_id` not propagated from search step to mutation step. Triple fix: (1) `calendar_id` added to `get_events_tool` catalogue outputs + reference_examples with `semantic_type="calendar_id"`, (2) `_CALENDAR_ID_PARAM` gains `semantic_type="calendar_id"` for planner semantic binding, (3) new `_resolve_calendar_id_from_context` helper reads both LIST and DETAILS store keys. (`apps/api/src/domains/agents/calendar/catalogue_manifests.py`, `apps/api/src/domains/agents/tools/calendar_tools.py`)
- **Context Store Classification Bug** — All unified `get_*_tool` names (get_events, get_emails, get_contacts, get_tasks) were classified as DETAILS by `classify_save_mode()` because "get" matched the DETAILS keyword rule. Mutable tools reading from LIST key found nothing. Fixed by `context_save_mode=ContextSaveMode.LIST` on manifests and decorators. (`apps/api/src/domains/agents/registry/catalogue.py` + 4 catalogue files + 4 tool files)
- **GetEventDetailsTool calendar_id Lost** — In ID mode (`get_events_tool(event_id="abc")`), `calendar_id` was resolved for the API call but not included in the result dict. Events stored in the registry had no `calendar_id`. Fixed in `_execute_single`, `_execute_batch`, and `format_registry_response`. (`apps/api/src/domains/agents/tools/calendar_tools.py`)
- **Usage Limits Cache KeyError** — `check_user_allowed()` read `cached["allowed"]` directly but `cache_set_json()` wraps data in `{"data": {...}}` envelope. Fixed with `cached.get("data", cached)` unwrap. (`apps/api/src/domains/usage_limits/service.py`)
- **Semantic Pivot Translating User Content** — Planner received `english_enriched_query` (with translated content like "merci" → "Thank you") instead of `original_query` (user's language). Email bodies, event titles, task names were sent in English. Fixed: planner now always receives `original_query` for content extraction; English enriched version passed as structural context with explicit "CONTENT RULE" directive. (`apps/api/src/domains/agents/services/smart_planner_service.py`, `apps/api/src/domains/agents/prompts/v1/smart_planner_prompt.txt`, `apps/api/src/domains/agents/prompts/v1/smart_planner_multi_domain_prompt.txt`)
- **Email Reply Recipient Override Ignored** — `execute_email_reply_draft()` did not pass the `to` field to `client.reply_email()`, and `google_gmail_client.reply_email()` hardcoded the recipient to the original sender. Draft modifications to recipient were silently ignored. Fixed across Google, Microsoft, Apple clients and protocol. (`apps/api/src/domains/agents/tools/emails_tools.py`, `apps/api/src/domains/connectors/clients/google_gmail_client.py`, `apps/api/src/domains/connectors/clients/microsoft_outlook_client.py`, `apps/api/src/domains/connectors/clients/apple_email_client.py`, `apps/api/src/domains/connectors/clients/protocols.py`)
- **Email Reply Missing Quoted Body** — Gmail and Apple reply_email sent only the new body without the quoted original message. Fixed: both now include `> On [date], [sender] wrote:` quoted block (Microsoft handles this server-side). (`apps/api/src/domains/connectors/clients/google_gmail_client.py`, `apps/api/src/domains/connectors/clients/apple_email_client.py`)
- **Microsoft Outlook Forward Missing CC** — `forward_email()` accepted `cc` parameter but never added `ccRecipients` to the Graph API request. (`apps/api/src/domains/connectors/clients/microsoft_outlook_client.py`)
- **Contact Update Missing Address** — `execute_contact_update_draft()` did not pass `address` field to client. (`apps/api/src/domains/agents/tools/google_contacts_tools.py`)
- **Email Reply HITL Asked for Recipient** — Semantic validator treated reply/forward same as send, requiring recipient + subject + body. Reply only needs body; forward only needs recipient. Fixed with separate `email_reply`/`email_forward` insufficient content domains. (`apps/api/src/core/constants.py`, `apps/api/src/core/i18n_hitl.py`)
- **Contacts Catalogue Alias Mismatch** — `reference_examples` used `emails`/`phones` (old aliases) instead of `emailAddresses`/`phoneNumbers` (actual Google API field names in registry). (`apps/api/src/domains/agents/google_contacts/catalogue_manifests.py`)
- **Email Subject Not Top-Level** — `reference_examples` declared `emails[0].subject` but subject was only in nested `payload.headers`. Promoted to top-level in `build_emails_output()` with Apple Mail fallback. (`apps/api/src/domains/agents/tools/mixins.py`, `apps/api/src/domains/agents/emails/catalogue_manifests.py`)
- **Calendar HITL Timezone Mismatch** — `current_event` dates from Google API were in UTC while draft dates were in user timezone, causing wrong before→after display (e.g., "17h→16h" instead of "17h→15h"). Fixed: UTC→user timezone conversion for `current_event` (update) and `event` (delete). Same fix for task `current_task.due`. (`apps/api/src/domains/agents/tools/calendar_tools.py`, `apps/api/src/domains/agents/tools/tasks_tools.py`)
- **Draft Model Inconsistency** — `EmailReplyDraftInput.to_reply_email_args()` did not include `to` field. (`apps/api/src/domains/agents/drafts/models.py`)
- **Post-HITL Search Results Leak** — After HITL confirmation, `[search] N event(s):...` from intermediate steps was concatenated with the execution result instead of being replaced. (`apps/api/src/domains/agents/nodes/response_node.py`)

## [1.9.4] - 2026-03-23

### Changed

- **Systematic Settings Priority Chain Enforcement** — Comprehensive refactoring of ~291 runtime constant usages across ~80 files to use `settings.field_name` instead of direct constants. Enforces the priority chain APPLICATION (admin UI / DB) > .ENV (settings) > CONSTANT (fallback only). Six fix patterns applied: direct replacement (Pattern A), `getattr` simplification (Pattern B), module-level alias re-sourcing (Pattern C), None sentinel for function defaults (Pattern D), Pydantic `default_factory` for domain schemas (Pattern E), and f-string description updates (Pattern F). Constants now reserved exclusively for: `Field(default=...)` in config files, SQLAlchemy `default=`/`server_default=`, structural values (node names, state keys, Redis prefixes, scheduler IDs). (`apps/api/src/` — 80+ files across all domains)
- **i18n Chain Fix** — `i18n_dates.py` had a hardcoded `DEFAULT_LANGUAGE = "fr"` bypassing settings, and `i18n_drafts.py` imported from `i18n_types.py` (also hardcoded) instead of `i18n.py` (which reads from settings). Both now correctly route through the settings-backed `i18n.py` bridge. (`apps/api/src/core/i18n_dates.py`, `apps/api/src/core/i18n_drafts.py`)
- **Agent Constants Alias Cleanup** — Removed 4 redundant aliases in `agents/constants.py` (`CONTEXT_ACTIVE_WINDOW_TURNS`, `CONTEXT_RESOLUTION_TIMEOUT_MS`, `CONTEXT_DEMONSTRATIVE_CONFIDENCE`, `CONTEXT_CURRENT_ITEM_CONFIDENCE`) that bypassed settings. Consumers migrated to `settings.*` access. (`apps/api/src/domains/agents/constants.py`, `apps/api/src/domains/agents/services/context_resolution_service.py`)
- **Personalities Constants Cleanup** — Removed re-exported `DEFAULT_LANGUAGE`, `SUPPORTED_LANGUAGES`, and `FALLBACK_LANGUAGES` from `personalities/constants.py`. `FALLBACK_LANGUAGES` was capturing the constant "fr" at import time; replaced with inline `(settings.default_language, "en")` in the single consumer. (`apps/api/src/domains/personalities/constants.py`, `apps/api/src/domains/personalities/models.py`)
- **Token Counter Aliases Re-sourced** — `TOKEN_THRESHOLD_SAFE/WARNING/CRITICAL/MAX` module-level aliases in `token_counter_service.py` now read from `settings.*` instead of constants, while preserving backward-compatible exports for tests. (`apps/api/src/domains/agents/services/token_counter_service.py`)

### Fixed

- **Places Tool Crash on Language Parameter** — `get_places_tool()` raised `TypeError: unexpected keyword argument 'language'` when the LLM planner included a `language` parameter in the execution plan. Added optional `language: str | None = None` parameter to accept the argument gracefully (tool already reads language from runtime context). (`apps/api/src/domains/agents/tools/places_tools.py`)

## [1.9.3] - 2026-03-23

### Added

- **Journal Semantic Search Overhaul** — Migrated journal embeddings from local E5-small (384d) to OpenAI `text-embedding-3-small` (1536d) via pgvector `Vector()` column with HNSW index. Added `search_hints` field (LLM-generated keywords in user vocabulary) to bridge the semantic gap between assistant introspection and user queries. Search hints are displayed as badges and editable in Settings → Personal Journals. 3 Alembic migrations (search_hints column, pgvector migration with data purge, injection tracking). (`apps/api/src/domains/journals/embedding.py`, `apps/api/src/domains/journals/service.py`, `apps/api/src/domains/journals/models.py`)
- **Journal Temporal Continuity** — Configurable `JOURNAL_CONTEXT_RECENT_ENTRIES` setting injects the N most recent journal entries regardless of semantic score, ensuring the assistant always has access to its latest reflections. Deduplication with semantic results prevents double injection. (`apps/api/src/domains/journals/context_builder.py`)
- **Journal Injection Tracking** — New `injection_count` and `last_injected_at` columns track how often each journal entry is actually used in prompts. Fire-and-forget background update via `safe_fire_and_forget` to avoid response latency. (`apps/api/src/domains/journals/repository.py`, `apps/api/src/domains/journals/context_builder.py`)
- **Journal Planner Injection** — Journal context is now injected into the planner prompt (in addition to the response prompt), using `intelligence.original_query` as the semantic search query. Separate debug tracking via `journal_planner_injection_debug` state key. (`apps/api/src/domains/agents/nodes/planner_node_v3.py`)
- **Debug Panel Enhancements** — Journal debug section split into Response + Planner sub-sections with `InjectionSubSection` reusable component. Recent entries show "RECENT" badge instead of score bar. Tooltips on injection and extraction entries show full title + content on hover. Background extraction section shows action details. Semantic search scores logged at `info` level for threshold calibration. (`apps/web/src/components/debug/components/sections/JournalInjectionSection.tsx`)
- **Memory Emotional Safety Directive** — Dynamic behavioral directive in psychological profile: `DANGER_DIRECTIVE` activates when any memory has `emotional_weight ≤ -5`, with 4 absolute prohibitions (no jokes, no dismissal, no minimization, no comparison on TRAUMA/DOULEUR topics). Sensitivity-category memories now format `usage_nuance` as imperative obligation (`⚠ OBLIGATION:`) instead of informational italic. Response prompt reinforced with CRITICAL compliance instruction. (`apps/api/src/domains/agents/middleware/memory_injection.py`, `apps/api/src/domains/agents/prompts/v1/response_system_prompt_base.txt`)
- **Embedding Models in LLM Pricing** — OpenAI embedding models (`text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`) added to the LLM model administration table for cost tracking. (`infrastructure/database/seeds/`)

### Fixed

- **LLM Cost Tracking Using Wrong Model Name** — 5 background services (journal extraction, journal consolidation, memory extraction, interest extraction, interest content reflection) were tracking token costs against `LLM_DEFAULTS[type].model` (hardcoded code default) instead of the actual model configured in the admin UI. When admins changed models via the application, costs were still calculated with the old default prices. Fixed by replacing `LLM_DEFAULTS[type].model` with `get_llm_config_for_agent(settings, type).model` which resolves the effective config (code defaults → DB admin overrides). (`apps/api/src/domains/journals/extraction_service.py`, `apps/api/src/domains/journals/consolidation_service.py`, `apps/api/src/domains/agents/services/memory_extractor.py`, `apps/api/src/domains/interests/services/extraction_service.py`, `apps/api/src/domains/interests/services/content_sources/llm_reflection_source.py`)
- **Hardcoded Runtime Values Ignoring Settings** — Multiple runtime constants used directly instead of their corresponding `settings.*` fields, bypassing `.env` and application configuration. Fixed: `API_MAX_ITEMS_PER_REQUEST` in HITL dispatch and task orchestrator nodes, `JOURNAL_ENTRY_CONTENT_MAX_LENGTH` in extraction/consolidation service calls, semantic fallback threshold, context reference confidence, HITL demotion confidence, semantic validation fallback confidence, retry middleware parameters, default item confidence, email truncation ratio. (`apps/api/src/domains/agents/nodes/hitl_dispatch_node.py`, `apps/api/src/domains/agents/nodes/task_orchestrator_node.py`, and 7 other files)
- **Constants Misaligned with Production Config** — 25+ constant default values in `constants.py` diverged from actual `.env.prod` production values (e.g., `SEMANTIC_FALLBACK_THRESHOLD` was 0.4 in code but 0.75 in prod, `JOURNAL_CONTEXT_MIN_SCORE` was 0.3 but 0.55 in prod). All constants realigned with production values. `.env.example` also realigned with `.env.prod` for all application configuration values.
- **395+ Hardcoded Config Defaults** — All `Field(default=X)` in 9 config files (agents, connectors, journals, database, advanced, llm, observability, voice, mcp) replaced with named constants from `constants.py`, ensuring the fallback chain APPLICATION > .ENV > CONSTANT is respected even with a minimal `.env` file.
- **LLM_DEFAULTS Misaligned with App Config** — `browser_agent` default was `openai/gpt-4.1-mini` but app uses `anthropic/claude-opus-4-6`. `hitl_question_generator` was `openai/gpt-4.1-mini` but app uses `anthropic/claude-sonnet-4-6`. `journal_extraction/consolidation` was `openai/gpt-5-mini` but app uses `qwen/qwen3.5-plus`. All aligned with actual application configuration. (`apps/api/src/domains/llm_config/constants.py`)
- **Journal Max Entry Size Not Respected** — User-configurable "Max entry size" setting in Personal Journals was ignored by the LLM — the extraction and consolidation prompts used a hardcoded constant (2000) instead of the user's configured value. Fixed by reading `user.journal_max_entry_chars` from DB and passing it to prompts as a MANDATORY size constraint, and to `service.create_entry()`/`service.update_entry()` calls. (`apps/api/src/domains/journals/extraction_service.py`, `apps/api/src/domains/journals/consolidation_service.py`, `apps/api/src/infrastructure/scheduler/journal_consolidation.py`)

## [1.9.2] - 2026-03-22

### Fixed

- **Browser agent unavailable in production** — Playwright Chromium binary was missing from the production Docker image (`Dockerfile.prod`). The Python package was installed but `playwright install chromium` was never executed, causing `BrowserPool` initialization to fail silently (`_healthy=False`) and all browser tools to return "Browser pool is not healthy". Added Chromium binary download in the builder stage, `PLAYWRIGHT_BROWSERS_PATH` env var, and Chromium runtime system dependencies (libnss3, libatk, libgbm, etc.) in the final stage. Dev image (`Dockerfile.dev`) was already correct. (`apps/api/Dockerfile.prod`)
- **Broadcast notification spam for new and existing users** — New users who connected for the first time received the entire history of broadcast messages. Additionally, existing users with many unread broadcasts were overwhelmed with notifications. The `GET /broadcasts/unread` endpoint now only considers the 3 most recent *eligible* broadcasts (non-expired, created after the user's signup date) and returns only the unread ones among those. This uses a two-subquery approach: one to select the N most recent eligible broadcast IDs, another to exclude already-read IDs. New `MAX_UNREAD_BROADCASTS` constant centralizes the limit. (`apps/api/src/domains/notifications/repository.py`, `apps/api/src/domains/notifications/broadcast_service.py`, `apps/api/src/domains/notifications/router.py`, `apps/api/src/core/constants.py`)
- **Confusing logout button** — The user profile section (avatar + name + email + icon) in the navbar was mistaken for a profile link rather than a logout action. Replaced with a clear red icon-only button (`bg-destructive` + `LogOut` icon). Removed unused `proxyGoogleImageUrl` import. (`apps/web/src/app/[lng]/dashboard/layout.tsx`)
- **Assistant leaking admin-only features to regular users** — When asked "which LLM do you use?", the assistant mentioned admin interfaces like "Admin > LLM Configuration" which are inaccessible to regular users. Added a directive to the app identity prompt instructing the assistant to never reference admin panels, admin settings, or backend configuration options. (`apps/api/src/domains/agents/prompts/v1/app_identity_prompt.txt`)
- **Usage limits console error on startup** — `useUsageLimits` hook logged `ERROR: Failed to fetch` when the backend was unreachable (e.g., during startup). Network errors (`TypeError`) are now silently ignored since the polling interval will retry automatically. (`apps/web/src/hooks/useUsageLimits.ts`)

## [1.9.1] - 2026-03-22

### Added

- **User Consumption Export** — Authenticated users can now export their own LLM token usage, Google API usage, and aggregated consumption summary as CSV from Settings → Features → "My Consumption Export". Three export types with date range filters (current month, last month, last 30 days, all time). Security: `user_id` forced server-side via `current_user.id` — no `user_id` parameter exposed on user endpoints, preventing IDOR. 7 introspection-based security unit tests. (`apps/api/src/domains/google_api/user_export_router.py`, `apps/web/src/components/settings/ConsumptionExportSection.tsx`)
- **Shared Export Service** — Extracted admin export query logic into reusable service functions (`export_token_usage_csv`, `export_google_api_usage_csv`, `export_consumption_summary_csv`) with shared date parsing helper. Both admin and user endpoints delegate to the same service, eliminating code duplication. (`apps/api/src/domains/google_api/export_service.py`)
- **Dual-Mode Export Component** — Unified `ConsumptionExportSection` React component with `mode` prop (`'admin'` | `'user'`). Admin mode shows user filter with autocomplete; user mode shows date filters only and calls user-scoped API endpoints. Admin wrapper (`AdminConsumptionExportSection`) reduced to a thin passthrough. Unique HTML IDs per mode prevent DOM conflicts when both instances coexist for superusers. (`apps/web/src/components/settings/ConsumptionExportSection.tsx`, `apps/web/src/components/settings/AdminConsumptionExportSection.tsx`)
- **Export Unit Tests** — 26 unit tests: `_parse_date_range` validation, CSV output for token/Google API/summary exports, empty data handling, consumption aggregation with partial data, and 9 router security tests (no `user_id` parameter exposed, auth dependency present, correct prefix, allowed params whitelist). (`apps/api/tests/unit/domains/google_api/`)
- **User Export Internationalization (6 languages)** — 18 translation keys per language under `settings.user.export.*` namespace (en, fr, de, es, it, zh) for section title, description, date presets, export card labels, and status messages. (`apps/web/locales/`)

### Fixed

- **Admin export code duplication** — Admin export endpoints (`/admin/google-api/export/*`) refactored to delegate to shared `export_service` functions instead of inlining SQLAlchemy queries. No behavioral change. (`apps/api/src/domains/google_api/router.py`)

## [1.9.0] - 2026-03-22

### Added

- **Per-User Usage Limits** — New domain `src/domains/usage_limits/` enabling administrators to define per-user quotas on tokens, messages, and cost (EUR). Supports both period-based (monthly rolling cycle aligned with account creation) and global/absolute limits. Each dimension can be set to a numeric value or unlimited (null). Includes admin manual block/unblock with reason tracking. (`apps/api/src/domains/usage_limits/`)
- **5-Layer Defense in Depth Enforcement** — Multi-layer enforcement architecture preventing any bypass: Layer 0 (HTTP 429 in chat router before SSE stream), Layer 1 (SSE error in agent service for scheduled actions), Layer 2 (centralized LLM invocation guard in `invoke_with_instrumentation()` covering all background services), Layer 3 (proactive runner skip for blocked users), Layer 4 (migration of direct `.ainvoke()` calls). Fail-open design: infrastructure failures don't block users. (`apps/api/src/domains/agents/api/router.py`, `apps/api/src/domains/agents/api/service.py`, `apps/api/src/infrastructure/llm/invoke_helpers.py`, `apps/api/src/infrastructure/proactive/runner.py`)
- **Admin Usage Limits Dashboard** — Dedicated admin section with searchable, paginated table showing all users with period and global usage gauges (tokens, messages, cost). Inline block toggle with optimistic updates, edit modal with current consumption display per limit dimension. WebSocket endpoint for real-time gauge updates with ticket-based BFF authentication. (`apps/web/src/components/settings/AdminUsageLimitsSection.tsx`, `apps/web/src/components/settings/AdminUsageLimitsEditModal.tsx`, `apps/api/src/domains/usage_limits/websocket.py`)
- **User Usage Limits Dashboard Tiles** — Two dashboard cards (Period Limits / Global Limits) showing color-coded progress gauges when limits are configured. Automatically hidden when all limits are unlimited. (`apps/web/src/components/usage/UsageLimitsTile.tsx`, `apps/web/src/components/usage/UsageGauge.tsx`)
- **Chat Blocking on Limit Exceeded** — Disabled message input, voice input, and destructive alert banner when user is blocked (limit reached or manual block). HTTP 429 handling in chat stream client. SSE error handler for `usage_limit_exceeded` error code with specific toast notification. (`apps/web/src/app/[lng]/dashboard/chat/page.tsx`, `apps/web/src/lib/api/chat.ts`, `apps/web/src/lib/sse-handlers/handlers.ts`)
- **Usage Limits Redis Caching** — 60-second TTL Redis cache on limit check results using existing `cache_get_json`/`cache_set_json` helpers. Cache invalidated after token persistence and admin updates. Stale cycle detection prevents false blocking after billing cycle rollover. (`apps/api/src/domains/usage_limits/service.py`)
- **Usage Limits Configuration** — New `UsageLimitsSettings` config module with feature flag (`USAGE_LIMITS_ENABLED`), default limits for new users via env vars, and configurable cache TTL. Empty string env var handling via `BeforeValidator` for Pydantic-settings compatibility. (`apps/api/src/core/config/usage_limits.py`)
- **Usage Limits Prometheus Metrics** — Two counters: `usage_limit_check_total` (by result status) and `usage_limit_enforcement_total` (by enforcement layer and limit type). (`apps/api/src/infrastructure/observability/metrics_usage_limits.py`)
- **Usage Limits Unit Tests** — 42 unit tests covering `_compute_status` pure logic (manual block, cycle/absolute limits, warning/critical thresholds, zero limits, mixed configurations, stale cycle detection), schema validation (constraints, serialization, enum roundtrip), and `_build_limit_detail` helper. (`apps/api/tests/unit/domains/usage_limits/`)
- **Usage Limits Documentation** — ADR-060 (architectural decision record) and technical documentation covering domain structure, enforcement layers, caching, API endpoints, configuration, and frontend integration. (`docs/architecture/ADR-060-Usage-Limits.md`, `docs/technical/USAGE_LIMITS.md`)
- **Internationalization (6 languages)** — Complete `usage_limits` namespace with translations for all UI elements (admin section, edit modal, dashboard tiles, blocked banner, error messages) in French, English, German, Spanish, Italian, and Chinese. (`apps/web/locales/`)

### Fixed

- **Settings focus loss on preference change** — `refreshUser()` in AuthProvider now compares `JSON.stringify(prev)` vs response before calling `setUser()`, preventing unnecessary re-renders when user data hasn't changed. Context value memoized via `useMemo`. Eliminates focus loss in input fields across all settings tabs (Preferences, Features, Administration). (`apps/web/src/lib/auth.tsx`)
- **Token/cost values mismatch with dashboard** — Usage limits token calculation now includes cached tokens (`cycle_prompt + cycle_completion + cycle_cached`) and cost calculation includes Google API costs (`cycle_cost_eur + cycle_google_api_cost_eur`) to match the dashboard display. (`apps/api/src/domains/usage_limits/repository.py`)
- **Philips Hue connector 500 error** — Fixed `connector_global_config` table storing `'philips_hue'` (lowercase enum value) instead of `'PHILIPS_HUE'` (uppercase enum name) expected by SQLAlchemy `Enum(native_enum=False)`. Data corrected in DB.
- **SQLAlchemy mapper initialization failure** — Added `import_all_models()` call in `main.py` lifespan to ensure all domain models are loaded before the first ORM query. Prevents `UserUsageLimit` forward reference resolution failure. (`apps/api/src/main.py`)
- **Admin settings section ordering** — Reorganized administration tab sections in logical order: Users → Limits → Export → Broadcast → Connectors → LLM → Google API → LLM Config → Personalities → Skills → RAG → Voice → Debug. Renamed section titles for consistency. (`apps/web/src/app/[lng]/dashboard/settings/page.tsx`)

## [1.8.2] - 2026-03-21

### Added

- **Scheduler Leader Election Resilience** — Centralized `SchedulerLeaderElector` class replaces inline leader election logic in `main.py`. Non-blocking background re-election ensures the scheduler always starts, even when a stale Redis lock exists from a killed container (Docker restart/SIGKILL). Includes automatic lock renewal, idempotent shutdown, and comprehensive structured logging (15 event types with `worker_id` correlation). (`apps/api/src/infrastructure/scheduler/leader_elector.py`)
- **Leader Elector unit tests** — 17-test suite covering immediate acquisition, no-Redis fallback, re-election after stale lock, scheduler error rollback with lock release, callback error resilience, double-start guard, and idempotent shutdown. 90% code coverage. (`apps/api/tests/unit/infrastructure/scheduler/test_leader_elector.py`)
- **Leader election debugging guide** — New "Leader election stale lock" section in the debugging guide with Redis diagnostic commands and resolution steps. (`docs/guides/GUIDE_DEBUGGING.md`)
- **SETNX lock variants documentation** — Comparison table of the three Redis SETNX lock patterns (`OAuthLock`, `SchedulerLock`, `SchedulerLeaderElector`) in the Redis architecture ADR. (`docs/architecture/ADR-029-Redis-Multi-Purpose-Architecture.md`)

### Fixed

- **Scheduler not starting after container restart** — When Docker recreated the API container, the stale `scheduler:leader` Redis lock (TTL 120s) from the killed worker prevented the new worker from acquiring leadership. The worker gave up permanently after a single failed SETNX, leaving all 15+ background jobs (journal consolidation, interest notifications, token refresh, etc.) idle. The new `SchedulerLeaderElector` retries every 5s in the background until the lock expires, then starts the scheduler. (`apps/api/src/main.py`, `apps/api/src/infrastructure/scheduler/leader_elector.py`)

## [1.8.1] - 2026-03-21

### Added

- **Journal Extraction Debug Panel** — Background journal extraction results (create/update/delete actions) now visible in the Debug Panel. New `debug_metrics_update` SSE event type emits extraction details after `await_run_id_tasks` completes. Frontend merges supplementary metrics into current debug state via `DEBUG_METRICS_UPDATE` reducer action. Extraction sub-section shows action type badges (CREATE/UPDATE/DELETE), theme, title, mood per action. (`apps/api/src/domains/agents/api/service.py`, `apps/web/src/components/debug/components/sections/JournalInjectionSection.tsx`)
- **Planner v3 Skill Guard** — Early insufficient content detection now skips when a deterministic skill has high domain overlap with the query. Prevents false-positive clarification requests on multi-domain skills (e.g., daily briefing = event+task+weather+email). New `_has_potential_skill_match()` helper with configurable `SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS` constant. (`apps/api/src/domains/agents/nodes/planner_node_v3.py`, `apps/api/src/core/constants.py`)
- **Journal Extraction Debug Registry** — In-process `_extraction_debug_results` dict with TTL-based eviction (5 min) stores extraction results per `run_id` for consumption by the SSE streaming service. (`apps/api/src/domains/journals/extraction_service.py`)
- **Planner Skill Guard unit tests** — 284-line test suite covering skill match detection, domain overlap, missing domain threshold, disabled skills, and edge cases. (`apps/api/tests/unit/domains/agents/nodes/test_planner_v3_skill_guard.py`)
- **Smart Home connector category** — `smart_home` category added to frontend connector constants and Admin Connectors section with Philips Hue entry. (`apps/web/src/constants/connectors.ts`, `apps/web/src/components/settings/AdminConnectorsSection.tsx`)
- **Smart Home i18n descriptions** — Connector description for `philips_hue` and `smart_home` category label/description added across 6 languages. (`apps/web/locales/*/translation.json`)

### Changed

- **Weather card temp range** — Current weather cards now display min/max temperature range (not shown for forecast cards which already have it in main stats). (`apps/api/src/domains/agents/display/components/weather_card.py`)
- **Journal entry ID formatting** — Entry headers in extraction and consolidation prompts now use `[id=UUID | ...]` format with a dedicated ID reference table for easy LLM copy-paste. Reduces UUID hallucination in update/delete actions. (`apps/api/src/domains/journals/extraction_service.py`, `apps/api/src/domains/journals/consolidation_service.py`)
- **Journal prompts UUID guidance** — Introspection and consolidation prompts now include CRITICAL instruction to copy-paste exact UUIDs from entry headers, with placeholder `<copy exact UUID from entry header>` in JSON examples. (`apps/api/src/domains/agents/prompts/v1/journal_introspection_prompt.txt`, `apps/api/src/domains/agents/prompts/v1/journal_consolidation_prompt.txt`)

### Fixed

- **Journal hallucinated UUID rejection** — `ExtractedJournalEntry.entry_id` now validates UUID format via `field_validator`, rejecting malformed IDs from LLM hallucination. Both extraction and consolidation services filter out actions referencing unknown entry IDs before applying them. (`apps/api/src/domains/journals/schemas.py`, `apps/api/src/domains/journals/extraction_service.py`, `apps/api/src/domains/journals/consolidation_service.py`)

## [1.8.0] - 2026-03-21

### Added

- **Philips Hue Smart Home Connector** — Full integration with Philips Hue Bridge CLIP v2 API for smart lighting control via natural language. Dual connection mode: local (press-link pairing on same network) and remote (OAuth2 via api.meethue.com cloud relay). 6 LangChain tools: `list_hue_lights_tool`, `control_hue_light_tool`, `list_hue_rooms_tool`, `control_hue_room_tool`, `list_hue_scenes_tool`, `activate_hue_scene_tool`. Multilingual color support (CIE xy mapping for en/fr/de/es), fuzzy name resolution for natural language control ("éteins le salon" → room "Salon" → grouped_light off). (`src/domains/connectors/clients/philips_hue_client.py`, `src/domains/agents/tools/hue_tools.py`)
- **Hue Bridge discovery & press-link pairing UI** — Multi-step wizard in Settings > Smart Home: bridge discovery via discovery.meethue.com, bridge selection, 30-second countdown press-link pairing flow, automatic connector activation. Separate remote mode path via OAuth2 redirect. (`apps/web/src/components/settings/connectors/HueBridgePairingForm.tsx`, `apps/web/src/components/settings/connectors/hooks/useHueConnect.ts`)
- **Hue agent with catalogue manifests** — Dedicated `hue_agent` with versioned prompt (`hue_agent_prompt.txt`), 6 tool manifests with multilingual semantic keywords (en/fr/de/es/it/zh) for Smart Planner tool selection. Agent registered in LangGraph graph with conditional routing edge. (`src/domains/agents/hue/catalogue_manifests.py`, `src/domains/agents/graphs/hue_agent_builder.py`)
- **HueOAuthProvider** — OAuth2 provider dataclass implementing `OAuthProvider` Protocol for Hue Remote API. Factory method `for_remote_control()` with dynamic redirect URI construction. PKCE support via existing `OAuthFlowHandler`. (`src/core/oauth/providers/hue.py`)
- **Smart Home domain taxonomy** — New "hue" domain in `domain_taxonomy.py` with `result_key="hues"`, enabling Smart Planner to route smart home intents. New `RegistryItemType.HUE_LIGHT` for Data Registry frontend rendering. (`src/domains/agents/registry/domain_taxonomy.py`, `src/domains/agents/data_registry/models.py`)
- **Smart Home i18n (6 languages)** — 22 translation keys per language for Hue connector UI: pairing wizard, mode selection, countdown, error messages, connection status. Covers en, fr, de, es, it, zh. (`apps/web/locales/*/translation.json`)

### Changed

- **ConnectorTool credential retrieval** — Added `is_hue` branch in `ConnectorTool.execute()` for Hue-specific credential retrieval via `get_hue_credentials()`, following the existing `is_apple` pattern. (`src/domains/agents/tools/base.py`)
- **Client registry** — `PhilipsHueClient` registered in `ClientRegistry._ensure_initialized()` alongside Google, Apple, and Microsoft clients. (`src/domains/connectors/clients/registry.py`)
- **Connector models** — New `ConnectorType.PHILIPS_HUE` enum value with `is_hue` property, `_HUE_CONNECTOR_TYPES` frozenset, `"smart_home"` functional category. (`src/domains/connectors/models.py`)
- **UserConnectorsSection** — Added "Connected Smart Home" and "Available Smart Home" sections with `HueBridgePairingForm` integration. (`apps/web/src/components/settings/UserConnectorsSection.tsx`)

### Fixed

- **LLM provider error messages** — `OverloadedError` (529) and `RateLimitError` (429) from Anthropic/OpenAI now display a user-friendly message ("Le service d'IA est temporairement surchargé. Veuillez réessayer dans quelques instants.") instead of raw technical error types (`APIStatusError`). Detection covers `stream_error()` and `generic_error()` in all 6 languages. (`src/domains/agents/api/error_messages.py`)

## [1.7.2] - 2026-03-20

### Added

- **Technical Blog (20 articles × 6 languages = 120 pages)** — Full blog system with category-organized technical articles covering architecture, integrations, features, security, and engineering. Each article enriched with verified code-sourced facts (file paths, exact numbers, real class/function names). 5 categories: Architecture (4), Integrations (4), Features (6), Security (2), Technical (4). Articles include real Python code snippets from the codebase (Prometheus metrics, `load_prompt()`, `ToolResponse`, `get_llm()` factory). (`apps/web/src/app/[lng]/blog/`, `apps/web/src/components/blog/`, `apps/web/src/data/blog-articles.ts`)
- **Blog illustrations** — 20 unique PNG illustrations (one per article) served via Next.js `<Image>` with lazy loading, responsive `sizes`, and `priority` on article hero. (`apps/web/public/articles/`)
- **Blog preview on landing page** — `BlogPreviewSection` component showing 6 featured articles with illustrations, inserted before the CTA section. Promotes blog discovery for visitors exploring LIA. (`apps/web/src/components/landing/BlogPreviewSection.tsx`)
- **Tailwind Typography plugin** — Installed `@tailwindcss/typography` for proper `prose` class rendering in blog article bodies. Configured via `@plugin` directive in globals.css.
- **Tempo distributed tracing (production)** — Deployed Grafana Tempo on RPi5 prod, completing the observability trifecta (metrics + logs + traces). Service `lia-tempo-prod` with 0.5 CPU / 512 MB limits, 7-day retention with automatic compaction, zstd/snappy compression. Enables Dashboard 06 (Logs & Traces), trace↔log↔metric correlation via exemplars, and Tempo service graph in Grafana. (`docker-compose.prod.yml`, `infrastructure/observability/tempo/tempo.yml`)
- **Scheduler leader election** — Redis SETNX-based leader election ensures only 1 of 4 uvicorn workers starts APScheduler. Eliminates duplicate job execution caused by `--workers 4`. Lock renewed every 30s (TTL 120s) with automatic failover if leader crashes. Non-leader workers skip scheduler entirely. (`src/main.py`, `src/core/constants.py`)

### Changed

- **SEO & GEO (Generative Engine Optimization)** — Enhanced metadata for Google and AI search engines:
  - OpenGraph images per article (PNG illustrations) with `summary_large_image` Twitter cards
  - `image` and `articleSection` fields added to JSON-LD `BlogPosting` schema
  - `authors` metadata on article pages
  - OpenGraph image on blog listing page
  - Sitemap XML extended with 21 blog URLs (listing + 20 articles) with hreflang alternates
  - `robots.txt` updated: blog paths allowed for all crawlers, AI search bots (OAI-SearchBot, PerplexityBot, Claude-SearchBot) explicitly permitted
  - `llms.txt` updated with blog link and corrected statistics
- **Landing page meta descriptions** — SEO-optimized with keywords "Open Source", "Multi-Agent", "HITL", "6 Languages", "7 LLM providers", "Privacy by design" in all 6 languages.
- **Landing stats correction** — Agent count corrected from 18 to 15 (verified: 15 domain agent builders in `src/domains/agents/graphs/`). Prometheus metrics count corrected from 500 to 350 (verified: 357 metric definitions across 17 observability files).
- **Blog navigation** — `nav.blog` link integrated into `NAV_SECTIONS` array with same styling as other nav items (was isolated in "Right actions" zone with different markup). Supports both anchor links (`#section`) and route links (`/blog`) in the same nav. (`LandingHeader.tsx`)
- **Landing navigation order** — Reordered to: Comment ça marche → Fonctionnalités → Sécurité → Technologie → Blog (was: Fonctionnalités → Comment ça marche → ..., Blog separated).
- **Prometheus remote-write receiver (production)** — Added `--web.enable-remote-write-receiver` flag to prod Prometheus, enabling Tempo's metrics-generator to push span metrics (service graphs, span latency histograms). (`docker-compose.prod.yml`)
- **Grafana prod parity with dev** — Added `grafana.ini` volume mount (Tempo feature flags: `tempoSearch`, `tempoServiceGraph`, `traceqlEditor`) and `depends_on: [prometheus, loki, tempo]`. (`docker-compose.prod.yml`)

### Fixed

- **Factual accuracy audit (8 corrections × 6 languages = 48 fixes)** — Systematic verification of all blog article claims against actual source code:
  - Agent count: 18+ → 15 (verified via `find graphs/ -name "*_builder.py"`)
  - LLM configuration: "environment variables" → "Administration > LLM Configuration" (admin UI is primary, env vars are fallback)
  - Claude model name: `claude-3.5-sonnet` → `claude-sonnet-4-5`
  - RAG embedding model: `E5-small (384 dims)` → `text-embedding-3-small (1536 dims)` (verified in `constants.py`)
  - Wake word: "Hey LIA" → "OK Guy" (verified in `sherpaKws.ts`)
  - Prometheus metrics: 500+ → 350+ (verified: 357 definitions)
  - Prompt count: 45+ → 55 (verified: `find prompts -name "*.txt"`)
  - Token reduction: 93% → 96% (verified in `NormalFilteringStrategy` docstring)
- **Consistent agent count across all surfaces** — Updated FAQ, meta descriptions, `llms.txt`, landing stats, `WebSiteJsonLd`, and all blog references from "18+" to "15" across all 6 languages.
- **Scheduler ×4 duplicate execution** — All 4 uvicorn workers were running independent APScheduler instances, causing every job to execute 4× per interval. Root cause: `--workers 4` in `Dockerfile.prod` with no leader coordination. Fixed with Redis leader election (root cause) + `SchedulerLock` on 5 previously unprotected jobs as safety net: `token_refresh`, `currency_sync`, `memory_cleanup`, `interest_cleanup`, `unverified_account_cleanup`. (`src/main.py`, `src/infrastructure/scheduler/*.py`, `src/core/constants.py`)
- **Tempo OTLP export failures (4 months of silent errors)** — API spammed `Failed to export traces to tempo:4317, StatusCode.UNAVAILABLE` continuously since Tempo was never deployed in prod. Two sub-bugs: (1) Tempo service absent from `docker-compose.prod.yml` despite full config existing, (2) `OTLPSpanExporter(insecure=not settings.is_production)` forced TLS for Docker-internal gRPC — changed to `insecure=True`. (`tracing.py`, `docker-compose.prod.yml`)
- **Background task timeout (memory/interest/journal extraction)** — Post-response LLM extraction tasks (memory, interests, journals) were silently abandoned after 5s timeout. On RPi5 with network latency, LLM calls routinely exceed 5s. Increased `await_run_id_tasks` timeout from 5s to 15s. (`src/infrastructure/async_utils.py`, `src/domains/agents/api/service.py`)
- **Weather hourly forecast `save_details_missing_primary_id`** — Context registry for weather uses `primary_id_field="date"`, but hourly forecast payload lacked a `date` field (only daily/current had it). Added `date` field to hourly forecast registry item. (`weather_tools.py`)
- **Qwen `extra_body` LangChain warning** — `extra_body` (for Qwen thinking mode) was nested inside `model_kwargs` dict, triggering LangChain `UserWarning: Parameters {'extra_body'} should be specified explicitly`. Moved to direct kwarg of `init_chat_model`. (`adapter.py`)

## [1.7.1] - 2026-03-20

### Fixed

- **Constants centralization audit (25 files)** — Systematic elimination of ~60 hardcoded default values across backend and frontend. All configurable defaults now reference centralized constants from `src/core/constants.py` instead of inline literals. Prevents silent divergence between code paths that should share the same default value.
- **Journal settings persistence bug** — Numeric settings (prompt injection budget, max entry size, max search results) appeared to save successfully but reverted on page refresh. Root cause: React `useState` initializers ran once with stale `initialData` and were never synchronized with actual server values. Fix: added `useEffect` sync + removed hardcoded `initialData` from `useJournals`, `useHeartbeatSettings`, and `useInterests` hooks. The API is now the single source of truth for all settings.
- **`journals_enabled` inconsistent defaults** — Three code paths used different fallback values for the same field: `router.py` defaulted to `True`, while `context_builder.py` and `context_aggregator.py` defaulted to `False`. This caused journals to appear enabled in the UI while being silently excluded from heartbeat context and prompt injection. Unified to `JOURNALS_ENABLED_DEFAULT = True`.
- **Proactive notification language bug** — `proactive/runner.py` and `proactive/notification.py` used `"en"` as the language fallback, while all other code paths used `"fr"`. Users without an explicit language preference received notification titles in English instead of French. All sites now use `DEFAULT_LANGUAGE` constant.
- **Interest eligibility checker wrong defaults** — `EligibilityChecker` used heartbeat defaults (min=1, max=3) for interest notifications instead of interest-specific defaults (min=2, max=5). Interests were under-notified (capped at 3/day instead of 5). Refactored constructor to accept `default_min_per_day` / `default_max_per_day` parameters, passed from each scheduler with the correct constants.
- **Frontend optimistic update without revert** — `useInterests.ts` `updateSettings` applied optimistic state changes but never reverted on mutation failure. Added `refetchSettings()` on error to restore server state.

### Changed

- **12 new constants in `constants.py`** — `HEARTBEAT_MIN_PER_DAY_DEFAULT`, `HEARTBEAT_PUSH_ENABLED_DEFAULT`, `HEARTBEAT_NOTIFY_START/END_HOUR_DEFAULT`, `INTEREST_NOTIFY_MIN/MAX_PER_DAY_DEFAULT`, `HEARTBEAT_DECISION/MESSAGE_LLM_MODEL_DEFAULT`, `TOKEN_SUMMARY_CACHE_TTL`, `JOURNALS_ENABLED_DEFAULT`, `JOURNAL_CONSOLIDATION_ENABLED/WITH_HISTORY_DEFAULT`.
- **User model `server_default` alignment** — All 15 user preference columns in `auth/models.py` (timezone, language, interests×4, heartbeat×5, journals×4) now reference constants instead of string literals.
- **`EligibilityChecker` parameterization** — Added `default_start_hour`, `default_end_hour`, `default_min_per_day`, `default_max_per_day` constructor parameters to support task-specific fallback values.

### Security

- **CVE-2026-33228 — `flatted` Prototype Pollution (HIGH)** — Transitive dev dependency `flatted <= 3.4.1` (via eslint → flat-cache) vulnerable to prototype pollution via `parse()`. Fixed via `pnpm.overrides` forcing `flatted >= 3.4.2`. Dev-only dependency — no production runtime impact.
- **GitHub Actions bumped** — codecov/codecov-action 5.5.2→5.5.3, softprops/action-gh-release 2.3.2→2.3.3, github/codeql-action 3.28.16→3.28.17 (PR #63).

## [1.7.0] - 2026-03-20

### Added

- **Personal Journals — Carnets de Bord (evolution)** — The AI assistant now maintains thematic personal journals (self-reflection, user observations, ideas & analyses, learnings) written in first person, colored by its active personality. Dual trigger system: post-conversation extraction (fire-and-forget background task analyzing last user message + context) and periodic consolidation (APScheduler every 4h, reviews and reorganizes notes). Semantic context injection into both response AND planner prompts via E5-small cosine similarity search with configurable minimum score prefiltering (`JOURNAL_CONTEXT_MIN_SCORE`) — two distinct queries (response: tone/formulation, planner: reasoning/learnings). Prompt-driven autonomous lifecycle management: the assistant decides what to keep, summarize, merge, or delete based on a configurable size constraint. Full user control: enable/disable without data loss, configurable consolidation, optional conversation history analysis (with cost warning), 4 numeric settings (max total chars, context budget, max entry chars, max search results). CRUD operations in Settings > Features with theme-based accordion, size gauge, and real cost tracking. GDPR compliant: JSON/CSV export + bulk delete. LLM models configurable in Admin > LLM Configuration (category: background). Heartbeat integration: journals as a context source for proactive notifications with dynamic query (second pass after context aggregation), toggleable badge in heartbeat settings. Debug panel: dedicated "Personal Journals" section showing injection metrics (entries found/injected, scores, budget, per-entry details). (`src/domains/journals/`, `journal_introspection_prompt.txt`, `journal_consolidation_prompt.txt`, `JournalInjectionSection.tsx`, `ADR-057-Personal-Journals.md`, 35 unit tests)

### Database

- **Migration `journals_001`** — Created `journal_entries` table (UUID PK, user_id FK CASCADE, theme, title, content, mood, status, source, session_id, personality_code, char_count, embedding ARRAY(Float), timestamps). Added 11 columns to `users` table: journals_enabled, journal_consolidation_enabled, journal_consolidation_with_history, journal_max_total_chars, journal_context_max_chars, journal_last_consolidated_at, journal_last_cost_tokens_in/out/eur/at/source. Composite indexes on (user_id, status, created_at) and (user_id, theme).
- **Migration `journals_002`** — Added 2 user-configurable columns: journal_max_entry_chars (Integer, default 2000), journal_context_max_results (Integer, default 10). Idempotent upgrade (skips if columns already exist).

## [1.6.1] - 2026-03-19

### Added

- **System RAG Spaces — App Self-Knowledge (evolution)** — LIA can now answer questions about itself, its features, and usage directly in conversation. Built-in FAQ knowledge base (119+ Q/A across 17 sections) indexed from English Markdown files (`docs/knowledge/`), with LLM translation at response time (6 languages). Includes: `SystemSpaceIndexer` with SHA-256 hash-based staleness detection, `is_app_help_query` detection in QueryAnalyzer, RoutingDecider Rule 0 override (prevents misrouting "how do I connect my calendar?" to the planner), App Identity Prompt (~200 tokens) injected conditionally (lazy loading — zero overhead on normal queries), 3 admin API endpoints (list/reindex/staleness), admin UI section with staleness badge and reindex button, automatic indexation at app startup (idempotent — skips if hash matches), 3 Prometheus metrics, seed script (`task db:seed:system-rag`). (`system_indexer.py`, `app_identity_prompt.txt`, `ADR-058`, 35 unit tests)

### Database

- **Migration `system_rag_spaces_001`** — `rag_spaces`: added `is_system` (Boolean, NOT NULL, default false) and `content_hash` (String(64), nullable). Made `user_id` nullable on `rag_spaces`, `rag_documents`, `rag_chunks` (system spaces have no owner). Replaced unique index `uq_rag_spaces_user_id_name` with partial unique indexes: `uq_rag_spaces_user_name` (WHERE user_id IS NOT NULL) and `uq_rag_spaces_system_name` (WHERE is_system = true). Added index `ix_rag_spaces_is_system`.

## [1.6.0] - 2026-03-19

### Added

- **Browser Control (evolution F7)** — Interactive web browsing via Playwright headless Chromium. Autonomous ReAct agent (`browser_task_tool`) navigates websites, searches content, clicks elements, fills forms, and extracts data from JavaScript-rendered pages. Multi-step interaction handled internally — planner sends a natural language task, agent executes autonomously. Includes: session pool with cross-worker Redis recovery, SSRF prevention (reuses web_fetch URL validator), accessibility tree extraction via CDP, generic cookie banner auto-dismiss (20+ multi-language selectors), anti-detection (Chrome UA, webdriver flag removed, dynamic locale/timezone from user preferences), page crash recovery, Prometheus metrics (6 gauges/counters/histograms). Activation via admin connector panel. (`infrastructure/browser/`, `browser_tools.py`, `browser_agent_builder.py`, `browser_agent_prompt.txt`, 36 unit tests)
- **Qwen provider support** — Added Qwen (Alibaba Cloud) as a native LLM provider via DashScope international OpenAI-compatible API. 3 models: qwen3-max (thinking-only), qwen3.5-plus (tools + vision + thinking), qwen3.5-flash (cost-effective). Includes thinking mode mapping (reasoning_effort → enable_thinking + thinking_budget), implicit cache, streaming metrics, model profiles with pricing. (`adapter.py`, `model_profiles.py`, `llm_pricing_seed.sql`, `AdminLLMConfigSection.tsx`)
- **Ollama dynamic model discovery** — Admin LLM config now dynamically lists models installed on the Ollama server with real capabilities. Two-phase discovery: `GET /api/tags` + `POST /api/show` per model (parallel). Dropdown auto-populates when selecting Ollama as provider. In-memory cache (60s TTL), 5s HTTP timeout, per-model error isolation. New endpoint: `GET /admin/llm-config/providers/ollama/models`. (`ollama_discovery.py`, `service.py`, `router.py`, `AdminLLMConfigSection.tsx`)
- **ADR-059** — Architecture Decision Record for Browser Control (ReAct agent, CDP accessibility, Redis session coordination, anti-detection).
- **Browser technical documentation** — `BROWSER_CONTROL.md` (architecture, configuration, security, metrics, limitations).
- **Browser security section** — Added "Browser Automation Security" to `SECURITY.md` (sandbox, SSRF, input sanitization, anti-detection trade-offs).

### Changed

- **LLM config metadata** — Filtered out internal `"default"` fallback entries from the model dropdown for all providers (was showing "default" as a selectable model name).
- **LLM serializer** — Added `content_summary` to `CONTENT_FIELDS` for proper serialization of browser page content (prevents 60-char truncation).
- **Type domain mapping** — Added `browsers` to `SKIP_FILTER_RESULT_KEYS` (browser content always relevant, not emptied by intelligent filtering).

## [1.5.2] - 2026-03-18

### Added

- **RAG Spaces — 15 document formats** — Extended RAG document upload from 4 to 15 formats: PDF, TXT, MD, DOCX, PPTX (slides + tables + notes), XLSX (multi-sheet), CSV, RTF, HTML, ODT, ODS, ODP, EPUB (spine-ordered), JSON, XML (defusedxml). Each format has a dedicated text extractor with edge-case handling. (`processing.py`, `constants.py`, `service.py`)
- **RAG Spaces — Google Drive folder sync** — Link Google Drive folders to RAG Spaces for automatic file vectorization. Manual sync with incremental change detection (skip unchanged, re-process modified, auto-delete removed). Supports Google Docs/Sheets/Slides via API export. Per-file error isolation, Semaphore(5) throttling, atomic sync lock, 500-file pagination cap. Feature flag: `RAG_SPACES_DRIVE_SYNC_ENABLED`. (`drive_sync.py`, 6 API endpoints, 5 frontend components)
- **RAG Drive folder browser** — Folder picker dialog showing both folders (navigable) and files (preview) so users can see what will be synced before selecting.
- **Drive sync Prometheus metrics** — 4 new metrics: `rag_drive_sync_runs_total`, `rag_drive_sync_duration_seconds`, `rag_drive_sync_files_total`, `rag_drive_sources_total_count`.
- **ADR-056** — Architecture Decision Record for RAG Drive Sync (manual-first, non-recursive, incremental sync, per-file error isolation).

### Changed

- **RAG upload format display** — Compact "15+ supported formats" label with tooltip listing all formats (was: "PDF, TXT, MD, DOCX").
- **RAG document model** — Added `source_type`, `drive_source_id`, `drive_file_id`, `drive_modified_time` columns for Drive integration.

### Database

- **Migration `drive_sources_001`** — New `rag_drive_sources` table + 4 columns on `rag_documents` with indexes and FK constraints.

## [1.5.1] - 2026-03-17

### Added

- **Skill Generator meta-skill** — Built-in system skill (`skill-generator`) that guides users through creating custom SKILL.md files from natural language descriptions. 4-phase advisory process: need analysis, archetype selection (Prompt Expert / Advisory / Plan Template), generation with format validation, and delivery with import instructions. Includes 3 reference files (format specification, full tool catalogue with 60+ tools and 17 agents, archetype examples) and a sandboxed Python validation script. Multilingual support (body in user's language, description in English). Compliant with the agentskills.io open standard.

### Security

CodeQL security hardening and code quality sweep. Addresses 667 code scanning alerts (35 critical/high security, 33 errors, 47 warnings, 552 notes). Zero functional regression — all 6,279 unit tests pass.

### Security

- **Removed `verify=False` on Static Maps proxy** — TLS certificate validation was disabled on the `httpx` client proxying Google Static Maps requests, exposing the Google API key to potential MITM interception. Now uses default `verify=True`. (`connectors/router.py`)
- **Added `photo_name` input validation on Places photo proxy** — The `{photo_name:path}` route parameter accepted arbitrary path segments, potentially reaching unintended Google API endpoints with the server's API key. Added regex validation (`^places/[^/]+/photos/[^/]+$`) matching Google's official resource name spec. (`connectors/router.py`)
- **Removed stack-trace exposure in SSE error events** — Exception details (`str(e)`) were sent to the client via Server-Sent Events, potentially leaking internal paths, SQL queries, or connection strings. Replaced with generic error message; detailed error preserved in server logs. (`notifications/router.py`)
- **Masked admin password in CLI output** — The `create_admin.py` setup script printed the admin password in clear text to stdout, capturable by Docker logs or CI pipelines. Now displays masked output. (`scripts/data/create_admin.py`)
- **Gated TLS bypass by `NODE_ENV` in RAG upload proxy** — `rejectUnauthorized: false` was applied unconditionally (not just in development). Now only disables TLS validation when `NODE_ENV !== 'production'`. (`apps/web/src/app/api/rag-upload/[spaceId]/route.ts`)
- **Fixed incomplete HTML tag stripping regex** — `</script>`, `</style>`, `</head>` regexes did not match variants with whitespace before `>` (e.g., `</script >`). Added `\s*` to closing tag patterns. (`display/components/base.py`)

### Fixed

- **`ToolValidationError` crash on multi-field validation** — `validate_fields()` passed `fields=missing` (plural) to `ToolValidationError.__init__` which only accepts `field=` (singular), causing a `TypeError` when 2+ required fields were missing. Fixed to `field=", ".join(missing)`. (`tools/validation_helpers.py`)
- **Uninitialized `errors` variable in email/calendar tools** — `errors` was assigned only inside the `mode == "batch"` branch but could theoretically be accessed outside it after refactoring. Added defensive `errors = None` initialization before branching. (`emails_tools.py`, `calendar_tools.py`)
- **`AgentService.__init__` duplicated mixin attributes** — Four attributes were manually duplicated from `GraphManagementMixin.__init__`. Refactored to use `super().__init__()`. Added missing `hitl_orchestrator` initialization to the mixin. (`api/service.py`, `graph_management.py`)
- **Overly broad `except Exception` in approval gate** — Tool manifest fallback catch was `except Exception:` (masking DB/network errors), while `validator.py` used the specific `except ToolManifestNotFound:`. Narrowed to match. (`approval_gate_node.py`)
- **Overly broad `except Exception` in place card** — Opening hours parsing caught all exceptions instead of the expected `(ValueError, IndexError, TypeError)`. (`place_card.py`)

### Changed

- **Added debug logging to 18 silent `except: pass` blocks** — Best-effort patterns (user preferences, cache invalidation, CalDAV close, LLM callbacks, OAuth discovery, session cleanup) now emit `logger.debug()` for production observability without changing error-handling behavior.
- **Extracted `get_user_language_safe()` DRY helper** — Replaced 4 identical try-except-for-language patterns in `places_tools.py` with a single shared helper in `runtime_helpers.py`. Narrows exception scope from `Exception` to `(ValueError, KeyError, RuntimeError, AttributeError)`.
- **Elevated `token_counter_service` fallback level warning** — Unknown fallback levels now emit `logger.warning` (was silent `pass`) to surface configuration drift.

### Removed

- **16 unused constants** from `agents/constants.py` — 7 legacy `NODE_*_AGENT` constants (replaced by agent catalogue), 1 `CONTEXT_DOMAIN_TASK_LISTS`, 8 legacy `HITL_*` keys (replaced by Phase 3.3 orchestrator).
- **10 legacy `_*_direct_tool_instance` variables** — Unused module-level tool instances in `calendar_tools.py`, `drive_tools.py`, `emails_tools.py`, `google_contacts_tools.py`, `tasks_tools.py`. Marked `LEGACY` in code, excluded from tool registry by underscore prefix convention.
- **12 unused global variables** — Dead logger instances (`goal_inferrer.py`, `planner_utils.py`), obsolete constants (`PRIOR_ALPHA/BETA`, `_CURRENCY_USD/EUR`, `_DESTRUCTIVE_LABEL_WITH_CHILDREN`), write-only `_last_update`, unused `TypeVar T`.
- **~25 unused imports** across 18 files — Removed unused `Language`, `Set`, `List`, `Dict`, `Optional`, `Tuple`, `ast`, `re`, `json`, `subprocess`, `os`, `yaml`, `asdict`, `Template`, `UUID`, `get_function_complexity` imports from source, scripts, and infrastructure files.
- **Self-assignment dead code** in `mixins.py` — `ToolOutputMixin = ToolOutputMixin` and `create_tool_formatter = create_tool_formatter` (no-ops, re-exports handled by `__init__.py`).

## [1.5.0] - 2026-03-17

### Added

- **Persistent specialized sub-agents (F6)** — Delegation system allowing the principal assistant to spawn ephemeral expert sub-agents for complex tasks (research, analysis, synthesis). Includes full DDD domain (`src/domains/sub_agents/`), ORM model, repository, service, REST API (10 endpoints), 3 pre-defined templates (Research Assistant, Writing Assistant, Data Analyst). Sub-agents execute through a simplified direct pipeline (query analysis → planner → parallel executor → LLM synthesis), bypassing the full graph's semantic validator, approval gate, and response node. Read-only V1 (all write tools blocked). Feature flag: `SUB_AGENTS_ENABLED`.
- **Sub-agent planner integration** — Transversal `delegate_to_sub_agent_tool` always included in planner catalogue via `NormalFilteringStrategy`. Planner prompt extended with `{sub_agents_section}` guidelines. Multiple delegates execute in parallel (wave-based). Depth limit: sub-agents cannot spawn sub-sub-agents.
- **Sub-agent catalogue manifests** — `AgentManifest` + `ToolManifest` with semantic keywords for natural discovery (`src/domains/agents/sub_agents/catalogue_manifests.py`).
- **Sub-agent token guard-rails** — Per-execution budget (`SUBAGENT_MAX_TOKEN_BUDGET`), daily budget per user (`SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY`), auto-disable after consecutive failures (`SUBAGENT_MAX_CONSECUTIVE_FAILURES`). `TokenTrackingCallback` consolidation into parent tracker.
- **Sub-agent HITL rejection fallback** — When user rejects a plan with delegation steps, system auto-replans without sub-agents. Catalogue exclusion via `exclude_sub_agent_tools` flag.
- **Sub-agent semantic validator exceptions** — `for_each` cardinality check and repeated-tool consolidation exempt `delegate_to_sub_agent_tool` steps (each step delegates to a different expert).
- **Sub-agent user preference** — Per-user `sub_agents_enabled` toggle (Settings > Features > Sub-Agents). `SubAgentsSettings.tsx` component. `PATCH /auth/me/sub-agents-preference` endpoint.
- **Sub-agent stale recovery job** — APScheduler job recovers sub-agents stuck in `executing` state (configurable interval).
- **Sub-agent observability** — Prometheus metrics module (`metrics_subagent.py`). Sub-agent notification type in SSE/FCM.
- **Skills DB refactoring** — Normalized skills persistence from JSONB `disabled_skills` columns to two relational tables: `skills` (registry: name, is_system, owner_id, admin_enabled, description, descriptions) + `user_skill_states` (user_id, skill_id, is_active). Migration includes data migration from legacy columns. `SkillPreferenceService` for sync, toggle, and state queries. `active_skills_ctx` ContextVar replaces `disabled_skills_ctx` (positive set).
- **Skills admin system-toggle** — `PATCH /skills/admin/{name}/system-toggle` endpoint. When admin disables a system skill, `is_active` is set to `false` for all users. New `adminSystemToggleSkill` in `useSkills` hook. Admin view fetches from `/skills/admin/list`.
- **Skills preference repository** — `SkillRepository` and `SkillStateRepository` for normalized DB access, with `ensure_states_for_user()` and `get_active_skill_names()` methods.
- **HITL plan approval question prompt** — Dedicated prompt template (`hitl_plan_approval_question_prompt.txt`) for generating approval gate questions, avoiding ambiguous/contradictory formulations.
- **Subagent synthesis prompt** — Dedicated prompt (`subagent_synthesis_prompt.txt`) for sub-agent result synthesis.
- **Provider cost adjustment documentation** — Investigation of Anthropic billing delta (~11%) with recommended `cost_adjustment_factor` solution (`docs/technical/PROVIDER_COST_ADJUSTMENT.md`).
- **Google Routes client** — `GoogleRoutesClient` for directions/transit route queries (`src/domains/connectors/clients/google_routes_client.py`).
- **Sub-agents i18n** — All 6 languages (en, fr, de, es, it, zh): templates names/descriptions, settings labels, LLM type label.
- **Sub-agents documentation** — `docs/technical/SUB_AGENTS.md`, `docs/INDEX.md` updated, `docs/ARCHITECTURE.md` updated for skills DB model.
- **104 files changed** — 8,029 insertions, 251 deletions across backend, frontend, docs, and configuration.

### Changed

- **Skills context propagation** — Replaced `disabled_skills_ctx` (negative set) with `active_skills_ctx` (positive set) in `AgentService` and skill injection. Only active skills are injected into the assistant prompt.
- **Skills frontend** — `AdminSkillsSection` now uses `admin_enabled` flag and `adminSystemToggleSkill`. `SkillsSettings` user view shows only admin-enabled system skills. `useSkills` hook accepts `adminView` parameter.
- **HITL interrupt handler** — Removed misleading token metadata from `STREAM_DONE` payload (HITL tokens are partial/incomplete).
- **Smart planner prompts** — Extended with sub-agent delegation section, explicit `execution_mode` (sequential/parallel) and `timeout_seconds` per step in plan schema, guidelines for both single-domain and multi-domain planners.
- **Query intelligence** — Added `include_sub_agent_tools` flag to `ToolFilter` (always `true` for planner).
- **Conversation repository** — Updated queries for sub-agent session tracking. Google API costs now included in per-message and aggregate cost totals.
- **LLM factory** — Added `subagent` LLM type with default model configuration.
- **LLM defaults migration** — Router, planner, semantic validator, approval gate switched to Anthropic `claude-sonnet-4-6` (reasoning: low). Compaction switched to `gpt-4.1-mini` (reasoning: medium).

### Fixed

- **Skills system-disable propagation** — Admin-disabled system skills are now properly excluded from the agent flow (was only excluded from UI, not from assistant context).
- **Google API cost not included in totals** — Costs from Google APIs (Routes Matrix, etc.) stored in `google_api_cost_eur` were not added to the displayed total cost. Fixed in conversation service (per-message cost), conversation repository (aggregate queries), chat service (user statistics), and streaming debug panel. All cost displays now show LLM + Google API combined.
- **HITL question tokens not tracked** — Token consumption for HITL approval question generation was not tracked, causing cost under-reporting (~€0.03/request on Anthropic models). Fixed by wrapping `TrackingContext` in a `TokenTrackingCallback` for the HITL question generator.
- **HITL approval question ambiguous** — Approval gate could generate two contradictory questions in a single prompt. New dedicated prompt template (`hitl_plan_approval_question_prompt.txt`) enforces a single YES/NO-answerable question.
- **Debug panel DB-aggregated tokens** — HITL flows now fetch DB-aggregated token totals (includes tokens from prior SSE request: router, planner, HITL question) for accurate debug panel display.
- **Google Routes Matrix JSON parsing** — `GoogleRoutesClient` now handles both JSON array and NDJSON response formats (was failing on standard JSON array responses).
- **Concurrent connector access in parallel execution** — `ConcurrencySafeConnectorService.is_connector_active()` was not wrapped with the concurrency lock, causing "concurrent operations are not permitted" errors during parallel sub-agent/tool executions.

## [1.4.7] - 2026-03-16

### Added

- **Intelligent context compaction (F4)** — LLM-based conversation history summarization when token count exceeds a dynamic threshold (configurable ratio of response model context window). Preserves recent messages and critical identifiers (UUIDs, URLs, emails). Includes `/resume` user command for forced compaction, 4 HITL safety conditions, chunked summarization for large histories, descriptive fallback on LLM failure. Configurable via 6 `.env` settings (`COMPACTION_*`). New LLM type `compaction` (GPT-4.1-nano default) visible in admin LLM config panel. 6 Prometheus metrics. Graph entry point changed: `compaction → router`. Schema version bumped to 1.1 with migration.
- **Planner cost-awareness for web search** — `unified_web_search_tool` catalogue description now includes cost constraint (max 1 call per plan), directing planner to use lightweight `brave_search_tool` for additional searches.
- **FAQ `/resume` command** — Added FAQ entry explaining the `/resume` command in all 6 languages (en, fr, de, es, it, zh).

## [1.4.6] - 2026-03-16

### Added

- **Heartbeat email source** — Proactive notifications now aggregate today's unread inbox emails as a 9th context source. Supports Google Gmail, Apple Email, and Microsoft Outlook via dynamic provider resolution. LLM filters for urgent/actionable emails only (skips newsletters, marketing). Configurable via `HEARTBEAT_CONTEXT_EMAILS_MAX` (default: 5).
- **Gmail message normalization** — `GoogleGmailClient.get_message()` now extracts top-level `from`, `subject`, `to`, `cc`, `body`, `_provider` fields, matching the format already produced by Apple and Microsoft normalizers. Enables provider-agnostic message consumption throughout the application.
- **Plan validation error logging** — `PlanValidator` now logs individual validation errors and warnings with full details (code, message, step_index, tool_name, context) for debugging.

### Fixed

- **Plan validator false UNAUTHORIZED errors** — `planner_node_v3` was not passing `oauth_scopes` from state to `ValidationContext`, causing all scope-requiring tools to fail validation. Fixed by reading `state["oauth_scopes"]` (matches `approval_gate_node` pattern).

## [1.4.5] - 2026-03-16

### Added

- **External Content Wrapping (F2)** — Prompt injection prevention for untrusted web content. All external content (web pages, Perplexity synthesis, Brave snippets, Wikipedia summaries) is wrapped in `<external_content>` safety markers with an `[UNTRUSTED EXTERNAL CONTENT]` warning before being sent to the LLM. Tag occurrences within content are escaped to prevent marker breakout. Feature-flagged via `EXTERNAL_CONTENT_WRAPPING_ENABLED` (default: `true`).
- **`content_wrapper` module** (`src/domains/agents/utils/content_wrapper.py`) — `wrap_external_content()` and `strip_external_markers()` functions with XML attribute injection prevention (`source_url` quote escaping).
- **21 unit tests** for content wrapping covering wrapping, stripping, roundtrip, tag escape attacks, XML attribute injection, and real-world integration scenarios.

### Changed

- `fetch_web_page_tool` — Markdown content is wrapped with safety markers after sanitization and truncation (step 11).
- `web_search_tools` — Perplexity synthesis, Brave snippets, and Wikipedia summaries are individually wrapped when `external_content_wrapping_enabled` is true.
- `.env.example` — Added `EXTERNAL_CONTENT_WRAPPING_ENABLED` variable.

### Fixed

- `html_renderer.py` — Removed incorrect `web_fetch` → `WebSearchCard` mapping that rendered an empty card. Web fetch results are inline in the LLM response text and do not need a visual card.

## [1.4.4] - 2026-03-16

### Added

- **Web Search/Fetch Cache** — Redis TTL cache for `unified_web_search_tool` (5 min) and `fetch_web_page_tool` (10 min) results. Reduces external API calls (Brave, Perplexity) and HTTP fetches for repeated queries. Configurable via `WEB_SEARCH_CACHE_ENABLED`, `WEB_SEARCH_CACHE_TTL_SECONDS`, `WEB_FETCH_CACHE_TTL_SECONDS` environment variables. Multi-tenant isolated by user_id.
- **`force_refresh` parameter** on `unified_web_search_tool` and `fetch_web_page_tool` — allows planner to bypass cache when user explicitly requests fresh results.
- **`WebSearchCache` class** (`src/infrastructure/cache/web_search_cache.py`) — follows existing `ContactsCache` pattern with `CacheEntryV2` format, automatic Prometheus metrics (`cache_hit_total`/`cache_miss_total`), and graceful degradation on Redis errors.
- **Recency normalization** — `_normalize_recency()` function converts non-standard planner values (`"7d"`, `"pd"`, `"1w"`) to canonical values (`"day"`, `"week"`, `"month"`). Prevents cache key fragmentation and ensures correct API parameter passing.
- **Catalogue manifest enum constraint** — `recency` parameter on `unified_web_search_tool` manifest now has an `enum` constraint guiding the planner to generate valid values only.
- **13 unit tests** for `WebSearchCache` covering cache hit/miss, TTL, disabled state, Redis errors, multi-tenant isolation, and recency key differentiation.

### Changed

- `unified_web_search_tool` — Cache check before triple parallel search (Perplexity + Brave + Wikipedia), cache store after success. Registry updates excluded from cache (RegistryItem objects not serializable).
- `fetch_web_page_tool` — Cache check before HTTP fetch, cache store after extraction. Eliminates redundant HTTP calls for same URL within TTL window.
- `.env.example` — Added 5 new web cache configuration variables.
- `docs/technical/WEB_FETCH.md` — Added cache architecture section, Redis TTL documentation, `force_refresh` parameter documentation.
- `docs/technical/TOOLS.md` — Added `unified_web_search` and `fetch_web_page` to cache hit rates table.
- `docs/architecture/ADR-029-Redis-Multi-Purpose-Architecture.md` — Added `web_search:{user}:{hash}` and `web_fetch:{user}:{hash}` cache keys to architecture diagram and key reference table.

## [1.4.3] - 2026-03-16

### Changed

- **httpx** 0.27.2 → 0.28.1 — Migrate test fixture from `app=` to `ASGITransport(app=)`, add explicit `follow_redirects=False` on 6 OAuth credential flows (RFC 6749/7009)
- **langgraph** 1.0.10 → 1.1.2 — Required by langchain 1.2.12
- **langchain-core** 1.2.17 → 1.2.19
- **langchain** 1.2.10 → 1.2.12
- **langchain-openai** 1.1.10 → 1.1.11
- **langchain-anthropic** 1.3.4 → 1.3.5
- **langchain-google-genai** 3.2.0 → 4.2.1 — SDK rewrite (google-generativeai → google-genai)
- **firebase-admin** 6.8.0 → 7.2.0 — Removed deprecated send_all/send_multicast (not used)
- **ruff** 0.8.4 → 0.15.6 — Exclude new UP042/UP045/UP046/UP047 cosmetic rules
- **mypy** 1.13.0 → 1.19.1 — Remove stale type:ignore, add overrides for new strict checks
- **pytest** 8.3.3 → 9.0.2
- **pytest-asyncio** 0.24.0 → 1.3.0
- **pytest-cov** 6.0.0 → 7.0.0
- **psycopg** 3.2.10 → 3.3.3
- **pgvector** 0.3.6 → 0.4.2
- **redis** 7.1.0 → 7.3.0
- **uvicorn** 0.40.0 → 0.41.0
- **asyncpg** 0.30.0 → 0.31.0
- **sentence-transformers** 5.2.0 → 5.3.0
- **opentelemetry** 1.39.1 → 1.40.0 (api, sdk, instrumentation-fastapi, exporter-otlp)
- **python-jose** 3.4.0 → 3.5.0
- **python-dotenv** 1.0.1 → 1.2.2
- **email-validator** 2.2.0 → 2.3.0
- **apscheduler** 3.10.4 → 3.11.2
- **readability-lxml** 0.8.1 → 0.8.4.1
- **markdownify** 0.14.1 → 1.2.2
- **jsdom** 28.1.0 → 29.0.0
- **types-passlib** 1.7.7.20240819 → 1.7.7.20260211
- **types-python-jose** 3.3.4.20240106 → 3.5.0.20250531
- **pytest-mock** 3.14.0 → 3.15.1
- **testcontainers** 4.8.2 → 4.14.1
- **debugpy** 1.8.9 → 1.8.20
- **safety** 3.2.11 → 3.7.0
- **bandit** 1.8.0 → 1.9.4
- **15 frontend packages** (react 19.2.4, firebase 12.10, zod 4.3.6, vitest 4.1, @hey-api/openapi-ts 0.94.1, etc.)
- **13 GitHub Actions** (checkout v6, upload-artifact v7, codecov v5, docker actions v4/v7, etc.)

### Fixed

- **CI pipeline**: Use venv in backend CI jobs (fixes MyPy import resolution)
- **CI pipeline**: Fix Alembic head detection regex for typed annotations
- **CI pipeline**: Fix synchronous Store call check false positive (exclude `await` lines)
- **CI pipeline**: Rename codecov `file` → `files` for v5 compatibility
- **CI pipeline**: Regenerate pnpm-lock.yaml after jsdom 29 merge
- **CI pipeline**: Mark checkpointer tests as integration (were failing with wrong DB user)
- **CI pipeline**: Lower coverage threshold to 40%
- **Security**: Add OPENAI_API_KEY to .env.example

### Documentation

- Update STACK_TECHNIQUE.md with all version bumps
- Update GUIDE_DEVELOPPEMENT.md test examples (ASGITransport)
- Update README.md badges (LangGraph 1.1.2, LangChain 1.2.12)

## [1.4.1] - 2026-03-15

### Fixed

- **Heartbeat timezone conversion**: Proactive calendar notifications now display event times in the user's local timezone instead of raw ISO/UTC strings. Fixes notifications reporting events 1 hour early (LLM misinterpreting UTC as local time)
  - Multi-provider support: Google (offset in ISO), Microsoft (naive + timeZone field), Apple CalDAV (naive local times)
  - Naive datetimes (no offset, no timeZone) now default to user timezone instead of UTC, fixing a 1-hour-late display for CalDAV events
  - Task due dates cleaned to date-only format (prevents misleading midnight-UTC timezone shifts)
  - Recent heartbeat/interest notification timestamps converted to user timezone
  - Prompt header now includes "(times in user's local timezone)" for LLM clarity
  - DRY refactor: `_resolve_user_tz()` replaces 3 duplicated timezone fallback blocks
- **Interest notification 0 tokens / 0€**: Token tracking now correctly accumulates tokens from both LLM phases (content generation + presentation formatting). Previously only the presentation phase was counted, and generation phase tokens (LLM reflection) were lost
  - Added `tokens_in`/`tokens_out` fields to `ContentResult` dataclass
  - `LLMReflectionContentSource` now returns tokens in `ContentResult` (in addition to persisting via TrackingContext)
  - `_extract_llm_tokens()` helper with `response_metadata` fallback for non-standard providers
- **Interest presentation LLM provider mismatch**: `LLMAgentConfig` was created without `provider` parameter, defaulting to `"openai"` while model was `claude-sonnet-4-6` (Anthropic) — causing silent 404 errors and raw unformatted content as fallback

### Added

- **CI/CD hardening for public repo**: Comprehensive pipeline overhaul for open-source best practices
  - **Branch protection on `main`**: PR required with 1 review (external contributors), 7 required status checks, force push forbidden, stale review dismissal, conversation resolution required. Admins can bypass for direct pushes
  - **SHA-pinned GitHub Actions**: All actions across 3 workflows (`ci.yml`, `security.yml`, `release.yml`) pinned by commit SHA with version comments — prevents supply-chain attacks via tag mutation
  - **`permissions: contents: read`** on CI workflow (least privilege principle)
  - **Code Hygiene CI job**: New job with 6 checks — `.bak` files, sync Store calls, Redis setex without `json.dumps`, i18n keys sync (EN vs 5 languages), Alembic migration conflicts (revision chain parsing), `.env.example` completeness
  - **Docker build smoke test CI job**: Builds API and Web production images without pushing (catches broken Dockerfiles), with GHA cache
  - **Pre-commit hook aligned with CI**: Added i18n keys sync, Alembic migration conflict detection (date prefix), `.env.example` completeness checks to local pre-commit hook
  - **Repo settings**: `delete_branch_on_merge`, `allow_update_branch`, `allow_auto_merge` enabled; homepage URL set
  - **Dependabot groups**: Minor/patch updates grouped per ecosystem (pip, npm) to reduce PR noise; GitHub Actions updates grouped
  - **`.editorconfig`**: New file enforcing consistent formatting across IDEs (indent 4 for Python, indent 2 for TS/JS/JSON, LF line endings, CRLF for Windows scripts)
  - **GitHub labels**: Added `security`, `ci`, `docker`, `python`, `frontend`, `agents`, `priority:high`, `priority:low`
  - **CI tests aligned with pre-commit**: Fast unit tests only (excluding slow/integration/e2e/benchmark markers + 10 ignored files), coverage threshold 43%
  - **CI/CD documentation**: New `docs/technical/CI_CD.md` with full pipeline architecture, check matrix, troubleshooting
- **`extract_llm_tokens()` centralized helper**: New `src/infrastructure/llm/token_utils.py` — single reusable function for extracting token usage from LangChain AIMessage across all providers (DRY refactor from 2 duplicated implementations)

### Changed

- Updated heartbeat context source tables in docs to reflect multi-provider support (Google/Apple/Microsoft Calendar, Google Tasks/Microsoft To Do)
- Ruff and Black now lint `tests/` in addition to `src/` (aligned with pre-commit hook)
- Interest LLM reflection prompt: heading level fix (`##` → `###`), free-form format with paragraphs instead of strict sentence limits

### Fixed

- **i18n desync**: 3 keys missing in fr/de/es/it/zh (`chat.voice_mode.processing`, `speaking`, `error_permission`), 87 keys missing in en/fr (`settings.interests.*` section). All 6 languages now have 2,587 keys in perfect sync
- **Mixed language in docs**: French documentation files (`GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md`, `INTERESTS.md`) contained English sentences — translated to French

## [1.4.0] - 2026-03-14

### Added

- **RAG Knowledge Spaces**: Users can create personal knowledge spaces containing their own documents (PDF, TXT, MD, DOCX) to enrich AI assistant responses
  - **Space management**: Create, edit, delete, and toggle activation of knowledge spaces per user
  - **Document processing pipeline**: Background processing with text extraction, chunking (RecursiveCharacterTextSplitter), and embedding (OpenAI `text-embedding-3-small` via TrackedOpenAIEmbeddings)
  - **Hybrid search retrieval**: Semantic similarity (pgvector cosine) + BM25 keyword matching with configurable alpha fusion
  - **Response Node injection**: RAG context automatically injected into assistant responses when active spaces exist
  - **Full cost transparency**: Embedding costs tracked per document (indexing) and per query (retrieval) in TokenUsageLog, MessageTokenSummary, and UserStatistics
  - **Admin reindexation**: Endpoint to reindex all documents after embedding model change, with Redis flag to disable RAG during migration and automatic vector dimension ALTER
  - **14 Prometheus metrics**: Document processing RED, retrieval performance, space lifecycle Gauges, reindex tracking
  - **Grafana dashboard**: Dedicated RAG Spaces dashboard (18th) with 21 panels
  - **Full frontend**: Space list, detail, document upload (drag & drop + progress), processing status polling, activation toggle, active spaces indicator in chat, settings section
  - **i18n**: Full translation support in 6 languages (en, fr, de, es, it, zh)
  - **Feature flag**: `RAG_SPACES_ENABLED=true` to enable (default: true)

## [1.3.0] - 2026-03-14

### Changed

- **FastAPI 0.128.0 → 0.135.1**: Major framework upgrade pulling Starlette 0.50.0
- **Removed Starlette UTF-8 patch**: Starlette 0.50 natively defaults to `encoding="utf-8"` in Config, making the `patch_starlette_utf8()` monkey-patch obsolete
- **SSE ClientDisconnect handling**: Added graceful catch for `starlette.requests.ClientDisconnect` (raised since Starlette 0.42) — client disconnections during streaming are now logged as info instead of errors

### Fixed

- **SSE CancelledError log level**: Client disconnections during streaming are now logged as `info` instead of `error` in orchestration and streaming services — prevents false error alerts and inflated error metrics
- **DB connection leak on client disconnect**: `session.close()` in `get_db_session()`/`get_db_context()` and `tracker.commit()` in the graph streaming finally block are now shielded with `asyncio.shield()`, preventing SQLAlchemy connection pool exhaustion when clients disconnect mid-stream
- **Stale tests**: Fixed 8 pre-existing test failures in semantic validation and routing modules (obsolete feature flag test, incorrect planner_iteration assertions, incomplete mock settings)

## [1.2.0] - 2026-03-14

### Changed

- **Node.js 20 → 22 LTS**: Upgraded Docker images, CI workflows, and engine requirements to Node.js 22 LTS (supported until April 2027)
- Closed Dependabot PR #4 (Node 25 — not LTS) and PR #6 (Python 3.14 — still in beta)

## [1.1.0] - 2026-03-14

### Added

- **LAN Access & SSL Configuration**: Configurable `SSL_DOMAIN` env var for self-signed certificates covering nip.io domains, enabling LAN access from mobile/other devices
- **SSL cert sharing**: Web container now uses ssl-init certificates via `--experimental-https-key`/`--experimental-https-cert`, ensuring consistent certs across API and Web
- **Documentation**: Added section 4.4 "LAN Access & SSL Configuration" in Getting Started guide

### Fixed

- **Token tracking upsert**: Replaced two-step UPDATE-then-INSERT with PostgreSQL native `INSERT ... ON CONFLICT DO UPDATE` for atomic, race-condition-free token summary persistence
- **Tracking resilience**: Token tracking failures no longer break the chat flow (graceful error handling in `TrackingContext.commit()`)
- **WebSocket HMR refresh loops**: Fixed `NEXT_PUBLIC_ALLOWED_DEV_ORIGINS` format — must be hostname only (e.g., `192.168.1.100.nip.io`), not full URL with protocol/port
- **SSL key permissions**: Changed key.pem to 644 so non-root containers (Next.js `node` user) can read it

### Changed

- `.env.example` is now a development template (was production), `.env.prod.example` remains the production template
- `generate-certs.sh` is fully configurable via `SSL_DOMAIN` and `SSL_IP` env vars (no hardcoded IP)
- Frontend dependencies updated: Next.js 16.1.6, i18next 25.8.18, lucide-react 0.577.0, tailwindcss 4.2.1

## [1.0.0] - 2026-03-13

First public open-source release of LIA.

### Features

- **Multi-Agent Orchestration**: LangGraph-based pipeline with Router, Planner, Orchestrator, and Response nodes
- **16+ Domain Agents**: Contacts, Email, Calendar, Drive, Tasks, Weather, Wikipedia, Perplexity, Brave Search, Web Search, Web Fetch, Places, Routes, Reminders, Context, Query, and dynamic MCP agents
- **Human-in-the-Loop (HITL)**: 6 interaction types — Plan Approval, Clarification, Draft Critique, Destructive Confirm, FOR_EACH Confirm, Modifier Review
- **Smart Planner**: LLM-based execution plan generation with dependency graphs and wave-by-wave parallel execution
- **Plan Pattern Learner**: Redis-based Bayesian learning; high-confidence patterns (>=90%) bypass semantic validation
- **Model Context Protocol (MCP)**: Admin MCP (persistent) + Per-User MCP (ephemeral) with OAuth flow support
- **MCP Apps**: Interactive HTML widgets in sandboxed iframes via PostMessage JSON-RPC bridge
- **Excalidraw Integration**: LLM-driven diagram builder with intent-based element generation
- **Skills System**: agentskills.io standard SKILL.md files with per-user toggle and deterministic bypass strategies
- **Multi-Channel Messaging**: Generic abstraction with Telegram as first implementation (webhook, OTP binding, voice)
- **Autonomous Heartbeat**: LLM-driven proactive notifications with two-phase approach (decision + personality-aware rewrite)
- **Voice Mode**: TTS (Edge/OpenAI/Gemini) + STT (Sherpa-onnx Whisper, CPU-only)
- **Multi-Provider LLM**: 6 providers (OpenAI, Anthropic, Gemini, DeepSeek, Perplexity, Ollama) with dynamic config via Admin UI
- **Multi-Provider Connectors**: Google, Apple iCloud, and Microsoft 365 with mutual exclusivity per functional category
- **Scheduled Actions**: User-scheduled deferred task execution
- **Session-based Auth (BFF)**: HTTP-only cookies in Redis, no JWT exposed to frontend
- **Enterprise Observability**: OpenTelemetry traces, Prometheus metrics, Grafana dashboards, Langfuse LLM analytics
- **Internationalization**: 6 languages (fr, en, es, de, it, zh)
- **Multi-arch Docker**: `linux/amd64` + `linux/arm64` builds for Raspberry Pi deployment
- **Comprehensive Test Suite**: 2,300+ tests (unit, integration, e2e, benchmark)

### Infrastructure

- FastAPI 0.128 backend (Python 3.12+) with async SQLAlchemy 2.0 + asyncpg
- Next.js 16 frontend (React 19, TypeScript) with TailwindCSS 4
- PostgreSQL 16 (+ pgvector) for data and vector search
- Redis 7 for sessions, cache, distributed locks, and pattern learning
- APScheduler for 9 background jobs
- Circuit breaker, rate limiting, and distributed locks
- SOPS/Age encryption for secrets management

[Unreleased]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.13.3...HEAD
[1.13.3]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.13.2...v1.13.3
[1.13.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.13.1...v1.13.2
[1.13.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.13.0...v1.13.1
[1.13.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.12.4...v1.13.0
[1.12.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.12.1...v1.12.2
[1.12.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.12.0...v1.12.1
[1.12.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.11.5...v1.12.0
[1.11.5]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.11.4...v1.11.5
[1.8.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.8.1...v1.8.2
[1.8.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.7.2...v1.8.0
[1.7.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.7.1...v1.7.2
[1.7.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.6.1...v1.7.0
[1.6.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.5.2...v1.6.0
[1.5.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.5.1...v1.5.2
[1.5.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.7...v1.5.0
[1.4.7]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.6...v1.4.7
[1.4.6]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.5...v1.4.6
[1.4.5]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.4...v1.4.5
[1.4.4]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.3...v1.4.4
[1.4.3]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.1...v1.4.3
[1.4.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jgouviergmail/LIA-Assistant/releases/tag/v1.0.0
