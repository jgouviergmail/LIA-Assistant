# Lot 4 — Briefing 2.0 (P15)

**Program**: [Interdomain Intelligence Program](2026-07-21-interdomain-intelligence-program.md) · **Status**: SPEC (2026-07-22) → implementation
**No ADR** (no architectural decision — composition of existing mechanisms; recorded here + tracker).

## Verified anchors

- Chat prefill EXISTS: `/dashboard/chat?draft=<text>` (QW-9 onboarding deep-link,
  consumed once, never auto-sent) — actionable cards need NO new mechanism.
- `CardsBundle` is a frozen 6-section model; the service gathers fetchers in
  parallel with per-section Redis TTL (`BriefingService._section`).
- Synthesis (`generate_synthesis`) currently sees personality only.
- Lot 2/3 outputs available: `OpenLoopRepository.list_open_for_user`,
  `ScheduledAction.last_executed_at/next_trigger_at`.

## Scope

### (a) New card « For you » (`for_you`)
Backend fetcher `fetch_for_you(user_id, user_tz)` (own sessions, briefing
pattern) aggregating, without any LLM cost:
- **Open loops** (Lot 2): top `BRIEFING_MAX_OPEN_LOOPS_ITEMS` OPEN loops,
  earliest due first — {subject, counterparty, direction, due_hint, days_open}.
  Gated by `OPEN_LOOPS_ENABLED` (section NOT_CONFIGURED when off → card hidden).
- **Automations digest** (Lot 3): executions in the last 24 h ({title,
  executed_at}) + next upcoming ({title, next_trigger_at}). Always available
  (empty state when none).
DECISION (spec-time): the "interest of the day" sub-block is DEFERRED — the
interest notification channel already serves it; rendering one here without
generated content is hollow, and generating costs LLM per refresh. Recorded.
Cache TTL: short (`SECTION_FOR_YOU_TTL_SECONDS = 300`) — loops/executions move.
Wire: `CardsBundle.for_you` + `build_cards` gather + section constants +
statuses map. Contract note: CardsBundle gains a field → frontend types updated.

### (b) Portrait-informed synthesis
`generate_synthesis` gains an optional `user_model_block` input filled via
`build_journal_user_model_block(user_id, format="brief", flow="briefing")`
when journals are enabled for the user (best-effort, "" on failure) —
injected as a system-prompt block so the tone/priorities match the compiled
portrait. No new prompt file needed if the synthesis prompt is builder-based —
verify at implementation; if it is a versioned .txt, add `{user_model_block}`
placeholder.

### (c) For-you card (frontend) — REQUALIFIED at implementation time
Counter-verification (2026-07-22): actionable deep-links ALREADY EXIST on
MailsCard/AgendaCard/BirthdaysCard (`chatDraftHref` + `onOpenChat`, shipped
by the parallel uncommitted workstream after the 2026-07-21 analysis). The
remaining scope is ONLY: TS types for `for_you` in `types/briefing.ts`
(CardsBundle grows a field — tsc breaks otherwise), new `ForYouCard.tsx`
(BriefingCard wrapper pattern; loops sub-block direction-aware with
`chatDraftHref` deep-link; automations digest lines), TodayBriefing grid
integration, i18n keys ×6, vitest coverage.

## Tests
Backend: fetcher (loops gated by flag; digest windows; empty states),
bundle/schema, synthesis receives portrait block (mocked), cache TTL constant.
Frontend (vitest): ForYouCard render states (ok/empty/hidden), deep-link href
composition + aria-labels on the three actionable cards, i18n keys ×6 parity.
Gates: backend fast suite + `task test:frontend` + `pnpm exec tsc --noEmit
--incremental false` + a11y/hooks/cc ratchets + i18n parity script.

## Out of scope
Interest-of-the-day content (deferred, see (a)); briefing UI redesign; any
new backend endpoint (the bundle endpoint already serves the new section).
