# ADR-330 — Landing media served without runtime work: pre-generated illustrations, and a video the operator declares

**Status:** Accepted — 2026-10-01, owner request: a looping, AI-generated video
between the hero and the promise section, with play/pause and sound controls and
a credit line; the section titles pulsing on the music while the sound is on;
and blog illustrations that « take a long time to load ». Owner arbitrations on
the way: the video is hosted on a server of the owner's (not committed, not
linked from X), under the host's default name; the sound keeps playing while
the reader scrolls; a copy is hosted only with the author's accord.

**Amends:** ADR-215 / B03 (the host-neutral image gains a RUNTIME media origin,
never a build-time one), ADR-136 (CSP: `media-src` gains `https:`, the posture
`img-src` already had), `docs/technical/LANDING_PAGE.md` (structure, blog
illustrations, the video section).

## Context

Measured before anything changed (2026-10-01):

1. **The blog illustrations were 28 PNG masters of 2752×1536 RGBA, 6 to 9 MB
   each (194 MB in `public/`, copied into the production image).** The image
   optimizer on the Raspberry Pi decoded one per variant per cache expiry:
   0.4–0.6 s per cold variant, up to 4.8 s of time-to-first-byte when the 14
   cards of a page arrived together, and the cache is emptied by every deploy.
   Its `/_next/image?…` responses carry no file extension, so Cloudflare marks
   them `DYNAMIC` and never caches them — every visitor's every variant reached
   the Pi, while a plain file under `public/` is cached at the edge by
   extension (`MISS` then `REVALIDATED`, a 304 per request). The social image
   (`og:image`, `twitter:image`, JSON-LD) pointed at the raw 8 MB PNG, declared
   as 1200×675; X refuses images above 5 MB, so no card preview. And the 29th
   article (`tabular-administration`, v2.2.0) had no illustration at all —
   a broken image nothing noticed.
2. **The video is 306 s of 1080p24 whose picture is a halftone dither — noise
   for every encoder.** The master is X's own 10.4 Mbit/s encode (the variant
   list of the tweet, measured). A CRF sweep with VMAF against it: AV1 1080p
   gives 83 at 3.9 Mbit/s, H.264 1080p 85.5 at 5.8 Mbit/s, and **720p loses
   the dither at any bitrate** (VMAF ≤ 76 at 4–6 Mbit/s; visually, the dots
   turn to mush). Full length at 1080p is therefore 150 MB (AV1) to 220 MB
   (H.264) per file: past GitHub's 100 MB limit, and `public/` ships in the
   image. **X's video CDN refuses a third-party `Referer`** (`403` for
   `https://lia.jeyswork.com/`, `206` for `https://x.com/` and for none) —
   stripping the referer would circumvent a protection the rights holder set —
   and the official embed widget allows neither autoplay-loop-muted with our
   controls, nor the sound at our button, nor any reading of the frame clock,
   and loads X's scripts and cookies on every visit.
3. **The public pages are prebuilt and host-neutral** (B03, `generateStaticParams`):
   nothing deployment-specific may be in the build, which also rules out a
   `NEXT_PUBLIC_*` URL — it would put the owner's media origin into the image
   every self-hoster downloads. The CSP is serialised at build time too.
