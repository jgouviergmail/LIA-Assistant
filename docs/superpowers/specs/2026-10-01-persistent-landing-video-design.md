# Persistent landing video and beat-driven effects — design

Owner request (2026-10-01): the landing video and its music keep playing while the
visitor moves between the public pages, every visited page's titles beat with it,
it stops by itself on the sign-in page; and six beat-driven effects (C, D, E, G, H,
J of the proposal) when the video plays with its sound on.

Amends ADR-330. Measured facts this design rests on: the public pages share ONE
layout (`app/[lng]/layout.tsx`); twelve pages plus the maps wear the `.cosmos` skin
and compose their own header and footer; the `(auth)` group and the dashboard have
their own layouts under the same root; a language switch is a `router.push`, so the
`[lng]` layout re-renders with another param and its client tree remounts.

## 1. One `<video>` element for the whole visit

- `LandingVideoHost` (client) is mounted by the root layout around `{children}`.
  It owns the `<video>` element and a context through which the landing's section
  REGISTERS its frame. The element is created once per layout instance and never
  re-parented: React keeps it across `Link` navigations.
- The landing page keeps its section (`#video`): it fetches the descriptor
  (`/api/landing-media`, as today), draws an EMPTY frame of the right aspect ratio
  — the slot — and the caption under it, and registers `{ element, video }` with
  the host on mount, unregistering on unmount. Nothing else of the video is in the
  page; no page but the landing ever asks the server about it.
- The host positions the player over the slot in DOCUMENT coordinates
  (`position: absolute` on the body, `top/left/width/height` from the slot's rect +
  the scroll offsets): it scrolls with the page natively, no per-scroll work, and
  is re-measured on resize, on a `ResizeObserver` of the slot and of the body.
  Framed, the controls sit in the frame's corner as before.
- With no slot on the page (any other public page, or the landing scrolled past
  the frame) and the music on, the player DOCKS: `position: fixed`, bottom-left
  (the eyes keep the right), a small thumbnail of the same element with pause,
  sound, « back to the video » (a `Link` to `/{lng}#video`, client-side so the
  element survives) and close. Muted or paused, with no slot, it hides — a muted
  video out of view was already paused (ADR-330 §3): the dock generalises
  « off-screen with the sound on » to every page.
- Close = the visitor's pause: the dock goes, the element stays paused and
  hidden; back in the frame, the play button is the way in (no autoplay after a
  close).
- Route gate: the player exists on the PUBLIC pages only — a declared list
  (`lib/landing/player-routes.ts`), every top-level route under `app/[lng]` named
  on one side or the other by a test, so a page added later must choose. On a stop
  route (sign-in and the other `(auth)` pages, the dashboard, `/share`,
  `/account-inactive`) the element is paused and unmounted.
- A language switch or a full reload remounts the host. The player records
  `{ time, sound, at }` in `sessionStorage` on unmount and on `pagehide`; a fresh
  host finding a record younger than `PLAYER_RESUME_MAX_AGE_MS` and a slot resumes
  at that time, with the sound when it was on (the visitor had already clicked).
- The playback policy (`useVideoPlayback`) is unchanged in its rules; its two
  observers watch the SLOT element (`near`, sticky; `in view`), and « no slot »
  reads as « out of view ».

## 2. The beat reaches every page

- The driver writes on `document.documentElement` (`:root`), no longer on the
  landing's `<main>`: `--beat` (every beat), `--beat-bar` (the bar beats alone),
  `--beat-hue` (degrees, ±8° on a four-bar cycle), and `data-beat` while it runs.
- The stylesheet reads `:root[data-beat] .cosmos …`: the hero's lines and every
  `h2` as today, on every page wearing the skin.

## 3. The six effects (sound on, `transform` / `opacity` only, nothing under reduced motion)

| | Where | What |
|---|---|---|
| C | the video frame (`.landing-video-frame::after`) | a pre-painted glow ring whose opacity follows `--beat`, stronger on `--beat-bar` |
| D | the header logo (`.landing-logo`) | `scale(1 + 0.08·beat)` — a heartbeat |
| E | the ghost words (`.cosmos-ghost-frame`) | `scale(1 + 0.025·beat)` and opacity `0.75 + 0.25·beat` on the FRAME (the word's own transform belongs to the scroll drift) |
| G | the chat mockup's active step dot (`.cosmos-demo-step-dot`) | `scale(1 + 0.6·beat)` |
| H | the chapter rail's active numeral (`.cosmos-chapter-rail [aria-current]`) | `scale(1 + 0.35·beat)` |
| J | the signature gradient text (`.cosmos-grad-text`) | `filter: hue-rotate(var(--beat-hue))` |

Every rule is guarded by `:root[data-beat]`; the driver never runs under reduced
motion, and the reduced-motion media query neutralises the rules again.

## 4. Out of scope, in writing

- An animated transition between the frame and the dock (a FLIP across two
  positioning schemes): the swap is instant, like the pill was.
- A caption track; the dashboard; the native shells (the WebView loads the same
  pages, nothing shell-specific is added).
