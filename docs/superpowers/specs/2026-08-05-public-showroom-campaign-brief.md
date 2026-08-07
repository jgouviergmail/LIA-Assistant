# LIA Public Showroom Campaign Brief

**Date:** 2026-08-05
**Status:** Planned; public distribution is blocked until the P0 launch gate is green
**Campaign name:** Ask. Approve. Verify.
**Program contract:** docs/superpowers/specs/2026-08-05-public-web-showroom-program.md
**Implementation contract:** docs/superpowers/plans/2026-08-05-public-web-showroom-lot0.md
**Budget assumption:** No media budget was supplied. The pilot therefore uses owned and earned channels only; paid promotion remains disabled until P0 outbound-intent evidence and the separate installer-success gate are both proven.

## 1. Campaign overview

**One-sentence campaign:** Let technical self-hosters experience one controlled personal-assistant mission, inspect the evidence, and decide from the code whether LIA deserves installation.

**Core message:**

> LIA turns a personal intention into controlled action, shows what it did, respects every refusal, and can be self-hosted.

**Primary SMART objective:** After at least 14 complete days and at least 500 `demo_mission_started` client emission attempts, achieve `demo_completed / demo_mission_started` of at least 35%, `demo_first_hitl_decided / demo_mission_started` of at least 30%, `demo_first_proof_opened / demo_completed` of at least 20%, and combined destination-specific outbound CTA attempts per completion of at least 15%, with zero unresolved material honesty complaint and zero serious/critical accessibility defect. These are aggregate best-effort event-attempt proxies, not unique visitors, guaranteed deliveries, GitHub arrivals, or installations.

**Secondary objectives:**

- establish LIA as a personal action assistant, not a generic chatbot or coding agent;
- convert curiosity into source inspection before asking for installation;
- collect objections and reproducible failure reports in GitHub;
- defer P2, paid acquisition, and Discord operating cost until evidence supports them;
- once the installer gate is green, recruit a named, consenting beta cohort and measure whether each qualified installation completes a first approved successful workflow by day 7.

The campaign borrows OpenClaw's “show, do not merely tell” dynamic and its clear personal/local promise. It does not copy historical unsafe exposure, raw internal reasoning, or Discord as a privileged runtime.

## 2. Target audiences

### Primary audience

Developers, local-AI users, and self-hosters who want a personal assistant that can coordinate email, calendar, tasks, and context but distrust black-box autonomy.

Pain points:

- assistants explain what to do but do not coordinate action;
- agent demos hide permissions, failures, and refusals;
- self-host claims often collapse during first installation;
- multi-agent architecture is marketed without inspectable evidence.

Motivations:

- control over action and data;
- visible boundaries and reproducibility;
- a useful personal workflow rather than a benchmark;
- source quality, deployment clarity, and contributor access.

Discovery channels: GitHub, Hacker News, technically strict subreddits, LangGraph/FastAPI/local-AI communities, technical blogs, and short unedited execution clips.

Buying stage: problem-aware and solution-comparing. They need proof before commitment.

### Secondary audience

Privacy-conscious technical power users who manage dense personal workflows and will tolerate self-hosting only if setup and approval semantics are clear.

They care more about the outcome and refusal controls than the framework names. Use the mission receipt, synthetic disclosure, and installer proof; avoid leading with “multi-agent”.

### Contributor audience

Open-source engineers interested in orchestration, HITL, observability, i18n, and deployment correctness.

Their CTA is Inspect the implementation or Reproduce the proof, not merely Star the repository.

## 3. Message hierarchy

| Question | Message | Proof |
|---|---|---|
| Why care? | One morning request spans inbox, calendar, tasks, weather, and conflicting constraints. | The overloaded-morning mission. |
| What is LIA? | A personal assistant that plans and coordinates controlled action. | Four-source fan-out, proposals, decisions, receipt. |
| Why trust it? | Approval is explicit, refusal is preserved, and the synthetic storyboard shows bounded execution facts. | Real HitlActionCard UI contract, empty reasoning field, simulation receipt preserving refusal. |
| Why believe the architecture? | Every claim links to source, tests, or an explicitly synthetic fixture at an immutable commit identity. | Proof drawer URLs pinned to one full 40-character commit SHA. |
| Why install it? | The full self-hosted version can use private context and persistent capabilities unavailable in the showroom. | Clean-machine installer evidence, only after its gate. |
| What next? | Try the mission, inspect the proof, then visit GitHub. | Guided CTA sequence. |

