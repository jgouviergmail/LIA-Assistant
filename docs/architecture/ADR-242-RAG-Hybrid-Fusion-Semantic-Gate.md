# ADR-242: RAG hybrid fusion — gate on the semantic score, BM25 as a bounded bonus

**Status**: Accepted (2026-08-22)
**Deciders**: LIA core team
**Technical story**: embedding-stack review 2026-08-22 (gemini-embedding-2 evaluation), which found a live production defect in the RAG fusion instead

## Context

RAG Spaces scored a chunk as `alpha * semantic + (1 - alpha) * bm25_normalised`
(prod: `alpha = 0.7`), then dropped anything below `RAG_SPACES_RETRIEVAL_MIN_SCORE`
(prod: `0.55`). Two properties of that formula combined into a severe defect.

**1. BM25 was normalised by the corpus-wide maximum.** `score / max(scores)`
awards `1.0` to the best lexical match in the space *whatever its absolute
quality*. On a query whose language does not match the documents — the normal
case for LIA, whose FAQ corpus is English and whose users write French — BM25 is
pure noise, and that noise still received the full `1 - alpha = 0.30`.

**2. The threshold was compared against an alpha-shrunk score.** A chunk with no
lexical overlap tops out at `0.7 * semantic`, so passing a threshold documented
as `0.55` actually required `0.55 / 0.7 = 0.786` in cosine terms — well above the
median of a *correct* answer (0.733 measured). Measured on the real `lia-faq`
corpus: **36% of correct answers cleared the semantic threshold and were then
pushed under it by the fusion.**

Reproduced on the live production database on 2026-08-22, running the production
code path:

```
Q: « C'est quoi un espace de connaissances ? »
   semantic top-1 = "What are Knowledge Spaces?"   sem=0.683   ← the answer
   fusion          [DROP] hyb=0.478 (sem=0.683 bm25n=0.000)
                   [KEPT] hyb=0.660 (sem=0.575 bm25n=0.857)  "How LIA sees you…"
   → retrieve_rag_context returned 1 chunk: the wrong one.

Q: « Est-ce que mes données sont chiffrées ? »
   the 5 relevant chunks all [DROP] at hyb 0.438-0.473, bm25n=0.000
   → retrieve_rag_context returned 0 chunks.
```

A third, independent defect compounded it for one of the 6 supported languages:
`tokenize_text` matched `[\w']+`, and `\w` matches Han characters, so an entire
Chinese sentence tokenized to **one** token. BM25 degenerated into
exact-sentence matching and scored 0 on every real query, while the
max-normalisation still handed `1.0` to an arbitrary chunk.

## Decision

**1. `min_score` gates on the semantic score, before any lexical signal.** The
setting recovers the meaning its name and documentation always claimed, and it
means the same thing whether or not the query shares vocabulary with the
documents. Gating first also skips the BM25 index build entirely on a turn that
matched nothing — the common case, since user-document RAG runs on every turn.

**2. BM25 becomes a bounded re-ordering bonus**: `score = semantic + beta * bm25n`
with `RAG_SPACES_BM25_BONUS_WEIGHT = 0.05` replacing `RAG_SPACES_HYBRID_ALPHA`.
It can promote an exact-term match over a near-tie; it can never admit or evict
a chunk. Max-normalisation is kept — a chunk's lexical bonus should express its
standing in the whole space — but it is now bounded by `beta` instead of
deciding relevance.

**3. `RAG_SPACES_RETRIEVAL_MIN_SCORE` moves 0.55 → 0.62**, recalibrated on the
raw semantic axis.

**4. `tokenize_text` splits space-less scripts into character bigrams**
(CJK ideographs, kana, hangul), leaving space-separated scripts untouched.

**5. One global threshold, not a per-language table.** The optimum is flat across
all six languages (the 10th percentile of a correct answer's score spans
0.610-0.696 over 12 measured corpus/language combinations), so six constants
would add drift risk for no gain — and they would be unkeyable anyway, since a
document's language and a query's language are independent.

