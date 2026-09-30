# ADR-324 — A personal radio: a grid decides, models only write, the antenna runs only while someone listens

**Status**: accepted — 2026-09-26 (owner request: adapt tokenFM into a personal, on-demand radio in each person's language; owner arbitrations Q1–Q9, 2026-09-26: no sharing between accounts, short royalty-free beds with vocal transitions, no mobile shells yet, titles + summaries + full texts + an expert analysis, a verification pass off / news / all with its cost stated, a header player + a dashboard card + a page, paid probes on the dev slots, no scheduled editions — on demand, a 30-minute timer by default, the cost shown live —, the demonstrator off; no replay, no retention; the station may have its own personality)
**Amends**: ADR-119 (an alert joins the core), ADR-167 (external content), ADR-184 (published bounds), ADR-185 (exact counts), ADR-245 (one seam per provider family; the write path rejects), ADR-259 (the logo menu carries several actions), ADR-263 (a new consultation surface), ADR-266 (an evidence recipe), ADR-272 (every euro traced to the person), ADR-275 (a truncated answer is a refusal), ADR-280 (a new capability switch), ADR-304 (no transaction across a network call), ADR-305 (a family declares its offer), ADR-309 (one prompt layout), ADR-317 (no content in logs), ADR-318 (instants, never wall clocks), ADR-323 (declared language, English for the model)

## Context

tokenFM (read 2026-09-25: home, « nouveautés », « transparence », the grid) is a
generated radio: a fixed grid (a bulletin at the top of the hour, headlines at twenty and
forty past, flashes, columns), synthetic voices, and the sources of every item shown.
LIA's adaptation keeps the radio and changes its subject: the station talks to ONE
person, in their language, about their day (agenda, reminders, commitments, tickets,
mails, bookmarks, meetings, memories…) and about the world (a curated catalogue of public
outlets, plus the sites the person adds).

Owner arbitrations: no sharing between accounts (Q1); a few royalty-free music beds, short,
with a vocal introduction over the music and a vocal transition out of it (Q2); no
lock-screen shells yet (Q3); titles, summaries AND full articles, plus an expert analysis
by a dedicated model (Q4); an LLM verification pass off / news / all with a warning on its
cost (Q5); a header player, a dashboard card and a `/dashboard/radio` page (Q6); paid L0
probes allowed on the dev slots (Q7); NO scheduled editions — on demand, the start time
announced, then in the background, stopped by a 30-minute timer by default, the cost shown
live (Q8); the demonstrator keeps it off (Q9); no replay, no retention; the radio may have
its own personality, distinct from the chat's.

## Decision

1. **Two tiers.** A shared NEWSROOM collects public feeds for the instance (fetch, parse,
   full text — no model, no per-person cost); a personal ANTENNA produces segments for one
   listener, and every euro it spends is billed to that listener (ADR-272). The antenna
   only runs while someone listens: a session ends when the player stops reporting, sits
   paused too long, or the timer's farewell has aired.

2. **A deterministic grid decides; models only write.** `radio/grid.py` is a pure
   function of what has aired, the listener's clock, their frequencies and what there is
   to say: the opening, the listener's journal first, a bulletin at the top of the hour,
   headlines at :20/:40, the journal of a new edition, then a weighted draw that never repeats a
   format twice in a row, bounds briefs per half hour, never airs a personal format in
   public mode, never schedules a dialogue a one-voice cast cannot perform, never
   outlasts the timer. Measured by simulation (grid × running order, 40 seeds): two
   defects fixed before any wiring — (a) a session with a few minutes left and nothing
   fitting ENDED MID-GRID with no farewell: the grid now signs off whenever a timer
   exists and nothing fits; (b) a bulletin drawn in rotation at 8:55 took the nine
   o'clock news from a session listening at nine: a clock format is not drawn in
   rotation when its own mark comes sooner than its minimum gap (unless the session
   stops first).
   Amended 2026-09-28 (owner request: avoid consecutive programmes of the same
   style wherever possible): the FILL draw relaxed spacing and repetition together,
   letting a frequent brief win again while another eligible format waited inside
   its gap. It now removes the previous format whenever any other fill candidate
   exists, then applies the listener's frequency weights to the alternatives.
   A repeat remains possible only when no alternative fits the hard constraints;
   clock and edition priorities, material availability, the timer and failure rests
   keep their existing rules. No additional production or source read is needed.

3. **Material isolation.** A segment's `FactPack` holds ONE material — personal, news, or
   neutral (clock, weather) — enforced at construction; only the host speaks about the
   person (a personal or sensitive fact cited by another role drops the line). The
   listener's taste is never a fact (decision 13): three kinds nobody produced —
   `programme`, `interest`, `memory` — left the vocabulary rather than wait for a writer
   to voice a taste as a claim.

4. **The writer writes, the verifier decides what airs.** The schema carries no bound (a
   bound refuses the whole answer where the doctrine repairs, ADR-184/269); the
   deterministic verifier drops a line that cites nothing, cites an unknown fact, speaks
   a number no cited fact states (canonical digits: « 3,9 » = « 3.9 », « 0,5 » ≠ « 5 »;
   the digits of the cited fact's OUTLET NAME count — « according to France 24 » was
   measured as two false positives of three), quotes too long, or speaks in a role the
   format does not have; it REFUSES a script with no body, one past its length ceiling,
   or one that lost more than a quarter of its sourced lines (ADR-275: a shortened answer
   announced as whole is the defect). Measured on real feeds (2026-09-26, deepseek-flash
   and gpt-5.6-luna): bulletins FR/EN 12/12 and 13/13 lines kept, headlines 7/7, brief
   3/3, in 3–10 s.

5. **The expert analysis.** A dedicated slot reads the article's FULL text and returns
   points by angle (context, history, facts, vigilance, outlook); a point stating a
   figure the article does not state is dropped whole. Measured: 5–6 points, all kept,
   5–8 s; the writer then stages a 14–15-line anchor/expert dialogue, every line kept,
   on both model families.

6. **One prompt layout.** The static part (station, language, personality, contract,
   bounds — every bound read from the verifier's own constants) is identical for every
   segment of a listener, above the dynamic-context marker (ADR-309); the listener's
   first name is offered only to a format the host speaks (measured: an anchor told the
   name said « Je suis Alex »); every text a stranger wrote — headline, summary, article,
   outlet name, a mail subject in the person's day — travels inside the untrusted-content
   wrapper, and both prompts say it is data (ADR-167).

7. **Voice families.** A TTS engine is a family (billing free / characters / tokens,
   the controls it accepts); one seam renders a line's delivery (energy, pace, tone) for
   each and reports what it could not render. Gemini TTS is token-billed (measured 35
   audio tokens per second; 0.50 $ / 9 $ per million until 2026-12-31) and reports its
   usage; the factory refuses a token-billed engine to a caller that does not record
   tokens (the chat keeps Edge), and one door (`synthesize_billed`) returns the audio
   with its billing units. A cast gives each role a voice (read forgivingly: an id the
   current engine does not hold falls back to a default), alternating genders.
   Amended 2026-09-27 (the owner's settings stopped saving): the settings page reads
   the same way — a stored voice the engine no longer offers in the listener's language
   reads as automatic (`listener_settings.listener_preferences`; an engine that cannot
   list its voices right now keeps the stored choice, it cannot tell) — and re-reads when
   the `radio_voice` slot is saved or reset (the `radio_voices` revision). A voice of the
   previous engine, sent back by the page, had made every save refused as
   `radio_voice_unknown`: the write path still refuses one, and nothing sends it any more.
   And each engine keeps its own (owner request, the same evening): the stored settings hold
   the voices per `provider/model` (`voices_by_engine`, `cast.engine_key`), the page reads and
   writes the engine in place's, a save replaces that engine's alone under a row lock (a new
   mapping, every other engine's kept), and an engine switched back to finds its voices.

8. **Sound** (superseded by decision 28: the music is now the player's, continuous).
   Nine 18-second beds generated once with Lyria (provenance and hashes
   shipped; 0.56 $ in all), one mix per segment: music alone, dipped under the intro,
   gone for the body, back under the outro and out — loudness-normalised (−16 LUFS);
   measured 22 s mixed in 0.45 s, every line transcribed back by Whisper.

9. **The newsroom.** A catalogue of 27 feeds MEASURED live (AP and EFE refuse a declared
   crawler, Swissinfo has no feed, NHK and The New Humanitarian are stale, Al Jazeera
   forbids its articles); every request validated at every redirect, robots.txt honoured
   (RFC 9309: 4xx allows, 5xx/429 refuses for an hour, loads serialised per origin),
   bodies bounded, conditional GETs (13 of 27 feeds answered 304 on a second pass).
   Defects found and closed: `feedparser.parse(bytes)` reads the bytes as a LOCAL FILE
   PATH first (a hostile server answering `/srv/x.xml` made it read that file) — always a
   stream; readability's byte path raises on every page — the page is decoded here (HTTP
   charset, then `<meta>`, then UTF-8, WHATWG supersets); a 304 was taken for a redirect;
   a non-ASCII ETag would have failed every later fetch; the shared SSRF validator raised
   on a DNS label past 63 characters. A listener adds a SITE, not a feed URL: the
   address itself, else the feeds its page advertises, else the conventional paths of
   publishing systems, each through the same safe fetch and robots.txt (a site whose
   robots.txt cannot be read is UNREACHABLE, never « forbidden »), and the feed found is
   described — title, declared language, entries — before anything is stored. Measured
   on real sites: four of four found in 0.1–0.4 s (one only at `/feed/`), a site
   without feed said so in 2 s, a private address and a mistyped name refused before
   any request.

10. **Produced ahead, just in time.** Two slots always wait planned (the next to produce
    and the one its writer hands over to by name); once the listener hears the antenna,
    one production at a time, started when the ready audio ahead no longer covers its
    expected time × safety + margin; before the first sound, the first two slots are
    produced at once (never a third: a listener who stops at once would pay for it).
    Measured by simulation (12 seeds × 30 min, realistic stage timings): no gap after
    the start, first sound ≤ 20 s, the farewell last.

11. **The player** (the music moved to its own layer, decision 28). ONE audio element: the station's music starts inside the click (the
    autoplay rule is satisfied for every segment after it) and fills every gap; segments
    arrive as blobs (`media-src` allows `blob:`, not the API's origin) through the API
    client (cookie, native header, 401/403 identical); a report every few seconds is
    answered with the session's state (no SSE dependency); a session the API opened after
    the listener pressed stop is stopped at once.

12. **A shared defect found on the way (structured output).** The strict-mode analysis
    judged schemas « compatible » that do not have the strict SHAPE; the Responses path
    every current OpenAI model takes sends a schema unconverted, and OpenAI answered 400
    on EVERY call for `SynthesizedMinutes`, `TabularContent` and `DebriefDraft` (measured
    on gpt-5.6-luna). The analysis now requires `additionalProperties: false` and every
    property required, else `function_calling` — never by bending a schema, whose
    defaults keep an omitted field from failing on every other provider.

13. **The listener's taste is context, never a fact.** What they care about (active
    interests, strongest first) and what they said they like or dislike (the live
    memories of the `preference` category, newest first) reach the WRITER only, in a
    `LISTENER` block ABOVE the dynamic-context marker — the same for the whole session, so
    inside the prefix every segment shares (it had been below it, re-sent uncached with
    every segment). No line may state it (« since you love jazz »): it chooses which
    stories come first and angles a column. What may be read is decided at the start:
    public mode reads nothing, memories follow `users.memory_enabled` (the chat's own gate
    on memory injection — the MEMORY switch governs learning, not use), interests the
    operator's switch; each read on a short session, recorded as a consultation.
    Only a format that CHOOSES news is shown it: told the listener rides a bike, a host
    said « the weather decides the bike » in the listener's own day (one run in three on
    one family) and that family's verifier let it through — a writer cannot hint at what
    it was never told, so the listener's segments share two cached prefixes instead of
    one. Measured on three families (2026-09-26): after that, no script stated or hinted
    a taste.

14. **What the measurement of every format found, and how the verifier learned it.**
    Two formats could never air, invisible to every unit test: (a) the COLUMN — an
    opinion had no kind, the writer marked it `analysis`, which requires an analysis
    fact a column never has, so every opinion line was dropped (0 of 2 columns aired);
    (b) the OPENING, the first sound of every session — the writer put its few words
    over the music, and a segment with no body is refused (0 of 2 openings aired). A line
    kind `opinion` (the columnist's alone, citing the story it comments, every figure
    from it) and a station format's lines read as its body (a repair, only where there is
    no material: a news format with no body is still refused) fixed both: 3 of 3 columns
    and 4 of 4 openings aired on three families. Two repairs the same runs asked for: the
    date or time said without citing the clock cites it (« il est 10 h 21 » in a
    greeting was the opening's only drop on one family), and a delivery word off the
    vocabulary reads as the default (three of eight scripts of one family were refused
    for `delivery.energy` alone; none of seven after). The model verifier sees each line's
    KIND and applies two tests — strict for facts, « supported unless a specific claim
    the facts do not hold » for opinions: told the rule after the strict test, one family
    rejected three opinions in four on every pass; with two explicit tests, one line in
    eighteen, and every column aired. Every other format was measured the same way on
    the three families, and the prompt corrected where the measure said so: `number`'s
    guide asked « why it matters » against the rule « report, do not comment », so one
    family typed its explanation `analysis` and the segment was refused (0/1, then 5/5
    once the guide stopped contradicting the rule); a line citing nothing must be a
    `transition` (one family typed hand-overs `fact` and lost the segment); the
    verifier reads a greeting by the listener's first name and a kind suggestion that
    follows from a cited fact as station language, and anything said ABOUT the
    listener that no fact states as unsupported. Result: opening, my_day, headlines,
    column, number, for_you, recap and sign-off aired on the three families (bulletin,
    brief and analysis were measured earlier); with verification on every format the
    residual refusals were real speculations the checker caught.

15. **The listener's day is read, never fetched twice.** The DAY (appointments,
    reminders, tasks, commitments, tickets waiting on them, birthdays, unread mail, the
    weather) and the personal CORNER (health, meetings, notifications, people gone
    quiet, knowledge spaces, kept answers, the conversation under way) are two parts
    decided by the SOURCE: « for you » picks from the corner first. The sources the Today
    Briefing carries are read from its CACHE (never a fetch, so never a consultation);
    the seven others by the radio's own readers, concurrently, each on its own short
    session, what they opened recorded (a reader that raised as `failed`). A source the
    listener switched off is never READ, not merely unsaid; in company only the weather
    is read. Every source has exactly one reader — asserted at import. The feed languages
    a listener may choose are those the catalogue speaks (a `zh` stored for `zh-CN` would
    have been shown as chosen and never heard).

16. **One form of address for a whole session, and the whole chain proven at runtime.**
    Each segment is written by its own call, so nothing kept the register: in one real
    session the day said « vous » and « for you » said « tu ». The static prompt now fixes
    the familiar form of the listener's language for every programme — the application's
    own register — and the measurement found it held on the three families (the only
    formal words left were the noun « rendez-vous » and a quoted e-mail subject). The
    first runtime proof in the dev container ran the real service, launcher,
    orchestrator, grid, antenna, writer, verifier, Edge voices and ffmpeg mix on the
    container's Redis, a fake player listening in real time: six minutes gave the
    opening, the listener's day, the number, the headlines, « for you » and the
    sign-off, first sound at 8 s, 16 s of station music in all between programmes, and
    every segment heard — the session closes server-side when the farewell is produced
    and the player plays its queue out before it ends.

17. **A voice that fails in passing is tried again; a format's grammar is enforced, not
    only asked.** The free engine answers without audio once in twenty-four syntheses
    (measured 2026-09-26): at fourteen lines, about one segment in two was lost to a
    failure a second attempt outlives. A line is tried again while its failure is
    TRANSIENT — `TTSProviderError.transient`, read from the code and the status the
    client recorded, never from the message — through the one retry policy
    (`retry_async`, which gained a predicate for a failure family that states its
    retryability in a field), up to `RADIO_TTS_LINE_ATTEMPTS`; a failed attempt bills
    nothing and leaves its concurrency slot while it waits. The format's grammar held
    the same lesson: told « four to six stories — never more », one family wrote a
    bulletin of ten, another of seven, and a brief told two stories. `FormatSpec.stories_max`
    (headlines 5, bulletin 6, every one-story format 1) is published to the writer from
    the field the editor enforces: the first stories told are kept and the rest cut as a
    REPAIR that never counts against the segment — a story being the news facts one line
    tells together, so three outlets on one event count once. The neighbours are named
    by a plain-English `spoken_as`, never by their id (handed `brief`, a writer said
    « le brief » and « un bref »). The prompt followed the measure: a story on a subject
    the listener said they dislike is left out unless it is among the most important (a
    bulletin had aired football to a listener who said they dislike it); the station
    speaks to ONE person (« hello everyone », a plural « your news » on one family); a
    writer short of facts is short, never padding with the time or a repetition (a brief
    of one thin story restated it and read the clock); a number is written exactly as its
    fact writes it (a « seven » in words became « 7 », the only line of its story
    dropped, the headlines refused); and to the verifier a line citing nothing may only be
    station language. After the changes, brief, bulletin, analysis, headlines, number and
    column aired on the three families, the bulletins cut to their bound. Three targets
    were then aligned on their format's grammar — bulletin 130 s (six stories at most),
    brief 30 s, « for you » 35 s: given 75 s for ONE thing said simply, one family filled
    it with musings — and the half-hour simulation, which had used the old targets as
    real durations, turned that into gaps: a short segment followed by a long production
    (a brief, then an analysis) starved the one production allowed in flight while the
    listener hears the antenna. The look-ahead now covers the production that FOLLOWS
    when the next segment is too short to (`session._lead_s`, over the two slots always
    planned): without it, 10 of 12 seeds and the targeted test fail; with it, none.

18. **What the listener heard, never what the writer was offered; the news already on air
    is shown; a figure is read in the listener's convention.** Two real sessions in the dev
    container found two defects no unit test could. The antenna filed EVERY fact of a pack
    as heard, so a brief that tells one of the stories it is offered burned the others
    unheard: the production now returns the facts its voiced lines cite (`ProductionResult.
    aired`), and only those are remembered — an analysis that aired counts as its story,
    cited or not (`antenna.heard_facts`; a first version of the test passed with the rule
    removed, found by mutation). And three segments in a row told one event from three
    articles — the fingerprint is a normalised title by design, since a word match across
    languages is noise — so the news writer is shown the titles of the NEWS programmes
    already aired (fenced: written from strangers' text; never a personal title, which would
    carry the listener's life into a prompt whose voices may not speak of it), with one rule:
    a story already told is told again only among the most important, and then only what is
    new; the brief and the figure of the day are offered five stories, not three, so the
    choice exists. The session's second run aired no story twice. Measured in German,
    English and Chinese on the three families: the familiar address held (« du », « 你 »),
    the neighbours were named as a radio names them (« Kurzmeldung », « 简讯 ») once
    `spoken_as` avoided a cognate (« the column » had become « ma colonne »). One family
    writes large Chinese figures with the ten-thousand unit (« 60万 » for the fact's
    « 600 000 »), which the verifier read as « 60 » — every such line dropped, a bulletin
    refused, while « 60万 » against a « 60 » passed: `radio/numbers.py` reads a number
    followed by a multiplier (万, 亿, 千, and the « million »/« billion » words of the
    catalogue's languages) at its VALUE as well as its digits, so nothing that compared
    before compares differently, and the writer may use its language's own units. What it
    does not parse, on purpose: numbers in Chinese characters — « 一 » is a letter of
    everyday words, and parsing it would drop sound lines. « For you » tells ONE of the
    listener's things (the bound now counts a format's subjects, never what frames them:
    the clock, the weather, an analysis point); two things in one sentence still count as
    one — a line cannot be split, and dropping it would drop the segment.

19. **A process given up leaves no pipe open.** The full fast suite found a teardown error
    no radio test had shown: the bounded ffmpeg runner killed and awaited a process it
    gave up on (a cancellation, a timeout), but a bare ``wait`` returns as the process
    exits, before its pipes reach their end — on the Windows proactor a pipe was still
    open when the call returned in 3 runs of 10 after a cancellation, 6 of 10 after a
    timeout, and every time when the child was still writing; under load, the loop was
    gone before the callback that would have closed it, and the transport was reported
    unclosed. The runner now drains both pipes to their end with ``communicate`` (which
    closes their transports) under a bound; a child writing until it is killed makes the
    regression test fail every time without it.

20. **The newsroom reads for listeners, and one unit never stops a pass.** The cold review
    of the wiring's first lot found four defects in code every unit test passed. (a) A pass
    ran its feeds and articles under one `TaskGroup`: a single row the database refused
    cancelled the whole pass — every pass, since the feed stayed due — so ONE site a
    listener added, serving a 600-character `ETag`, would have frozen the instance's
    newsroom. Each feed and each article is now its own unit: a failure is logged by its
    id and counted, the reading filed `unfiled` so the feed backs off, and a feed's
    stories are filed BEFORE its reading, so new validators are never kept for stories
    that were not. (b) The validators were bounded to printable ASCII, not to their
    columns: now to both — one that does not fit is not kept, and the next request is
    simply unconditional. (c) A NUL in one item's title, link or summary passes feedparser
    intact (measured) and PostgreSQL refuses it in a text: the whole feed's batch was a
    row the database refuses. Control characters (C0, DEL, C1) read as a space in plain
    text, a link holding one is no link, and a site's title and declared language are
    cleaned the same way before a listener is shown them. (d) The collector read for
    NOBODY: the catalogue every few minutes on an instance nobody listens to, and the
    sites of a listener who left, for ever. The antenna's rule now holds for the
    newsroom: it reads the catalogue while anyone started a session within
    `RADIO_NEWSROOM_LISTENER_WINDOW_SECONDS` (a week: a weekly listener stays warm), and a
    listener's own sites while THEY did — `radio_preferences.last_listened_at`, filed at a
    session start by one statement that touches no setting. After a silence the first
    news arrives with the next pass; the grid already airs no news format without
    candidates. The catalogue, synchronised every pass, is rewritten only where what
    ships differs. A listener who never chose hears their DECLARED language and nothing
    else fixed (ADR-323; an instance-wide default language was a default the language
    guard refuses), and every language a person can declare has catalogue feeds of its
    own (asserted).

21. **Every euro of a session on the run's row.** Paid speech had no column on
    `message_token_summary`: the chat kept each answer's share on its bubble alone, and
    a radio session — whose main cost is its voices — has no bubble, so its live cost
    could not be read from the ledger every other surface reads. `tts_characters` and
    `tts_cost_eur` join the row through the same UPSERT (column arithmetic: a session
    commits once per production), `billed_cost_eur` includes them, and every reader that
    added the bubble's share on top stopped (the history, the aggregated summary — whose
    fallback JSONB lookup on the message table went with it). The consumption summary
    reads the runs (`total_tts_runs`), and the paid-TTS export lists each chat answer's
    bubble and, disjointly, each run whose speech no bubble carries. Migration
    `d79c9fc26844` copied the bubbles' shares onto their runs, summed per run id (a
    resumed turn keeps its id) and inventing no row — proven on PostgreSQL, with three
    mutations killed.