### Channel variations

- Website: outcome first; framework names remain secondary.
- GitHub README/release: architecture, limits, exact reproduction, and current installer truth.
- Hacker News: concise Show HN framing, technical disclosure, direct repository link, no growth language.
- Reddit: adapt context to each community; disclose authorship; ask for critique of one concrete boundary.
- Short video: no music-heavy montage; show request, fan-out, one approval, one refusal, receipt, and synthetic label.
- Technical article: explain why raw chain-of-thought and a single DEMO_MODE were rejected.
- Discord, if later justified: discussion/support only; never a more privileged agent.

## 4. Evidence ladder

The campaign must never present a lower evidence level as a higher one:

1. **E0 — Guided proof:** deterministic client-only mission, clearly synthetic.
2. **E1 — Source proof:** code/test/ADR links resolved through one full 40-character commit SHA, showing that the displayed primitives exist in LIA.
3. **E2 — Runtime proof:** disposable live-showroom acceptance with capability denial and zero-residual purge.
4. **E3 — Installation proof:** clean amd64 and native arm64 install using exact released artifacts.
5. **E4 — Independent proof:** a non-maintainer reproduces installation and an approved workflow.

P0 launches at E0+E1. A one-command claim requires E3. Testimonials, case studies, or community advocacy require E4 and explicit permission.

## 5. Channel strategy

| Channel | Role | Format | Effort | Launch rule |
|---|---|---|---|---|
| LIA website /demo | Primary experience and measurement | Interactive mission | High | First and mandatory |
| GitHub README | Consideration and source inspection | Hero clip, exact proof, limitations | Medium | Same release as P0 |
| GitHub Release | Release metadata tied to exact source | Notes, full-SHA proof ref, known limits | Medium | Only after release gates |
| GitHub Discussions | Structured feedback | One launch thread and reproducibility template | Low | Open before earned posts |
| Project blog | Technical differentiation | Design decision deep dive and public response FAQ | Medium | Publish before earned-channel submissions |
| Hacker News | High-signal technical discovery | Show HN post | Medium | Only after site, README, support thread, article, and FAQ are publicly reachable |
| Reddit | Audience-specific critique | Native post plus transparent link | Medium | After the same owned proof/response assets are live; one relevant community at a time |
| FastAPI/LangGraph/local-AI communities | Architecture credibility | Short technical note/demo | Medium | After initial objections are documented |
| Short-form video on existing accounts | Demonstrability | 15 s and 60 s cuts | Medium | Captioned and linked to /demo |
| Discord | Retention/community, not acquisition | Support and release feedback | High ongoing | Only after trigger in section 9 |
| Paid media | None during pilot | None | Disabled | Revisit only after P0 intent and separate installer-success evidence |

No channel is asked to manufacture “aura”. Aura is treated as the lagging effect of repeated credible proof, recognizable product identity, useful outcomes, and responsive maintainership.

## 6. Content calendar

Twenty percent of publication capacity remains intentionally free for responses, fixes, and community-created proof.