4. **Where a video can live**: the owner's VPS runs Caddy as its only listener
   on 443 (Let's Encrypt, HTTP/3, 20 TB/month) and serves static files with
   `sendfile`, Range and ETags; no CDN eviction, no third party.
5. **Synchronising titles with music**: the browser keeps the picture aligned
   with the sound it outputs, output latency included (Bluetooth: 150–250 ms),
   so a title driven by the presented frame's `mediaTime` is as synchronous as
   the picture; a FFT of the output would follow the loudness — the voice
   included — a frame late. The soundtrack has a steady pulse (129–134 BPM over
   the whole piece, measured by autocorrelation per 10 s window).

## Decision

1. **Blog illustrations are pre-generated static variants.** For every
   article, `apps/web/scripts/build-article-images.mjs` (sharp, the encoder
   Next ships) writes four WebP widths (`480, 768, 1024, 1536`) and a 1200×675
   JPEG for the social cards into `public/articles/`; `lib/blog/article-images.ts`
   is the ONE place that spells the names and the `sizes` of each surface
   (index cards, landing grid, article hero), `components/blog/ArticleIllustration.tsx`
   draws a plain `<img srcset sizes>` with `loading`/`fetchpriority` by
   position, and the article page announces its hero through React 19's
   `preload`. Nothing is resized at request time, ever; the masters are not
   versioned (git history keeps the 28 shipped before). A guard
   (`data/__tests__/blog-article-images.guard.test.ts`) refuses a slug without
   its full set, with a shrink-only list of articles still pending an
   illustration — it holds `tabular-administration`, whose illustration is
   the owner's decision.
2. **The landing video is the operator's, declared at run time.**
   `LANDING_MEDIA_BASE_URL` names the absolute URL of a directory holding
   `manifest.json` — the renditions, a poster, optionally a beat map, a
   credit, an AI-generated flag (schema: `lib/landing/media.ts`; every file is
   a BARE NAME resolved under that directory and nowhere else, the credit link
   is https or absent). `GET /api/landing-media` reads the variable at request
   time, fetches the manifest behind a 3 s timeout and a per-process cache
   (5 min, 60 s for a failure), and answers `{ video: null }` on anything but a
   valid manifest — a malformed variable is logged, never fatal. The section
   mounts in the browser only on a descriptor: without one, the page is
   exactly what it was. The renditions, the poster, the beat map, the manifest
   and a `PROVENANCE.json` are written by `scripts/assets/encode_landing_video.py`
   from a master kept outside the repository: AV1 and H.264, 1080p for
   viewports of 900 px and more, 720p for phones (`minWidth` in the manifest),
   AAC audio, names carrying the master's content hash so a year-long
   immutable cache is safe. Nothing owner-specific is in the code; the same
   files, attached to a release, let any operator host the video anywhere.
3. **Playback follows the reader.** Looping; the sources attach within 600 px
   of the viewport and the browser fetches ahead; playback starts when the
   frame is IN VIEW (not merely near — the first draft started early and
   paused at once), never under `prefers-reduced-motion` or `Save-Data` (the
   poster and the play button remain); a refused `play()` leaves the poster.
   **The sound is wanted by default** (owner decision, 2026-10-01): the first
   start is attempted WITH sound, and where the browser refuses sound without
   a gesture (`NotAllowedError` — the common policy on a first visit) the
   start falls back to muted, the sound button saying so; a click turns it on.
   Only that error triggers the retry: an `AbortError` from a `load()` racing
   a `play()` must not mute a video the browser would have played. A muted
   video pauses when it leaves the view or the tab, and resumes when back; a
   video with sound keeps playing — its music is what the reader chose, or
   accepted — and a floating control (pause, sound, back to the video)
   follows them. A browser that can play no rendition fires `error` and the
   section removes itself. `media-src` gains `https:`; the media origin also
   sends `Cross-Origin-Resource-Policy: cross-origin`, so the strictest
   embedder policy accepts it; the two JSON documents go through the web
   server and need no CORS.
4. **The titles beat on a map, not on a microphone.** The encoder analyses the
   soundtrack offline — spectral-flux onsets over 40 log-spaced bands, a tempo
   per 10 s window folded onto the piece's median, dynamic-programming beat
   tracking (Ellis 2007; its `alpha` is 8 because at 4 a loud off-beat hat was
   taken twice in 40 s of a synthetic track), each beat snapped to its onset —
   into `[ms, weight, bar]` triples (`lib/landing/beats-schema.ts`, bounded,
   strictly ascending). **The published instant is calibrated, never read
   raw**: the spectral flux of a transient peaks while it ENTERS the analysis
   window, so every onset is reported early by a fixed amount for a given
   window and hop — measured 2026-10-01 on a synthetic click track through the
   encoder's own functions, detected − true = −72.9 ms (standard deviation
   0.5 ms over 86 beats), nearly two frames before the drum; `ONSET_LEAD_MS`
   adds it back (bias 0.0 ms after, two edge artefacts left). **The bar phase
   is voted locally**, over ±16 beats on the low band: a bar opens where a
   beat's class leads the runner-up by 10 % and its mean reaches a quarter of
   the piece's median, never within two beats of the previous bar
   (`bar_flags`, unit-tested). A global `i % 4` was measured wrong on the
   shipped video — the tracker inserts or drops a beat in a breakdown, so the
   count from the start accented phase 0 for 55 s, phase 3 to 253 s, phase 0
   again, with margins up to 64 % — and the first local draft SUMMED instead
   of averaging, which marked a bar on the piece's first beat and fifteen
   pairs one beat apart. A tie or a bar-less passage marks nothing: on the
   shipped soundtrack 117 bars over 682 beats, 93 gaps of exactly four, the
   rest long stretches where the kick is even (every refusal on the margin,
   median 4.9 %, none on the floor). **The map's name carries the analysis
   version beside the master's hash** (`-beats-v2.json`,
   `BEAT_ANALYSIS_VERSION`): the file changes when the ANALYSIS changes, and
   everything under the media directory is served immutable for a year.
   The page loads the map through `/api/landing-media/beats` once the video
   PLAYS with its sound on — not when sound is merely wanted, so a start the
   browser turned muted fetches nothing — and a driver
   (`lib/landing/beat-sync.ts`) reads the presented frame's time through
   `requestVideoFrameCallback`, anchored on the frame's `expectedDisplayTime`
   when the browser gives it (the callback runs BEFORE the frame is shown),
   extrapolates between frames on the monotonic clock (`currentTime` where
   the API is absent), computes the value one display frame AHEAD
   (`BEAT_PAINT_LEAD_MS`, 16 ms: what a frame callback writes is painted at
   the next vsync), and writes ONE custom property, `--beat`, on `<main>`,
   with `data-beat` while it runs. The hero's `h1` (its lines — the entrance
   animation, filled forwards, owns the h1's own transform) and every section
   `h2` read it with `transform` alone: 6 px of lift and 4.5 % of scale at a
   full-strength beat (`--beat-lift`, `--beat-scale`, one place to tune; 2 px /
   1.8 % read as a tremor, the owner asked for a pulse, then for a more marked
   one), a **12 ms attack** (40 ms read late against the drum: a percussive
   visual wants a hit and a release, not a swell), a 180 ms release, a bar's
   first beat a quarter stronger — and **every beat pulses at least 60 % of
   the amplitude** (`BEAT_WEIGHT_FLOOR`): the map's weights are onset
   strengths scaled to their 95th percentile, so most beats sit at 0.3–0.7
   and, driven raw, the titles trembled on the loud hits and barely moved
   otherwise (measured: peaks of 1.6 % where 4 % was allowed); the weight now
   grades the beats, it no longer hides them. The origin follows the title's
   alignment (left from `lg` on the hero, centre below); nothing under reduced
   motion. Measured on the real soundtrack: 682 beats, median interval 451 ms
   (MAD 4 ms), 99.6 % of them on an onset stronger than the second around it
   — a figure the summary read on the PUBLISHED instant for a while and
   answered 9 % for a map that was right; it reads the analysis domain now.
   And the whole chain measured in a real Chromium against the dev server
   and the real 1080p video (a `MutationObserver` on the `--beat` writes, the
   presented frames through `requestVideoFrameCallback`, 15 s): 34 pulses for
   34 beats, every peak written between −6.7 and +27.5 ms of its beat's
   instant on the frame clock (median +9.6 ms — the attack's own 12 ms, one
   paint lead early), none farther than a display frame.
