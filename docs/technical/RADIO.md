# Radio LIA — technical reference (ADR-324)

A personal radio station, on demand, in the listener's language: their day and
the world's news, written, checked and voiced for them while they listen, and
never produced for nobody. Decisions and measurements live in
[ADR-324](../architecture/ADR-324-A-Personal-Radio-A-Grid-Decides-Models-Only-Write.md); this page says how the
parts fit.

## Two tiers

| Tier         | Scope                                                                                                      | Cost                             |
| ------------ | ---------------------------------------------------------------------------------------------------------- | -------------------------------- |
| **Newsroom** | the instance: reads public feeds (catalogue + the sites listeners added), stores items and their full text | no model, no per-person cost     |
| **Antenna**  | one listener's session: decides, writes, checks, voices and mixes one segment at a time                    | billed to the listener (ADR-272) |

The antenna runs only while someone listens: a session ends when the player
stops reporting, stays paused too long, the timer's farewell has aired, a
ceiling refuses the next production, or productions keep failing — a programme
the station chooses not to air (nothing to say, a script its editor refused) is
no failure (decision 33).

## Modules (`apps/api/src/domains/radio/`)

| Module                                                            | Role                                                                                                                                                            |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `formats.py`                                                      | the formats, their material, roles, durations, frequencies, and the music mood under each (`music_mood`)                                                        |
| `grid.py`                                                         | the deterministic running order (pure)                                                                                                                          |
| `session.py`, `programme.py`, `pacing.py`                         | the session's state machine, planned slots, lookahead                                                                                                           |
| `orchestrator.py`                                                 | one session's loop, the single writer of its state                                                                                                              |
| `runner.py`                                                       | runs loops in a worker under a lease (`held_claim`), stops them at shutdown                                                                                     |
| `service.py`, `view.py`, `schemas.py`                             | the doors (start, report, stop, audio) and their wire shapes                                                                                                    |
| `router.py`, `errors.py`, `listener_settings.py`                  | the routes, their coded refusals, what a settings write checks                                                                                                  |
| `adapters.py`, `wiring.py`, `settings_view.py`                    | the ports on the platform (account, slots, voices, ledger), one radio per worker, the settings as the pure modules take them                                    |
| `jobs.py`, `consultations.py`                                     | the newsroom pass and the media sweep; the reads filed on the `radio` consultation surface                                                                      |
| `live_store.py`, `codec.py`, `aired.py`                           | Redis state: session record, inbox, published state and segments, the aired ledger (what a listener heard, across sessions, and what each angle programme took) |
| `articles.py`                                                     | the radio page's article: the text the newsroom kept, translated on opening, once per story and language                                                        |
| `setup.py`, `setup_builder.py`, `preferences.py`, `options.py`    | the frozen per-session setup, the listener's settings, what settings may offer                                                                                  |
| `sources_view.py`, `names.py`                                     | what each source holds for the listener (pure); the character rules of a name the station says (the station's, a site's)                                        |
| `interests.py`, `interest_search.py`                              | the listener's interests as stories: a search result filed as a feed item (pure), searched with the listener's own key when a session starts                    |
| `budget.py`                                                       | the listener's radio's own rolling-day bound                                                                                                                    |
| `antenna.py`                                                      | one slot's segment: desk → pack → write → check → voice → mix                                                                                                   |
| `news_desk.py`                                                    | every news format's shortlist, the stories an angle comes back to, the exhausted desk (pure; read off the loop)                                                 |
| `flash.py`                                                        | a news flash: when LIA writes to the listener, the station breaks in (pure; out of the running order)                                                           |
| `packs.py`, `editorial.py`, `facts.py`, `personal.py`             | what a segment may say: facts, packs per format, news shortlists, the listener's material                                                                       |
| `meanings.py`                                                     | two headlines of one event, read by meaning: the relation, and the headlines' vectors every listener shares                                                     |
| `day_source.py`, `readers/`                                       | reading the listener's day and personal corner, and — for the journal's noon and evening editions — what was done today and what lies ahead                     |
| `prompting.py`, `writing.py`, `analysis.py`, `checking.py`        | the three model calls (writer, analyst, verifier)                                                                                                               |
| `script.py`, `verification.py`, `numbers.py`                      | the writer's answer, the deterministic editor, how a figure compares across languages and units                                                                 |
| `production.py`, `delivery.py`, `cast.py`, `audio.py`, `media.py` | voices, delivery, the voice-only mix, session audio files                                                                                                       |
| `newsroom/`                                                       | catalogue, safe fetch, robots.txt, parsing, full text, collector, site discovery                                                                                |

## A session's life

1. **Start** (`POST /radio/sessions`): the listener's profile, settings, taste
   (unless in company) and the engine's voices compose a frozen `RadioSetup`
   (`setup_builder.compose_setup`); the state is published BEFORE the record,
   and a new start replaces the account's previous session (its loop stops at
   its next tick).
2. **Loop** (`runner.RadioLoopLauncher`): one worker holds the session's lease
   and runs `orchestrator.run_session`: every tick it reads the player's last
   report, plans the next slots with the grid, and starts a production when the
   audio ready ahead no longer covers the next production's expected time — and,
   when the next segment is shorter than the production that follows it, that
   one's too (one production in flight once the listener hears the antenna).
   The stage timings are the instance's guess: the loop adds the most its own
   productions ran past them (`pacing.ran_late`, `StageTimings.lateness_s` —
   decision 39: a writer slot that thinks takes several times what one that does
   not takes).
   Before the first sound, the first two slots are produced at once. The
   farewell is planned only inside the sign-off window (`SIGN_OFF_WINDOW_SECONDS`
   before the stop); when nothing else fits before it, NOTHING is planned and the
   station's music plays — the grid is asked again at every tick. Before the
   farewell is produced it is confirmed on the real running order (projections
   use target durations, which real segments run well under): one that would air
   before the window is withdrawn (`ActionKind.WITHDRAW`) and planned again later.
   A format whose production failed rests (`FAILED_FORMAT_REST_SECONDS`, or its
   own minimum gap when longer) — even under the fill and clock rules; the
   opening and the farewell are exempt — and its slots planned before the
   failure leave with it (one already in production finishes). Only a FAILURE
   counts toward the stop (`RADIO_FAILURES_MAX` in a row): nothing to say or a
   refused script comes back as `NothingAired`, rests its format the same way,
   and never ends a session — the station plays its music instead.
   The fill draw may relax spacing, brief density and clock reservations when
   normal rotation has no candidate, but always chooses a different programme
   format when one is eligible. Repeating the previous format is the last
   resort; availability, listener choices, the cast, the timer, edition bounds
   and failed-production rests still apply.
