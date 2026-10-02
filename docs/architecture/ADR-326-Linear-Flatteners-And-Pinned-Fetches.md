# ADR-326 — Text flatteners are linear by construction, and a validated URL is fetched on the address the check saw

**Status:** Accepted — 2026-09-30, from the GitHub code-scanning triage of 2026-09-29/30 (owner request: a systemic answer, every hypothesis measured).

**Amends:** ADR-177 (plain-text projections), ADR-276 lot 13 (HITL preview flattening), ADR-301 (the voice twins and their corpus), ADR-303 (tool failures), ADR-317 (log facts).

## Context

GitHub's code scanning reported 28 CodeQL alerts, 10 Dependabot alerts and 11 unmergeable
Dependabot pull requests. A triage that reads the alerts one by one answers each one; the
owner asked for the systemic picture. Every finding below was measured on the running
development stack before anything was changed, and again after.

### What the alerts pointed at was a class, not three defects

Three alerts named a regular expression that could take super-linear time on a
hostile text (`py/redos` #900, `py/polynomial-redos` #901 and #916). The flatteners —
the functions that turn Markdown or HTML into the prose a bare surface renders: a
push body, a TTS line, a ticket comment, a radio excerpt, an e-mail card — run
**synchronously on the event loop**, over text a third party may have written.
Measured:

| Input | Cost before |
|---|---|
| A chat message of **51 characters** (empty table cells, spaces only), through the radio's excerpt | **4.5 s**, ×4 for every two cells added (exponential) |
| A plain-text e-mail body of **32 KB** (`<a` followed by blanks), through the normaliser, the detail level and the e-mail card, on the committed code | **3.3 s** of card rendering, the loop frozen for **3.0 s** (a ticker task measured the gap) |
| 40 KB of newlines through the voice projection | 14 s |
| 120 KB of `[a](http://x` through the Markdown link rule | 9 s |

A systematic sweep of 17 flatteners against 48 hostile shapes found **34 super-linear
combinations on 9 functions** on the API side and 11 on the browser side; CodeQL saw
three. They collapse to **seven root patterns**, each with the same shape: a quantifier
that can hand characters back to its neighbour (`\s+` followed by `[^<>]*`, two `[ \t]*`
around an optional cell, a lazy `.+?` with no bound before a backreference, `^\s*` that
crosses newlines at every line start, a fence taken greedily and retried shorter).

Two facts fixed the severity. The e-mail body reaches the card **whole**, before the
display truncation, at the default detail level (`full`) — the pagination keeps an
oversized line whole by design, and 32 000 blanks weigh few tokens — and the lot that
was being staged at the time makes the body reach the card at **every** level. And the
last message a person typed reaches the exponential rule through the radio's excerpt
(`radio/readers/conversation.py`). One shared event loop: one person's 51 characters
stall every other person's stream on that worker.

Two alerts (#907, #908) named a "suspicious character range". The range was real: the
literal « 豈 » (U+F900) that opened the CJK compatibility range had been normalised (NFC)
to U+8C48 on its way to the repository, and the class had become U+8C48–U+FAFF — 28 000
characters wide, overlapping the ideographs and the Hangul, counting every private-use or
Yi character as a token, and in the browser's twin wide enough to hold a surrogate, so an
emoji counted as one token there and a quarter on the server. `core/constants.py` held the
correct escapes all along; two private copies had been written as literals.

### What the alerts did not point at

Proving the image proxy free of SSRF (3 794 hostile URLs and 20 hostile redirects against
the real route, no host outside the allowlist contacted) led to the page-reading tool,
which was not free of it. It validated the URL, then let the client **follow redirects on
its own** and re-resolve the name, and checked only where the chain **ended**. Measured
with the real function over a recording transport: a redirect to the cloud metadata
address, to a private host or to the loopback was GET-ed and only then refused; a private
hop that redirected back to a public page was never refused at all; and a name that
answered a public address at check time and the loopback at connect time handed the
internal page back to the tool. The repository already knew the rule — the skills importer
refuses redirects "because they would bypass the pre-resolved DNS check", the radio's
newsroom validates every hop — and this tool was the outlier.

## Decision

### 1. A flattener reads a hostile text in linear time, and the build holds it

Every paired span a flattening rule recognises — an emphasis, a link label and its
target, a code span — is **bounded** by `MARKDOWN_SPAN_MAX_CHARS` (`core/constants.py`,
400), and a code span opens with at most `MARKDOWN_CODE_SPAN_TICKS_MAX` backticks. A span
past the bound keeps its marks and reads as prose; nothing is cut. Where a bound was not
the cause, the pattern was rewritten so that **no character can belong to two neighbouring
classes**: the anchor takes ONE blank then `[^<>]*`; a table row's cell is entered only
when one is there; a list marker is preceded by the blanks of its own line, never `\s`;
the icon span reads its class value up to the first occurrence of the ligature family with
possessive runs after it; a fence is taken whole and never handed back (`(?=(…))\2`, the
atomic form JavaScript can also write).

Two tests hold it, both in `tests/unit/domains/agents/display/`:

- `test_flatteners_are_linear.py` measures **growth**, never a wall-clock budget alone:
  11 flatteners × 26 witnesses, each at n and 4n characters, and a flattener may not take
  more than eight times longer on four times the text (linear ×4, quadratic ×16). A floor
  absorbs a loaded runner, a ceiling catches the absurdly slow, and a self-check applies
  the criterion to the former anchor pattern and expects it to fail — a guard that cannot
  fail proves nothing.
- `test_flatteners_differential.py` compares every rewritten pattern with its former
  form, frozen as it shipped, over **every short string of the pattern's alphabet**
  (137 000 to 2 000 000 strings each), so the language accepted is proved equal where the
  bound is not reached — and states, in a test of its own, what the bound changes.

The browser's twins (`lib/html-plain-text.ts`, `lib/live/delegation.ts`,
`lib/markdown-references.ts`) carry the same rewrites, the same bounds, and their own
growth guard (`lib/__tests__/flatteners-linear.test.ts`); the shared voice corpus
(`voice_projection_corpus.json`) gained the cases that pin the new behaviour on both
sides (a marker alone on its line, an emphasis past the bound, an emoji, Yi, private use,
compatibility ideographs, Hangul). `html_to_text` and `format_email_body` moved out of
`display/components/base.py` — frozen at its audited size, four lines from its cap — into
`components/html_flatten.py`, re-exported so their four importers see one surface.

The CJK class is declared **as code points** on both sides (`CJK_RANGES`, five pairs), the
Python pattern is asserted ASCII, and `test_projection_cjk.py` reads the TypeScript
constant and holds the two lists equal and disjoint.

### 2. A validated URL is requested on the address the check saw, one hop at a time

`validate_url` now returns, with its verdict, the **addresses it validated**
(`UrlValidationResult.resolved_ips`), and `pinned_stream` (`web_fetch/url_validator.py`)
is the ONE way a validated URL is requested: the URL's host is the first validated
address, the name travels in `Host` and, over TLS, in the SNI (so the certificate is
verified against the name, never the address), and `follow_redirects` is off. A redirect
is a new URL, which the caller validates and requests through `pinned_stream` again; the
page-reading tool walks its chain that way under `WEB_FETCH_MAX_REDIRECTS`, and attributes
the content to the URL it came from. A verdict that validated no address is refused with
a `ValueError` — fail closed, so a fake verdict in a test can never open a socket. The
name is sent in its **wire form** (`URL.raw_host`, IDNA-encoded): the cold review found
the first version sending `URL.host`, the decoded spelling, which a header cannot carry —
an internationalised name raised `UnicodeEncodeError` where the plain URL, encoded by the
client itself, had always worked. And the pinning `Host` wins over a caller's own, whatever
its case: a request a header could unpin would not be pinned.

The three readers share it: the page-reading tool, the radio's newsroom (which already
walked its hops) and the skills importer (which still refuses a redirect). The MCP
endpoint validator keeps its own copy of the address policy because `infrastructure`
cannot import a domain; `test_address_policy_drift_guard.py` holds the two copies equal
until the policy has a home both can import.