22. **The station's own slots, and prompts proven as files.** Four slots in a category of
    their own — `radio_writer`, `radio_analyst`, `radio_verifier` (each one schema-bound
    answer, output caps sized for a model that bills its thinking inside them) and
    `radio_voice` (the engine a session is cast from, the free one by default) — so an
    administrator tunes the station apart from the chat. The prompts joined the
    versioned store with the convention's literal marker line (a `{marker}`
    placeholder had kept them out of the cache-hygiene guard, which now holds the
    placeholders above the marker to the ones a session shares), and the radio's tests
    render the FILES rather than inline copies: the first run found a copy saying
    « ON AIR: » where the file says « ON AIR THIS SESSION: », and an assertion that
    could not tell the rule describing the listener block from the block itself. The
    admin screen drew its categories from a COPY of the backend's list, so a new
    category's slots would have vanished from it in silence: a category the page does
    not know is now drawn last, never lost, and every declared category's label is
    guarded in the six languages.

23. **Four doors, one cap, refusals the listener can read.** Eleven routes under `/radio`
    (start, report, stop, a segment's audio; the options, the settings and the sites),
    all behind the radio's capability switch — which is also read by the newsroom at
    every tick (route- AND service-enforced; the settings and the sites a listener added
    are records, kept while the switch is off). None holds a request session: the account
    is read on a session of its own and every store opens its own short one, because a
    start reads the listener's day and a site preview reaches a stranger's server
    (ADR-304). Both routes that reach a stranger carry the per-account rate limiter,
    authenticated through the route's own door. The instance's cap
    (`RADIO_MAX_ACTIVE_SESSIONS`) is taken BEFORE anything is read: a start JOINS the set
    of live sessions and then counts it, so two starts racing for the last place can
    never both land (a double that yields between the two calls proves it); the account's
    previous session does not count (it stops at its next tick), a session whose worker
    died holds no place past twice the idle timeout, and a start that fails after taking
    its place gives it back. Every refusal names itself with a stable `detail.code` —
    `radio_instance_full`, `radio_no_voice`, `radio_voice_unavailable` at a start;
    `radio_timer_too_long` (with `max_minutes`), `radio_voice_unknown`,
    `radio_personality_unknown` at a settings write (the write path rejects what the
    runtime would only coerce, ADR-245); `radio_source_refused` (with the outcome of the
    lookup) and `radio_source_limit` (with `max_sources`) for a site — and a guard holds
    every code to a sentence in the six languages and the player's list of start
    refusals to the API's. The start files the listening (`last_listened_at`, what the
    newsroom reads for) and records what it read of the listener under the `radio`
    consultation surface, inside a collector of the session's run.

