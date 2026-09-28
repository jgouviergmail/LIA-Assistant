# Radio LIA — sources and programmes (design)

Amends ADR-324 (decisions 38 onward once delivered). Owner decisions of 2026-09-27; written
before any code, executed lot by lot in TDD with a cold adversarial review after each lot.

## 1. What the owner asked

- **Sources are the raw material, programmes shape it.** The listener's own data (their
  interests included), the base sources in several languages (each one ticked or not) and
  the sources they add (ticked, renamed, deleted — up to 20). Kinds of news and feed
  languages are gone: everything airs translated into the listener's language, and every
  base source is ticked by default.
- **Programmes** are formats over that material, in the listener's language, each with a
  frequency the listener sets:
  - personal: the listener's **journal** in three editions (morning, noon, evening) — it
    absorbs « your day », the evening recap and « for you » — and a **relations** programme;
  - news, from the sources AND from the interests (an internet search): headline synthesis,
    briefs, quick headlines, the figure, analysis with experts, a deep-dive **dossier**, a
    **debate** with a conclusion, the **editorial**, a **discussion** between enthusiasts.
    The testimony was dropped: without a real person quoted by a source it would be invented.
- **A subject may come back** through another angle (another programme type, another voice),
  never twice in a row and never twice in the same programme type; only the briefs and the
  headline syntheses always renew their subjects.
- **Internet search for the interests**: the listener's own search connectors when they have
  a key, else a platform research slot.
- **Voices remembered per engine**: a listener's voices are kept for each provider/model.
- The news flash on a proactive notification (decision 32) stays as it is.

## 2. Lot 0 — voices remembered per engine