The tool's tests were rewritten over a **real client and a recording transport**: the
former ones replaced the client with a `MagicMock` and could not see where a redirect was
contacted. They now state that a redirect to a blocked destination is never contacted,
that a private hop on the way to a public page is refused, that a rebinding name cannot
steer the connection, and that a public redirect is followed and attributed to its end.

### 3. What the same triage hardened on the way

- The image proxy answers **400**, not 500, to what `urlparse` accepts and httpx refuses
  (`httpx.InvalidURL` is not a `RequestError`; a hostile `Location` made `urljoin` raise):
  420 of 3 794 hostile inputs used to reach the error handler.
- The Hue bridge validator accepts the **three RFC 1918 networks and nothing else**:
  `is_private` also said yes to the link-local range that holds a cloud's metadata address,
  to `0.0.0.0` and to the benchmarking, documentation and reserved ranges; and the pairing
  route no longer echoes the connection error's text, which distinguished a closed port
  from an absent host (0.00 s against 3.06 s, measured). The demonstrator's guard already
  refused these routes.
- A production instance **refuses `DEBUG=true` at boot** (`Settings._refuse_debug_in_production`):
  the error handler answers with `str(exc)` under debug, and a development `.env` copied to
  a host was the whole distance. Measured `False` on the live host; held by construction.