5. **The use-cases intro spans its column.** Its 48 rem cap put the title on two
   lines above a 1088 px grid at every desktop width; the cap and the 65 ch
   cap on the lead are gone, `text-pretty` keeps the last line whole.

## Consequences

- The host serves no image resize and no video byte: the illustrations are
  9.5 MB of files cached at the edge (194 MB of PNG left `public/` and the
  image), the video's cost is the media origin's. A page that never scrolls to
  the section downloads nothing of it; a reader who never unmutes never
  downloads the beat map.
- **Hosting a copy of someone's video is a reproduction: a credit is not a
  licence.** The directory is uploaded only with the author's accord, the
  manifest carries the credit and the AI-generated disclosure, and emptying
  the directory removes the section on the next cache expiry — no deploy.
- An operator shows their own video by hosting a manifest; a self-hoster
  without one sees no section. Captions are not modelled: the first clip
  carries music and no speech; a media that carries speech needs a manifest
  field for a caption track before it is published.
- The hermetic proof (`e2e/smoke/landing-video.spec.ts`) emulates the
  autoplay policy on a REAL input event: under Playwright every `evaluate` —
  every `expect` evaluates — is a user gesture to Chromium (measured:
  `navigator.userActivation.isActive` false from load until the first
  `page.evaluate`, true for about five seconds after each one), so the
  activation flag cannot stand for a gesture; and the axe scan waits for the
  entrance animations to end — scanned mid-fade, axe composites a translucent
  text over the background and reported 61 contrast violations no reader ever
  sees.