3. **Production** (`antenna.Antenna.produce`): the desk (the listener's day and
   corner, the news shortlists, what they already heard) is read at most once
   per `desk_ttl_s`; the slot's pack is built; the writer writes; the
   deterministic verifier repairs, drops or refuses; the model verifier reads
   the formats the listener chose; each line is voiced (in parallel, billed);
   the lines are joined with their pauses and loudness-normalised (voice alone —
   the music is the player's); the segment is published.
4. **Listening**: the player plays one segment after another over the station's
   music — continuous from the first answer to the farewell, in the mood the API
   names, lowered under every voice — and reports its position; each report is
   answered with the session's state. The timer counts LISTENING time: a report
   says `paused` when the listener paused (never inferred from `playing: false`,
   which is also the music between two segments), the stop moves while the pause
   lasts (`session.effective_stop_at`, published as `stop_at`) and resuming
   extends it by the pause. Between two programmes the station's music plays
   alone for `segment_gap_s` (`RADIO_SEGMENT_GAP_SECONDS`, fixed when the session
   starts, counted by every projection of the running order — decision 36); a
   news flash never waits for it.
5. **End**: the loop ends on its reason; the audio of a session nobody will
   finish (the listener stopped, nobody listens) is discarded at once; a
   session that ended on its timer keeps its audio for the player to play its
   queue out — the server closes when the farewell is PRODUCED, the player when
   it has been HEARD — and the orphan sweep removes it afterwards.

## The news flash

When LIA sends the listener a proactive notification while their radio is on,
the station breaks in (ADR-324 decision 32). Every `RADIO_FLASH_POLL_SECONDS` the
loop reads what was archived after its watermark (the session's start, then the
newest note a flash took) through the notifications reader, oldest first, at most
`FLASH_NOTES_MAX`; one flash at a time, only while the listener hears the antenna
(never before the first sound, while paused, or once the farewell is planned), never
in company or with the notifications switched off for the radio (no source at
all), never past a spending ceiling. A flash lives OUTSIDE the running order: its
place is numbered from `FLASH_SEQ_BASE`, the grid never plans one, and the answer
names it apart (`flash`). Its script breaks in, says what LIA wrote, and hands
back — naming only what will be true when it airs: the programme it cuts only
while more of it is left than the flash takes to produce (the loop's own
estimate), the next one only once it is ready, else general words. A notification
airs once — by a flash or by the corner (`facts.notification_key`): a note already
heard is not flashed, and the notes a flash tells are held from the corner while it
is produced. A flash that could not be produced is not tried again (nor one whose
production died with a worker: `orchestrator.reloaded` drops it); its notes stay in
the chat. A message or an image a connection sent through LIA is theirs, not LIA's:
the reader leaves it out (`peers.RELAYED_MESSAGE_TYPES`, decision 34), for the flash
and the corner alike.

## What a segment may say

A segment's `FactPack` holds one material (personal, news or neutral: the
clock and the weather). Every fact has an id, a kind, who may say it and its
source; the writer may state nothing else.

**Line kinds** decide what a line must cite: `fact` (a non-analysis fact),
`analysis` (an analysis fact — the expert), `opinion` (a commentator's view on
the story it cites — the editorialist's, or a speaker's of a debate or a
discussion, `OPINION_ROLES`), `transition` (structure; it may count its own
programme up to a small integer, nothing more).

