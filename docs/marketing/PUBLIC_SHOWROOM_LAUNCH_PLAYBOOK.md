# Public Showroom Launch Playbook (P0)

**Status:** Operational checklist — publication stays blocked until the P0 launch gate is green
**Technical guide:** [GUIDE_SHOWROOM.md](../guides/GUIDE_SHOWROOM.md) — how the showroom is built, every setting, deployment, and day-to-day operation
**Campaign:** Ask. Approve. Verify. — see `docs/superpowers/specs/2026-08-05-public-showroom-campaign-brief.md` (measurement contract, channel strategy, decision gates)
**Program:** `docs/superpowers/specs/2026-08-05-public-web-showroom-program.md`

## 1. Positioning (verbatim, every channel)

> LIA turns a personal intention into controlled action, shows what it did, respects every refusal, and can be self-hosted.

The flagship is the guided mission set on `/demo` — six missions, one per differentiating mechanism (orchestration, proactivity, memory, outbound calls, rich replies, in-app settings), the overloaded morning first among them. Each is **guided and synthetic**: a deterministic client-only storyboard over the real HITL, trace and rich-reply UI contracts. It is never described as live inference, and installation copy says *View source and current setup* — never *Install in one command* — until the installer gates pass (see the audit addendum, gates G0-G6).

## 2. Launch-day checklist (all MUST pass before enabling `guided`)

Technical gates:

- [ ] `task test:frontend` green (unit suites incl. showroom, product-telemetry, demo page).
- [ ] `task test:e2e:showroom` green — CLEAN telemetry-OFF build: zero `/api/v1` call across every decision path, axe dark+light without serious/critical findings, no overflow 320→1280, six locales.
- [ ] `task test:e2e:showroom:telemetry` green — CLEAN telemetry-ON build: the ONLY API traffic is the credential-less `POST /api/v1/product/showroom-events` (no Cookie/Authorization), `202` contract.
- [ ] Backend product suite green (`pytest tests/unit/domains/product`).
- [ ] `task lint:i18n` green (six-locale parity).
- [ ] Release Web build sets `NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=guided`, `NEXT_PUBLIC_PRODUCT_TELEMETRY=true`, and `NEXT_PUBLIC_SHOWROOM_PROOF_SHA=<full 40-hex source SHA>` (no fake value is ever committed; if a release tag is displayed, CI resolves `tag^{commit}` and requires equality).
- [ ] Every SHA-based proof URL answers HTTP 200 in release CI (source-link verification, not a DEV/PROD call).

Deployment dependencies (discovered in the 2026-08-06 consolidation — easy to miss):

- [ ] The hosted API runs with `PRODUCT_ANALYTICS_ENABLED=true`, otherwise the collector route is not mounted and every funnel attempt silently 404s (mission behavior is unaffected — but measurement is lost).
- [ ] The hosted Web build keeps its ordinary Web Vitals stream (`NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE` as deployed); that stream goes through the credentialed `/product/events` route, is EXCLUDED from the showroom funnel, and is disclosed (campaign brief §8.4).
- [ ] CDN / tunnel / reverse-proxy access-log policy for `/api/v1/product/showroom-events` is inventoried and disclosed; disable or redact where supported; never join infrastructure logs to the funnel (program §9.1).

Honesty gates:

- [ ] The labels *Guided demonstration*, *Synthetic data*, *No external action* are visible at every mission phase (e2e-asserted).
- [ ] A bounded text search over README/release/launch copy finds `live AI`, `real inference`, `one command`, `docker compose up` ONLY as warnings against the claim, never as promotion.
- [ ] Zero unresolved material honesty complaint at publication time.

## 3. Launch assets (produced from the hermetic capture)

Run `task test:e2e:showroom:capture` — artifacts land in Playwright's output directory (never committed):

- canonical sub-60s mission video (1440×900, real pacing, approve email / refuse calendar);
- `showroom-receipt.png` (refusal respected) and `showroom-proof.png` (drawer) stills;
- cut a 15-second approval/refusal excerpt from the canonical video.

Asset rules: no music-heavy montage; captions on; every clip links to `/demo`, never to a signup wall.

## 4. Publication order (campaign brief §5/§6 governs; summary)

1. Enable `guided` on the hosted release; verify links, telemetry behavior, support ownership.
2. Same release: README showroom section, GitHub release notes (synthetic/live/install limits + exact proof SHA), one launch Discussion, technical article, response FAQ.
3. Day +1: Show HN (engineering-first title, limitations in the first paragraph).
4. Day +2: ONE relevant subreddit, native post, authorship disclosed.
5. Days +4-7: answer everything; reproducible failures become issues; publish corrections.
6. Day 14 AND ≥500 `demo_mission_started` attempts: formal P0→P2 go/no-go on the program §16.3 thresholds. UTM convention: `utm_source=<channel>&utm_medium=social&utm_campaign=ask-approve-verify` on owned links only.

Reserve 20% of publication capacity for responses and fixes. Discord stays closed until the brief's §9 trigger (4 consecutive weeks of demand + named moderation).

## 5. Measurement quick reference

Every count is a **non-attributed client emission attempt** — never unique visitors, deliveries, GitHub arrivals, or installations (campaign brief §8 is the contract; dashboards must repeat that limitation and show raw counts beside ratios). The P0→P2 thresholds: completion ≥35%, first-HITL ≥30%, proof-open ≥20%, combined outbound CTA ≥15%, zero serious/critical a11y, zero unresolved honesty complaint.

## 6. Rollback

`guided` off = one Web rebuild with `NEXT_PUBLIC_PUBLIC_SHOWROOM_VARIANT=legacy`. No backend state, no data, no migration is involved.
