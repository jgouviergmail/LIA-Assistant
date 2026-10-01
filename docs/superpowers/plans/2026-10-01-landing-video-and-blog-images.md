# Landing video, beat-synced titles, static blog illustrations — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (the owner works inline, no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Status (2026-10-01):** executed and verified on Docker dev and the hermetic e2e build; the
renditions are encoded in `exports/landing-media/` (outside git). Still open, gated on the
author's accord for hosting a copy: the Metaclaude push (bumped to 0.95.0), the host apply
(`install-app.sh`, `.env`, `scp`), and `LANDING_MEDIA_BASE_URL` on the Pi. The 29th article
(`tabular-administration`) still needs an illustration.

**Goal:** Show an AI-generated video between the hero and the promise section of the landing — autoplay, muted, looping, with play/pause and sound controls and a credit line — hosted on a media origin the operator DECLARES at runtime, with the section titles pulsing on the music's beats while the sound is on; serve the blog illustrations as pre-generated static variants; let the use-cases intro span its column.

**Architecture:** The public pages are statically generated (B03 host-neutral image), so the video's location is read at REQUEST time by a tiny Next route handler (`/api/landing-media`) that fetches, validates and caches a `manifest.json` the operator hosts beside the files (`LANDING_MEDIA_BASE_URL`); the client section mounts only when a descriptor comes back. The beat map is produced OFFLINE by the encoding script (numpy, no new dependency), hosted beside the video, proxied by a second route and loaded only when the sound is switched on; the animation reads the presented frame's time (`requestVideoFrameCallback`) and writes ONE custom property on `<main>`; the titles move with `transform` alone. Blog illustrations become four WebP widths plus a 1200×675 social JPEG per article, generated once by a sharp script and served through `<img srcset>` — no runtime image work on the host, edge-cacheable by extension.

**Tech Stack:** Next.js 16 (App Router, route handlers), React 19 (`preload` from `react-dom`), zod 4, vitest + Testing Library, Playwright (hermetic e2e), sharp 0.35 (script only), ffmpeg (libsvtav1, libx264, libwebp), numpy (beat map), Caddy 2.11 (Metaclaude VPS).

**Spec:** this conversation (2026-10-01) — the measured decisions are restated in the ADR this plan adds (`docs/architecture/ADR-330-Landing-Media-Served-Without-Runtime-Work.md`).

## Global Constraints

- Nothing owner-specific in code or in the public image: the media origin is a runtime env var (`LANDING_MEDIA_BASE_URL`), unset = no section; the video's names, credit and beat map travel in the hosted manifest, never in the repository.
- CSP is built at compile time: `media-src` gains `https:` (as `img-src` already has); COEP stays `credentialless`; the media origin also sends `Cross-Origin-Resource-Policy: cross-origin`.
- No autoplay under `prefers-reduced-motion: reduce` or `navigator.connection.saveData`; sound only on a user gesture; muted video pauses when out of view, a video with sound keeps playing and gets a floating control.
- Beat animation: `transform` only, on `main h2`, at most 2 px / 1.8 % scale, only while playing with sound, never under reduced motion.
- Six languages for every new string (`landing.video.*`), inserted as TEXT at the `"promise": {` anchor (lia-i18n skill: no load/dump rewrite).
- Blog images: widths `[480, 768, 1024, 1536]` WebP + `-og.jpg` 1200×675; the 28 PNG masters leave `public/` (git history keeps them); `sizes` match the real grids.
- Every gate stays green: `task lint`, `task test:frontend`, `task test:frontend:coverage` thresholds, the ratchets, `test_doc_maps_guard.py`, the e2e landing specs.

## Review Focus

1. The manifest origin is down or slow at request time → the route answers `{ video: null }` within 3 s and caches the failure for 60 s; the page never waits. (Task 5 test: fetch rejects / times out.)
2. A manifest naming a file outside its directory (`../x.mp4`, `https://other.host/x.mp4`) → the file is REJECTED, not resolved. (Task 4 test.)
3. No rendition the browser can play (old Safari, AV1-only manifest) → the `<video>` `error` event hides the section; no broken box. (Task 7 test.)
4. `play()` refused by the browser (Low Power Mode) → poster + play button, no spinner, no retry loop. (Task 7 test.)
5. A blog slug without its generated variants → a guard test reads `public/articles` against `BLOG_ARTICLES` and fails the build. (Task 3 test.)

