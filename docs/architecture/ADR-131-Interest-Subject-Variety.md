# ADR-131: Interest Subject Variety — batch LLM clustering + two-level rarity selection

**Status**: ✅ IMPLEMENTED (2026-07-18)
**Deciders**: JGO
**Technical Story**: User-reported lack of variety in interest notifications — over-focus on the dominant theme.
**Related Documentation**: `docs/technical/INTERESTS.md` (§2.5.2, §2.5.2b, §2.5.2c, §2.5.5)

---

## Context and Problem Statement

Interest notifications felt repetitive: measured over 30 days in production, **~50 %
of notifications concerned a single perceived subject** (AI), while the selection
draw was already *uniform* (`INTEREST_TOP_PERCENT=1.0` — the "top 20 %" documented
behavior had been configured away). The root cause was **pool composition, not the
draw**: the dominant subject was fragmented into 9 of 19 active interests
(Anthropic, anthropic, OpenAI, langgraph, langchain, deepseek, qwen, "impact
sociétal de l'IA", "comparaison des API d'IA") — 9 lottery tickets for one theme.
A literal case-duplicate ("Anthropic"/"anthropic", cosine 0.987) had also slipped
past extraction-time dedup.

## Decision Drivers

- Perceived variety operates at the **subject** level (user feedback), not the
  category level and not the interest-row level.
- Every mechanism had to be validated by measurement before implementation
  (two benches + a simulation, 2026-07-18).

## Evidence (benches on the real prod snapshot, 19 interests)

1. **Embedding-threshold subject cooldown: REFUTED.** Topic-embedding space is
   compressed (0.74–0.99); ordering violates subject semantics
   (android/USA 0.794 > langchain/langgraph 0.783). No threshold separates
   same-subject from distinct-subject. Only ≥ 0.95 is reliable (true duplicate
   0.987, first false pair 0.890).
2. **LLM subject labeling — incremental: REFUTED, batch: VALIDATED.** With the
   production extraction LLM (gpt-5.2, temp 0.2): incremental labeling across 5
   arrival orders → 10–15 subjects, AI cluster split 1–5 ways, one aberrant merge
   (deepseek+qwen+Chine under "chine"), 89.2 % pairwise agreement. Batch labeling
   (all interests in one call) × 5 runs → stable ~12-subject partition, 98.2 %
   agreement.
3. **Selection simulation (300 reps × 30 days, model validated against prod:
   uniform simulated 47.9 % vs ~50 % measured).** All γ/β variants converge to
   subject equirepartition (~8 %/subject) because Bayesian weights are flat
   (0.75–0.98) — the "pure rarity vs weight blend" product decision dissolved.
   AI family: 50 % → 33 % (it legitimately holds 4 of 12 subjects). Variant
   **V5** (rarity at subject level AND intra-subject) cuts starvation from 0.8
   to 0.3 interests unserved per 30 days.

## Decision

1. **`subject` column on `user_interests` as derived data** (nullable String(100)).
   NULL = "needs clustering" — the stale marker. Topic renames and merges reset it.
2. **Batch LLM subject clustering job** (`interest_subject_clustering.py`):
   stale scan every 30 min + nightly full re-cluster at 04:15 (self-healing
   label drift). One `interest_extraction`-typed LLM call per user, index-keyed
   JSON protocol, defensive fail-open parsing.
3. **Two-level rarity selection** (`selection.py`, pure function, injected RNG):
   subject cooldown 36 h (a cooling sibling freezes its whole subject) →
   subject draw `p ∝ mean_weight^β / (1+recent)^γ` → intra-subject draw
   `p ∝ 1/(1+recent)^intra_γ`. Fail-open at every stage. Mode switch
   `INTEREST_SELECTION_MODE=uniform` is the instant, rebuild-free rollback.
4. **Duplicate hygiene**: extraction dedup hardened (embedding-failure fallback
   to string matching; rename-collision guard via case-insensitive lookup) +
   nightly retro-merge at cosine ≥ 0.95 or case/whitespace-equal topics
   (signals summed, notifications repointed, subject reset).
5. **Deterministic source hyperlinks** appended to notification content
   (markdown `[domain](url)`, i18n label ×6, cap `INTEREST_SOURCES_MAX_LINKS`);
   `markdown_links_to_plain` conversion for FCM/Telegram surfaces.
6. **Centralized proactive i18n** (`core/i18n_proactive.py::ProactiveMessages`):
   fixes the notification-titles table that was keyed `"zh"` while
   `User.language` is backend-canonical `"zh-CN"` (Chinese users silently
   received English titles).

## Consequences

**Positive**: dominant-subject share ~50 % → ~33 % (simulated, to be confirmed in
prod after 2 weeks); long tail served (starvation 0.3/30 d); duplicates self-heal
nightly; sources clickable in chat; every knob in `.env`.

**Negative / accepted**: ~1 LLM call/user/day for clustering (+ stale scans) on a
cheap model; residual batch-label wobble between nightly runs (self-healing,
selection fail-opens on NULL); benches ran on n=1 user (fr) — mitigated by the
`uniform` escape hatch, fail-open stages, and `interest_subject_recluster_total` /
`interest_selection_total` / `interest_selection_eligible_subjects` /
`interest_merge_total` metrics.

**Deferred (explicit)**: Grafana panels for the 4 new metrics (dashboard
`13-proactive-heartbeat.json`) — next dashboard pass, with visual verification per
the 2026-07 dashboard conventions.

## Alternatives Considered

- **Embedding-cosine subject cooldown** — rejected: refuted by evidence (1).
- **Incremental (extraction-time) subject labeling** — rejected: refuted by
  evidence (2); order-dependent drift re-creates fragmentation at the label level.
- **Category-level two-stage draw** — rejected: wrong granularity ("le problème
  n'est pas tant les catégories que les sujets dans les catégories").
- **Aggressive merge below 0.95** — rejected: 0.890 is a false pair on real data;
  merging would destroy legitimate granularity (Bitcoin vs Cryptomonnaies).

## Verification

- Unit: `test_selection.py` (cooldown/fail-open/rarity statistics, seeded),
  `test_selection_distribution.py` (30-day replay: AI < 40 %, ≤ 2 starved),
  `test_interest_subject_clustering.py` (parser), `test_dedup_hardening.py`
  (merge pairing), `test_sources.py`, `test_i18n_proactive.py` (zh-CN regression),
  `test_repository_merge.py`.
- Integration: `tests/integration/domains/interests/test_repository_subjects.py`
  (CI lookup, lookback window, merge repointing — real database).
- Migration: `0ef84488b15c`, replay-from-zero check green (F007 gate).
- Runtime: dev Docker boot + forced clustering run + selection dry-run
  (see plan T10).