- One helper names a knowledge space's file on disk (`rag_spaces/storage_paths.py`, with
  the containment check): `processing.py` built the path by hand without it, and
  `drive_ingest.py` could not lend its helper without an import cycle.
- The tool-embedding claim marker is owner-only (`0o600`); five dead stores and a `!=`
  NaN idiom are gone (#862, #893, #895, #896, #911).

### 4. Static analysis reads what ships

A local run of CodeQL 2.27.1 over HEAD with **no path restriction and no rule excluded**
reproduced the CI's 57 results inside the CI's perimeter exactly, found 894 results
outside it (795 in `alembic`, the `revision`/`down_revision` convention; the rest in
scripts; **no product vulnerability**), showed that the three globally excluded security
rules hid exactly the three known sites, and proved the extractor reads Python 3.14's
`except A, B:` as it reads `except (A, B):` (417 multi-type clauses, none misread).

The CodeQL configuration therefore covers `apps/api/scripts` (which `COPY . .` puts in the
image), `infrastructure/`, `scripts/deploy`, `scripts/install`, `scripts/release`, the
mobile shell's own scripts and the workflows, for which the `actions` language joins the
matrix. No security rule is excluded globally any more: a sound case is dismissed on
GitHub with its written reason, where the next occurrence of the same rule surfaces on its
own. The eight native files of the mobile shells (Java, Swift) were read by hand: the
origin is HTTPS-only, `openExternal` takes http(s) alone, the offline interface re-checks
the local page, iOS keeps App Transport Security.

### 5. Dependabot stays as it is

Every pull request that touched a Python lockfile was unmergeable by construction —
Dependabot edits the `uv pip compile` output pin by pin without re-resolving the graph
(ADR-112) — and the npm group rewrote an exact `pnpm.overrides` entry in the lockfile
alone. Eight pull requests were merged out of 120 on `pip`, three out of 61 on `npm`, none
since 2026-07-09. The owner keeps the robot as an awareness feed and regularises by hand,
as today; the seven open pull requests were closed with their root cause in a comment,
and the three green ones asked for a rebase.

## Consequences

- Measured after the change, same inputs, same stack: the hostile e-mail card renders in
  **0.65 ms** (was 3 362 ms), the 51-character message in **0.02 ms** (was 4 476 ms); the
  page-reading tool contacts the first hop only on every hostile chain; every growth guard
  is green on both sides and red on the former patterns.
- What a person may notice: an emphasis, a link label or a code span longer than 400
  characters keeps its marks on a bare surface; a code span opened by four or more backticks
  reads as prose; a list marker alone on a line no longer swallows the next line into an
  item; a redirect to a plain-`http://` page is upgraded to `https://` like the first hop
  (the radio's newsroom already did); a link past the bound in an e-mail card is drawn as
  typed. Each is pinned by a test that states it.
- A test that hands a flattener or a fetcher a fake verdict must give it an address; a
  test that records requests must read the name from `Host`, not from the URL.
- Adding a flattening rule means adding it to the guard's table; adding a fetch path means
  calling `pinned_stream`, never `client.stream`, on a validated URL.
- The bound is one constant per side (`MARKDOWN_SPAN_MAX_CHARS` and its TypeScript twin);
  changing one without the other fails the corpus.

## Alternatives considered

- **A regex engine with linear guarantees (RE2) or a timeout** — a new dependency on every
  flattener for a defect that seven pattern rewrites close, and a timeout turns a hostile
  input into a silent cut where the guard now refuses the pattern at build time.
- **Truncating the e-mail body before flattening** — kept as defence in depth in the plan,
  not as the fix: 80 KB would still cost about 19 s under the former pattern.
- **A tempered emphasis rule** (`(?!\1)`) was faster than the bounded one but accepted a
  different language on 6 of 263 short strings; the bounded form is exact.
- **Excluding the MCP validator's duplicate through a shared `core` module** — deferred;
  the drift guard holds the two equal until then.

## Measured, not assumed

`scratchpad` probes of the session, all read-only: the SSRF differential (3 794 inputs,
20 redirects, `MockTransport` under the real route), the growth series, the whole-chain
e-mail probe with HEAD's own detail levels, the event-loop ticker, the rebinding probe over
real sockets, the exhaustive pattern equivalences, the local CodeQL run
(`codeql-bundle-linux64 2.27.1`, checksum verified, throwaway container), the production
read of `settings.debug`.

## Amendment 2026-09-30 — what the first scan of the widened perimeter said

The scan that followed v2.1.1 closed the eleven alerts this decision fixed and opened
twenty-seven on the wider perimeter, each read on pieces before it was answered:

- **Two ReDoS findings on the rewritten patterns are false positives, measured.** CodeQL
  named its witnesses — `<a >` then `<a >a` repeated against the anchor rule, `\t|`
  repeated against the table rule — and both grow linearly through the real patterns
  and the real entry points (exponents 0.99 and 0.96; 0.86 ms and 0.26 ms at 64 000
  characters): its analysis models neither `\b` inside a lookahead nor a `(?=…)` guard.
  Both witnesses joined the growth guards on both sides, so the answer is held by a test
  rather than by a dismissal comment. The same day the guards learned to read a small
  measurement as at least 5 ms and to keep the best of three runs: under xdist on a loaded
  host, a 3 ms run read ×8.2 on a flattener whose exponent is 1.01 (measured in the
  container over four sizes), and a quadratic flattener starting from that floor still
  takes twice what the criterion admits.
- **The two `partial-ssrf` findings on the Google proxies are structural false
  positives**: scheme, host and path are literals, the person's value lands in the query
  string, and the redirects followed are Google's own. They are dismissed with that
  reason, not excluded by rule — the next occurrence of the rule anywhere else must
  surface.
- **`--!>` ends an HTML comment too** (a recovered parse error): read as an open comment,
  it dropped everything a reader wrote after it from an event's description. The closing
  pattern accepts both forms; the description was already escaped at insertion, so this
  was a loss of text, never an injection.
- **The Markdown export escapes a backslash where Markdown would read it** (before an
  ASCII punctuation character), and a link's brackets as the link's text is written,
  in the ONE function that escapes every mark: escaped later by a replace of its own, a
  backslash before a bracket was doubled after the bracket had been escaped, and `a\]b`
  reached the file as `\\]` — a literal backslash, then the bracket ending the link.
- **The qualification workflow refuses a candidate run id that is not a successful run
  of `release.yml` in this repository** before a byte of its artifact is used — the guard
  `release.yml` already applied to a qualification run id. The job writes no cache and
  runs by hand under an approval environment, so the finding was a false positive; the
  guard makes the input trustworthy by construction. In both workflows the run ids now
  reach the shell through the step's environment, never by expression expansion into the
  script — an expansion lands in the shell before the decimal check can read it, and
  `123"; …` would have left its quotes. The guard's logic was played locally against real
  run ids: a successful `release.yml` run accepted; a `ci.yml` run, a failed run, an
  unknown id, an empty or non-decimal value each refused for the reason named.
- **A development script verifies TLS by default** (`simulate_live_call.py --insecure`,
  passed by the `telephony:simulate:live` task for the self-signed certificate); the
  mobile shell's build scripts read a file in one call instead of checking then reading;
  and seventeen quality findings in operator scripts were fixed in the code (four implicit
  string concatenations that were sentences cut in two, four bare `exit()`, six pass-through
  lambdas, a dead store, two unused imports).

Found by the same scan, on the other side of the ledger: the five `rag_spaces` tests this
decision's `storage_paths` extraction broke on the runner. They patched `settings` on the
two modules that used to build the path and passed on the author's host, where the real
storage root exists — a settings read that moves is a census of every test patching the
module it left.

## Amendment 2026-10-02 — a fetched body is counted while it is decoded

The dependency audit of 2026-09-30 (finding F2) measured what a ceiling counted on DECODED
bytes is worth: httpx 0.28 inflates a whole raw chunk before any caller can count it.
Under a 1 MiB ceiling, a 200 MiB bomb of a few hundred kilobytes peaked at 141.8 MiB in
gzip and 400 MiB in zstd through `read_bounded`; the page-reading tool, which read the page
whole (`aread`) before checking its size, held 128 MiB for a 64 KiB gzip page under its
2 MB ceiling. Both paths were live in production.

- **`read_bounded` decodes the raw bytes itself** (`infrastructure/utils/bounded_read.py`)
  and never asks a decoder for more than what is left of the ceiling, plus one byte: the
  same bombs now peak at 2.2 MiB and 2.0 MiB. It decodes exactly what httpx advertises in
  the image — gzip, deflate (zlib-wrapped or raw, as httpx accepts it), zstd (the standard
  library's `compression.zstd`, every frame), and `x-gzip` as gzip, as RFC 9110 asks — and
  a test holds the two lists equal, so a decoder installed later (brotli) is a decision, not
  a refusal of the answers it invited. `pinned_stream` sends that list as `Accept-Encoding`
  unless its caller set one. What follows the end of a gzip or deflate stream is ignored, as
  httpx ignores it, and no longer read: the first version held it in the decoder's buffer,
  so a server that kept sending after the end filled the memory the ceiling was meant to
  protect (32 MiB measured for 16 MiB of trailing bytes, found by the cold review).
- **What it cannot bound, it refuses before decoding a byte**: another coding, or two
  stacked, is `UnsupportedEncodingError` — httpx passed an unknown coding through as if it
  were the body. A refusal, a corrupt body and a compressed stream cut before its end are
  all `httpx.DecodingError`, which every one of the seven callers already handled as a
  transport failure; a cut page is refused rather than shown shorter (ADR-275's rule). A
  response read already — a test transport building it with `content=` — answers to the
  ceiling alone.
- The page-reading tool reads through it, names its refusals (`INVALID_RESPONSE_FORMAT`:
  the coding it did not read, or a corrupt or incomplete body) and logs each by its host
  (`web_fetch_body_refused`). A header value the server chose reaches a failure message —
  which is not wrapped as external content — only as a short token; the `content-type`
  quote had the same gap. `test_pinned_stream_bounded_read_guard.py` holds the rule for
  every fetch path: a `pinned_stream` call is entered by `async with … as <name>`, and
  nothing reads `<name>` through an httpx reader inside the block. Red on the former tool
  (`aread`, `content`, `text`), green with no allowlist.
- Proven over a real socket (chunked transfer) in the production image built from the
  change: a 130 KB gzip bomb and a 4 KB zstd bomb refused in 0.02 s at a 4.7 and 4.0 MiB
  peak, both pages read whole, a server sending 20 s of bytes after its gzip stream let go
  of in 0.01 s, `br` refused.