---

### Task 1: Use-cases intro spans its column

**Files:**
- Modify: `apps/web/src/components/landing/UseCasesSection.tsx:20-26`

- [x] **Step 1: Edit** — wrapper `className="mb-8 max-w-3xl"` → `className="mb-8"`; lead `className="mt-4 max-w-[65ch] leading-relaxed text-muted-foreground"` → `className="mt-4 text-pretty leading-relaxed text-muted-foreground"`.
- [x] **Step 2: Measure in Docker dev** (Playwright script from `apps/web/e2e`, `ignoreHTTPSErrors`): at 1280/1536/1920 the `h2` and `p` widths equal the container's content width (1088) and the `h2` is on one line. Expected: `h2 1088px/1 line`.

### Task 2: Blog illustration module and component

**Files:**
- Create: `apps/web/src/lib/blog/article-images.ts`
- Create: `apps/web/src/lib/blog/__tests__/article-images.test.ts`
- Create: `apps/web/src/components/blog/ArticleIllustration.tsx`
- Create: `apps/web/src/components/blog/__tests__/ArticleIllustration.test.tsx`

**Interfaces (produces):**
```ts
export const ARTICLE_IMAGE_WIDTHS: readonly [480, 768, 1024, 1536];
export const ARTICLE_SOCIAL_IMAGE: { readonly width: 1200; readonly height: 675 };
export function articleImageSrc(slug: string, width: ArticleImageWidth): string; // `/articles/${slug}-${width}.webp`
export function articleImageSrcSet(slug: string): string;                        // "…-480.webp 480w, …"
export function articleSocialImageSrc(slug: string): string;                     // `/articles/${slug}-og.jpg`
export const ARTICLE_CARD_SIZES = '(max-width: 640px) 100vw, (max-width: 880px) 50vw, (max-width: 1024px) 33vw, 300px';
export const LANDING_CARD_SIZES = '(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 390px';
export const ARTICLE_HERO_SIZES = '(max-width: 768px) 100vw, 768px';
// <ArticleIllustration slug alt sizes priority? className? />  → <img srcSet sizes loading decoding fetchPriority>
```

- [x] **Step 1: Failing tests** — `articleImageSrcSet('x')` equals `'/articles/x-480.webp 480w, /articles/x-768.webp 768w, /articles/x-1024.webp 1024w, /articles/x-1536.webp 1536w'`; `articleSocialImageSrc('x')` is `/articles/x-og.jpg`; the component renders `loading="lazy" decoding="async"` by default and `loading="eager" fetchpriority="high"` with `priority`.
- [x] **Step 2: Run** `cd apps/web && pnpm vitest run src/lib/blog src/components/blog` → FAIL (module missing).
- [x] **Step 3: Implement** the module and the component (`<img>` with the `// eslint-disable-next-line @next/next/no-img-element -- pre-generated static variants, no optimizer` precedent).
- [x] **Step 4: Run** the same tests → PASS.

### Task 3: Generate the variants, switch the three callers and the metadata, guard the set

**Files:**
- Create: `apps/web/scripts/build-article-images.mjs` (sharp; input dir of masters → `public/articles/`)
- Modify: `apps/web/src/components/blog/BlogCard.tsx:2,41-50`, `apps/web/src/components/landing/ShuffledBlogGrid.tsx:5,60-68`, `apps/web/src/components/blog/BlogArticleContent.tsx:2,57-66`
- Modify: `apps/web/src/app/[lng]/blog/[slug]/page.tsx:53-55,76,114` (social JPEG, true dimensions)
- Create: `apps/web/src/data/__tests__/blog-article-images.guard.test.ts` (every slug has 4 variants + og)
- Delete: `apps/web/public/articles/*.png` (masters moved to `exports/articles-masters/`, gitignored)
- Modify: `.claude/skills/lia-design/readme.md:183` (the format and the count), `docs/technical/LANDING_PAGE.md` (§ Illustrations du blog: script, widths, sizes, social image)