24. **The background: a pass that obeys the switch, a sweep that never deletes on doubt,
    a shutdown that gives the leases back.** The newsroom pass (`radio_newsroom_collect`)
    and the media sweep (`radio_media_sweep`) are registered only where the deployment
    ships the radio, each with a jitter from its own period, in a registrar of their own
    (`startup/scheduler_radio.py`; the startup step is frozen at its size) — and the
    jitter guard now DISCOVERS every `scheduler_*.py` rather than trusting a hand-kept
    list, which the radio's would have escaped. The pass takes no `SchedulerLock`: a
    leader runs one at a time, a pass ends under its interval (refused at boot
    otherwise), and a newly elected leader first ticks about an interval after it starts;
    at worst a handover reads one feed twice, which every write absorbs. The sweep reads
    the live sessions from Redis and removes nothing when it cannot (without them no
    directory is known orphaned); an entry that vanishes while it lists is skipped. The
    audio lives in the container's WRITABLE LAYER (`/app/data` belongs to the runtime
    user; the four workers of one container share it; a recreate wipes it — the radio
    keeps nothing), never a named volume. A stopping worker cancels its session loops
    within `LOOP_STOP_TIMEOUT_S` (counted in the graceful-shutdown budget guard, and
    imported only where the radio is shipped); each gives its lease back, and the
    listener's next report restarts the loop on a worker that stays.

25. **Counted where every outcome is visible, one alert for the silent loop.** Twelve
    metrics (`metrics_radio.py`), all drawn on dashboard `31-radio`: starts by outcome
    (counted at the route, where both refusal paths meet), sessions ended by reason (a
    worker stopping ends nothing), loops broken by a defect, segments by format and
    outcome with the production time of every aired one — counted in `Antenna.produce`,
    the one place that sees them all (the orchestrator turns a defect into « nothing »,
    and a production returns « nothing » both for nothing to say and for a failure), the
    newsroom's ticks, readings, stories and texts, the orphans swept and the site lookups.
    One core alert, `RadioNewsroomStalled`: the AGE of the newsroom's last tick that ran
    to its end — a pass, or a tick with the radio switched off — above
    `ALERT_CORE_RADIO_NEWSROOM_STALL_SECONDS`. The stamp is never written at boot
    (uvicorn recycles its workers, and a boot stamp would hide a stall) nor by a failed
    pass, so its age covers both silences; three promtool cases, a runbook, and an
    evidence recipe (ADR-266). The loops' failures stay on the dashboard: the listener
    hears them, and a provider outage has its own signal. Measured before trusting the
    voice path (a paid probe on the dev slot): Gemini TTS refuses an empty input with a
    400 and no usage, and seven inputs built to draw silence — punctuation, emoji, a
    bare URL, « stay silent », a digit, zero-width characters — all came back spoken
    with a usage report. A 200 without audio was never produced; the client now counts
    that path, with no-JSON and encoding failures, and logs the tokens the vendor
    reported, so a future occurrence is seen.

26. **On screen where the instance offers it now; measured in the browser.** One
    predicate (`radioAvailable`: the operator's switch when published, else the
    deployment's ceiling) governs the header's control (from `lg`), the logo menu below
    `lg` — which now carries SEVERAL actions, the recorder's then the radio's —, the home
    page's card, the settings section and the page, which says the radio is not offered
    rather than offering a start the API would refuse. The bar under the header publishes
    its height (`--radio-banner-h`) and the chat's full-height shell subtracts it:
    measured, without it starting the station pushed the composer below the fold (the
    gap under the bar is the wrapper's padding — a margin collapses out of the box whose
    height is published). A settings write or a site refused is told in the listener's
    words with the bound the API published (`lib/radio/errors.ts` over
    `getApiErrorFields`; the hooks answer a result, never a bare `false`). Hermetic
    browser journeys cover the start, the stop, a refused start, the phone's menu and an
    instance without the radio; an axe journey scans the page before and on air, and
    found the bar's secondary text at 4.28:1 on its tinted ground (now the foreground
    colour). A header spec that offers EVERY feature control at once — the shell's own
    configuration offers neither meetings nor the radio — found a defect that predates
    the radio: in German at 1280 px, with meetings on, the nav's last label covered the
    first control, and at 1536 px the row, capped at the page's 1280 px, had LESS room
    than below it while `2xl` added the token counters. The nav's labels now wait for
    `2xl`, where the header row is widened to `96rem`; the spec measures 1536 px too.