- `media-src https:` lets a page load media from any https origin, as
  `img-src https:` already let images; the threat (exfiltration through a
  media URL) was already open through images.
- Left open, in writing: an HEVC rendition for Apple devices without AV1
  hardware (a 30–40 % smaller fallback than H.264); the illustration of
  `tabular-administration`; a measurement of the 1080p/720p choice on real
  phones.

## Amendment 2026-10-01 — the element belongs to the visit, and the beat reaches every page

Owner request the same evening: the video and its music keep playing while the
visitor moves between the public pages, every visited page's titles beat with
it, it stops by itself at sign-in; six beat-driven effects on top; and the hero's
planetarium switched off (`LANDING_PLANETARIUM_ENABLED`, the component kept).

1. **One `<video>` element for the whole visit.** `LandingVideoHost`
   (`components/landing/video/LandingVideoHost.tsx`) is mounted by the root
   `[lng]` layout around every page: it owns the element and a context through
   which the landing's section REGISTERS its frame. The section keeps its request
   (`/api/landing-media`), draws an EMPTY frame at the clip's ratio — the slot —
   and the caption; no page but the landing ever asks the server, and the player
   exists only once a frame has been registered. The element is never
   re-parented: React keeps it across `Link` navigations, and its three places
   are attributes of its container (`data-mode`): FRAMED over the slot, placed in
   DOCUMENT coordinates (`lib/landing/frame-placement.ts`: the rect plus the
   scroll offsets, written on the container, re-measured by a `ResizeObserver`
   of the slot and of the body, on resize and on load — it scrolls with the page
   natively, no per-scroll work); DOCKED bottom-left (the eyes keep the right)
   while its music plays with the frame off-screen or no frame at all — a small
   thumbnail of the same element with pause, sound, « back to the video » (a
   `Link` to `/{lng}#video`, client-side, so the element survives) and close;
   HIDDEN when muted or paused with no frame. The playback policy is unchanged:
   its observers watch the SLOT (`useIntersects` remembers which element it
   measured, so a new slot starts unmeasured rather than with the last one's
   answer, while « near » stays sticky across slots — the sources are never
   detached), and no slot reads as out of view. Close is the visitor's pause.
2. **The route decides where the player may live** (`lib/landing/player-routes.ts`):
   a declared list of public pages, the `(auth)` pages, the dashboard, `/share`
   and `/account-inactive` as stops, and a test demanding that every route under
   `app/[lng]` be named on one side — a page added later chooses in writing. On a
   stop route the element is paused, then unmounted.