- [x] **Step 1: Guard test first** — reads `BLOG_ARTICLES` and asserts `existsSync(public/articles/<slug>-<w>.webp)` for the four widths and `-og.jpg`. Run → FAIL (no files yet).
- [x] **Step 2: Script** — for each `*.png` in the input dir: `sharp(master).resize({ width: w }).webp({ quality: 82, effort: 6 })` ×4 and `.resize(1200, 675, { fit: 'cover' }).jpeg({ quality: 82, mozjpeg: true })`. Run: `node apps/web/scripts/build-article-images.mjs exports/articles-masters` → 140 files, ~10 MB.
- [x] **Step 3: Callers** — replace `next/image` with `<ArticleIllustration>` (card: `ARTICLE_CARD_SIZES`, landing grid: `LANDING_CARD_SIZES`, hero: `ARTICLE_HERO_SIZES` + `priority`), add `preload(articleImageSrc(slug, 1024), { as: 'image', imageSrcSet, imageSizes: ARTICLE_HERO_SIZES, fetchPriority: 'high' })` from `react-dom` in `BlogArticleContent`.
- [x] **Step 4: Metadata** — `imageUrl = origin ? `${origin}${articleSocialImageSrc(slug)}` : null`, width/height from `ARTICLE_SOCIAL_IMAGE`, JSON-LD `image` likewise.
- [x] **Step 5: Run** guard + blog tests → PASS; `task lint:frontend`; in Docker dev open `/fr/blog` and `/fr/blog/<slug>`: the network panel shows `.webp` candidates sized to the grid, the hero preloaded.

### Task 4: Landing media descriptor (pure) and CSP

**Files:**
- Create: `apps/web/src/lib/landing/media.ts` (zod schema of the hosted manifest, `resolveLandingMedia(manifest, baseUrl)` → `LandingVideoDescriptor`)
- Create: `apps/web/src/lib/landing/__tests__/media.test.ts`
- Modify: `apps/web/src/lib/csp.ts:158` (`media-src 'self' data: blob: https:`), `apps/web/src/lib/__tests__/csp.test.ts` (new `it`)

**Interfaces (produces):**
```ts
export interface LandingRendition { src: string; type: string; minWidth?: number }
export interface LandingVideoDescriptor {
  poster: string; renditions: LandingRendition[]; aspectRatio: [number, number];
  durationSeconds: number | null; hasBeats: boolean;
  credit: { label: string; url: string } | null; aiGenerated: boolean;
}
export const landingMediaManifestSchema: z.ZodType<LandingMediaManifest>;
export function resolveLandingMedia(manifest: unknown, baseUrl: string): LandingVideoDescriptor; // throws on invalid
export function resolveMediaFile(baseUrl: string, name: string): string; // rejects '/', '..', '://', '?' in name
```

- [x] **Step 1: Failing tests** — a valid manifest resolves every `src` and `poster` to `${base}/${name}`; `credit.url` must be `https:`; a name with `..`, a leading `/`, a `://` or a `?` throws; `hasBeats` is true iff `beats` names a file; `aspectRatio` defaults to `[16, 9]`.
- [x] **Step 2: Run** → FAIL. **Step 3: Implement** with zod 4. **Step 4: Run** → PASS.
- [x] **Step 5: CSP** — add `'https:'` to `media-src`, test `expect(prod.get('media-src')).toEqual(expect.arrayContaining(["'self'", 'blob:', 'data:', 'https:']))`, run `pnpm vitest run src/lib/__tests__/csp.test.ts` → PASS.

### Task 5: Runtime routes `/api/landing-media` and `/api/landing-media/beats`

**Files:**
- Create: `apps/web/src/lib/landing/media-origin.ts` (server-only: reads `LANDING_MEDIA_BASE_URL`, validates `http(s)` origin, strips trailing `/`; `fetchJsonCached(url, ttlMs)` with a module-level Map, 3 s timeout via `AbortSignal.timeout`, negative cache 60 s)
- Create: `apps/web/src/app/api/landing-media/route.ts` (`GET` → `{ video: LandingVideoDescriptor | null }`, `Cache-Control: public, max-age=300`, `export const dynamic = 'force-dynamic'`)
- Create: `apps/web/src/app/api/landing-media/beats/route.ts` (`GET` → the validated beat map or 404)
- Create: `apps/web/src/lib/landing/beats-schema.ts` (`{ version: 1, beats: [number, number, boolean][] }`, ms ascending, weight 0..1, ≤ 20 000 entries)
- Create: `apps/web/src/app/api/landing-media/__tests__/route.test.ts`