**The deterministic editor** (`verification.verify_script`) repairs what is
mechanical — whitespace, titles, refs, part order, a date or time said without
citing the clock, a station format written all over its music, the stories past
the format's `stories_max` (the first told are kept; the facts one line cites
together are one story; a repair never counts against the segment) — drops a line
that cites nothing it needs, an unknown fact, a number no cited fact states
(canonical digits across conventions; the cited outlet's name counts), a quote
past the fair-use bound, a guest voicing the person, an opinion in a voice that
is not a commentator's; and refuses a segment with no body, one far past its length, or one
that lost more than a quarter of its sourced lines. A fact line resting on the
analyst's points of ONE story alone also cites that story's own fact
(`_with_story`): the anchor tells the article's details, which live in the points,
and half its fact lines cited them alone, even when told not to (decision 34).

**The model verifier** (`checking.py`, optional per listener: off, news, all)
applies two tests by kind: the strict test to facts, analyses and transitions
(nothing beyond the cited facts, nothing said about the listener that no fact
states), the view test to opinions (a commentator's judgement, images,
figures of speech and replies to another speaker are theirs; supported unless a
specific claim — who, what, how many, what will happen and how certain, how the
source presented it — is missing from the facts). It compares meanings, not words, a framing (« in the
editorial, from » an outlet) covers nothing but itself, and each verdict states what
the cited facts hold about the line's specific statements BEFORE deciding
(`LineVerdict.evidence`). Its verdict drops lines under the same refusal rules.
A change to its prompt is measured on a FIXED set of labelled scripts with planted
claims, never on rounds that write new scripts each time (decision 34: 31 % of the
supported lines rejected before, 12 to 16 % after, every planted claim caught;
decision 39, the view test on 145 lines of editorials, dossiers, debates and
discussions: 13 % of the supported lines rejected where the column test rejected
22 %, 51 % of the unsupported caught where it caught 58 %).

**Renew or take an angle** (decision 39, `FormatSpec.renews_subjects`). The
headlines, the bulletin, the brief and the figure bring what was never heard. The
analysis, the editorial, the dossier, the debate and the discussion take an angle
on ONE story and may come back to a story heard: its fact is marked
(`RadioFact.returning`, « heard before » in the writer's FACTS), and only such a
programme may take a story its ALREADY HEARD block lists. An angle never takes the
subjects of the programme just before it (`antenna._told_at`: what each place
told, the last `TOLD_KEPT_SLOTS`, a flash excepted) nor one its own type already
took (the ledger's `angles` set, `AiredLedger.treated`). The discussion's writer
chooses its story among four; the dossier and the debate read the analyst's
points on theirs, like the analysis.

## Editorial sources without commercial pitches

Radio programmes leave out advertising, sponsored or commercial partnerships,
sales, shopping deals, discount codes and commercial offers. The
[shared content policy](../../apps/api/src/domains/shared/commercial_content.py)
recognises explicit disclosures and sales pitches, and removes advertising
paragraphs from otherwise useful excerpts. An economic report, a scientific
partnership or a professional promotion remains editorial information.

These checks run before feed items, interest-search results and unread mail fill
their selection limits. The shortlist also checks previously stored news and
custom feeds. News reads and the mail scan remain bounded. Radio's mail mode
uses a separate cache and fallback namespace; the dashboard's ordinary mail
cards retain their existing behaviour and the unread count describes the fetched
messages before commercial filtering. Transactional mail and editorial newsletters
retain their useful content while commercial inserts are left out.

The existing writer, analyst and verifier prompts carry the same policy for
mixed or less explicit content. No extra model call is introduced to classify
commercial sources. These rules combine explicit source signals with that
semantic policy; a keyword alone does not prove that every article mentioning
a partnership or a reduction is advertising.

## The listener's material

Two parts, decided by the source (`personal.py`): the **day** (appointments,
reminders, tasks, commitments, tickets, birthdays, unread mail, the weather)
and the **corner** (health, meetings, notifications, people gone quiet,
knowledge spaces, kept answers, the conversation under way).

**The journal** (ADR-324 decision 41) is the one programme that tells them, in the
edition of the moment on the listener's clock (`formats.JournalEdition`,
`journal_edition`; `JOURNAL_NOON_FROM_HOUR`, `JOURNAL_EVENING_FROM_HOUR`): the
morning's day ahead and things to note (the day, then the corner); the noon's what
was done, then what is left (the day alone); the evening's look back — what was
done, the day, the corner, then tomorrow and the rest of the week — over what
earlier sessions said too. What each edition is made of is one table
(`packs._EDITIONS`); the desk's `done` and `ahead` parts are filled by lot 4b's
readers. The grid calls it after the opening and once per new edition of the local
day (never twice in one, never back to back with the previous edition's, never by
the draw); the antenna decides the edition ONCE from the programme's air time and
hands it to the desk and to the writer (`WritingRequest.edition`). The former
`my_day`, `for_you` and `recap` are read as the journal where a live session stored
them (`formats.read_format`) and their stored frequencies are dropped entry by
entry (`formats.read_frequencies`).

**What was done and what lies ahead** are parts of their own (`personal.JournalPart`,
`PersonalDraft.part`; the day and the corner stay decided by the source): six « done »
readers (`readers.DONE_READERS` — `agenda.py` the appointments over by now, `tasks.py`
the tasks ticked today, `reminders.py` the reminders that rang, read from the message
each one left in the chat under `REMINDER_NOTIFICATION_MESSAGE_TYPE`, `tickets.py` the
tickets closed today, `sent_mail.py` the e-mails sent from the sent folder's headers
(the `sent_mails` source, independently switchable from unread `mails`),
`actions.py` what LIA did from the effect register — the `actions` source, with its own
switch) and three « ahead » readers (`AHEAD_READERS`: the appointments, the open tasks
due and the pending reminders from tomorrow to seven days on, under the day's own keys,
so `personal_facts` — one fact per record, every source bounded per part — never lets
the week retell what the day holds). The day source reads them for the editions the
desk may be asked before it is read again (`ListenerDay.parts_due`: the edition of now
and the one at the end of the desk's time to live), records a source once whatever the
parts it read for (`failed` when any read of it failed), and treats a missing connector
as nothing to read and refused credentials as a failure. The radio's consultation
surface gained the sections `agenda`, `tasks`, `mails`, `sent_mails`, `reminders` and `actions`.

- The sources the Today Briefing carries reuse its readers and cache through
  `BriefingService.read_selected_cards`: a cold or expired section is fetched without
  requiring a prior dashboard visit. The radio selects its own enabled sources before
  any cache or source read; dashboard display preferences do not hide radio sources.
  Cache hits (including empty days) open nothing. Live reads are recorded once per
  source under the radio session, together with the other parts' reads; a failed
  section never voices its stale payload. Costs stay on the session's tracker.
- The seven others are read by `readers/` (one table, `OWN_READERS`, asserted
  complete at import), concurrently, each on its own short session (ADR-304);
  what they opened is recorded on the radio's consultation surface.
- A source the listener switched off is never read; in company only the
  weather is. Setting the journal's frequency to `off` also prevents all
  personal journal reads, while keeping weather for the opening and the
  independently configured notification flashes.

**Taste** (`readers/taste.py`, `prompting.ListenerTaste`): active interests and
remembered preferences reach the WRITER as context, never as facts — shown
only to the formats that choose news, above the prompt's dynamic marker. The
interests read are ONE count, `RADIO_INTEREST_TOPICS_MAX` (0 with the interests
capability off): the writer is told exactly the topics the search looks up.

**Heard, never offered**: a segment remembers the facts its voiced lines cite
(`ProductionResult.aired`, `antenna.heard_facts`), so a story the writer left
out stays on the desk. The HEADLINES of the stories heard (`antenna.aired_headlines`
— never a programme's title, which names one or two of a bulletin's six stories)
reach the next news writer in its `ALREADY HEARD` block (fenced: strangers
wrote them), in this session and the ones before it over two days, and a story
that block lists is never told again — from another outlet, another article or
another angle: a key and a fingerprint cannot tell that two articles tell one
event, the writer can. What words can decide is decided before the writer: an
article whose headline shares at least 60 % of its words — and at least three —
with a headline heard, or with one already chosen for the programme, tells the
same story and is not offered (`editorial.same_headline`, articles and
prepositions left out; a headline written without spaces is matched by its
fingerprint alone). What MEANING can decide is decided there too (decision 34,
`meanings.py`): an article whose headline is at least `RADIO_SAME_EVENT_SIMILARITY`
(0.9, cosine) close to one heard or chosen tells the same event. The vectors are the
platform's embeddings of the headlines, computed by the ANTENNA the first time a
desk meets a headline — billed to that listener's run, never by the newsroom — and
shared through Redis (`radio:headline:{model}:{dimensions}:{sha256}`, as long as
a story may air). A blind reading leaves the words to judge and rests until the
desk is read again; 0 turns the reading off and embeds nothing. Every language fills
the desk (decision 38): a gathering reads the stories never heard first, so its bound
keeps what can still air; a story meets only the heard headlines it shares words with
(`editorial._Told`) and every meaning at once (`HeadlineMeanings.told_among`); and the
desk is read off the event loop (`news_desk.read_news_desk`).

**Each programme its own data.** Within a session: the clock fact reaches only
the opening (now) and a programme announced for a clock mark (that mark); the
weather is said once — held by a production in flight (`packs.SAID_ONCE_KINDS`), so
the two productions of the start never both carry it; the journal's evening edition
leaves out what this session already said; an analysis of a story is read once per session
and reused. Across
sessions, the aired ledger (`aired.py`, five sorted sets per account under
`radio:aired:{user}:personal|news|fingerprints|headlines|angles` — the last one
`{format}:{k|s|h}:{value}`, what each angle programme took) dates every member: a
story's keys, its fingerprint and its headline are remembered as long as a news
format may still air it (`NEWS_MAX_AGE_S`, 48 h — the oldest a shortlist reads),
a fact of the person's day for a day; each member leaves on its own date, trimmed
at the next write and filtered at every read. The ledger holds what was HEARD
(decision 35): a produced segment carries, line by line, what each voiced line tells
(`aired.HeardLine`, published as `ProducedSegment.memory`, never sent to the player),
and the loop files a line once the player's report has passed its start
(`orchestrator._file_heard`). A programme produced ahead of a session stopped early,
or skipped, files nothing; a flash is filed once `flash_heard` covers it; a loop taken
over files what its predecessor had not (`read_ready`). The newsroom files a story only when it is
younger than what it keeps (`collector._kept_since`, the purge's own line): a
feed keeps listing stories the purge removed, and they came back « new ».

## The listener's interests

A news programme draws from the sources OR from what a search found for the listener's
interests (ADR-324 decision 40). When a session's loop starts, its parts launch one
refresh beside it (`interest_search.refresh_listener_interests`, a task they own and
cancel): the interests the start already read (`RADIO_INTEREST_TOPICS_MAX`, the same ones
the writer is told — none in company, none with the operator's interests capability
off) are searched with their OWN key — their Brave key's news endpoint over the desk's
days (`brave_freshness`: a custom day range, never the week whose older results were
dropped unfiled), else their
Perplexity key (the articles its answer rests on, `search_results`) — each at most once per
`RADIO_INTEREST_FRESH_SECONDS` (`radio:interests:{user}:{digest}`: the topic is never a
key's text). Their key, their spend, never recorded as the platform's; each search is one
consultation on the radio's surface (sections `brave`, `perplexity`), `failed` when the
service could not answer — a Brave client's `None` is a failure, never « nothing found ». A
refresh never raises: its stories reach the desk at its next reading.

What a search found is normalised exactly as a feed item (`interests.interest_story`: the
newsroom's canonical URL, bounded plain text, fingerprint, a date never later than when it
was found; a story older than any programme may air is not filed) and filed under the
listener's interest row (`radio_feeds.kind = 'interest'`, at `INTEREST_FEED_URL`, one per
listener) with its own outlet (`radio_news_items.outlet`). The newsroom never reads that row
but reads its stories' text like any other; the settings never list, count, rename, pause
or remove it, nor count its stories as a source's; the shortlists, the aired ledger, the
article page and the retention read them unchanged.

The desk reads the sources and what a search found under TWO bounds
(`news_candidates(limit=, interests_limit=)`): the sources' `NEWS_CANDIDATES_READ_MAX`, and
the most the searches can file within the desk's horizon (`interests.interest_stories_max`,
`adapters.interest_stories_limit`) — measured on dev 2026-09-29, a shared bound left four
of six such stories past 1 214 source stories, paid for and heard by nobody. A session
holding no interest (in company, the capability off, none left) reads none of them: what a
search found earlier would voice what the listener cares about.

Each format's shortlist draws from ONE material (`NewsCandidate.from_interests`,
`news_desk.read_news_desk(interests_first=)`): the sources first; once a programme of a
format aired, the format's next turn goes to the other material — to whichever has stories
when the other has none. A programme that did not air keeps its turn.

## The newsroom

- **Catalogue** (`newsroom/catalogue.py`): feeds measured live, each with its language —
  every one airs, translated into the listener's; a listener unticks one by its address
  (`disabled_feeds`, decision 38).
- **Collector** (`newsroom/collector.py`, scheduler leader): due feeds read with
  conditional requests and exponential back-off, items stored once, full texts
  fetched per outlet in series; each feed and each article is its own unit (one
  refusal never stops a pass). It reads the catalogue while anyone started a session
  within `RADIO_NEWSROOM_LISTENER_WINDOW_SECONDS`, and a listener's own sites while
  they did (`radio_preferences.last_listened_at`, filed at every start) — never a site
  they paused. A pass reads at most `RADIO_NEWSROOM_FEEDS_PER_PASS` due feeds (60).
  Every entry in an accepted feed body is examined, regardless of feed order;
  only stories published within `RADIO_NEWSROOM_RETENTION_SECONDS` are stored
  (48 h by default). Large inserts are batched. `RADIO_NEWSROOM_FEED_MAX_BYTES`
  bounds the entire decoded feed body (4 MiB by default); a larger body is
  rejected, and `RADIO_NEWSROOM_TEXTS_PER_PASS` bounds article-page downloads.
- **Safe fetch** (`newsroom/fetch.py`): every hop validated against private
  addresses, bodies bounded (decoded bytes), `https` only.
- **robots.txt** (`newsroom/robots.py`): honoured for feeds and pages; an
  unreadable one is a refusal for an hour — and, to the settings, « the site
  does not answer ».
- **A listener's site** (`newsroom/sources.discover_feed`): the address, else
  the feeds its page advertises, else the conventional paths; the feed found is
  described before it is added, and looked for again when it is.

## Audio

Voice families say how a provider bills (free, characters, tokens) and what a
line's delivery can ask of it; the cast gives each role a voice. A line whose
synthesis fails TRANSIENTLY (`TTSProviderError.transient`: the code and the
recorded status, never the message) is tried again, up to `tts_attempts`, through
`retry_async`; only the attempt that returned audio is billed. A rate limit
(`TTSProviderError.rate_limited`: the code or a 429) waits what the provider
asked (`Retry-After`), else 5 s doubling at each attempt, never more than
`RADIO_TTS_RATE_LIMIT_WAIT_MAX_SECONDS` — and the wait is SHARED by the
segment's lines (one cooldown, honoured inside the concurrency gate), so the
lines voiced in parallel stop knocking together. A delivery
control is sent only to a model measured to take it (`voice/families.controls_for`:
the Gemini 2.5 and 3.1 previews refuse any style annotation). A segment is the
voice alone: a short breath before the first word (the player lowers the music
over it), a pause after each line, a longer one between parts; the mix is
planned purely (`audio.plan_segment`) and run through the bounded ffmpeg runner.

For headerless PCM and u-law, the client declares a `RawAudioSpec` at its
configured rate. [Audio preparation](../../apps/api/src/domains/voice/audio_output.py)
wraps the samples unchanged in WAV before ffprobe; encoded responses pass
through unchanged and the segment retains its single final MP3 encode. Billing
precedes this wrapping. An incomplete raw sample sequence returned by the client
is refused at this boundary without another synthesis; validation inside the
provider client keeps its existing retry behaviour. The optional metadata protocol
leaves clients whose responses already have a container on their existing path.
Cancellation before the mix is published removes its partial MP3 and propagates;
line files are cleaned by production, and a pre-existing final file is left intact.

Radio keeps its existing segment player and cast of voices. The personal Simli
[speaking-avatar integration](SPEAKING_AVATAR.md) covers comments and Live audio;
it does not route Radio programmes through one face or create another synthesis.

## The station's music

Four moods — `morning`, `news`, `evening`, `calm` (`formats.MusicMood`): news is
read over the news music at any hour, everything else follows the listener's
clock (morning from 05:00 to noon, evening from `JOURNAL_EVENING_FROM_HOUR`, calm
otherwise). Every segment and the session itself carry their `mood` on the wire
(the session's is that of what airs next; null when the listener's clock cannot
be read, and the player then plays calm music, never silence).

The library is a dozen instrumental tracks per mood, about two minutes each,
generated once with Lyria 3.5 by `scripts/assets/generate_radio_music.py` and
committed under `apps/web/public/radio/music/<mood>/` with their provenance
(`PROVENANCE.json`: prompt, model, hashes, measured loudness) and the player's
manifest (`apps/web/src/data/radio/music-library.json`). A song whose text part
carries words was refused at generation (Lyria returns lyrics there; section
markers only when nothing is sung); every kept track is silence-trimmed,
loudness-normalised in two passes to −18 LUFS (measured: −18.7 to −18.3 across
the 48) and faded out. `tests/unit/domains/radio/test_music_library.py` holds
the library to the moods and every file to its hash.

## The player

`apps/web/src/lib/radio/`: a controller (plain class, tested without React)
over the voice element and the station's music (`music-bed.ts`: two decks
crossfaded, a shuffled bag per mood, one master level lowered under every
voice; `web-audio.ts` routes both decks through Web Audio — iOS ignores an
element's `volume` — from this origin's files). The permission to play is taken
inside the click for the voice and the music; the music starts with the first
answer, which names its mood. Segments are fetched as blobs through the API
client (`media-src` allows `blob:`); a report every few seconds and at every
boundary; a session the API opened after the listener pressed stop is stopped
at once.

Playback permission is acquired synchronously within the start gesture using
a cached silent stereo WAV (0.1 s, 8 kHz, PCM8). Its two channels match every
shipped music track, keeping the Web Audio decks on the same channel layout
when music replaces silence. A completed priming play pauses only if its
silent source is still selected; a late completion cannot pause a new segment.

**A news flash** is not queued: its audio is fetched as soon as an answer names
it, and it airs the moment it is ready — cutting the programme on air, which
resumes from the position where it stopped (`playSegment(url, startAt)`: the
element seeks), or before the next one between two programmes. While it airs the
reports name the programme it cut, frozen; once it ended every report carries
`flash_heard`. An answer names the waiting flash anew each time, as a new object:
the player tells flashes apart by their number, never by identity, and a flash
fetched while the listener paused keeps its audio for the resume.

Every asynchronous player operation belongs to its session's abort signal:
starting, reporting, fetching audio, playing and resuming a flash. After stop,
a late success or failure cannot touch a later session, even while that new
session is still starting. A late successful start is closed on the server.
An old advance cannot clear the new session's pending advance.
A browser refusal to resume leaves the same programme paused for another
gesture; it neither skips the programme nor escapes as an unhandled rejection.

Where it shows — all behind ONE predicate, `radioAvailable` (`lib/radio/availability.ts`:
the operator's switch when published, else the deployment's ceiling):

| Surface                                                             | Component                                                                                      |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Header, from `lg`                                                   | `RadioControl` (the click takes the permission to play)                                        |
| Logo menu, below `lg`                                               | `DashboardMobileNavMenu` (the recorder's action, then the radio's)                             |
| Under the header, every dashboard page                              | `RadioBannerSlot` — publishes `--radio-banner-h`, which the chat's full-height shell subtracts |
| Home page, under the quick-access bar, right above « My dashboard » | `RadioDashboardCard`, handed to `TodayBriefing` as its `aboveBriefing`                         |
| `/dashboard/radio`                                                  | `RadioPage` (says the radio is not offered where it is not)                                    |
| Settings › Voice & Media                                            | `RadioSettings`                                                                                |

A refusal the API names (`detail.code`) is told in the listener's words with the
bound it published (`lib/radio/errors.ts`); a start refusal stays on the bar.

**The bar** (`components/radio/RadioBanner.tsx`) reads in three groups: the
STATION — its name, where it stands, what airs (the only part announced,
`role="status"`) —, the METERS — the minutes left before the automatic stop, the
cost so far and what the planned listening will cost —, the ACTIONS — the page,
then pause and stop side by side, the same size in a two-column grid (stop keeps
its destructive colour, ADR-207; on a phone they are two equal halves of the
bar). It holds still: what airs keeps its line through a pause and the line
stays, empty, between two programmes; the pause button holds the width of the
longer of its two labels (`StackedLabel`) — before, a pause changed the bar's
height and the button's width, and a second click meant to resume could land on
stop (measured in Chromium: identical boxes before and after a pause, desktop and
phone). Each figure is named for a screen reader by visually hidden text, never
by an `aria-label` on a plain span (prohibited by ARIA 1.2, read by none).

The slot's background is clipped to its content: the spacing below the bar reveals
the dashboard background while the bar retains its opaque contrast. The spacing
still contributes to `--radio-banner-h`, in both compact and expanded states,
so the chat's height calculation remains the same.

**The station on screen** is named by the session it carries (`station_name` on
every session answer, frozen at the start), else the listener's language's
(`radio.station_name`); the home card shows the session's name while one is
live and names it, and the listener's own otherwise (`useRadioStationName`) —
tuning in, off air, and once a session is over, since the station may have been
renamed since. Stopping from the keyboard hands the focus to « Start again » once
the stop the listener pressed has ended the session.

**The articles of the session** (`components/radio/RadioArticles.tsx`): under the
programme, every story the aired segments cited (`article_id` on a transcript
source), each once, in the order it first aired — kept by the controller
(`RadioView.articles`, `lib/radio/articles.ts`) once the session is over, so a
reader finishes the article they opened, and cleared at the next start. Each
folds, and a folded one asks nothing: its reader (`useRadioArticle`) mounts when
it opens — and the original stays one click away beside the fold, so the article
can be read at its outlet without asking for a translation. `GET /radio/articles/{id}` answers the text the newsroom kept — whole,
else the outlet's summary, said as such — with its paragraphs set apart, in the
listener's language: translated on opening by the `radio_translator` slot when
the feed speaks another language, once per story and language (the shared cache
`radio:article`, kept as long as the story may air; two readings at once, on any
worker, make ONE translation — `SharedArticleFlights` over `shared_flight`, the
claim held longer than a translation may take), billed to the reader under a run
of its own (`radio_article_<hex>`, ADR-272) and said: its cost, or nothing paid
when read back. An article the newsroom cut (`newsroom.fulltext.was_cut`: it keeps
exactly the first `ARTICLE_MAX_CHARS` characters of a longer one) ends on its last
whole sentence and says the rest is at the outlet. A translation that fails — a
ceiling, a cut answer, the slot's timeout, a provider error — shows the original,
said so, with what it cost. Past the listener's radio budget (decision 37) no model
is asked: the original, said so (`budget_reached`), nothing billed, nothing filed. The slot's default timeout (`LLM_DEFAULTS`) stays under
the edge proxy's documented 100 s read timeout, and the page waits longer
(`RADIO_ARTICLE_TIMEOUT_MS`, `apps/web/src/lib/constants.ts`), so the server's
verdict always arrives first. Only a web address becomes a link, opened without a
referrer.

## Settings

`RadioPreferences` is strict on the way in and tolerant field by field on the
way out; `GET /radio/options` publishes every list and bound a write enforces
(ADR-184). Saves are serialised in the page: one full replace in flight, the
latest state after it.

Every choice says what it covers, under its control (`aria-describedby`): each
programme (with the bound it enforces — `stories_max` — and the hours the journal's
noon and evening editions start, `noon_from_hour` and `evening_from_hour`), each
personal source, each news source.

**The news sources** (`RadioSourcesFields`, `GET /radio/sources`, decision 38): every
base source with a checkbox (ticked by default; unticking saves the settings, then
reads the sources again), its language, the stories it published over the window a
programme airs from and how many of them the listener never heard, and a badge when
its last readings failed; the listener's own sites the same way (the checkbox pauses
one, the row renames or removes it: `PATCH`/`DELETE /radio/sources/{id}`) and the form
that checks, then adds, a site. The totals are what the station can air; « Forget what
I heard » (`DELETE /radio/heard`) asks first, then lets every story air again. No kind
of news, no language to choose: everything airs translated.

