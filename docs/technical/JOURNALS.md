# Personal Journals (Carnets de Bord) — Technical Documentation

## Overview

Personal Journals give the AI assistant a living, evolving personality through introspective notebooks. The assistant writes its own reflections, observations, analyses and learnings, colored by its active personality. These notes influence future responses via semantic context injection.

**Key distinction from memories**: Memories store factual data about the user (psychological profile). Journals store the assistant's own perspective and reflections.

## Architecture

### Domain Structure

```
apps/api/src/domains/journals/
├── __init__.py              # Package docstring
├── constants.py             # Domain constants (entry limits, emoji maps)
├── models.py                # SQLAlchemy models (JournalEntry + 4 enums)
├── schemas.py               # Pydantic schemas (API + internal LLM)
├── repository.py            # Data access layer (CRUD + semantic search with min_score)
├── service.py               # Business logic (CRUD + embedding + size tracking)
├── router.py                # FastAPI endpoints (CRUD + settings + export)
├── extraction_service.py    # Background post-conversation extraction
├── consolidation_service.py # Periodic journal maintenance
└── context_builder.py       # Prompt injection via semantic relevance (with debug data)
```

### Database Schema

**Table: `journal_entries`**

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID (FK→users) | Owner, CASCADE delete |
| theme | String(30) | self_reflection / user_observations / ideas_analyses / learnings |
| title | String(200) | Short descriptive title |
| content | Text | Full entry content |
| mood | String(20) | reflective / curious / satisfied / concerned / inspired |
| status | String(20) | active / archived |
| source | String(20) | conversation / consolidation / manual |
| session_id | String(100) | Conversation session that triggered extraction |
| personality_code | String(50) | Personality active when entry was written |
| char_count | Integer | Content character count (size tracking) |
| embedding | Float[] | E5-small 384-dim vector (semantic search) |
| created_at | DateTime | Auto-set |
| updated_at | DateTime | Auto-updated |

**User model additions** (13 columns):
- `journals_enabled` (bool) — User feature toggle
- `journal_consolidation_enabled` (bool) — Periodic consolidation toggle
- `journal_consolidation_with_history` (bool) — Include conversation history
- `journal_max_total_chars` (int) — Max size limit (user-configurable)
- `journal_context_max_chars` (int) — Injection budget (user-configurable)
- `journal_max_entry_chars` (int) — Max chars per entry (user-configurable)
- `journal_context_max_results` (int) — Max search results (user-configurable)
- `journal_last_consolidated_at` (DateTime) — Last consolidation timestamp
- `journal_last_cost_*` (5 fields) — Last intervention cost tracking

**Migrations**:
- `journals_001` — Creates `journal_entries` table + 11 initial user columns
- `journals_002` — Adds `journal_max_entry_chars` + `journal_context_max_results` (idempotent)

### Data Flow

```
Conversation
    │
    ├── response_node.py ──┬── [INJECTION] build_journal_context(query=last_message)
    │                      │   → semantic search (min_score prefilter)
    │                      │   → {journal_context} in response prompt
    │                      │   → debug data → debug panel
    │                      │
    │                      └── [EXTRACTION] extract_journal_entry_background()
    │                          → fire-and-forget → LLM introspection → create/update/delete entries
    │
    ├── planner_node_v3.py ── [INJECTION] build_journal_context(query=goal+intent)
    │                          → semantic search (min_score prefilter)
    │                          → {journal_context} in planner prompt
    │
    ├── APScheduler (every 4h) ── process_journal_consolidation()
    │                              → batch eligible users → LLM consolidation → maintain entries
    │
    └── Heartbeat (proactive) ── _fetch_journals(query=dynamic_context)
                                  → second pass after context aggregation
                                  → journal entries enrich notification context
```

### Semantic Search & Prefiltering

- **Embeddings**: E5-small (384 dims, local, free, ~107ms/embed on RPi5)
- **Search**: Cosine similarity computed in Python (not SQL/pgvector)
- **Min score prefilter**: `JOURNAL_CONTEXT_MIN_SCORE` (default 0.3) — entries below this threshold are discarded BEFORE being sent to the LLM. This eliminates noise and reduces prompt token usage.
- **LLM autonomy**: The LLM receives remaining entries WITH their similarity scores and decides which to use based on contextual relevance
- **Volume**: ~80 entries max per user → brute-force cosine similarity is fast enough

### Configuration