- [x] **Step 1: Failing tests** (`vi.stubEnv`, `vi.stubGlobal('fetch', …)`): unset env → `{ video: null }` and fetch never called; a manifest → descriptor with absolute URLs; a 500 / a timeout → `{ video: null }`; the second call within the TTL does not fetch again; `/beats` → 404 without video, 200 with the parsed map, 404 on an invalid map.
- [x] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [x] **Step 5: Env plumbing** — `.env.example` and `.env.prod.example` (documented, empty by default), `docker-compose.prod.yml` web `environment` (`- LANDING_MEDIA_BASE_URL=${LANDING_MEDIA_BASE_URL:-}` with the SEC-037 comment), the two demo env examples (empty), `docker-compose.demo-instance.yml` if its web service lists env explicitly.

### Task 6: Beat engine (pure) and the title choreography CSS

**Files:**
- Create: `apps/web/src/lib/landing/beat-sync.ts`
- Create: `apps/web/src/lib/landing/__tests__/beat-sync.test.ts`
- Modify: `apps/web/src/styles/globals.css` (after `.cosmos .landing-section` rules)

**Interfaces (produces):**
```ts
export const BEAT_ATTACK_MS = 40; export const BEAT_DECAY_MS = 180; export const BEAT_BAR_GAIN = 1.25;
export function createBeatTrack(map: BeatMap): BeatTrack;           // { intensityAt(seconds: number): number }  in [0, 1]
export function startBeatDriver(video: HTMLVideoElement, host: HTMLElement, track: BeatTrack): () => void;
// host gets data-beat="" while running and style --beat; the returned function stops and cleans up.
```
Envelope: `e = elapsed_ms ≤ attack ? elapsed/attack : exp(-(elapsed-attack)/decay)`; intensity = `min(1, weight × (bar ? BAR_GAIN : 1) × e)`; binary search of the last beat ≤ t; `t < first beat` → 0.

- [x] **Step 1: Failing tests** — at a beat's time + 40 ms the intensity equals the weight; it decays to < 0.05 after 700 ms; before the first beat it is 0; a bar beat of weight 0.8 peaks at 1; the lookup is monotonic in time (random probes vs a linear scan).
- [x] **Step 2: Run** → FAIL. **Step 3: Implement** (driver: `requestVideoFrameCallback` when present → `{mediaTime, now}`; a rAF loop extrapolates `mediaTime + (performance.now() - now)/1000`; fallback `video.currentTime`; writes `host.style.setProperty('--beat', v.toFixed(3))` only when it changed by > 0.005). **Step 4: Run** → PASS.
- [x] **Step 5: CSS**
```css
/* Beat-synced titles (ADR-330): one custom property written by the video
   section's driver, read by every section title; transform only. */
.cosmos main[data-beat] h2 {
  will-change: transform;
  transform-origin: 0 60%;
  transform: translateY(calc(var(--beat, 0) * -2px)) scale(calc(1 + var(--beat, 0) * 0.018));
}
.cosmos main[data-beat] .text-center h2 { transform-origin: 50% 60%; }
@media (prefers-reduced-motion: reduce) { .cosmos main[data-beat] h2 { transform: none; will-change: auto; } }
```

### Task 7: The video section, its controls, the floating pill, the strings