**The station's name** (`station_name`, at most `station_name_max_chars`):
the listener's own name for their station, said by its host at the opening and
shown by the player — in company too —; empty is the name their language gives
it. The write path refuses markup, template braces and every control, format,
surrogate or private-use character (checked on the RAW value — folded first, a
line feed would have become a space and passed), folds the spaces, and keeps an
unassigned character, which the listener's newer browser may know as an emoji.
The field saves when the listener leaves it or presses Enter (never per
keystroke, nor on the Enter that picks an input method's candidate), strips what
the API refuses and counts by code point as the API does (`withStationName`: a
cut never leaves half a surrogate pair). A name may hold digits: the editor
blanks a MENTION of it before reading a line's numbers
(`verification._without_station`), and the model verifier is told it below its
marker. A session keeps the name it started with.

**The voices** are the ones the `radio_voice` slot's engine offers in the
listener's language. A stored voice the engine no longer offers reads as
automatic (`listener_settings.listener_preferences` — an engine that cannot list
its voices right now keeps the stored choice), and the page reads its options and
settings again when that slot is saved or reset (the `radio_voices` revision,
`stores/revisionStore.ts`): a voice of the previous engine, sent back with the next
save, had made every save refused. Each engine keeps its own voices: the stored settings
hold them per `provider/model` (`voices_by_engine`), a save replaces the voices of the
engine in place alone (the row locked, every other engine's kept), and an engine switched
back to finds its voices; the flat voices of an older row are offered to the engine now in
place, then filed under it at the next save. Four roles are the listener's to voice (the
host, the anchor, the expert, the editorialist — `CONFIGURABLE_ROLES`); the commentators
of a debate or a discussion are the station's, cast with voices nobody else speaks with
when the engine has them (`cast._speaker_voice`), and a commentator who would sound like
LIA or like another voice of the programme stays silent (`Cast.voiced_roles`); a programme
the cast cannot give its distinct voices is not planned (`voices_by_format`).

**The budget** (`RadioBudgetFields`, `GET /radio/budget`): what the listener's
radio spent over the rolling window against its bound, and, at the bound, when it
lifts — nothing when the instance sets no bound.

## Routes

All under `/radio`, behind the capability switch, each answering for the caller only
(another account's session, segment or site reads as absent). None holds a request
session (ADR-304).

| Route                                                                                                                           | Refusals (`detail.code`)                                                                                                                            |
| ------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /sessions`                                                                                                                | `radio_instance_full`, `radio_no_voice`, `radio_voice_unavailable`, `radio_budget_reached` (429, + `max_eur`, `lifts_at`)                           |
| `POST /sessions/{id}/playhead`, `POST /sessions/{id}/stop`                                                                      | — (404 when not the caller's)                                                                                                                       |
| `GET /sessions/{id}/segments/{seq}/audio`                                                                                       | — (`Cache-Control: no-store`)                                                                                                                       |
| `GET /options`, `GET /preferences`, `GET /budget`                                                                               | —                                                                                                                                                   |
| `GET /articles/{id}`                                                                                                            | — (404 when the story is not the caller's to read: the catalogue's, or one of their own sites')                                                     |
| `PUT /preferences`                                                                                                              | `radio_timer_too_long` (+ `max_minutes`), `radio_voice_unknown`, `radio_personality_unknown`; 422 for an unticked address that is not a base source |
| `GET /sources` (every source and what it holds), `PATCH /sources/{id}` (rename, pause), `DELETE /sources/{id}`, `DELETE /heard` | — (404 when the site is not the caller's)                                                                                                           |
| `POST /sources/preview`, `POST /sources` (rate-limited per account)                                                             | `radio_source_refused` (+ `outcome`), `radio_source_limit` (+ `max_sources`)                                                                        |

Every code has a sentence in the six languages (`tests/unit/domains/radio/test_errors.py`).

## Configuration

`RadioSettings` (`apps/api/src/core/config/radio.py`), every value documented in
`.env.example`: `RADIO_ENABLED` (the deployment's ceiling; the operator's switch is
the `radio` capability), the session bounds (`RADIO_TIMER_*`, `RADIO_IDLE_TIMEOUT_SECONDS`,
`RADIO_PAUSE_TIMEOUT_SECONDS`, `RADIO_MAX_ACTIVE_SESSIONS`, `RADIO_FAILURES_MAX`), the
look-ahead (`RADIO_STAGE_*`, `RADIO_LOOKAHEAD_*`), production (`RADIO_TTS_*`,
`RADIO_MIX_TIMEOUT_SECONDS`, `RADIO_QUOTE_MAX_CHARS`, `RADIO_ANALYSIS_*`,
`RADIO_VERIFICATION_DEFAULT`), the newsroom (`RADIO_NEWSROOM_*`), the listener's sites
(`RADIO_CUSTOM_SOURCES_MAX`, `RADIO_SOURCE_PREVIEW_RATE_LIMIT_*`) and the media
(`RADIO_STORAGE_PATH`, `RADIO_MEDIA_*`); `RADIO_FLASH_POLL_SECONDS` is how often a
session looks for what LIA just wrote (a news flash's delay); `RADIO_TTS_RATE_LIMIT_WAIT_MAX_SECONDS` bounds
the wait a voice's rate limit may ask; `RADIO_COST_ESTIMATE_MIN_AUDIO_SECONDS` is the
radio a session must have produced before its rate prices the rest (the estimate
below); `RADIO_SAME_EVENT_SIMILARITY` is how close in meaning two headlines tell one
event (0 turns the reading off); `RADIO_INTEREST_*` bound the listener's interests
(interests read — told to the writer and searched —, stories kept per search, how long a
search is reused; together they bound the interest stories a desk reads);
`RADIO_SEGMENT_GAP_SECONDS` is the station's music
between two programmes; `RADIO_BUDGET_24H_EUR` is what one listener's radio may spend
over a rolling day (0 = no bound). Bounds that contradict each other refuse the
boot. The model slots (`radio_writer`, `radio_analyst`, `radio_verifier`,
`radio_translator` — the page's article) and the voice slot (`radio_voice`) are
administered in their own category of the LLM settings.

## Background jobs

| Job                      | What it does                                                                                                                                                          |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `radio_newsroom_collect` | one newsroom pass per `RADIO_NEWSROOM_INTERVAL_SECONDS`, under the capability read at every tick; no lock (a bounded pass on the leader)                              |
| `radio_media_sweep`      | removes the session directories no live session claims and nobody touched for `RADIO_MEDIA_ORPHAN_AGE_SECONDS`; removes nothing when the live sessions cannot be read |

Both are registered by `infrastructure/startup/scheduler_radio.py`, only where
`RADIO_ENABLED` is true. A stopping worker cancels its session loops within
`LOOP_STOP_TIMEOUT_S` (`radio/constants.py`); each gives its lease back and the next
report restarts it elsewhere.

## Observability

`infrastructure/observability/metrics_radio.py`, drawn on dashboard **31 - Radio**:
starts by outcome, sessions ended by reason, loops broken, segments by format and
outcome with their production time (counted in `Antenna.produce`), the newsroom's
ticks, readings, stories and texts, orphans swept, site lookups. Core alert
`RadioNewsroomStalled` (the age of the newsroom's last tick that ran to its end —
never stamped at boot nor by a failed pass): runbook
[RadioNewsroomStalled](../runbooks/alerts/RadioNewsroomStalled.md). The logs carry
identifiers and counts, never a programme's words, a listener's site or a story.

## Spend

Every token and every character a session costs is recorded under the
session's run and shown live; the ceilings are asked before every production
(a refusal ends the session with `budget`). The model verifier's cost is
stated where it is chosen. An article's translation is billed to the reader
who opened it, under a run of its own, through the same structured door (its
ceiling asked there); its cost comes back with the article. A headline's embedding
(decision 34) is billed to the session whose desk meets it first, and read from
Redis by the others for nothing (measured: 76 headlines, 0.0002 €).

**The radio's own budget** (decision 37, `budget.py`): `RADIO_BUDGET_24H_EUR` (2 €)
over a rolling day (`BUDGET_WINDOW_SECONDS`) on everything the radio bills a
listener — their sessions and article translations, found by the run prefix
(`RADIO_RUN_ID_PREFIX`, matched literally). A run counts its whole ledger row
(`billed_cost_sql`) while its last spend is in the window: when that errs, it costs the
listener a little waiting, never the platform a euro past the bound. A start past it is refused before it takes a
place (`radio_budget_reached`, with the bound and when it lifts: the oldest runs leave
the window first); the loop asks it after the account's ceilings before every
production and every flash (`radio_spend_blocked`; the session ends as `budget`); an
article is shown untranslated. It bounds the radio on top of the account's ceilings,
never instead of them.

**What the planned listening will cost** (`view.cost_estimate`, on every report
as `cost_estimate_eur` over `cost_estimate_s`): the cost so far divided by the
radio produced, times the listening the timer planned (`SessionState.planned_s`,
fixed at the start — a pause moves the stop, never what was planned), or an hour
when no timer stops the station. The spend follows production and production
follows listening, so the session's own rate prices the rest in whatever models
and voices it runs on — no tariff is re-typed. Nothing is published before
`RADIO_COST_ESTIMATE_MIN_AUDIO_SECONDS` of radio was produced (the opening's rate
alone would be a guess), while the cost is unknown, once the session's end is
decided, nor for a timer no plan was recorded for; the bar says it with two
significant digits after rounding (« ≈ 0,051 € pour 30 min », « ≈ 0,12 € par
heure »).

**The prompt cache.** Every model call of the radio is ONE structured call
through `single_call_messages`, its static prompt above the marker (ADR-309), so
each provider's adapter applies its own cache mechanism exactly as for the chat.
Measured on dev over 48 h of radio runs, the share of the prompt read from the
cache: the writer 72 % and 71 % (two model families), the verifier 0 % and 50 %,
the analyst 20 %, the translator 0 % (one call per article and language: nothing
to read again). The verifier's static prompt (717 tokens) and the analyst's (467)
sit under the ~1 024-token minimum of breakpoint caches: a structural gap, not a
missing policy. The « frequent exchanges » rhythm (ADR-311) decides three effects
of a ReAct LOOP — every tool bound, the context after the question, the history
by blocks —, none of which exists in a single structured call; the radio already
follows its principle (the stable prefix first, calls every 30 to 90 s). And the
cache weighs little here: over 36 dev sessions the models cost 0.1465 € and the
voices 2.9985 € — 95 % of a session is speech, where no prompt cache applies.

## In the transparency registers

A session and each article translated on opening are one row each in the
decision register (`agent_decisions`), under the run their euros and reads
already carry (`register.py`, ADR-324 decision 31): route `radio` or
`radio_article`, authorship `user` — the listener started it —, execution
`direct`. A session is filed when it ends, by whoever sees the end: its loop
(`SessionBooks`, a port of `RadioLoopLauncher`), or the service when no loop
holds it — a stop, and a start that replaces a session no loop holds — through
`record_decision_once`, so two closers racing leave ONE row. The end reads as the
listener would say it (`END_OUTCOMES`, refused at import when an end is
missing): the timer and the listener's stop are `answered`, nobody listening and
a ceiling `interrupted`, failing productions `failed`, the reason kept unless the
timer ended it. A defect after the end files the end that stands; a shutdown or
a takeover files nothing. A translation is filed when the call returns (`failed`
when nothing usable came back); a reading from the cache files nothing, nor one the
budget refused (no call was made). The reads
are the listener's consultations (`consultations.py`): personal sources, searches,
reading the stored newsroom material (`radio:news`), and every notification poll
(`radio:notifications`), including an empty answer. Reading stored news is not a
claim that the originating website was contacted again. A failed or cancelled
read is recorded as failed; completed reads survive an interrupted gathering.
Sources disabled by the listener and briefing cache hits remain unrecorded because
no source was opened. The account's Consultations tab identifies these rows with
its translated Radio LIA badge, alongside the consulted domain and exact count;
repeated polls fold visually without deleting records. A session appears in the
decision register when it ends, not while it is still playing. An interrupted
article translation also closes its decision record, and one-shot decision writes
survive cancellation without duplicating the run. Nothing the radio does is an
action changing the person's resources, and none of it is LIA's initiative.

## State and retention

Redis family `radio` (`USER_RUNTIME`) holds a session's record, inbox, state,
segments and loop lease, and the aired ledger; `radio:active` (`GLOBAL`) counts
live sessions; `radio:article` (`GLOBAL`) keeps an article's translation per story
and language (a public text in a language is nobody's personal data), and its
claim lives under the `shared_flight` family. Audio
lives under one directory per session in the container's writable layer
(`RADIO_STORAGE_PATH`, shared by the workers of one container, wiped at every
recreate) and is never kept once the session is over and played: no replay, no
archive. In dev that path falls inside the repository tree (the bind mount of
`apps/api`), so `apps/api/data/radio/` is git-ignored: its files are a listener's
day spoken aloud, and one `git add -A` staged them once. PostgreSQL keeps the listener's settings and sites (`radio_preferences`,
purged and exported with the account) and the newsroom's feeds and stories
(`radio_feeds`, `radio_news_items`, stories purged past
`RADIO_NEWSROOM_RETENTION_SECONDS`).