3. **A language switch remounts the host** (`router.push` to another `[lng]`),
   as a full reload does: the player records `{ time, sound }` in the session on
   unmount and on `pagehide` (`lib/landing/player-session.ts`, never throwing),
   and a fresh host resumes from a record younger than two minutes once its slot
   comes — muted if the sound was off, with the sound otherwise (the visitor had
   clicked for it, and the browser remembers the gesture on the origin).
4. **The driver writes on the document** (`:root`): `--beat`, `--beat-bar` (the
   bar beats alone) and `--beat-hue` (±8° on a four-bar cycle, locked on the
   bars so the colour breathes with the phrase, never with the clock), and
   `data-beat` while it runs; the stylesheet reads `:root[data-beat] .cosmos …`,
   on every page wearing the skin.
5. **Six effects, sound on, `transform`/`opacity` only, none under reduced
   motion** (`globals.css`, under the beat block): C — the frame's glow ring, a
   pre-painted shadow whose opacity follows the beat and the bar; D — the header
   logo's heartbeat (`.landing-logo`, 8 %); E — the ghost words breathe on their
   FRAME (the word's own transform is the scroll drift's); G — the chat mockup's
   active step dot (`.cosmos-demo-step-dot`); H — the chapter rail's active
   numeral (`.cosmos-chapter-rail`); J — the signature gradient's hue drift
   (`filter: hue-rotate(var(--beat-hue))` on `.cosmos-grad-text`); K — LIA's
   eyes JUMP between two beats and land, squashed, on the next: the driver's
   fourth property, `--beat-progress` (0 on a beat, 1 just before the next),
   draws the arc in `sin(π·progress)`, the beat's own envelope squashes the
   face from its feet on landing (`scale(1 + 0.12·beat, 1 − 0.12·beat)`), a
   bar adds height — on the face's root (`.lia-eyes`), which neither the drag
   (placed by `left`/`top`) nor the rig (the parts) transforms. Proposed and
   refused by the owner: a breathing nebula, an equaliser glyph in the dock, a
   CTA ring, twinkling stars.
6. Not done, in writing: an animated transition between the frame and the dock
   (a FLIP across two positioning schemes) — the swap is instant, as the pill
   was; a caption track; the native shells measure nothing new (the WebView
   loads the same pages).

## Amendment 2026-10-03 — several videos, one after the other

Owner request: a second video (`StopShipping`, by @vikktorrrre, AI-generated —
the clip announces its generator itself), the two playing in turn, for ever.

1. **The manifest stays version 1 and gains `next`** (`lib/landing/media.ts`):
   the top level is the first video, `next` the ones that follow in playing
   order (at most `LANDING_MEDIA_MAX_NEXT`), every entry under the first one's
   rules (bare file names, https credit). Version 2 was rejected: the manifest
   is read at RUN time by whatever build a deployment runs, and a reader that
   predates `next` drops the unknown key (Zod strips it) and keeps playing the
   first video alone — so one directory serves the old build and the new one,
   and publishing the second video required no coordinated deployment.
   `/api/landing-media` answers `{ video, next }`; the page reads an answer with
   no `next` (cached before) as a single video. The beat map is asked by rank,
   `/api/landing-media/beats?video=N`, the first when absent.
2. **One element still, handed the next video** (`LandingVideoHost`): the host
   keeps the RANK of the video the player holds and the list it received; a
   single video loops as before, one of several ends, and `ended` moves the
   rank (back to the first after the last). The new sources load on the same
   element, which carries on from the first frame with the sound it had — the
   end of a non-looping element fires `pause` then `ended`, so nothing reads it
   as the visitor's pause. The caption under the frame credits the video
   playing (the registry publishes the rank); the beat map is the playing
   video's, and the driver never runs one video's map against another's clock.
   A re-fetched list equal to the one held is the one held: returning to the
   landing no longer hands the player new descriptors that reloaded what played.