| Period | Content or action | Channel | Owner role | Dependency | Status |
|---|---|---|---|---|---|
| Week -2 | Complete P0 interaction, truth, a11y, and zero-agent-call gates | Website/tests | Engineering | P0 implementation | Blocked by implementation |
| Week -2 | Draft README proof section and one launch Discussion | GitHub | Founder + engineering | Full 40-character proof SHA contract | Blocked by P0 gate |
| Week -1 | Capture 60 s mission, 15 s refusal, proof and receipt stills | Video artifacts | Founder | Hermetic capture test | Blocked by P0 gate |
| Week -1 | Draft and review Show HN/Reddit variants, technical article, and response FAQ | Owned drafts | Founder | Final copy and known limits | Planned |
| Launch day, step 1 | Enable guided /demo; publish README, release, Discussion, technical article, and response FAQ | Website + GitHub + blog | Engineering + founder | All P0 gates green | Gated |
| Launch day, step 2 | Verify public links, telemetry behavior, support ownership, and correction path | Website + GitHub + blog | Engineering + founder | Launch-day owned assets live | Gated |
| Day +1 | Publish transparent Show HN submission | Hacker News | Founder | Article and FAQ publicly reachable; support thread staffed | Gated |
| Day +2 | Publish one community-specific post | Reddit | Founder | Article and FAQ live; first objections reviewed | Gated |
| Day +3 | Share proof-drawer architecture cut | Technical communities | Founder | Article and FAQ live | Gated |
| Days +4–7 | Answer questions, convert failures into issues, publish corrections | GitHub/community | Founder + engineering | Daily triage | Gated |
| Week +2 | First funnel review; revise copy/pacing only from evidence | Internal + changelog | Product | Minimum seven days of data | Gated |
| Week +3 | Publish what changed and what remained unproven | Blog/Discussion | Founder | Review complete | Gated |
| Week +4 or later | Publish clean-install proof if installer gates are green | GitHub/blog/video | Engineering | E3 evidence | Blocked by installer |
| Day 14 and 500 mission-start attempts | Formal P2 go/no-go decision | Decision record | Owner | Both thresholds reached | Gated |
| After independent install | Feature first non-maintainer reproduction | GitHub/blog | Community | Permission and E4 proof | Blocked by evidence |
| After P0 go and installer E3 | Open a bounded P2 public beta | Website + dedicated runtime | Owner + engineering | P0 decision green and E3 clean-install proof green | Blocked by both gates |

## 7. Required assets

### Must-have before launch

- interactive P0 mission with six locales;
- 60-second canonical mission capture;
- 15-second approval/refusal capture;
- proof-drawer and refusal-receipt stills;
- README showroom section;
- release note with synthetic/live/install limits, exact full proof SHA, and an optional display tag only after CI proves `tag^{commit}` equals that SHA;
- one GitHub Discussion for questions and reproduction reports;
- technical article: Why LIA shows execution facts, not chain-of-thought;
- channel-specific launch drafts;
- response FAQ covering synthetic data, privacy, models, self-host status, and roadmap;
- telemetry dashboard/query definitions for every denominator.

### Must-have before installation promotion

- versioned installer entrypoint;
- exact artifact/source manifest;
- clean amd64 and native arm64 evidence;
- provider/profile limitations;
- recovery/resume evidence;
- current manual fallback;
- first-workflow verification instructions.

### Nice-to-have after proof

- independent installation video;
- maintainer interview or technical podcast;
- community-contributed mission;
- multilingual native-speaker copy review;
- Discord server with moderation and support ownership.

## 8. Measurement contract

### 8.1 Bounded P0 event vocabulary

The dedicated credential-less endpoint `POST /api/v1/product/showroom-events` accepts only these showroom events and returns `202 Accepted`. It is not the ordinary authenticated product-event route: it invokes no session dependency, ignores both the normal LIA cookie and the public-demo cookie, never reads `Request.client`, forwarding headers, User-Agent, or referrer, and stores neither a user/run identity nor network metadata. The browser calls it with `credentials: "omit"` and keeps only in-memory guards needed to attempt each event at the intended transition; it creates no persistent run identifier, and the endpoint stores no correlation identifier.

This is **non-attributed application measurement**, not anonymous network transport. The CDN, hosting platform, load balancer, or reverse proxy can observe and may retain a source address independently of the application. The launch gate inventories and discloses those policies, disables or redacts route access logs where supported, and forbids any join between infrastructure access data and the showroom funnel.

| Event | Client transition represented | Counting rule |
|---|---|---|
| `demo_viewed` | Demo page mounted | One best-effort attempt per page mount |
| `demo_mission_started` | Visitor explicitly starts a mission, including a separately started restart | One best-effort attempt per explicit start |
| `demo_first_hitl_decided` | First accepted HITL decision of that mission run | At most one attempt per started run |
| `demo_hitl_confirm` | A decision is confirmed | One attempt per confirmed decision; action-mix count only |
| `demo_hitl_edit` | The email decision is submitted as edited | One attempt for that decision; action-mix count only |
| `demo_hitl_cancel` | A decision is refused | One attempt per refused decision; action-mix count only |
| `demo_completed` | The mission first reaches its receipt | At most one attempt per started run |
| `demo_first_proof_opened` | Proof drawer is first opened after completion | At most one attempt per completed run |
| `demo_source_clicked` | Source CTA is activated after completion | At most one outbound attempt per completed run |
| `demo_release_clicked` | Release CTA is activated after completion | At most one outbound attempt per completed run |
| `demo_install_guide_clicked` | Installer-guide CTA is activated after completion | At most one outbound attempt per completed run |