27. **What the owner's first session on dev found, read from its logs.** The station played
    nothing but its music — « the next programme is being prepared » — for minutes. Three
    defects, each invisible to every unit test. (a) **A direction the model refuses
    silenced every line.** The Gemini family declared the style direction for all its
    models; measured on the Interactions API (2026-09-26, one line with and without a
    `speech_metadata` annotation), `gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`
    take one, while `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts` and
    `gemini-3.1-flash-tts-preview` answer 400 to ANY annotation — and the catalogue offered
    only the 2.5 previews. A control is now declared per model prefix
    (`TtsFamily.model_controls`, read through `controls_for`): a model nobody measured is
    sent none, because a refused control fails the whole synthesis where a withheld one only
    loses its nuance, which the segment reports as `unrendered`. (b) **The 2.5 previews
    answer raw samples** (`audio/L16;codec=pcm;rate=24000`, little-endian, no header) where
    the 3.8 models answer a WAV; read as a WAV, every transcode failed, and the retries of a
    failure read as transient multiplied the calls until the vendor answered 429. The
    client wraps declared raw samples in a WAV container at their declared rate
    (`media/pcm.wav_container`). (c) **An end the pure core decided was never written.**
    Nobody listening or productions failing were returned, not written into the state: the
    player was never told and kept waiting on the station's music, and each of its reports,
    every five seconds, restarted a loop that ended again at once — 164 restarts, and as
    many `radio_sessions_ended_total` increments, for four sessions. The loop now writes
    every end before publishing it (`session.ended_for`, the one transition the listener's
    stop, the ceiling and the runner's defect path share, the first reason standing); the
    runner's test double had published the end itself — the fictional shape that kept the
    defect green. And the refusal was visible nowhere: the client raised it without a line
    and read the Interactions API's `error.code` as « unknown »; it now logs
    `gemini_tts_http_error` with the model, the status and the bounded code, never the
    vendor's prose. Proven on dev: a real session ended visibly (`failures`, in 30 s)
    instead of hanging; the 2.5 model voiced three lines with no direction and the radio's
    mixer joined them (14.5 s); a session on the default engine aired from its opening to
    its farewell.


28. **The station's music is continuous and the player's; a segment is the voice alone.**
    The owner found the short beds middling (2026-09-26) and asked for music that never
    stops, lowered under the voices — first from a third-party site's « royalty-free »
    stream, which was read and refused: it is no stream but a catalogue of uploaded
    songs (with vocals), its terms grant a listener no licence, its robots.txt disallows
    exactly `/media/audio`, and its files carry no CORS header, so no browser could duck
    them through Web Audio (and iOS ignores an element's `volume`). What replaced the
    beds: four MOODS (`MusicMood`: morning, news, evening, calm) — news is read over the
    news music at any hour, everything else follows the listener's clock
    (`music_mood`, `daypart_mood`; the evening starts with the journal's evening edition,
    one notion of evening); every segment and the session carry their mood on the wire, computed with
    the listener's timezone from the session's frozen setup (none when it cannot be
    read — the player then plays calm music, never silence). A library of a dozen
    instrumental tracks per mood, about two minutes each, generated ONCE with Lyria 3.5
    (`scripts/assets/generate_radio_music.py`, 54 generations for 48 kept — five refused
    by the provider's own filters, one refused here, for lyrics or a length under
    90 s (a text part with WORDS is lyrics: measured on the first song, an
    instrumental returns section markers only);
    4.40 $ with the measurement, inside the 5 € the owner granted), silence-trimmed,
    two-pass loudness-normalised (−18.7 to −18.3 LUFS measured across the 48), committed
    under `apps/web/public/radio/music/` with its provenance and a manifest the player
    imports (`music-library.json`; `test_music_library.py` holds moods, files and
    hashes together, so a reinstall needs nothing regenerated). In the browser
    (`music-bed.ts`): two decks crossfaded over 4 s when a track nears its end or the
    mood changes, a shuffled bag per mood (every track before any repeats, never the
    same twice in a row), one master level lowered by about 12 dB under every segment
    in 0.35 s — under the half second of silence a segment now opens with — and raised
    in 1.2 s after it; routed through Web Audio (`web-audio.ts`) from this origin's
    files; the permission to play taken inside the click for voice and music alike, the
    music started by the first answer, which names its mood; a report never changes the
    music under a segment on air (the segment's own mood governs, the session's only in
    a gap). On the server the per-format beds, their module and their mix went: a
    segment is its lines joined with their pauses and normalised to −16 LUFS
    (`audio.plan_segment`). Proven: a real Chromium starts the calm music at the first
    answer (e2e), and a real session on dev published its moods and aired voice-only
    segments.

29. **What the owner heard in a first long session, and what changed** (seven returns,
    2026-09-26 evening; every cause proven from the dev logs and the database before any
    change).
    (a) **The station airs until its stop, and the stop counts listening time.** The
    farewell aired nine minutes before a 30-minute timer: the grid signed off whenever a
    timer existed and nothing fitted — decision 2's repair, written for a session with
    minutes left — and the running order is projected on TARGET durations (a column 180 s,
    an analysis 270 s) real segments ran well under (57 to 96 s). The farewell is now
    planned only inside the sign-off window (`SIGN_OFF_WINDOW_SECONDS`); when nothing fits
    before it, nothing is planned and the station's music plays — the owner's choice, so a
    listener never wonders whether it broke — the grid asked again at every tick. A
    farewell planned early is confirmed on the real running order before it is produced and
    withdrawn otherwise (`ActionKind.WITHDRAW`; the loop applies it and sleeps, so a case on
    the window's edge cannot spin — a mutant that did hung the loop). A pause stopped
    nothing: eleven minutes of pause had run against the timer. The player now says
    `paused` (never inferred from `playing: false`, which is also the music between two
    segments), the published stop moves while it lasts (`effective_stop_at`) and resuming
    extends it by the pause.
    (b) **A failed format rests.** Six analyses were drawn in a row and each failed: a
    failed slot left the running order, and a format's minimum gap read the aired slots
    alone. A failure is remembered (`SessionState.failed`) and its format rests
    `FAILED_FORMAT_REST_SECONDS` or its own minimum gap, whichever is longer — under the
    fill and clock rules too; the opening and the farewell are exempt.
    (c) **Why they failed.** The verifier's answer was cut at exactly 4 000 tokens three
    times — a model that bills its reasoning inside the cap (ADR-285): its cap is now the
    writer's, pinned by a test. And the voices met 38 rate limits in one session, retried
    after 1 s and 2 s whatever the provider asked: a rate limit is now read structurally
    (`TTSProviderError.rate_limited`: its code or a 429), waited as long as the provider's
    `Retry-After` says, else 5 s doubling, never past `RADIO_TTS_RATE_LIMIT_WAIT_MAX_SECONDS`,
    and SHARED by the segment's lines — one cooldown honoured inside the concurrency gate;
    `retry_async` gained a `delay_for` hook, its single policy otherwise unchanged.
    (d) **Each programme says its own data, once, and is announced like a programme.** The
    date and the time came back before « my day »: the clock fact was in every pack, and the
    editor repairs a time said without citing it into a cited one. The clock now reaches the
    opening (now) and a programme announced for a clock mark (its mark) only; the weather is
    said once a session — and a production in flight HOLDS it (`SAID_ONCE_KINDS`, taken
    with no await between the desk and the pack, given back whatever happens): the start
    produces two slots at once and both desks read what was said before either had aired,
    so the weather reached the opening and the listener's day alike (found by the cold
    review); the journal's evening edition leaves out what the session said; an analysis of a story is
    read once a session. « Voici le commentaire : » and « c'était la chronique, la
    suite c'est la chronique » came from a neighbour named by a cognate (`spoken_as` read the
    column as « the commentary ») and a prompt that asked to hand over by name and to pick up
    from the previous programme: a programme is never read out as a label nor closed by its
    own name, and a hand-over is a few natural words of the listener's language. A
    programme that tells one story announces it first by its headline and its outlet. The
    first proof after the change found the announcement written as a SUMMARY, then said
    again by the body (« 500 miles … recharging gaps », twice in three lines), and a
    hand-over translated word for word from the prompt's English example (« Un mot pour toi
    suit ») — the announcement is now a headline, never a summary, no line says again what an
    earlier one said, and the examples ask for the presenter's own words, never a rendering;
    measured afterwards, « En RD Congo, le crash qui a coûté la vie à quatorze personnes,
    selon France 24. » opened a brief whose body said only what was new, and the hand-overs
    read « On retrouve maintenant le bulletin d'information. », « À suivre, les titres de
    l'actualité. ». The same proof found an event told twice: the headlines retold a match
    the bulletin before them had told, from another article, and the next session retold a
    mass from a third. A key and a fingerprint cannot tell that two articles tell one event
    (a word match across languages is noise, decision 18); the writer can, if it is shown
    what was told — and it was shown the PROGRAMMES' titles, which name one or two of a
    bulletin's six stories. The next news writer now sees the headlines of every story
    heard (`antenna.aired_headlines`, in an `ALREADY HEARD` block, fenced), and a story it
    lists is never told again — from another outlet, article or angle; the exception « unless
    among the most important » went with it (the owner: every programme its own data). The
    writer did not always obey: shown « Près de 600 000 fidèles attendus pour la messe
    géante… », it chose « Près de 600 000 fidèles attendus à la messe… » as the next
    session's figure of the day. So what words CAN decide is decided before the writer: an
    article whose headline shares at least 60 % of its words — and at least three, articles
    and prepositions left out — with a headline heard over the ledger's horizon, or with one
    already chosen for the programme, tells the same story and is not offered
    (`editorial.same_headline`; 0.9 on that pair, while two different stories rarely share
    half; a headline written without spaces is left to its fingerprint).
    (e) **What was heard stays heard, across sessions.** The ledger lived one day, renewed at
    every write, while a column and an analysis read stories two days old, and the newsroom
    filed again as « new » the stories its purge had just removed (164 purged at 21:31, 165
    « new » at 21:36, their texts downloaded again). Three sorted sets per account date every
    member — a story's keys, its fingerprint and its HEADLINE for `NEWS_MAX_AGE_S`, a fact
    of the person's day for a day — each leaving on its own date; the next session's first
    news writer is shown the most recent headlines heard (`ON_AIR_SHOWN_MAX`), so an event
    heard yesterday evening from one article is not told again this morning from another;
    the newsroom files only what is younger than what it keeps (one line for the purge and
    the filing). The first ledger's names are
    never reused: its plain sets were still on dev, a sorted-set call on one answered
    WRONGTYPE, and the whole ledger read as unavailable (measured on dev 2026-09-27; the
    unit tests' Redis double now refuses a call on a key of another type, as Redis does).
    (f) **The settings say what each choice covers**: every programme (the bound it
    enforces, the hours of the journal's editions), every kind of news (its outlets per language, the EXACT
    count it published over 48 hours in the languages the listener hears — a kind that
    publishes little says so before it is picked alone), every personal source; the figures
    are the API's (ADR-184, ADR-185).
    (g) **The article, whole and in the listener's language.** The programme says a story
    in a few sentences; the page now lists the session's articles and opens one whole —
    translated on OPENING when its feed speaks another language (owner decision: translating
    what is merely offered would be paid for nothing), by a slot of its own
    (`radio_translator`, tuned in the admin), once per story and language (a shared cache
    for as long as the story may air; two readings at once, on any worker, make ONE
    translation — `shared_flight`, whose claim can now outlive a long build, `claim_ttl_s`),
    billed to the reader under a run of its own and said with the article. The newsroom
    keeps a text whole when it fits, else exactly its first `ARTICLE_MAX_CHARS` characters
    (`was_cut`): such an article ends on its last whole sentence and says the rest is at
    the outlet — a page bound written first could never bind below the newsroom's and was
    removed, and the newsroom's one-paragraph-per-line text is set apart by blank lines for
    the page and the translator alike. The slot's timeout stays under the edge proxy's
    documented 100-second read timeout (a plain request the reader waits for); a refused
    translation shows the original with what it cost. The original stays one click away
    beside every fold (owner request, 2026-09-27): reading the article at its outlet asks
    for no translation.
    Proven on dev — the voice slot brought back to the free engine in the proofs' own
    process (owner instruction), the owner's configuration untouched: a 40-second pause
    moved the stop by 40 seconds; the opening said the date and the time once and no later
    programme said them; an English article was translated in 6.0 s for 0.000396 €, opened
    again from the cache in no time for nothing, and two readings of another at once made
    one translation (0.000634 € and 0 €); a story that is not the reader's read as absent;
    a five-minute session with a 40-second pause aired the station's music between its
    programmes and its farewell last, heard 34 s before the stop; two sessions in a row
    aired no article twice. Stated, not solved: a feed flooded by one event — a dozen
    articles on one mass — still brings it back from new angles (two briefs in a row in a
    three-minute session, the headlines heard shown and the rule stated), because an angle
    shares a name or two with what was heard and no word match can tell it from another
    story; and one writer family slipped once into the formal address and closed a
    programme by its name. Telling an angle from a story needs meaning, not words — a
    decision for the owner (it would give the newsroom a model, decision 1).
30. **The owner's second returns: the station above the day, a name of its own, what the
    listening will cost, a bar that holds still** (2026-09-27).
    (a) **The radio sits under the quick-access bar, right above « My dashboard »** —
    never above the hero (owner request, refined the same night): the page hands the card
    to the briefing's lead-in slot (`TodayBriefing`'s `aboveBriefing`), kept when the
    briefing fails since the radio does not depend on it. Placed mid-page, a card that
    waited for its own read of the configuration landed a round trip late and pushed « My
    dashboard » down (the cold review's finding): `/config` is public, so the layout reads
    it from its first render, not after the session, and hands its last read to every
    page under it as a starting point (`AppConfigSeedContext`) — each reader still reads
    its own, so nothing is staler than before. Proven in the browser with every read of
    the configuration held 4 s: reached from another page the card is there within 2 s,
    and without the seed the same journey fails.
    (b) **The listener names their station.** `station_name` joins the settings, at most
    `STATION_NAME_MAX_CHARS` (published as `station_name_max_chars`), strict on the way in:
    markup, template braces and every control, format, surrogate or private-use character
    are refused, checked on the RAW value — its test found the first version folding the
    spaces first, which turned a line feed into a space and let it through —, the spaces
    folded, empty for the name the listener's language gives the station. An UNASSIGNED
    character is kept on both sides: what this server's Unicode does not know yet is a
    newer emoji to the listener's browser, which cannot know the server's version and
    would meet a refusal. It is frozen in the session's setup like every other choice (a
    rename reaches the next session), said by the host at the opening, and published on
    every session answer: the bar and the media session show it; the home card shows the
    session's name while one is live and names it, and the listener's own otherwise —
    tuning in, off air, and once a session is over, since the listener may have renamed the
    station since. A name may hold digits (« Radio 42 », « FM 98.5 »): the cold review
    found every line naming such a station dropped as an unsupported number — an opening
    that says nothing else refused, and a session ending on `failures` — so the editor now
    blanks a MENTION of the name before reading a line's numbers (never « supports » the
    name's numbers everywhere, which would let « 42 deaths » pass), the clock's repair
    reads the line the same way, and the model verifier is told the name below its marker
    — the static prefix every listener shares stays one. The settings field saves when the
    listener leaves it or presses Enter — never per keystroke, which would save every
    half-typed name, nor on the Enter that picks an input method's candidate —, strips what
    the API refuses and counts as the API counts, by code point, so a cut never leaves half
    a surrogate pair (the field's own `maxLength` counts UTF-16 units: stricter for a
    character outside the basic plane, never looser). In company (public mode) the
    station keeps the name its listener gave it: a name is the station's, chosen to be
    said on air, not a fact about its listener.
    (c) **What the planned listening will cost**, beside what it has cost: every report
    publishes the cost so far divided by the radio produced, times the listening the timer
    planned (`SessionState.planned_s`, fixed at the start: a pause moves the stop, never what
    was planned), or an hour when no timer stops the station. The spend follows production
    and production follows listening, so the session's own rate prices the rest in whatever
    models and voices it runs on — a per-model table re-typed here would be a second
    authority on prices. Nothing is published before `RADIO_COST_ESTIMATE_MIN_AUDIO_SECONDS`
    of radio was produced (the opening's rate alone is a guess), while the cost is unknown,
    once the session's end is decided (the listening it planned will not happen, while the
    player drains what is queued), nor for a timer no plan was recorded for (a session
    stored before the plan existed: an hour would say « for 60 min » on a 30-minute
    timer); the bar says it with two significant digits AFTER rounding (0.0995 € reads
    « 0,10 € »), because it is an estimate.
    (d) **The bar reads in three groups and holds still.** The station (its name, where it
    stands, what airs — the only part announced), the meters (the minutes left, the cost and
    the estimate), the actions (the page, then pause and stop side by side in a two-column
    grid, the same size in every language; stop keeps its destructive colour at its
    neighbour's size, ADR-207; on a phone, two equal halves of the bar). Measured in the
    browser before the change: a pause removed the line of what airs — the bar changed
    height, on a phone the resume button moved from under the finger — and « Pause »
    became the wider « Reprendre », moving both buttons, so a second click meant to resume
    could land on stop. What airs now keeps its line through a pause, the line stays (empty)
    between two programmes, and the pause button holds the width of the longer of its two
    labels, each drawn with its icon and only the shown one named: identical boxes before
    and after a pause, desktop and phone. The cost had an `aria-label` on a plain `<span>`,
    which ARIA 1.2 prohibits and no screen reader reads: every figure is now named by
    visually hidden text. Stopping from the keyboard took the stop button away with the
    live controls and left the focus on the page's body: once the stop the listener
    pressed has ended the session, the focus goes to « Start again » — never when the
    session ended by itself, nor once the listener moved the focus elsewhere.
    (e) **The cache, asked about and measured.** The owner asked whether the chat's cache
    policies reach the radio, and whether « frequent exchanges » fits it. They do: every
    model call of the radio is one structured call through `single_call_messages`, its
    static prompt above the marker (ADR-309), so each provider's adapter applies its own
    mechanism exactly as for the chat. Over 48 hours of radio runs on dev the writer read
    72 % and 71 % of its prompt from the cache (two model families), the verifier 0 % and
    50 %, the analyst 20 %, the translator nothing (one call per article and language);
    the verifier's static prompt (577 tokens) and the analyst's (467) sit under the
    ~1 024-token minimum of breakpoint caches — a structural gap, not a missing policy.
    « Frequent exchanges » (ADR-311) decides three effects of a ReAct loop — every tool
    bound, the context after the question, the history by blocks —, none of which exists in
    a single structured call; the radio already follows its principle, the stable prefix
    first and calls every 30 to 90 seconds. And the cache weighs little here: over 36
    sessions the models cost 0.1465 € and the voices 2.9985 € — 95 % of a session is
    speech, where no prompt cache applies. Not done, on purpose: lengthening the verifier's
    prompt past the minimum (a longer prompt is measured for quality first, and context is
    never traded for a cent), and reordering the writer's dynamic part (it would help the
    implicit caches alone).
    Proven on dev, on the proof account only (the free voice engine forced in the proof's
    own process, the owner's configuration untouched): a name typed « Radio   Preuve » was
    saved and read back folded, a zero-width space refused; the start answer and every
    report named the station, and the opening said it; an eight-minute session published
    no estimate while 93 s of radio were produced and 0.00685 € for its 480 s once 198 s
    were — exactly the cost so far over the radio produced times the plan —, held between
    0.0068 € and 0.0070 € to its end (0.0052 € spent for 354 s produced), and a 30-second
    pause moved the stop by 30 s and left the plan at 480 s. Found on the way, and stated
    rather than hidden: the first proof sessions produced little and one ended after 45 s
    on `failures` — the account had heard every story the newsroom held in its languages,
    so two formats had « nothing to say », and a production with nothing to say is counted
    as a failure; the proof account's ledger was reset to measure the estimate.

31. **The radio in the transparency register** (2026-09-27, the owner asking whether the
    radio's acts reach it with the right classification). Its model calls already reached
    the ledger — every euro under the session's run — and its reads the consultation
    register, filed as the listener's (`consultations.py`, source `user`); but the run they
    are filed under pointed at NOTHING in the decision register, so the registers' overview
    — the turns of a day, how they ended — never saw a radio session happen (measured on
    dev: 47 sessions and 5 article translations in twelve days, none there). Two acts now
    take one row each, under the run their euros and reads already carry, route `radio`
    and `radio_article`, authorship `user`, execution `direct` (`radio/register.py`):
    - **A session is filed when it ends, by whoever sees the end**: its loop
      (`SessionBooks`, a port of `RadioLoopLauncher`), or the service when no loop holds it
      — a stop that finds none, and now a start that REPLACES a session no loop holds,
      which nobody closed before (a report on a replaced session never revives its loop:
      its state stayed un-ended until its keys expired). Two closers may race, so the row
      is written by `record_decision_once` — an insert that does nothing on a second
      filing — never by the turn's merge, which would read the race as a session run twice
      (proven on PostgreSQL). The end reads as the listener would say it: the timer and
      the listener's stop are `answered` (the latter with its reason), nobody listening
      and a spending ceiling `interrupted`, failing productions `failed` — one table,
      refused at import when an end is missing. A defect AFTER the end files and counts the
      end that stands (a programme that ran to its timer and only failed to close its parts
      used to be counted as a failure), and the audio follows that reason. A shutdown or a
      takeover files nothing: the session goes on elsewhere.
    - **An article translated on opening is an act of its own**, filed when the call
      returns — `failed` when no usable translation came back; a reading served from the
      shared cache called no model and files nothing.
    - Neither is an ACTION: nothing of the person's changed, so `agent_effects` stays
      untouched, and neither ever appears among LIA's initiatives.
    Proven on dev, on the proof account only: a session listened to for 75 s then stopped
    left ONE row (`radio`, `user`, `direct`, `answered`, `listener`, one segment, 76.9 s);
    opening a story in another language translated it (0.0012 €) and left one row
    (`radio_article`, `answered`) with its inference under the same run, and opening it
    again, served from the cache, left none. The same audit found runs outside the radio
    that nobody filed and a reflection billed twice; they are closed by ADR-263's
    amendment of 2026-09-27, which makes every accounted run name who files it.

32. **A news flash when LIA writes to the listener** (2026-09-27, owner request: « LIA must
    make a transition to interrupt the programme, say and comment on the notification,
    then go back to the programme where it stopped »). When LIA sends the listener a
    proactive notification while their radio is on, the station breaks in (`flash.py`):
    - **Out of the running order.** A flash is numbered from `FLASH_SEQ_BASE` (100 000),
      never planned by the grid, one at a time, telling at most `FLASH_NOTES_MAX`
      notifications — those archived after the watermark (the session's start, then the
      newest note a flash took), read every `RADIO_FLASH_POLL_SECONDS` (15 s) through the
      reader of the personal corner, oldest first. Only while the listener hears the
      antenna: never before the first sound, while paused, or once the farewell is
      planned; never in company or with the notifications switched off for the radio
      (no source at all), never past a spending ceiling; a source that breaks costs the
      flash, never the session, and a flash that could not be produced is not tried again
      (its notes stay in the chat, where the corner may come back to them).
    - **The player cuts and resumes.** Every answer names the waiting flash apart from the
      segments (`flash`); the player holds the programme on air at its position, plays the
      flash, then resumes the programme from that position — the element seeks
      (`playSegment(url, startAt)`) — or, between two programmes, airs it before the next.
      While it airs, the reports keep naming the programme it cut, frozen where it stopped;
      once it ended, every report says `flash_heard` (the highest flash played to its end)
      and the loop drops it. The answer to that report is built before the loop reads it,
      so it may name the flash once more: the player never airs a flash it heard.
    - **A flash names only what will be true when it airs.** It is written when it starts
      and heard when it is ready, and the programme on air may be over by then — measured on
      the first proof: written over the welcome and heard after it, it said « back to the
      welcome ». The programme it cuts is named only while more of it is left than the
      flash takes to produce (the loop's own estimate: `production_s` × `lookahead_safety`
      + `lookahead_margin_s`); otherwise the next programme, once it is READY (one still in
      production may never air); otherwise the host goes back in general words.
    - **The script**: one line that breaks in, what LIA wrote in fact lines citing it, at
      most one kind or practical word asserting nothing more, and the hand-back — never
      when LIA wrote it. A notification airs ONCE, by a flash or by the corner: one key
      for both (`facts.notification_key`), a note already heard is not flashed, and the
      notes a flash tells are held from the corner while it is produced (the corner
      reads the same notifications, newest first).
    - **Books**: a look that found notes is a consultation of the notifications under the
      session's run (a look that found nothing is not filed); the flash's model and voice
      spend are the session's; its seconds count as radio in the cost estimate
      (`flash_audio_s`).
    The mutants and the cold review found three defects, fixed: the player compared the
    waiting flash by object IDENTITY, while every answer names it as a new object — an
    answer arriving while its audio was on the way threw the audio away and fetched it
    again a report later; it compares numbers now. A loop taken over after a worker died
    kept a flash whose production died with it — one flash at a time, it held every
    later one; `reloaded` drops it. And the corner could tell a note a flash was
    telling. Proven: in Chromium, a programme cut about 4.7 s in resumed there (the
    element restarting at 0 fails the spec); on dev, on the proof account only,
    a notification sent through the real dispatcher aired 15 to 20 s later (the poll, then
    about five seconds of production), 18 to 23 s of audio, heard in three movements — « Flash
    info, je coupe un instant. », what LIA wrote, the hand-back —, gone from the answers once
    reported heard, one more `radio:notifications` consultation under the session's run.
33. **The station's silence is no failure** (2026-09-27, found by the flash's proof). Three
    productions that aired nothing in a row end a session on `failures`; an analysis its
    editor refused, a corner with nothing to say and a refused column were three, and a
    default account's session ended 25 to 30 s in — cutting the flash it was voicing.
    Decision 30 had stated it as a limit (45 s on « nothing to say »). But the stop exists for
    a station that BREAKS, and choosing silence over a programme the station cannot stand
    behind is the editor working. So the antenna tells them apart where it sees every
    outcome (`Antenna._counted`): nothing to say or a refused script comes back as
    `NothingAired` — its format rests exactly as after a failure, and the stop never counts
    it; a writer with no usable script, a check that could not run, a voice or a mix that
    failed, a defect still count. A station with nothing more to say plays its music (the
    grid's rule 8) until its timer, each format tried at most once per
    `FAILED_FORMAT_REST_SECONDS`. And the rest now reaches what was planned BEFORE the
    failure: a second column planned while the first was in production was produced after
    its refusal and refused the same way — the waiting slots of a failed format leave with
    it (one already in production is paid for, and finishes). Proven on dev, the proof
    account: three editorial non-productions in a row, and the session ran to the
    listener's stop.
34. **What airs is chosen, checked and remembered better** (2026-09-27, the owner's
    third returns). Each change was measured before it was kept:
    - **A connection's words are theirs.** A message or an image a connection sent through
      LIA is archived as a proactive notification, but its substance is the connection's
      (`peers.RELAYED_MESSAGE_TYPES`): neither a flash nor the corner tells it as LIA's.
      The query leaves it out, so three of them never use up a flash's bound.
    - **The verifier reads meanings, and says what the facts hold before it decides.**
      Measured on a FIXED set — the real columns of two measuring rounds, labelled line by
      line, and nine claims no digit betrays planted in them (30 scripts, three passes):
      the verifier as first written rejected a supported line 31 % of the time (21 % of
      the fact lines, « in the column, from BBC Afrique » read as a claim; 37 % of the
      opinions) and refused one column in two. A framing now covers nothing but itself,
      other words may say what the facts say, and each verdict first states what the
      cited facts hold about the line's specific statements (`LineVerdict.evidence`,
      written before `supported` — a model writes its fields in order): 12 to 16 % (5 to
      8 % of the fact lines, 16 to 20 % of the opinions), one column in four refused, and
      every planted claim still rejected (27 of 27). About 170 more output tokens and
      1.2 s per check, inside the look-ahead's writer allowance (measured p90: 4.3 s to
      write, 4.1 s to check, against 12 s). Two ideas were measured and dropped: asking
      the verifier to QUOTE the words it rejects changed nothing (15 % against 16 %),
      and a rule reading that quote would drop a TRUE rejection whenever a model quotes
      loosely; and paired rounds that rewrote their scripts every time swung from −8 %
      to −48 % on opinions — only a fixed set measures a prompt. What remains is the
      slot model's reading of paraphrase: the same supported opinions, pass after pass.
    - **An analysis rests on its story.** The anchor tells the article's details, and
      they live in the analyst's points: half the anchors' fact lines cited points alone
      (21 of 43 over three rounds), even with the writer told not to — so four analyses
      in four lost their setting-out line when first measured, two the whole segment.
      The editor repairs it
      (`verification._with_story`, ADR-184: repaired before validation, never reported):
      a fact line citing only points of ONE story also cites that story's own fact;
      fifteen analyses in fifteen aired. The writer's instruction, measured without
      effect, was taken back.
    - **Another article of an event heard is no news.** An outlet tells one event under
      headlines sharing too few words for the word rule (« L'Espagne renverse
      l'Angleterre à Wembley » and « L'Espagne continue sur sa lancée en renversant
      l'Angleterre à Londres »: two). The antenna reads the headlines' MEANINGS
      (`meanings.py`): the platform's embedding of a headline the first time a desk meets
      it, billed to that listener's run — the newsroom still calls no model (decision 1)
      — and shared with every listener through Redis (`radio:headline`, as long as a
      story may air). Two headlines at or above `RADIO_SAME_EVENT_SIMILARITY` (0.9) tell
      one event: once one is heard, or chosen for the same segment, the others are left
      out. Measured on the dev newsroom (80 stories, 101 pairs labelled by hand):
      outside the one story twenty articles covered (a papal visit), every pair
      telling one event stood at 0.906 or more and two distinct events at 0.871 at
      most; inside it, one event and two overlapped between 0.874 and 0.898 (two
      masses, on two days, at 0.898); headline with summary separated worse (one
      match told twice fell to 0.823). At 0.9 nothing distinct is joined, and a big
      story's other angles stay the writer's to judge, shown what was heard. The
      threshold is a setting, and 0 turns the reading off. A blind reading leaves the
      words to judge and rests until the desk is read again; an answer of another
      shape keeps nothing (which vector is whose cannot be told). A session keeps the
      vectors as the provider's float32 — 6 KB a headline at 1 536 dimensions, where
      Python floats weighed 49 KB — and reads them under one lock, so the two desks of
      a start never buy one reading twice. Proven on the proof account: 76 headlines
      read cold in 1.0 s for 0.0002 € on the session's run, then in 0.003 s from
      Redis for the next session; 26 pairs of the day joined, 3 of which the words
      already joined; the other article of a heard incident left out of the bulletin.

35. **What was heard is filed when it is heard** (2026-09-27, the owner: « I never heard
    177 articles! »). The ledger across sessions filed a segment's facts when it was
    PRODUCED, and a session produces ahead of its listener — two programmes before the
    first sound, then one in flight —, so a session stopped after its opening had filed
    the programmes produced ahead of it: measured on dev over twenty sessions, at least
    30 of 77 news productions filed as heard had never aired, and the « 177 » counted fact
    keys for 119 distinct stories. Now a produced segment carries, line by line, what each
    voiced line tells (`HeardLine`: where it starts, the personal and news keys it says,
    the fingerprints and headlines of the stories it tells first — `ProducedSegment.memory`,
    published with the segment, never sent to the player), and the session's loop files a
    line once the player's report has passed its start (`orchestrator._file_heard`, after
    every read of the inbox). A programme the player never reported playing — produced
    ahead, skipped — files nothing; a flash is filed whole once `flash_heard` covers it; a
    loop taken over reads the published segments (`read_ready`) and files what its
    predecessor had not (what it files again is re-dated, never doubled). Within a session
    the antenna's own memory still follows production: a fact produced for a programme
    about to air is not offered to the next one. A ledger that fails costs the next
    session a repeat, never this one.