- **Storage.** `radio_preferences.preferences` gains `voices_by_engine`:
  `{engine_key: {role: voice_id}}`, where `engine_key` is `"{provider}/{model}"` of the
  `radio_voice` slot (`cast.engine_key(config)`). The wire model keeps `voices` (the CURRENT
  engine's): the page is unchanged.
- **Read** (`listener_settings.listener_preferences`, the session's setup): the current
  engine's entry; failing that, the legacy flat `voices` when every one is offered by the
  current engine (a row written before this lot); then the forgiving filter of decision 7
  (a voice the engine no longer offers reads as automatic).
- **Write** (`save_preferences`): strict against the current engine's voices as today, then
  merged under the current engine key in ONE transaction that locks the row
  (`SELECT … FOR UPDATE`), every other engine's entry kept, the legacy field dropped — a new
  dict, never an in-place JSONB mutation.
- **Tests**: the resolution (current, legacy adopted, legacy refused, unknown engine), the
  merge on real PostgreSQL (another engine's voices survive a save), the setup reading the
  current engine's voices.

## 3. Lot 1 — sources

### Backend

- **Preferences.** `news_categories` and `news_languages` leave the wire model (stored values
  are ignored by the field-by-field tolerant read). New `disabled_feeds: list[UUID]` — the
  catalogue feeds the listener unticked; empty by default, so every base source is heard.
  Strict on write (every id is a catalogue feed: `radio_feed_unknown`), tolerant on read.
- **The listener's own sites** get a `paused` column (`radio_feeds`, owner rows only;
  migration): a paused site is neither read by the newsroom nor offered to a session. A site
  can be renamed (`outlet`, same character rules as the station's name, bounded) and paused
  or resumed: `PATCH /radio/sources/{id}` `{title?, paused?}`; 404 when not the caller's.
  `RADIO_CUSTOM_SOURCES_MAX` goes to 20.
- **Setup and desk.** `RadioSetup` drops categories and languages and freezes
  `disabled_feeds`. `news_candidates` offers the catalogue feeds not disabled, in EVERY
  language, and the listener's own unpaused sites. The writer's and the verifier's prompts
  say that facts may be in any language and that the programme is spoken in the listener's
  (checked: the verifier compares meanings, numbers are canonical digits).
- **Collection capacity.** With 27 base feeds and up to 20 sites per recent listener, the
  per-pass bounds are raised from the measurement of a real pass on dev (duration per feed,
  pass timeout kept under the interval); the collector skips paused sites.
- **What each source holds for the listener** — `GET /radio/sources/overview`: every
  catalogue feed and own site with its name, language, whether it is ticked/paused, whether
  it is failing (back-off), how many stories it published within `NEWS_MAX_AGE_S` and how
  many of them the listener never heard (the aired ledger: story keys and fingerprints) —
  plus the totals « N stories available, M never heard ». One aggregate query over the
  window (ADR-185), the ledger read once.
- **« Forget what I heard »** — `DELETE /radio/heard`: removes the listener's four aired
  sets. A session already on air keeps its own memory until it ends (stated).
- **« Nothing new »** — when the news desk holds stories but every one was heard, the
  station says so once per session in a short host segment (`NOTHING_NEW`, material NONE,
  not selectable, planned by the grid on a new `news_exhausted` input), then plays its music
  and its personal programmes; news formats come back as soon as the desk has something new.

### Web

- One « Sources » block replaces the kinds/languages fields: **your data** (the personal
  sources' switches, the active interests shown with a link to manage them), **base
  sources** (a checkbox per feed with its language and counters), **your sources** (checkbox
  = not paused, inline rename, delete, counters, a failing badge; the add form). A totals
  line and the « Forget what I heard » button (confirmation dialog). Mobile-first, the
  settings' components (`FormSection`, `RowActions`, `Checkbox`), six locales.

## 4. Lot 2 — subject rules and angle programmes

- **Two families of news programmes** (declared on `FormatSpec`, `renews_subjects`):
  - *fresh* — headlines, bulletin (headline synthesis), brief, the figure: never a subject
    the listener heard (today's rules);
  - *angle* — analysis, editorial (the column, relabelled), **dossier**, **debate**,
    **discussion**: may take a subject already heard (the host says it comes back to it),
    never the subject of the programme just before, never one already treated by the same
    programme type (a per-type memory in the aired ledger, same horizon as the stories).
- **A subject** is an event: the same story, the same fingerprint across outlets, or the
  same meaning of the headline (decision 34).
- **New formats.** `DOSSIER` (anchor and expert: history, context, facts, analysis,
  outlook, an open question; the analyst reads the full text first), `DEBATE` (a moderator
  and two to three speakers with opposed views, a conclusion by the moderator),
  `DISCUSSION` (two to three enthusiasts talking a subject through). Personas are the
  station's commentators — never presented as real people.
- **Opinion lines.** The `opinion` line kind extends from the column to the debate and the
  discussion: attributed to its speaker, it asserts no new fact, and only the facts it
  cites are checked (the column test). Measured on a FIXED set of labelled scripts with
  planted claims before shipping (decision 34's method), within the paid-measurement budget.
- **Voices.** The four configurable roles stay; new speaker roles (`SPEAKER_A…C`) are cast
  automatically with other voices of the engine, distinct from the four when the engine
  has enough; a format needing more distinct voices than the cast holds is not planned.

## 5. Lot 3 — interests

- **Material.** The listener's active interests (strongest first, bounded per session).
- **Search.** (a) The listener's own search connector (Brave, Perplexity) when they have a
  key — their spend, never recorded as the platform's (owner rule), each call a consultation
  of the listener's data surface (ADR-263); (b) otherwise the `radio_researcher` slot, on a
  model DECLARED to search the web on every call (a capability of its family, measured; no
  such model configured means no interest material, never invented results), billed to the
  session's run and counted in the radio budget.
- **Stored as articles.** Results become stories of a per-listener interest source
  (`radio_feeds` owner row of kind `interest`, never read by the collector), so the shortlists,
  the ledger, the article page and the retention work unchanged; a search is reused while
  its results are fresh.
- **Two versions of each news programme.** A news format's pack draws from the sources or
  from the interests; when both have material the session alternates (remembered per
  format in the session state).

## 6. Lot 4 — the journal and relations

- **`JOURNAL`** replaces `MY_DAY`, `RECAP` and `FOR_YOU`; its edition follows the listener's
  clock: morning (planned and to do: appointments, reminders, tasks, commitments, tickets,
  birthdays, unread mail, and the corner's items « to note »), noon (done this morning, what
  is left this afternoon, unread mail), evening (done today, tomorrow and the rest of the
  week). Aired after the opening, and once more when a session crosses into another edition.
- **« Done »** comes from new readers, each bounded and recorded as a consultation: past
  appointments of the day, tasks completed today, reminders fired today, tickets closed
  today, LIA's own actions today (the effect register), mail sent today where the provider
  exposes it (a provider that does not is stated, never read as « nothing sent »).
- **`RELATIONS`**: the recent exchanges of every kind (the CRM overview's own aggregates)
  and what is expected on both sides (open commitments, replies owed).
- Stored frequencies of the removed formats are dropped entry by entry on read; a live
  session's setup naming them is read forgivingly.

## 7. Cross-cutting

- Every removed or renamed format, field and route is read forgivingly where it was stored
  (preferences, setups in Redis, segments), strict on write.
- Every new user-facing string in six locales; every refusal a stable `detail.code`.
- Metrics: format labels follow the registry; new readers are counted where they run.
- Docs: ADR-324 decisions 38+, `RADIO.md`, one line in `CLAUDE.md`, `AGENTS.md` regenerated.
- Proofs on dev on the proof account only; never a session on the owner's account.