No event contains visitor text, fixture values, locale, referrer, fingerprint, action ID, tool argument, or persistent identifier. Abuse control uses only fixed global minute/day Redis counters, never an IP-, cookie-, or browser-derived key. Redis failure or quota exhaustion drops the event; it never falls back to identifiable collection. Because delivery is fire-and-forget, every count is an emission-attempt proxy. A navigation can occur even if its CTA event is lost.

### 8.2 P0 campaign indicators

| Indicator | Numerator | Denominator | Source | Cadence |
|---|---|---|---|---|
| Page-to-mission intent proxy | `demo_mission_started` attempts | `demo_viewed` attempts | Bounded first-party product events | Daily first 7 days, then weekly |
| Mission completion proxy | `demo_completed` attempts | `demo_mission_started` attempts | Bounded first-party product events | Daily first 7 days, then weekly |
| HITL engagement proxy | `demo_first_hitl_decided` attempts | `demo_mission_started` attempts | Bounded first-party product events | Weekly |
| Decision mix | Each of `demo_hitl_confirm`, `demo_hitl_edit`, `demo_hitl_cancel` | Sum of the three decision-category attempts | Bounded first-party product events | Weekly |
| Proof interest proxy | `demo_first_proof_opened` attempts | `demo_completed` attempts | Bounded first-party product events | Weekly |
| Acquisition north star | Sum of `demo_source_clicked`, `demo_release_clicked`, and `demo_install_guide_clicked` attempts | `demo_completed` attempts | Bounded first-party product events | Daily/weekly |
| Destination intent | Each destination-specific CTA event, reported separately | `demo_completed` attempts | Bounded first-party product events | Daily/weekly |

GitHub's aggregate repository traffic, referrer, clone, release-download, and star counts are reported in a separate panel. They are non-causal context: there is no visitor-level or run-level join to the non-attributed showroom event attempts, so none becomes the numerator or denominator of a showroom conversion rate.

### 8.3 Installation and first-value evidence

Installation measurement is a separate, explicit opt-in proof stream. It is never joined to the non-attributed showroom funnel.

| Indicator | Numerator | Denominator | Source | Cadence |
|---|---|---|---|---|
| Installer success | Opt-in installations producing the bounded completion proof | All installation attempts enrolled in that opt-in evidence run | Installer E3 evidence | Per release and architecture |
| Product north star at day 7 | Qualified cohort installations recording at least one approved successful workflow by the end of day 7 | All qualified installations in the same named, consenting beta cohort | Instance-local record plus separately consented aggregate report | Weekly during beta |
| Independent reproduction | Non-maintainer clean installs that also reproduce an approved workflow | Raw count only; no release-download denominator | Permissioned E4 reports | Per release |

The named beta cohort definition, enrollment window, supported profile, qualification checks, day-0 timestamp, approved-workflow success oracle, consent version, withdrawals, and missing-report treatment are fixed before enrollment. Coverage is published; opt-in results are never generalized to all installations.

### 8.4 Exclusions and limitations

- Campaign collection is enabled only in the public production release configuration. The repository default plus DEV, test, ordinary CI, and preview deployment templates set `NEXT_PUBLIC_PRODUCT_TELEMETRY=false`; only the public release job may combine `true` with campaign-collector connectivity. A CI configuration assertion rejects any non-release target that could send events to that collector. The API of that hosted release must run with `product_analytics_enabled=true`, or the collector route is not mounted and every attempt is silently lost (mission behavior is unaffected either way).
- The public shell keeps its existing bounded telemetry outside the showroom funnel: the `[lng]` layout's `TelemetryBootstrap` emits Web Vitals and PWA signals through the ordinary credentialed `/product/events` route on every page, `/demo` included. This stream is disclosed, never joined to showroom events, and the hermetic contract builds zero its sample rate (`NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0`) so the network oracle stays deterministic.
- Because `NEXT_PUBLIC_PRODUCT_TELEMETRY` is fixed at Web build time, CI and the Taskfile produce two clean, separately built artifacts: the ordinary telemetry-off build and one telemetry-on hermetic contract build. Reusing one build while changing only the runtime environment is invalid evidence.
- The telemetry-enabled hermetic E2E contract test uses an isolated local interceptor and no persistent campaign sink. It asserts the exact endpoint, enum-only body, absence of `Cookie` and `Authorization`, Fetch credentials mode `omit`, and the `202 Accepted` contract without contaminating campaign data. The telemetry-off build asserts zero showroom request.
- Automated unit/E2E runs and non-production previews are therefore excluded by construction, without fingerprinting.
- Internal production browsing and JavaScript-capable bots cannot be reliably excluded under this non-attributed, no-fingerprint application-event design. Their attempts remain a disclosed limitation. Non-JavaScript crawlers normally emit nothing, but that is not treated as a complete bot filter.
- Every rate names its denominator; do not mix people, sessions, runs, event attempts, GitHub aggregates, downloads, or opted-in installations.
- Do not claim anonymous transport, unique visitors, arrived GitHub visits, installations, or attribution from these non-attributed application event attempts.
- The first formal P0 review waits for both 14 complete days and 500 `demo_mission_started` attempts.
- Report raw counts beside rates, flag telemetry loss, and mark opt-in metrics and coverage as incomplete where applicable.
- No performance uplift is claimed without a pre-declared baseline or randomized controlled comparison.