36. **The station's music between two programmes** (2026-09-27, owner decision). Five
    seconds of the station's music separate two programmes (`RADIO_SEGMENT_GAP_SECONDS`,
    0 = none), fixed in each session when it starts (`SessionState.gap_s`): every
    projection of the running order leaves it (`programme.next_air_at`, `_reproject`), so
    the look-ahead and the sign-off window count it, and every answer publishes it
    (`segment_gap_s`). The player rests that long after a programme ends before it plays
    the next — the music at full level —; a news flash never waits for it, a pause lets it
    lapse and a stop clears it. Each rest is a few seconds of music in place of speech,
    so a long listening pays for fewer voiced seconds.
37. **A listener's radio has a budget of its own** (2026-09-27, owner decision: « limit
    the radio to 2 euros per user per 24 hours », so that nobody leaves a station playing
    at the platform's expense). The bound is `RADIO_BUDGET_24H_EUR` (2 €, 0 = none), over a
    ROLLING window (`BUDGET_WINDOW_SECONDS`, a day), on everything the radio bills a
    listener: their sessions (`radio_<hex>`) and article translations
    (`radio_article_<hex>`), found by the run prefix spelled once (`RADIO_RUN_ID_PREFIX`,
    matched literally — `LIKE`'s underscore escaped). What a run spent is its ledger row,
    every family (`billed_cost_sql`, ADR-272), and a run counts WHOLE while its last
    spend lies in the window — a session is filed once per production, so `updated_at`
    is its last euro. When that errs, it costs the listener a little waiting, never the
    platform a euro past the bound: no 24 hours ever hold more than the bound, plus what
    was already under way when it was crossed — it is asked before each production,
    flash and translation (`budget.py`). It is the radio's own bound, on top of the account's
    ceilings, never instead of them. Three doors ask it, each at its moment:
    - **a start** is refused before it takes a place or reads anything —
      `radio_budget_reached` (429) with the bound (`max_eur`) and when enough of the spend
      leaves the window to play again (`lifts_at`, the oldest runs leaving first); the bar
      quotes both in the listener's locale, and quotes nothing it was not sent;
    - **the loop**, before every production and every flash, asks the account's ceilings
      then the radio's own (`radio_spend_blocked`): past it the session ends as `budget`
      (« a spending limit was reached »);
    - **an article's translation**: no model is asked and nothing is filed; the original
      is shown, said so (`budget_reached` — never as a failed translation).
    The settings say what the radio spent over the window against its bound, and, at the
    bound, when it lifts (`GET /radio/budget`). The voices stay an administrator's choice
    in the LLM settings (the owner kept them there): the budget is what bounds a
    listener's spend.
38. **Sources are the raw material** (2026-09-27, owner decisions: « everything is
    translated », every base source ticked by default, a listener's sites « ticked,
    renamed, deleted — up to 20 »). The kinds of news and the feed languages are gone:
    every story airs translated into the listener's language — the writer translates the
    substance of a fact written in another language, the verifier compares meanings — and
    what a listener chooses is WHICH sources feed their station:
    - **the base sources**, the catalogue, each one heard unless the listener unticks it
      (`disabled_feeds`, by feed address: an address the catalogue does not hold is refused
      on write, and forgotten on read once the catalogue drops it; the kinds and languages
      an older row stored are read as nothing);
    - **their own sites**, up to `RADIO_CUSTOM_SOURCES_MAX` (20), each renamed (the
      station's name's character rules, `names.speakable_name`, at most
      `source_title_max_chars`) or PAUSED (`radio_feeds.paused`, migration `4c1e8b2f9a37`):
      a paused site is neither read by the newsroom nor offered to a session, and it is
      kept — `PATCH /radio/sources/{id}` (`{title?, paused?}`, 404 when not the caller's).

    `GET /radio/sources` says, for every source, what it published over the window a
    programme airs from (`NEWS_MAX_AGE_S`) and how many of those stories the listener never
    heard — a story whose key or fingerprint the aired ledger holds was heard
    (`sources_view.py`, pure; the stories read by one statement over the window, the ledger
    once, ADR-185) —, whether its last readings failed, and the totals the station can air
    (the ticked base sources and the running sites; an unticked source or a paused site
    still says what it holds, so ticking it back is an informed choice). « Forget what I
    heard » (`DELETE /radio/heard`, after a confirmation) removes the listener's aired sets: every story may air again — a session on air keeps its own memory until it
    ends. When the desk holds stories and the listener heard every one, the station says
    so ONCE a session, in a short host segment (`NOTHING_NEW`: never offered in the
    settings, planned by the grid on the desk's `news_exhausted` — `editorial.everything_heard`,
    the shortlists' own predicate, so an empty newsroom is not a listener who heard it
    all) — and only to a listener who hears a news programme —, then plays its music and
    its personal programmes until something new comes. With 27 base feeds and up to 20 sites
    per recent listener, a newsroom pass reads 60 due feeds (`RADIO_NEWSROOM_FEEDS_PER_PASS`;
    measured, at 20 a pass, 37 feeds already needed two).

    Every language fills the desk, which the review of this decision measured before
    shipping it: 818 stories in 48 hours on dev, the 300 a gathering reads covering 17 of
    them, and the told relation read pair by pair — 300 stories against 300 headlines heard
    held the event loop two seconds per desk. So a gathering reads the stories never heard
    first (`repository.news_candidates`: the heard keys and fingerprints ordered last, so
    the bound keeps what can still air and what was heard still tells an exhausted desk from
    an empty one); a story is compared with a heard headline only when they share the words
    `same_headline` requires (an index, `editorial._Told`) and with every meaning at once
    (`HeadlineMeanings.told_among`, one slice of the relation) — 18 ms for the same desk —;
    and the desk is read off the event loop (`news_desk.read_news_desk`, on copies).

39. **Two families of news programmes, three new ones, and the checks measured on them**
    (2026-09-27, owner decisions: the subject rules and the angle programmes approved, the
    column renamed « editorial », « a debate with a conclusion », « a discussion between
    enthusiasts »). Each rule below was measured on dev before it was kept.
    - **Renew or take an angle** (`FormatSpec.renews_subjects`). The headlines, the
      bulletin, the brief and the figure RENEW the news: never a story the listener heard
      (the rules before). The analysis, the editorial (the column, relabelled) and the three
      new programmes take an ANGLE on one story and may come back to a story heard: its fact
      says so (`RadioFact.returning`, rendered « heard before »), and the writer's ALREADY
      HEARD rule lets such a programme, and only it, take it. An angle never takes the
      subjects of the programme just before it (the antenna remembers what each place told,
      the last `TOLD_KEPT_SLOTS`; a flash is no place) nor a subject its own type already
      took (`AiredLedger.treated`: a fifth set, `radio:aired:{user}:angles`, members
      `{format}:{k|s|h}:{value}` over the stories' horizon, filed when HEARD like the rest and
      read forgivingly — a member naming a format this release no longer knows is left out).
      A subject is an event: a key, a fingerprint, a headline by its words or its meaning
      (decision 34).
    - **Three programmes**, rare, forty minutes apart at least: the DOSSIER (anchor and
      expert, the story in chapters from the analyst's points, closing on ONE open question),
      the DEBATE (a moderator and two or three speakers holding opposed positions from their
      first line to their last; the moderator concludes where they agree and where they
      differ, never who is right) and the DISCUSSION (two or three enthusiasts talking one
      story through — the writer chooses it among four). The dossier's five minutes (at most
      seven and a half) were measured on the half-hour simulation: seven could not be
      produced behind three short programmes without the listener waiting.
    - **Commentators** (`speaker_a` to `speaker_c`) are the station's, never presented as
      real people, and never configured (`CONFIGURABLE_ROLES`: a stored choice for one is
      refused on write and ignored on read). They are cast automatically (`cast._speaker_voice`:
      a voice nobody speaks with, else one lent by a role that never speaks in a debate or a
      discussion — the expert's, the editorialist's —, else one no other commentator has, the
      moderator's before LIA's: silent in a debate, it is heard in a discussion).
      A programme speaks with the roles that have a voice of their own (`Cast.voiced_roles`:
      a commentator with LIA's voice — the host frames every programme — or with the voice
      of another role of the same programme is left out, and the writer is given the roles
      that speak); a format needing more distinct voices than the cast gives it is not
      planned (`voices_by_format`, per format, where one count served the whole cast). An
      `opinion` line is theirs as it is the editorialist's (`OPINION_ROLES`;
      `opinion_outside_commentators` elsewhere).
    - **Room to write.** First measured with a writer slot reasoning « low »: a dossier, a
      debate or a discussion is a script of 1 to 2 k tokens, yet 7 of 12 calls stopped at
      exactly 8 000 — the thinking is billed inside the cap (ADR-285). `radio_writer` and
      `radio_verifier` default to 16 000 (a cap is billed only as far as it is used); 2 of
      the next 30 drafts still stopped at it, both dossiers (a limit, stated below).
    - **The verifier's VIEW test**, measured on a FIXED set (decision 34's method): the four
      scripts of the first round and four discussions written on the desk's REAL shortlists,
      145 cited lines labelled by hand, 24 of them unsupported, three passes each. The
      column test rejected 22 % of the supported lines, caught 58 % of the unsupported and
      refused 10 scripts of 24; the view test — a commentator's judgement, images, figures
      of speech and replies to another speaker are theirs; how certain a claim is and how the
      source presented it are claims — rejects 13 %, catches 51 % and refuses 7. A further
      clause for words about the conversation itself (« the three of us, tonight ») measured
      equal (13 %, 50 %, 7) and was not kept; the prompt as shipped (its framing example
      renamed after the editorial) measured once more: 12 %, 54 %, 5.
    - **The writer's guides measured, not rewritten.** Guides amended to hold every fact line
      to its facts, the debate to the question its story raises and the discussion to a
      story that invites curiosity, paired with the guides in place (15 drafts each, the
      same packs, the verifier above): 10 aired against 11, the discussion's difference one
      draft's (16 lines of 20 rejected). On the desk's real shortlists (the eight freshest
      stories, as two lists of four), the discussion chose an idea or a work 6 times in 6
      over an arrest, a budget, a withdrawal and floods, without being told to; 5 of 6 aired.
    - **The loop learns how long its productions take** (found by this decision's review).
      The stage timings are the instance's guess, measured on a writer that does not think
      (`RADIO_STAGE_WRITER_SECONDS`, 12 s); a writer slot that thinks took 15 to 65 s, and the
      repository's half-hour simulation could not see it — it produces every programme in
      exactly its estimate. Replayed with the latencies measured: 59 s per half-hour of music
      alone while a programme was due (22 s had the long programmes written as fast as the
      short ones). The loop now adds the most its own productions ran past the estimate
      (`pacing.ran_late`, `StageTimings.lateness_s`), the news flash's estimate included:
      10 s per half-hour, and a writer that does not think produces exactly as before.
      Scaling the estimate by a programme's length was measured first and barely helped:
      the short programmes are most of the wait.
    - **Proven at runtime** (2026-09-28, the proof account, a fifteen-minute session with the
      dossier, the debate and the discussion alone, every programme checked): the opening,
      a dossier (237 s, anchor and expert), two discussions (246 and 210 s, three
      commentators each, two different stories); the ledger's `angles` set filed what was
      heard under each programme; 0.03 € for the session. The debate was refused by the model
      check, as it was in the two earlier runs: its speakers argue past what the article says
      — « a waiver at twelve is a signal », « someone judged she could keep up » — and the
      check is right to drop it (a stated limit below). Two earlier runs were stopped by the
      dev voice engine's DAILY quota (100 syntheses a day on its tier, one per line), not by
      the code.

40. **A listener's interests are a source of stories** (2026-09-28, owner decisions: the
    interests searched « with the listener's own Brave or Perplexity key, else a platform
    research slot »; every news programme in two versions, from the sources or from the
    interests). Each part was measured or proven on dev before it was kept.
    - **Searched with the listener's own key** when a session's loop starts, beside it (a task
      the session's parts own and cancel, which never raises): their strongest interests
      (`RADIO_INTEREST_TOPICS_MAX`, 5 since the amendment below, from the taste the start already read — none in
      company, none with the operator's interests capability off), each at most once per
      `RADIO_INTEREST_FRESH_SECONDS` (six hours; `radio:interests:{user}:{digest}`), their
      Brave key's news endpoint first (articles with their dates and outlets), else their
      Perplexity key (the articles its answer rests on — the client now hands back its
      `search_results`). Their key, their spend: never recorded as the platform's. Each
      search is one consultation on the radio's surface (`brave`, `perplexity`), `failed`
      when the service could not answer — the Brave client answers `None` on every error,
      and reading it as « nothing found » would have marked the topic searched and hidden the
      outage for six hours.
    - **Filed as stories**: normalised exactly as a feed item (`interests.interest_story`:
      the newsroom's canonical URL, bounded plain text, fingerprint, a date never later
      than when it was found; older than any programme may air, never filed) under the
      listener's interest row (`radio_feeds.kind = 'interest'`, one per listener at
      `INTEREST_FEED_URL`; migration `73f828799cdf`), each story with its own outlet
      (`radio_news_items.outlet`). The newsroom never reads that row (`feed_states`) but
      reads its stories' text like any other; the settings never list, count, rename,
      pause or remove it as a site, nor count its stories as a source's; the shortlists,
      the aired ledger, the article page and the retention read them unchanged.
    - **One material per programme, in turn**: a shortlist draws from the sources OR from
      the interests (`NewsCandidate.from_interests`, `read_news_desk(interests_first=)`),
      the sources first; once a programme of a format aired, its next turn goes to the
      other material — to whichever has stories when the other has none. A programme that
      did not air keeps its turn.
    - **The platform's research slot waits for the owner** (measured 2026-09-28 on dev,
      without Anthropic): through the platform's structured door, one path returned real,
      recent articles — a Responses-API model with the hosted `web_search` tool (4 topics,
      20 articles, all dated within the week, 17 reachable, 19 sites, 4 to 6 searches a
      call, 30 s); the instance's Perplexity key had no credit, and OpenAI's search models
      are refused by the Responses API or retired (`gpt-4o-mini-search-preview` answers
      404 while the catalogue lists it active). Every such search is billed PER CALL on top
      of the tokens, which no tariff of the platform records — the slot is not built until
      that fee is priced and traced like every other euro.
    - **Amended 2026-09-30 (owner review): one count, two bounds, no story bought for
      nothing.** Measured on dev 2026-09-29: 1 214 source stories in 48 hours, and four of
      the six stories a search had found fell past the 300 freshest the desk read — filed,
      paid for with the listener's key, and read by no programme; and the writer was told
      eight interests while the search looked up three. Now: ONE count
      (`RADIO_INTEREST_TOPICS_MAX`, 5) is applied once, where the start reads the interests
      (`read_taste(interests_max=)`, 0 with the interests capability off): the writer is
      told exactly the topics the search looks up. The desk reads the sources and what a
      search found under TWO bounds (`news_candidates(limit=, interests_limit=)`), the
      second the most the searches can file within its horizon
      (`interests.interest_stories_max`: topics × stories per search × (horizon ÷ freshness
      + 1), proven tight by a simulation), so no story a key paid for is cut while the
      interests stay the same — and 0 when the session holds no interest
      (`adapters.interest_stories_limit`): in company, with the capability off or with none
      left, what a search found earlier used to air anyway, voicing what the listener cares
      about. A Brave search asks for the desk's days (`interest_search.brave_freshness`,
      its custom `YYYY-MM-DDtoYYYY-MM-DD` range) instead of the week, whose older results
      were dropped unfiled.