**System (.env)**:
- `JOURNALS_ENABLED` — Global feature flag
- `JOURNAL_EXTRACTION_ENABLED` — Post-conversation extraction
- `JOURNAL_EXTRACTION_MIN_MESSAGES` — Min messages threshold (default: 4)
- `JOURNAL_CONSOLIDATION_INTERVAL_HOURS` — Scheduler interval (default: 4)
- `JOURNAL_CONSOLIDATION_COOLDOWN_HOURS` — Per-user cooldown (default: 12)
- `JOURNAL_CONSOLIDATION_MIN_ENTRIES` — Min entries for eligibility (default: 3)
- `JOURNAL_CONSOLIDATION_HISTORY_MAX_MESSAGES` — Max conversation messages for history analysis (default: 50)
- `JOURNAL_CONSOLIDATION_HISTORY_MAX_DAYS` — Max lookback days (default: 7)
- `JOURNAL_DEFAULT_MAX_TOTAL_CHARS` — Default max size (default: 40000)
- `JOURNAL_DEFAULT_CONTEXT_MAX_CHARS` — Default injection budget (default: 1500)
- `JOURNAL_MAX_ENTRY_CHARS` — Default max per entry (default: 2000)
- `JOURNAL_CONTEXT_MAX_RESULTS` — Default max search results (default: 10)
- `JOURNAL_CONTEXT_MIN_SCORE` — Min cosine similarity for prefiltering (default: 0.3)

**User (Settings > Features)**:
- Enable/disable journals (data preserved when disabled)
- Enable/disable periodic consolidation
- Enable/disable conversation history analysis (with cost warning)
- Max total chars (cannot be set below current usage)
- Context injection budget (chars injected into prompts)
- Max entry chars (cannot be set below largest existing entry)
- Max search results (entries returned by semantic search)
- All administered via `PATCH /journals/settings`

### LLM Configuration

Two entries in `LLM_DEFAULTS` + `LLM_TYPES_REGISTRY`:
- `journal_extraction` — Post-conversation (frequent, lightweight)
- `journal_consolidation` — Periodic review (rare, complex)

Both configurable in Admin > LLM Configuration (category: `background`).

### Heartbeat Integration

Personal Journals are integrated as a context source for proactive heartbeat notifications:

- **Source name**: `journals` — appears as a toggleable badge in heartbeat settings
- **Activation**: Badge is green when `journals_enabled=true`, grayed out when disabled
- **Dynamic query**: Unlike other sources fetched in parallel, journals use a **second pass** — after all other context is aggregated (calendar, weather, emails, tasks, interests), a dynamic query is built from the aggregated summary and used for semantic search
- **Budget**: Limited to 3 entries to keep the heartbeat prompt small
- **Prefiltering**: Same `JOURNAL_CONTEXT_MIN_SCORE` threshold applies
- **Prompt injection**: Journal entries appear as "ASSISTANT JOURNAL ENTRIES (your own reflections)" in the heartbeat context, allowing the assistant to personalize notification tone and content

### Debug Panel

The debug panel includes a "Personal Journals" section showing injection metrics:

- **Summary**: Entries found vs. injected, characters injected vs. budget, max results setting
- **Per-entry details**: Rank, theme emoji, title (25 chars), similarity score with visual bar, mood, source (conversation/consolidation/manual), date, char count
- **Budget indicator**: Entries that were found but not injected due to budget constraints are marked with a "BUDGET" badge and displayed at reduced opacity
- **Score legend**: Color-coded (green ≥0.70, yellow 0.50-0.69, red <0.50)

Data flow: `context_builder(include_debug=True)` → `state_update["journal_injection_debug"]` → `streaming_service` → SSE `debug_metrics` chunk → frontend `JournalInjectionSection.tsx`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/journals` | List entries (filter by theme/status, pagination) |
| POST | `/journals` | Create entry manually |
| PATCH | `/journals/{id}` | Update entry |
| DELETE | `/journals/{id}` | Delete entry |
| DELETE | `/journals` | Delete all (GDPR) |
| GET | `/journals/themes` | Available themes |
| GET | `/journals/settings` | User settings + size/cost info |
| PATCH | `/journals/settings` | Update user settings |
| GET | `/journals/export` | Export JSON/CSV (GDPR) |

## Related ADRs

- [ADR-057: Personal Journals](../architecture/ADR-057-Personal-Journals.md)
