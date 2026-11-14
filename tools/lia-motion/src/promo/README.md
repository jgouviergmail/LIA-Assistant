# LIA promotional film — « Ton quotidien. LIA garde le fil. »

A 114-second motion-design film in French, 1920 × 1080 at 60 fps, cut to the
measured beat grid of an original soundtrack. Since 2026-11-14 it is the
landing's presentation film and opens the repository's README (ADR-341
amendment). Its thread speaks to everyone: six chapters, each a strong scene and then an illustrated
enumeration of the capabilities behind it, before everything links up.

Unlike the earlier presentation film, the product screens here move: they are
rebuilt at 1.6× the application's scale from the current captures
(`apps/web/public/screenshots`), with the interface's French labels, the domain
colour code (`apps/web/src/lib/domain-tone.ts`), Lucide chrome, filled Material
Symbols in cards and the companions' real rig (`@/components/eyes`). All names
and data are fictitious; no account or provider is contacted.

The companions (`parts/Companion.tsx`) are drawn at their native size — the
skin is em-based, so a frame size is a font size, never a scaled bitmap — with
bodies taken from the reviewed originals at 1024 px (`public/promo/companions`,
hashes checked against the application's manifests, see its `PROVENANCE.json`)
instead of the 192 px the application ships for its widget. Their faces are
played by the product's rig runtime, stepped at 60 Hz from each script's origin
(deterministic and cached): expressions, gaze, nods, gestures, blinks.

## Story, on the beat grid (`timing.ts`)

| Beats | Seconds | Section | Message |
| --- | --- | --- | --- |
| 0-15 | 0-8 | `Opening` (hook) | Ten domains, one per beat: « Ton quotidien est éparpillé. » |
| 16-23 | 8-12 | `Opening` (reveal) | The thread links them on the drop: « LIA garde le fil. » |
| 24-47 | 12-24 | `Context` | The dashboard builds itself; the thread links its sources; memory |
| 48-63 | 24-32 | `Chapter` 1 | « Les autres répondent. LIA te connaît. » — memory, interests, habits, commitments, portrait, psyche, personalities and avatars |
| 64-95 | 32-48 | `Action` | One sentence, three specialists in parallel, one click on « Confirmer » |
| 96-111 | 48-56 | `Chapter` 2 | « Elle fait le travail. » — documents, images, skills, MCP and plugins, knowledge spaces, context menus, interactive pages |
| 112-127 | 56-64 | `Anticipate` | On the phone, LIA writes first; one tap decides (the breakdown) |
| 128-143 | 64-72 | `Chapter` 3 | « Elle n'attend pas que tu demandes. » — proactive notifications and discussions, reminders, routines by time, condition or webhook, push, radio |
| 144-151 | 72-76 | `Simple` | Computer and phone, four settings in four clicks |
| 152-167 | 76-84 | `Chapter` 4 | « Partout avec toi. » — Live and Live direct, calls, Telegram, SMS, the mobile apps, the World, six languages |
| 168-179 | 84-90 | `Chapter` 5 | « Ton cercle, connecté. » — relayed messages, connections, read-only sharing, shared capabilities, access log |
| 180-195 | 90-98 | `Chapter` 6 | « Tout est tracé. » — registers, cost, human validation, export, security, dashboards, open source |
| 196-215 | 98-108 | `Linked` | Twenty-four capabilities around LIA: « Tout est relié. » (riser and build) |
| 216-227 | 108-114 | `Outro` | « Ton quotidien. LIA garde le fil. Tu gardes la main. » on the final hit |

Every word on screen lives in `copy.ts`; claims are the landing's own
(`landing.*` in `apps/web/locales/fr/translation.json`). Another language is
another copy object and another reviewed render.

## Render

From `tools/lia-motion`, with Node 24 and FFmpeg on the path:

```powershell
node scripts/render-promo.mjs stills 480 1770 4200   # review stills
node scripts/render-promo.mjs inspect 0 6839 20      # text overflow / edge / overlap audit
node scripts/render-promo.mjs render 0 719           # one section (repeat per range)
node scripts/render-promo.mjs audio                  # music + effects, ducked, -14 LUFS / -1.5 dBTP
node scripts/render-promo.mjs mux                    # master MP4 (CRF 14) + verification.json
node scripts/render-promo.mjs web                    # review/web MP4 (CRF 20), audio from the mix
```

Outputs go to `exports/lia-motion/promo/` (ignored by Git). Sections are
rendered as separate chunks so one can be redone alone; `mux` concatenates the
chunks in order and adds the mix.

## Sound

`sound.ts` places each effect so that its measured peak lands on its visual
event, and lists the three gestures under which the music dips briefly (send,
confirm, the tap on « Oui, vas-y »). The music, the effects and the generated
image are recorded with their prompts, generation ids and hashes in
`public/audio/promo/PROVENANCE.json`.