**Files:**
- Create: `apps/web/src/components/landing/video/LandingVideoSection.tsx` (server: labels from i18n → client)
- Create: `apps/web/src/components/landing/video/LandingVideo.tsx` (`'use client'`)
- Create: `apps/web/src/components/landing/video/use-landing-video.ts` (state machine hook: `idle → ready → playing | paused`, `muted`, `nearViewport`, `inView`, `userIntent`)
- Create: `apps/web/src/components/landing/video/__tests__/LandingVideo.test.tsx`
- Modify: `apps/web/src/app/[lng]/page.tsx` (mount after `<CosmosHero>`), `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (block `landing.video` before `"promise": {`), `docs/technical/LANDING_PAGE.md` (§3 list, new §10)

Strings (`landing.video.*`): `aria_label`, `play`, `pause`, `unmute`, `mute`, `ai_disclosure`, `credit_prefix`, `now_playing`, `back_to_video`, `external_link` (sr-only "opens in a new window"). Insert with a Python script FILE (never a heredoc), one block per language, then `json.loads` and assert `landing.hero.cta_star` and `landing.promise.eyebrow` are unchanged.

Behaviour:
- mount → `fetch('/api/landing-media')`; `video: null` → render nothing.
- descriptor → `<section id="video" class="landing-section scroll-mt-24 py-10 sm:py-14">` with the same container as the promise section; a `rounded-2xl border border-border/70 bg-background/80 shadow-sm overflow-hidden aspect-video` box; `<video playsInline muted loop preload="none" poster aria-label>` with `<source>` children attached only when the box is within 600 px (IntersectionObserver) and the page has loaded (`document.readyState === 'complete'` or the `load` event); then `video.play()` unless reduced motion or Save-Data; a rejected `play()` leaves the poster and the play button.
- `<source>` list: renditions whose `minWidth` is undefined or ≤ `window.innerWidth` (if none, all), in manifest order.
- controls (bottom-right overlay, `backdrop-blur`, `Button variant="secondary" size="icon"` with lucide `Play`/`Pause`, `Volume2`/`VolumeX`, `aria-pressed` on the sound button, translated `aria-label`); `error` on the video → section removed.
- out of view: muted → `pause()` (resume on re-entry unless the user paused); sound on → keeps playing and a fixed pill (portal to `document.body`, `role="group"` with `now_playing`, pause + mute buttons + a `back_to_video` link to `#video`) appears; `visibilitychange` hidden → pause when muted.
- sound on → `import('@/lib/landing/beat-sync')` + `fetch('/api/landing-media/beats')` once → `startBeatDriver(video, video.closest('main'), track)`; stopped on mute, pause, unmount, reduced motion.
- caption under the box: `<p class="mt-3 text-xs text-muted-foreground">` `{ai_disclosure}` · `{credit_prefix} <a href rel="noopener noreferrer" target="_blank">{label}<ArrowUpRight/> <span class="sr-only">{external_link}</span></a>`.

- [x] **Step 1: Failing tests** (jsdom; `HTMLMediaElement.prototype.play/pause/load` mocked; `IntersectionObserver` stubbed; `fetch` stubbed): nothing renders on `{video:null}`; renders the section with the credit link and the controls' names; the sources respect `minWidth`; reduced motion → `play` not called; play/pause button toggles; the sound button sets `muted=false` and `aria-pressed`; `error` on the video removes the section.
- [x] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. **Step 5:** `task lint:frontend` (a11y + hooks + complexity ratchets).

### Task 8: Hermetic e2e

**Files:**
- Create: `apps/web/e2e/fixtures/media/clip.mp4` (ffmpeg: `testsrc=size=64x36:rate=24` 2 s + `sine=440` 2 s, libx264 + aac, ~15 KB), `clip-poster.webp`, `clip-beats.json`
- Create: `apps/web/e2e/smoke/landing-video.spec.ts`

- [x] **Step 1: Spec** — `page.route('**/api/landing-media', …)` → descriptor with same-origin fixture URLs served by `page.route('**/e2e-media/**')`; `landing-media/beats` → the fixture map. Tests: (a) `{video:null}` → no `#video`; (b) the section mounts, `video` has `muted`/`loop`/`playsinline`, the play/pause button toggles `paused`, the sound button unmutes, scrolling to the finale shows the pill and its pause button pauses the video, axe (`scan.ts`) reports no blocking violation on the section; (c) `reducedMotion: 'reduce'` → the video stays paused until the play button is pressed.
- [x] **Step 2: Run** against the e2e standalone build (`apps/web/e2e/README.md`, port 3100) → PASS.

### Task 9: Encoding, poster, beat map, manifest, provenance (script)

**Files:**
- Create: `scripts/assets/encode_landing_video.py` (`--source`, `--out`, `--name`, `--credit-label`, `--credit-url`, `--ai-generated`; ffmpeg + ffprobe + numpy)
- Create: `apps/web/public/.gitignore` entry? No — add `apps/web/public/landing-media-dev/` to the root `.gitignore` (local fixture location, bind-mounted into the dev container).

Outputs in `--out`: `<name>-<sha12>-1080p.av1.mp4` (libsvtav1 preset 6 crf 48, 10-bit, g 240), `<name>-<sha12>-1080p.h264.mp4` (libx264 slow crf 29, High), `<name>-<sha12>-720p.av1.mp4` (crf 42), `<name>-<sha12>-720p.h264.mp4` (crf 27), all `-c:a aac -b:a 128k -movflags +faststart`; `<name>-<sha12>-poster.webp` (frame 0, 1600 px, q 78); `<name>-<sha12>-beats.json`; `manifest.json` (codecs strings from ffprobe: `av01.0.<level:02d>M.<bitdepth:02d>`, `avc1.<profile_idc:02x>00<level_idc:02x>`); `PROVENANCE.json` (source sha256, encoder lines, generated_at, credit).

Beat map: mono 22 050 Hz via ffmpeg pipe → STFT (2048/256) → 40 log-spaced bands, log-magnitude, half-wave rectified flux → tempo per 10 s window by autocorrelation in 60–180 BPM → dynamic-programming beat tracking (Ellis 2007, local period) → each beat snapped to the strongest onset within ±30 ms → weight = onset strength scaled to its 95th percentile, bar = the phase (mod 4) maximising low-band energy. Entries `[ms, weight, bar]`.

- [x] **Step 1: Run** `apps/api/.venv/Scripts/python scripts/assets/encode_landing_video.py --source exports/Underclass.mp4 --out exports/landing-media --name underclass --credit-label @anabology --credit-url https://x.com/anabology --ai-generated` (≈ 15 min). Expected sizes: 1080p AV1 ≈ 150 MB, 1080p H.264 ≈ 220 MB, 720p ≈ 85 / 115 MB, poster ≤ 200 KB, beats ≈ 10 KB.
- [x] **Step 2: Verify** the beat map on the audio: the first 20 beats fall on onsets (print the onset strength at each beat vs the mean), tempo ≈ 129 BPM then ≈ 136 BPM after 120 s.
- [x] **Step 3: Dev proof** — copy `exports/landing-media/` to `apps/web/public/landing-media-dev/`, set `LANDING_MEDIA_BASE_URL=https://localhost:3000/landing-media-dev` in `.env`, recreate `lia-web-dev`; a Playwright script measures: the section is mounted, the chosen `<source>`s, `video.paused === false` after scrolling near, `--beat` on `main` changes between two frames with the sound on, CPU of the rAF loop (< 0.3 ms per frame via `performance.now()` deltas).

### Task 10: Metaclaude — an optional static media route (separate repository)

**Files (D:\Developpement\Metaclaude):**
- Modify: `docker/Caddyfile` (`handle_path {$METACLAUDE_MEDIA_PREFIX:/.metaclaude-media-off}/* { root * /srv/media; header Cache-Control "public, max-age=31536000, immutable"; header Cross-Origin-Resource-Policy "cross-origin"; file_server }` inside `(site)` before the websocket route, with the comment explaining the inert default)
- Modify: `compose.yml` (proxy `environment: METACLAUDE_MEDIA_PREFIX`, `volumes: - ${METACLAUDE_MEDIA_DIR:-metaclaude-media}:/srv/media:ro`, named volume `metaclaude-media`)
- Modify: `.env.example` (the two variables, documented like `METACLAUDE_ALT_SITE`), `docs/DEPLOYMENT.md` (§ "Serving a static directory beside the app"), `CHANGELOG.md` (`[Unreleased]` → Added)
- Run: `./deploy/check.sh` (every `{$METACLAUDE_*}` forwarded), `node deploy/ratchets.mjs`, `node deploy/bump.mjs minor`.

Host apply (after the owner's push and the author's accord): one SSH session — `git -C <clone> pull`, `sudo ./deploy/install-app.sh`, `.env`: `METACLAUDE_MEDIA_PREFIX=/media`, `METACLAUDE_MEDIA_DIR=/srv/lia-media`, `sudo docker compose up -d proxy`; `scp` the output dir to `/srv/lia-media/lia/landing/`; verify from the laptop: `curl -sI https://myclaude.jeyswork.com/media/lia/landing/manifest.json` → 200, `Cache-Control: … immutable`, `Cross-Origin-Resource-Policy: cross-origin`, a Range request → 206.

### Task 11: ADR-330, maps, pointers, gates

**Files:**
- Create: `docs/architecture/ADR-330-Landing-Media-Served-Without-Runtime-Work.md`
- Modify: `docs/architecture/ADR_INDEX.md`, `CLAUDE.md` (2–4 lines + pointer), `AGENTS.md` via `task docs:sync-agents`, `apps/web/src/data/maps/history.json` + `text/history.{fr,en,de,es,it,zh}.json`, then `task docs:maps`, `task release:sync-counts` (ADR count).
- Gates: `task lint`, `task test:frontend`, `task test:frontend:coverage`, `cd apps/api && .venv/Scripts/pytest tests/unit/test_doc_maps_guard.py -q`, the three landing e2e specs + the new one.