### Rejected: admitting chunks on strong lexical evidence alone

A union branch (`semantic >= gate OR bm25 >= 0.6 * max`) recovers +14 points on
artificial rare-token queries, but it re-creates the very defect being fixed one
scope down: on an off-topic turn the corpus-wide BM25 maximum is itself noise.
Measured injection per irrelevant turn: 1.05 → 2.75 (`lia-faq`) and 0.30 → 3.60
(`how.fr.md`). Rejected.

## Consequences

Measured through the shipped code path, on the real `lia-faq` corpus (356
chunks) and per-language prose corpora, with 740 native queries:

| Scenario | before | after |
|---|---|---|
| FAQ (EN docs), fr queries | 0.525 | **0.867** |
| FAQ, en | 0.883 | **0.950** |
| FAQ, de | 0.533 | **0.883** |
| FAQ, es | 0.425 | **0.867** |
| FAQ, it | 0.450 | **0.842** |
| FAQ, zh | 0.208 | **0.817** |
| FR documents, fr queries | 0.707 | **0.827** |
| DE documents | 0.608 | **0.873** |
| ES documents | 0.662 | **0.896** |
| ZH documents | 0.075 | **0.887** |
| chunks injected per off-topic turn | 1.25 | **0.88** |

Recall rises in all six languages and noise falls, so the change is strictly
better on both axes. Two costs are accepted and stated:

- **Rare-token exact-term queries lose ~5 points** (0.820 → 0.770 measured on
  three-rare-token queries). That class is the least representative of a
  conversational assistant, and `search_documents` covers explicit document
  search.
- **Turns that legitimately match now inject more chunks** (they previously
  injected too few, or none). `RAG_SPACES_MAX_CONTEXT_TOKENS` still caps the
  prompt budget.

`RAG_SPACES_HYBRID_ALPHA` is deleted rather than deprecated: leaving a setting
that no longer influences anything is the failure mode the codebase already
forbids for dead code.

The debug panel now publishes the threshold it enforced — `min_score` is drawn
as a tick on every score bar and named in the empty-result message — so "why was
this chunk dropped" is answerable from the panel alone. The `relevance` score
tiers move 0.70/0.50 → 0.75/0.68, because nothing below the gate can reach a bar
any more and the old boundaries left the `low` tier unreachable.

## Alternatives considered

- **Reciprocal Rank Fusion.** Scale-free, and the best of the classic fusions
  measured (FAQ-FR 0.783 vs 0.525 for the old formula), but still below a plain
  semantic gate (0.883) because it lets a noisy lexical ranking reorder a sound
  semantic one.
- **Normalising BM25 over the candidates instead of the corpus.** Measured
  0.517 on FAQ-FR — the same lie, one scope down.
- **Dropping BM25 entirely.** Simpler, and best on paraphrase queries, but it
  gives up the case BM25 exists for: exact-term search, where BM25 alone scores
  1.000 against 0.720 for semantic-only.
- **Migrating to `gemini-embedding-2`.** Evaluated in the same review and
  rejected: it ignores `task_type` entirely (identical vectors for
  `RETRIEVAL_QUERY` and `RETRIEVAL_DOCUMENT`), costs 33% more, is ~9% slower,
  requires re-embedding every vector and re-calibrating nine thresholds, and
  measured *worse* than `gemini-embedding-001` on monolingual French prose
  (R@5 0.800 vs 0.950) — the shape of most user documents in production.

## References

- `apps/api/src/domains/rag_spaces/retrieval.py` — the fusion
- `apps/api/src/infrastructure/store/bm25_index.py` — the tokenizer
- `apps/api/tests/unit/domains/rag_spaces/test_retrieval_fusion.py` — the contract
- `apps/api/tests/unit/infrastructure/store/test_bm25_index.py` — tokenizer guards
- ADR-055 (RAG Spaces architecture), ADR-058 (system RAG spaces)
- ADR-184 (an enforced constraint must be published to whoever reads the value)