## 9. Decision gates

### P0 launch

All functional, honesty, accessibility, localization, responsive, proof-link, and hermetic network gates in the P0 plan pass.

### P2 investment

The program's completion, HITL, proof-open, outbound-CTA-attempt, accessibility, and honesty thresholds all pass. Failure leads to P0 iteration, not more distribution spend. This gate may authorize technical P2 preparation; a public P2 beta remains blocked until installer E3 clean-install evidence is also green.

### Installer promotion

Exact clean-machine evidence passes. Until then, CTA wording is View source and current setup, not Install in one command.

### Discord trigger

Create Discord only when all are true for four consecutive weeks:

- at least 25 distinct substantive GitHub/community participants per week;
- at least five synchronous-support requests per week that GitHub cannot serve well;
- one named moderation owner and one backup;
- response and incident rules are written;
- the server has a concrete recurring program beyond a bot channel.

If created, the bot has no runtime capability beyond linking to the Web showroom.

### Paid distribution trigger

Revisit paid spend only after P0 destination-specific outbound intent and separate clean-installer evidence are measured. Paid traffic must never be used to compensate for a failing organic funnel.

## 10. Risks and mitigations

| Risk | Signal | Mitigation |
|---|---|---|
| Synthetic demo feels deceptive | Honesty complaints or high early abandonment | Persistent labels, proof drawer, disclose E0/E1 explicitly |
| Technical audience dismisses marketing | Comments focus on claims over code | Lead with reproducible request, source, tests, and known limits |
| Wrong audience arrives for coding automation | Repo-X-Ray requests dominate | Keep personal mission flagship; code proof remains editorial |
| Outbound intent does not become installation | CTA attempts rise without separate installer evidence | Fix installer before stronger CTA; never count an attempt, GitHub aggregate, or download as an install |
| Maintainer is overwhelmed | Response SLA missed, issues duplicate | Stagger communities, one launch thread, reserve 20% capacity |
| Discord fragments support | Answers disappear from repository | Defer Discord; summarize durable answers back to GitHub |
| Negative feedback is hidden | Corrections absent from launch pages | Publish correction notes and link resolved issues |
| Costs rise before product proof | P2 or paid spend starts early | Enforce gates and retain P0 static fallback |

## 11. Immediate next steps

1. Review and approve the program specification and P0 plan.
2. Habits reconciliation is done (released in v1.28.0, `c5955b73`); verify the worktree is clean before implementation.
3. Implement and verify P0 only.
4. Create the must-have launch assets from the hermetic capture.
5. Prepare the GitHub Discussion, technical article, response FAQ, and channel drafts, but do not publish them.
6. Enable guided /demo only after the launch gate; publish and verify the owned article and FAQ before any Hacker News or Reddit submission.
7. Review evidence after both 14 complete days and 500 `demo_mission_started` attempts.
8. Continue installer activation as its independent workstream. Once the P0 go decision authorizes P2 technical preparation, both workstreams may proceed in parallel, but no public P2 beta may open before installer E3 clean-install proof is green.
9. Recruit and pre-register the named, consenting beta cohort only after its supported installer profile and day-7 success oracle are fixed.
10. Decide P2 public beta, Discord, and paid distribution only at their explicit gates.
