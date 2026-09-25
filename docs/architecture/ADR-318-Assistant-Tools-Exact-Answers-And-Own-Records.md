# ADR-318 — Exact answers, and LIA's own records, as tools

**Status**: accepted — 2026-09-25 (owner request 2026-09-24: « Outils proposés, attention, je parle bien de tools pour l'assistant : 1, 2, 3, 4, 5, 6 » — a calculator, date arithmetic, currency conversion, a journal lookup, the activity registers, the generated files)
**Amends**: [ADR-310](ADR-310-ReAct-Turn-Judged-On-Its-Result.md) (the date contract leaves the weather module), [ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) (every bound published from its source), [ADR-185](ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md) (exact totals beside capped lists), [ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md) (the registers read by a tool), [ADR-279](ADR-279-Generated-Assets-Gallery.md) (the gallery as a lookup), [ADR-226](ADR-226-Document-Generation-Agent.md) (card delivery), [ADR-290](ADR-290-Phone-As-A-Channel-Owner-Calls.md) / [ADR-301](ADR-301-Voice-Sessions-One-Policy-Per-Mode.md) (the phone's domains), [ADR-313](ADR-313-Long-Term-Memory-As-An-Active-Lookup.md) (the lookups share their parameters), [ADR-280](ADR-280-Complete-Capability-Control.md) (the journals switch hides its agent)

## Context

Two kinds of question had no tool. Everything below was measured before a line
changed.

**What a model must not do in its head.** Arithmetic (a percentage of an amount, a
split bill, a unit price), date arithmetic (days to a deadline, the weekday of a date,
ten working days from today, a time in another zone) and currency conversion came back
plausible and unverified. The ReAct loop had `run_python_tool` (ADR-249) — behind the
container sandbox, ReAct only; the pipeline had nothing. ADR-310 had already measured
dates as a weak point. The reference-rate API the billing reads
(`api.frankfurter.dev`, measured from the dev stack): a quote carries the day of its
rate (`"date": "2026-09-24"`), an unknown code answers 404, the same code twice 422,
and 30 currencies are published.

**What LIA itself holds.** Its journal is injected by relevance to the person's
MESSAGE — a subject the turn discovers on the way reaches no entry. Its registers
(ADR-263) record every action and consultation, and the model could not read them to
answer « what did you do for me this week ». Its gallery (ADR-279) keeps every file it
produced for a day, and the model could not find one again.

## Decision

1. **Three computation tools, one `calculation` domain** (`domains/agents/calculation`,
   read-only, no personal data, both execution modes):
   - `calculate_tool` evaluates an expression EXACTLY (`evaluator.py`): parsed by `ast`
     and walked node by node, never executed; decimal arithmetic in one context at the
     published precision, whose `Inexact` flag becomes `approximate` in the answer;
     an iterative walk (the published length admits a thousand-deep tree); `0 ** -1`
     and `ln(0)` refused — decimal returns infinities for them without raising
     (measured); huge powers overflow in 0.26 ms (measured on `9 ** 9 ** 9`); `^`,
     `×`, `÷` repaired, a decimal comma and a percent sign refused with the grammar;
     the trapped condition read structurally (`DivisionImpossible` sits in the
     trap's arguments, measured on 3.14.7).
   - `date_time_tool` answers six operations (`dates.py`): now, difference (days,
     weeks, calendar years/months/days, ELAPSED time on absolute instants — Python
     subtracts two datetimes sharing one `tzinfo` on their wall clocks, which read 24
     hours for the 25 of a clock change, measured), add (a missing day clamps to the
     month's end and says so; working days jumped a week at a time, so a huge count
     overflows instead of looping), weekday, business days (Monday to Friday, both
     ends included, public holidays NOT excluded and said), timezone conversion.
   - `convert_currency_tool` converts at the ECB reference rate and states its day:
     `CurrencyRateService.get_quote` returns the rate and the day; a pair the source
     does not publish raises `UnsupportedCurrencyError` (never retried, never cached as
     an outage; the refusal lists the published codes), while `get_rate` keeps its
     billing contract (`None`, the caller falls back to the database).
2. **The date contract lives in `core/date_contract.py`**: the ADR-310 wording and
   refusal, `read_moment` (ISO 8601 only, a date stays a date) and `period_bounds` (a
   day is a WHOLE day in the person's timezone). The weather module imports it.
3. **`search_journal_tool` — the journal as a lookup** (`journal` domain, registered
   where `JOURNALS_ENABLED`): one door (`journals/search.py`) embedding the subject
   with the JOURNAL's own model before any session opens, L0 feedstock excluded, the
   entries returned counted as injections. The relevance floor is the CONFIGURED one
   (`JOURNAL_CONTEXT_MIN_SCORE`), never the one the adaptive controller learns for the
   injection: measured on 17 real entries, the learned 0.70 kept one of the six entries
   scoring 0.68-0.705 for « style des réponses ». Gated at call time by the capability
   (the switch also hides `journal_agent` from the planner) and by the person's
   preference READ FROM THEIR ROW — a voice runtime carries no preference, and its
   default would have read « off » for everyone.
4. **`get_my_activity_tool` — the registers as a lookup** (`activity` domain): one
   session, four statements (`effects/activity.py`) — the newest actions under a
   published cap, their EXACT total, the exact count per outcome and the exact count
   of consultations per domain, under the tabs' own authorship filter. Actions are
   worded in the person's language from the label the register recorded.
5. **`find_generated_files_tool` — the gallery as a lookup** (`generated_file` domain):
   every family merged newest first under one cap with the exact total, only files
   whose deadline has not passed (`GalleryFilters.expires_after`), and every file found
   SHOWN as the chat's own card through the producers' stores, keyed by the
   conversation. Card delivery no longer depends on who queued the card: the image and
   document gates on the generation flags are gone (`image_generation/delivery.py`
   mirrors the documents'), because a card queued behind a closed gate is never shown
   and never freed.
6. **Shared seams**: `tools/lookup_parameters.py` (the ceiling clamp and the period
   refusal the lookups read the same way — the memory tool included);
   `attachments/urls.py` (the attachment path four producers and the response's URL
   allowlist wrote by hand);
   `_FLAG_GATED_TOOL_MODULES` (the tool registry's flag-gated families as one table).
7. **The phone reads what answers in words** (`PHONE_DOMAINS` += `calculation`,
   `journal`, `activity`); `generated_file` stays out, with its reason: it shows cards
   no voice surface draws.
8. **Found on the way, fixed**: the semantic stores declared no `text_search_mode`, so
   the validator's `autocorrect` mode would strip the conceptual terms a vector store
   matches on (memory `semantic`, documents `hybrid`, pinned by a test);
   `FLAG_GATED_DOMAINS` omitted `ticket` although the taxonomy declared
   `workboard_enabled` — its test read the table against the taxonomy and never the
   reverse, and now reads both; `search_memories` had no progress wording
   (`execution.steps`).

## Consequences

- Every bound a tool enforces is a setting. The parameter bounds —
  `CALCULATOR_EXPRESSION_MAX_CHARS`, `JOURNAL_SEARCH_MAX_RESULTS`,
  `EFFECT_ACTIVITY_MAX_ACTIONS`, `GENERATED_FILES_SEARCH_MAX_RESULTS` and the default
  window `EFFECT_ACTIVITY_WINDOW_DAYS` — are stated in the parameter wording the
  planner's manifest and the ReAct loop's schema share (ADR-310: the loop binds the
  schema, never the manifest), which a test pins; a ceiling past its bound is
  repaired, an expression past its length refused with the length.
  `CALCULATOR_PRECISION_DIGITS` is stated in the manifest and in every rounded result.
- Proven on the dev stack through the registry, for a real account: the calculator,
  a real ECB rate of 2026-09-24, 157 actions and 3,241 consultations counted exactly
  across 28 domains, three images found and queued as cards, the journal lookup
  matching French subjects above the configured floor.
- **Not covered, stated**: public holidays (no calendar of them is held); a bank's or a
  card's rate (the reference rate is said to be one); trigonometry is as exact as a
  float (flagged); the journal lookup costs one embedding call per search, recorded in
  the turn's tracker; the activity tool reads the two registers, not the proactive
  timeline of `domains/activity`; a file past its deadline is gone. Four other
  flag-gated domains (`image_generation`, `document_generation`, `health`, `devops`)
  declare no `feature_flag` and stay in the router's menu when their flag is off (read
  in `build_available_domains`) — a proposal, not part of this change. A direct voice
  session declares five more tools, paid on every turn of the session (ADR-300's
  measured premise: a direct session buys latency, not economy).