41. **One journal, three editions** (2026-09-28, owner decision: « merge "for you" into the
    journal »; lot 4a of the 2026-09-27 spec). « Your day », « for you » and the evening recap
    were three programmes over ONE material, each with a rule of its own (the day ahead never
    after 18:00, the recap once and only five minutes into a session, « for you » one item at
    a time). They are one programme, the listener's JOURNAL (`RadioFormat.JOURNAL`), whose
    EDITION follows the listener's clock (`JournalEdition`, `journal_edition`;
    `JOURNAL_NOON_FROM_HOUR` 12, `JOURNAL_EVENING_FROM_HOUR` 18 — the station's evening music
    keeps that hour): the morning's day ahead and things to note (the day and the corner); the
    noon's what was done, then what is left (the day alone — a short edition never becomes a
    catch-all); the evening's look back — what was done, the day, the corner, then tomorrow and
    the rest of the week — over what EARLIER sessions said too (the recap's rule,
    `heard_this_session`). What each edition is made of is ONE table (`packs._EDITIONS`,
    asserted complete at import); the desk carries `done` and `ahead`, filled by the readers
    of lot 4b and empty until then.
    - **The grid calls it, the draw never does**: right after the opening (rule 3), and again
      once the session crossed into another edition — or once the journal has something to
      say, when it had nothing at the start (rule 5, `GridReason.JOURNAL_EDITION`). An
      edition's journal airs ONCE — the bound is per edition of the listener's LOCAL day
      (`grid._edition_of`: the date and the edition, so a session past midnight hears the
      next day's morning), a session bound the fill draw never relaxes — and two editions
      never come back to back: the format's own gap (600 s) replaced
      `RECAP_MIN_ELAPSED_SECONDS`. The clock marks come first: the noon edition waits for the
      twelve o'clock news.
    - **The edition is decided ONCE, from the programme's AIR time** (a programme is produced
      ahead of it), by the antenna, and read by the desk that chooses the facts and by the
      writer alike (`WritingRequest.edition` — required on the journal, refused on any other
      programme; the writer's guide names the three editions and CONTEXT says which). What
      the grid is offered (`Antenna.available`) reads the moment's edition.
    - **Read forgivingly where the three were stored, written nowhere**: a live session's
      slot or failure naming `my_day`, `for_you` or `recap` reads as the journal
      (`formats.read_format`, `LEGACY_FORMATS` — the grid then knows the edition had its
      journal, or that it rests); a stored frequency for one of them is dropped ENTRY by
      entry — in the settings, where one unreadable key used to reset the whole map, and in a
      live session's setup — never the listener's other choices (`formats.read_frequencies`,
      one reader for both). A format nobody knows stays a snapshot this release cannot read.
    - The settings publish `noon_from_hour` beside `evening_from_hour`, and the journal's
      hint states its three editions with those hours in the six languages. The news desk's
      reading moved to `news_desk.py`: the antenna stood one line under the size cap.
    - **What was done and what lies ahead have readers of their own** (lot 4b). The day and
      the corner stay decided by a fact's SOURCE; a draft names its part when it is one of
      the two others (`PersonalDraft.part`, `personal.JournalPart`), and `personal_facts`
      bounds every source PER PART and keeps ONE fact per record — the week ahead never
      retells an appointment the day already holds, because the « ahead » readers write the
      day's own key. Six « done » readers (`readers.DONE_READERS`): the appointments over by
      now (the calendar, through the briefing's own door; an all-day event is never done
      before its day is), the tasks ticked today (the provider's `completed` stamp, read on
      the listener's clock), the reminders that rang (the message each one left in the chat,
      `REMINDER_NOTIFICATION_MESSAGE_TYPE` — written by the scheduler and read here through
      ONE constant, visible rows only, declared in `message_readers`), the tickets closed
      today (the board's closed statuses on its own visibility predicate, the status
      change's instant), the e-mails sent (the sent folder's headers alone — `in:sent`,
      native on Gmail, a folder on Graph and IMAP; the message's own date decides the day),
      and what LIA did (the effect register's succeeded rows, named as every other surface
      names them — a NEW source, `actions`, with its own switch and its words in six
      languages). Three « ahead » readers (`AHEAD_READERS`): the appointments, the open
      tasks due and the pending reminders from tomorrow to seven days on. The day source
      reads them for the editions the desk may be asked before it is read again — the
      edition of now and the one at the end of its time to live (`ListenerDay.parts_due`) —
      so a journal produced two minutes before noon holds what was done this morning; a
      source read for two parts is recorded ONCE, `failed` when any read of it failed; a
      missing connector is nothing to read, refused credentials a failure
      (`ConnectorAccessError`). The radio's consultation surface gained the sections
      `agenda`, `tasks`, `mails`, `reminders` and `actions`.

    - **A cold dashboard cache is not an empty personal day** (2026-09-28).
      Measured on dev: the journal was enabled and public mode off, but every briefing
      section was absent from Redis. The antenna read only that cache and therefore
      offered no journal. It now reuses the briefing's section readers and TTLs through
      `read_selected_cards`, fetching missing sections under the radio's own source
      selection, independently of dashboard visibility. Unselected sources are never
      opened; warm and legitimately empty sections are reused. Live reads join the
      session's consultation register, once per source across the journal's parts,
      and stay under its spend tracker; error sections never voice stale data. The
      briefing's cache-only API remains cache-only for callers that need that contract.

## Consequences

- A listener starts the radio — under the name they gave it — from the header, the logo
  menu, the home page (right above « My dashboard ») or its page; the first voice comes after the
  opening's production (announced), the station's music fills every gap until the stop —
  which a pause holds back —, and what the session has spent is on the bar while it
  spends, beside what the listening planned will cost. Under the programme, the session's
  articles open whole in the listener's language. When LIA writes to them in the chat,
  the station breaks in with a news flash and goes back to the programme where it
  stopped; a station with nothing more to say plays its music rather than stopping.
- Five programmes take an ANGLE on the news — the analysis, the editorial, a dossier, a
  debate, a discussion between the station's commentators — and may come back to a story
  the listener heard, saying so; the headlines, the bulletin, the brief and the figure only
  bring what was never heard.
- A listener who connected their own Brave or Perplexity key hears news programmes drawn in
  turn from their sources and from their interests.
- Every euro of a session is on its run's row — the writer's, the analyst's and the
  verifier's tokens, the headlines it was the first to embed, and the voices — and
  counts in the listener's ceilings and in the radio's own budget (2 € over any 24
  hours, translations included); the newsroom costs no model. The session, and each article translated on opening, is one
  row of the decision register under that run; its reads are the listener's
  consultations.
- An operator switches the radio off and, from the next newsroom tick, no stranger's
  server is read; a session already on air ends by itself (the idle rule); the
  listener's settings and sites stay.
- Stated limits, not discovered ones: the first session after a week of silence airs
  without news until the next newsroom pass (≤ one interval); a worker stopped
  mid-segment cancels the calls in flight, and what a vendor billed for a request whose
  answer never arrived is not recorded (the hard-kill limit of ADR-263); the audio's
  writable layer assumes ONE API container (the leader's sweep sees its own filesystem);
  two starts of one account in the same instant are both admitted until the first
  loop's next tick; a Gemini TTS answer without audio is counted and logged, not
  ledgered, until one is observed; the meeting recorder's bar uses the same muted-text
  pattern the axe scan flagged on the radio's (not scanned, not changed here); a TTS
  model's per-minute quota is the vendor's and was not measured — eight concurrent
  syntheses passed on the 2.5 preview, and a start voices about fifteen lines in its
  first seconds; an article of exactly `ARTICLE_MAX_CHARS` characters reads as cut (the
  page then points to the outlet for a rest that is not there); a translation the edge
  proxy cuts past 100 seconds reaches the page as an error it offers to retry — the
  translation, finished meanwhile, is then read from the cache; a flash airs 15 to 30 s
  after the notification (the poll, then its production); a notification whose words
  flatten to nothing is not told, and three such in a row right after the watermark
  would hold the flash source for the session (no writer sends one today); an account
  that heard everything the station holds plays music until the newsroom brings
  something (measured on the proof account after five sessions in half an hour); a
  development told under a headline this close to one heard (a toll that rises) is
  left out with it, for as long as the ledger remembers; the verifier still rejects
  about one supported opinion in five on the slot's current model, and a column
  in four is refused for it — another model on the `radio_verifier` slot would be
  measured with the same fixed set; the budget counts a run whole while its last spend
  is in the window, so a session begun before it counts in full and the bound lifts a
  little later than a per-call count would say, and what was already under way when the
  bound was crossed still airs (it is asked before each production); a line counts as
  heard once the player passed its start; a source's counters are the stories of the
  window its programmes air from, and « never heard » is exact — an article left out for
  telling an event already heard (decision 34) still counts as never heard; forgetting what
  was heard leaves a session on air with its own memory until it ends; the discussion talks
  from headlines and summaries (no analyst reads the article it chooses among four), so its
  speakers bring views rather than details, and a shortlist of four grave stories was not
  measured; a writer that thinks at length still stops at 16 000 tokens on some dossiers (2
  of 30 measured: a refusal, ADR-275 — the format rests); the view test lets about half the
  unsupported claims of an opinion through; a session learns its productions' time only once
  one has finished, so the first two are made on the instance's guess, a loop taken over
  learns again, and one late production raises every later estimate of the session (a
  writer that thinks: 155 s of audio ready ahead on average, against 108, discarded if the
  listener stops); a listener without a search key of their own has no interest stories
  until the research slot exists (decision 40); the interests are searched when a session
  starts, so its first programmes draw from the sources; a search's stories wait for the
  newsroom's next pass for their full text, so the analysis, the dossier and the debate
  take them only once it was read; the debate is refused by the model check more often
  than it airs (every live debate on dev, one draft in six of the measured set): a refused
  debate is a programme not aired and a format that rests, never a failure; with a
  listener who enabled only the angle programmes, the grid's fill pass may air the same
  one twice in a row rather than leave the music alone.

## Alternatives rejected

- **The discussion read from the analyst's points** (decision 39): the story would be chosen
  before the writer, which chose an idea or a work over grave news 6 times in 6.
- **Amended writer guides; a verifier clause for words about the conversation** (decision
  39): measured, neither did better.
- **A writer estimate scaled by the programme's length; a learnt lateness that forgets**
  (decision 39): scaling barely helped; forgetting (the 80th percentile of what was seen, a
  moving average) kept the listener waiting 15 or 31 s per half-hour against 10, for 20 or
  33 s less audio ahead.

- **Scheduled editions** (the owner's Q8): produced for nobody when nobody listens; the
  antenna runs only while someone does.
- **One antenna shared between listeners** (Q1): the day it speaks of is one person's.
- **A third-party music stream** (onlyai.fm, read 2026-09-26): no licence to
  listeners, `/media/audio` disallowed by its robots.txt, songs with vocals, no CORS
  (no duck through Web Audio, and none on iOS by `volume`).
- **A server-sent stream for the player**: every report is already answered with the
  session's state, and one audio element fetching blobs keeps the autoplay rule and the
  CSP (`media-src` allows `blob:`, not the API's origin).
- **A `SchedulerLock` around the newsroom pass**: its TTL either throttles the job or
  expires under a long pass; a bounded pass on the leader needs neither.
- **A boot stamp for the stall alert**: every recycled worker would reset the age of a
  stalled newsroom.
- **The verifier quoting what it rejects, and a rule reading the quote** (decision
  34): measured without effect, and a rule that drops a true rejection whenever a
  model quotes loosely. A « specific » opinion read from capitals and digits was not
  tried: German capitalises every noun, Chinese has none, and « Lavrov a démissionné »
  has neither a digit nor a doubt.
- **The radio's voice chosen in its own settings, with the prices** (the owner's first
  idea, 2026-09-27, withdrawn the same day: it would complicate the settings, and
  the engine stays the administrator's choice); the budget bounds the spend instead.
- **A run counted at its first spend** (decision 37): a session begun before the window
  would leave it while it still spends, and the bound would no longer hold over every
  24 hours.
- **Headline and summary embedded together** (decision 34): measured, they separate
  one event from two worse than the headline alone.
- **The headlines' vectors computed by the newsroom**: a model in the newsroom
  (decision 1), paid by nobody's run; the antenna embeds what a listener's desk
  meets, and shares it.
- **Container queries for the nav's labels** (shown exactly when they fit): no precedent
  in the codebase and a layout subtler than the defect; the breakpoint moves, the widest
  breakpoint gains the room it lacked, and a spec with every control holds it.