3. **The resume record names the video** (`{ video, time, sound }`; a record
   from before reads as the first video, a rank the list does not hold as the
   first video at its first frame), and the position is applied ONCE per mount
   — the next video loads metadata too, and must start at its beginning.
4. **The encoder appends** (`scripts/assets/encode_landing_video.py`):
   `--append` adds the video after the ones the manifest in `--out` names
   (replacing an earlier encoding of the same `--name`), and its provenance
   beside theirs in `PROVENANCE.json`; no rendition is taller than the master
   (a 720p master feeds the 720p pair, offered to every viewport); and
   `--copy-h264` serves a web H.264 master itself, remuxed, as its own
   rendition — measured on this one (1.04 Mbit/s): re-encoding lost seven VMAF
   points at the same rate (CRF 27, 93.2), AV1 at CRF 42 kept 94.0 at 0.78
   Mbit/s.
5. Effect C is no longer the ring this ADR first described: since v2.4.0 the
   framed video's edges fade and a shapeless radial halo swells on the beat
   (`docs/technical/LANDING_PAGE.md` § 4 and § 10). Not done: a transition
   between two videos (the cut is the clip's own).
6. **A skip button, the same move on request** (owner request, same day): with
   several videos the player offers « play the next video » (`SkipForward`,
   `landing.video.next` in the six languages) in the frame and in the dock; a
   single video offers nothing. It is the host's end-of-video move — the next
   rank, the first after the last — and a skip is a request to WATCH: the next
   video plays even after a pause the visitor asked for
   (`useVideoPlayback.continueWithNext`). Measured on the way: a source change
   resets a PLAYING element without a `pause` event (the media load algorithm
   rejects the pending play and fires `emptied`), so the player reads `emptied`
   as paused — otherwise the button said « pause » over a stopped element until
   the next video started.

## Alternatives rejected

- **Committing the renditions.** 150–220 MB per 1080p file, past GitHub's
  limit; a 720p-only set fits but loses the halftone the video is made of.
- **Linking X's file, or its widget.** The CDN refuses our referer and
  stripping it circumvents a protection; the widget controls nothing and
  tracks everyone.
- **A build-time URL.** It bakes the owner's origin into the public image.
- **Lighter sources under the image optimizer, with a persistent cache
  volume.** Still one resize per variant per expiry on the host, and still
  never cached at the edge.
- **A live audio analysis for the beat.** Follows loudness, voice included, a
  frame late, and depends on output latency.
- **An IP or a dedicated subdomain for the media origin.** The IP serves
  Caddy's internal CA (a subresource is blocked in silence); a subdomain needs
  a DNS record the owner preferred not to add. The host's own name serves.

## Implementation references

- `apps/web/scripts/build-article-images.mjs`, `apps/web/src/lib/blog/article-images.ts`,
  `apps/web/src/components/blog/ArticleIllustration.tsx`,
  `apps/web/src/data/__tests__/blog-article-images.guard.test.ts`
- `apps/web/src/lib/landing/media.ts`, `media-origin.ts`, `beats-schema.ts`, `beat-sync.ts`
- `apps/web/src/app/api/landing-media/route.ts`, `beats/route.ts`
- `apps/web/src/components/landing/video/LandingVideo.tsx`, `use-landing-video.ts`,
  `LandingVideoSection.tsx`; the choreography in `apps/web/src/styles/globals.css`
- `apps/web/src/lib/csp.ts` (`media-src`), `apps/web/e2e/smoke/landing-video.spec.ts`
- `scripts/assets/encode_landing_video.py`, `apps/api/tests/unit/scripts/test_encode_landing_video_*.py`
- `LANDING_MEDIA_BASE_URL` in `.env.example`, `.env.prod.example`, the demonstrator's
  env files, `docker-compose.prod.yml`, `docker-compose.demo-instance.yml`
