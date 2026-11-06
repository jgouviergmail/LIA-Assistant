# ADR-370 — A page the model writes runs in the chat, in the strictest frame the chat has

**Status**: Accepted, 2026-11-05.
**Date**: 2026-11-05

**Amends**:
[ADR-075](ADR-075-Rich-Skill-Outputs.md) and
[ADR-327](ADR-327-Skill-Library-And-Third-Party-Skills.md) — a frame's policy opens the document
(`frame_policy.with_leading_policy`): the regular expression that looked for `<head>` is gone from
the skills' frames too, because a comment or a string could feed it a false one.
[ADR-177](ADR-177-Rich-HTML-Response-Components.md) — a `<pre>` keeps its lines through the
Markdown pipeline, and what a person types is shown as words, never parsed as HTML.
[ADR-226](ADR-226-Document-Generation-Agent.md) — a page has a slot of its own beside a
document's (§8), and `store_document` is the one door both reach the attachments through.
[ADR-303](ADR-303-Tool-Failure-Restitution.md) and
[ADR-310](ADR-310-ReAct-Turn-Judged-On-Its-Result.md) — a failed call a later call of the same
tool answered is no failure of the turn: the honesty directive leaves it out.

## Context

On 2026-11-04 a person asked « fais moi un jeu de morpion en HTML super stylisé pour halloween »
and got the source of the page, cut short, in the answer. Replying with
`pas </script>, </body> et </html>` turned their own bubble into `pas ,  et `. Three separate
defects, each proved on the archived messages:

- **The code was never truncated by the model.** The stored answers were whole. A `<pre>` sits in
  an HTML block of CommonMark type 6, which ends at the first blank line; the rest became
  paragraphs, and `rehype-raw` moved the end of the block out of `<code>`. The rendering lost
  201 characters, 37 indentations and 6 blank lines of that page, and Copy returned a document
  with an unclosed `<script>`: a blank board and a clean console. 24 of the 48 code blocks stored
  in production were affected.
- **A person's message went through the same HTML parser**, which dropped the closing tags as
  stray markup: 6 of 733 user messages in production.
- **LIA had no way to show a page.** It could describe one, or print its source. The owner's rule
  settles what each request means: « donne-moi le code HTML pour… » shows the code in the answer,
  « fais-moi le jeu » shows the game.

## Decision

### 1. What is written reaches the screen

`lib/markdown-source.ts` protects what is preformatted before any Markdown runs: every line break
of a `<pre>` becomes `&#10;` (HTML answers only), so a blank line cannot end the block.
`lib/remark-literal-html.ts` turns every `html` node of a person's message into text. Both scans
are linear by construction (ADR-326). The same review replaced two quadratic regular expressions
of `normalizeMathDelimiters`, one of which killed the worker on `\(` and a run of blanks; 400,000
random texts confirmed the replacement gives the same result.

### 2. A thing is a tool call, its code is text

`generate_interactive_page` is a tool of the domain `interactive_page`, reached through the
analyzer like any other. The analyzer's rule 4 tells a request to MAKE something the person will
use from a request to SEE, GET or EXPLAIN its code; the second stays a conversation, and the code
reaches the answer through §1.

**Making is not playing.** The router gives a detected skill absolute priority, and a skill
offering the same kind of thing is one word away from a request to make one: asked for « un morpion
stylisé pour Halloween », the analyzer named the skill `tic-tac-toe`, alone or beside the page, and
a turn wrote the page then ran the skill. The rule is stated twice, because a prompt is a request
and the router an authority. The analyzer's rule 4 and the domain's description say that making
goes to the domain with no skill, and that using what a skill offers as it is stays that skill with
no domain. `effective_skill_name` then resolves what still contradicts: a skill named beside a page
verdict is suppressed, as it already was beside an MCP one (`reason="page_domain"`).

The verdict did not reach the ReAct loop, which decides for itself with every tool bound. Measured
on 2026-11-05 on a plain « fais-moi un petit jeu de morpion », routed to the page each time: it ran
the skill six times out of six, and the response, told to answer a request for a page, wrote five
times out of six that the conversation could not run a game, with its code, above the game itself.
Without the catalogue it still played in text on two turns out of six. On a turn `makes_a_page`
answers for, the loop now reads no catalogue and is told to call the tool, when the tool is bound
(`build_page_request_block`): seven pages out of seven, while « I want to play » kept the skill and
« give me the code » the code.

The tool has four modes, a closed enum published to the planner:

| Mode | Works from | Writer | File |
|---|---|---|---|
| `create` | the instructions | yes | yes |
| `revise` | the conversation's page | yes | yes |
| `show` | a page or HTML code that exists | no | yes |
| `code` | a page that exists | no | no |

`show` and `code` cost nothing: they read the conversation (`page_sources.py`) and pay no writer.
What exists is found in the MESSAGES, newest first, never in the registry channel of the graph
state, which is capped and evicts in silence. A person's own words are not searched: pasted code
reaches the tool through `source_data`, because a page must never be run out of a text nobody
asked to run.

### 3. Nothing the model writes runs outside the frame

A page is untrusted by definition: nobody reviewed it, and it may have been written after reading
a third party's mail. Measured on Chromium, Firefox and WebKit against the application's real
headers (2026-11-04), held by `apps/web/e2e/smoke/chat-page-app.spec.ts`:

- `sandbox="allow-scripts allow-forms"` and nothing else. The origin is opaque: no cookie, no
  storage, no parent. `allow-forms` is there because Chromium and Firefox never call a `submit`
  handler without it; `form-action 'none'` still refuses every submission.
- **The policy names no host.** The skills' policy allows `https:` images, and an image URL is a
  way out for whatever the page holds. `PAGE_CONTENT_POLICY` allows `data:` and `blob:`.
- **The policy opens the document**, as a prefix. A policy injected after a parsed `<head>` was
  bypassed by a `<head>` in a comment.
- **WebRTC is closed by hand.** A STUN packet left Chromium under this policy, `webrtc 'block'`
  included. The runtime runs before the page and takes the constructors away; `frame-src 'none'`
  stops a nested frame from handing back a fresh one.
- **Storage lives in memory.** An opaque origin makes `localStorage` throw, and a game's first
  line would kill the whole script.
- **A frame can always navigate itself**: no sandbox flag stops it, and its own policy has no word
  for it. What bounds it is the APPLICATION's `frame-src`, which allowed the whole of
  `www.google.com`, where `/s2/favicons?domain=<secret>.host` has Google resolve a domain the page
  names. The directive now names the one path shipped, `/maps/embed`. Held by the e2e journey on
  three engines; a redirect from that path was refused at the hop on Chromium and Firefox (WebKit
  cannot simulate a 302, so it was not measured there).
- **The bridge only listens**, and to two notifications: a height and a failure
  (`usePageFrameBridge`). The skills' bridge is not reused: `ui/open-link` makes the HOST open a
  URL, which is exactly the exit the sandbox closes.

The `.html` file carries the same policy, without the runtime. It is served as an `attachment`,
its card opens the download panel of the document viewer, and the preview refuses it: no surface
of the application renders it on its own origin.

A failure told by a page is shown as text, bounded, prefixed by a sentence of ours. A hostile page
can forge those words and nothing else: no markup, no link.

### 4. A page read back from history waits for a click

An endless loop in a frame blocks the host's thread on all three engines. A page that started by
itself on every opening would make its conversation impossible to open again. So a page runs at
once in the turn that made it, and behind a « Start » button everywhere else: another device, a
reload, a page of history (`restored`, set by `collectHistoryWidgets`; the live registry wins, so a
running game is never stopped by a read of the server). The click hands the frame the keyboard;
a page that started alone never takes it from the composer.

### 5. The model never reads the page

The page travels as a `PAGE_APP` registry item and reaches the answer as an empty sentinel, written
by the host alone. `structured_data` carries a title, a filename and an id, and is never empty:
a reader falls back on the registry payload when it is, which would hand the model the whole page.
Its code would be retyped into the answer and paid for twice. `PAGE_APP` is `EXTERNAL` in the
trust table, stays out of every text summary, and is not « the person's data » on the sandbox's
network card.

### 6. A page is kept with its message, under today's policy

`message_metadata.widgets` keeps the page and `source_offset`, where its own bytes start. Reading
history recomposes the document around those bytes (`_under_current_policy`): a flaw found in the
frame's policy reaches every page already archived, not only the next one. The prefix is ASCII, so
the offset reads the same in Python and in the browser.

### 7. What the writer can produce is what it is told

`INTERACTIVE_PAGE_MAX_BYTES` bounds a page, and the prompt publishes the tighter of that setting
and what the slot's output budget can hold (ADR-184), through a ratio measured on real pages. A
page that would load and do nothing is refused and said (`PageRefusal`): empty, over budget, a
script that never closes, an external script. A writer cut at its budget is a refusal, never a
page (ADR-275). `refusal_of` reads a page the way a browser tokenizes it, comments and strings
included.

### 8. A page has a budget of its own, and a retry that worked is no failure

ReAct requests no timeout, so a family's FLOOR is all a call ever gets there, and a document's is
120 s. Measured on 2026-11-05 at `high` reasoning, 44 to 67 s on one model, 95 to 158 s on two
others at 30,000 output tokens: real turns were cut at exactly 120 s, the tool's work lost.
The step now waits what the slot allows, floor and ceiling following it
(ADR-221 amendment 2026-11-05), so the loop never cuts what the client still waits for. The depth of
the reasoning stays the slot's: it is what separates a minute from three.

Pages were first written on the `document_generation` slot, so tuning one moved the other, while
their work differs: on average 13,000 to 29,000 output tokens for a page on the two models most
used on dev, 1,650 to 10,400 for a document in production. `interactive_page` is a slot of its own
(owner decision, 2026-11-05). A migration starts it on the row documents had, so nothing changes
until an administrator changes it; the rate limit and the step family stay shared.

The loop may relaunch a call that failed, and the response model never reads a tool's result: all
it knows is the failures directive. Listing the first attempt had it write « no page was produced »
beside the page the second one had shown, and quote a class name.
`failure_context._recovered_failures` leaves out a failure a later call of the same tool answered,
one success for one failure. A tool's failure message names no exception.

### 9. One switch

`PlatformCapability.INTERACTIVE_PAGES` removes the tool from every turn, the record staying
(ADR-280): a page already archived still opens. The demonstrator ships it off (owner decision,
2026-11-05).

## Consequences

- A person gets the thing they asked for, playable in the conversation, with its file below it
  and its source behind one button.
- A page in its first turn can freeze the tab: nothing stops an endless loop on the host's thread.
  The prompt forbids it and a reload recovers, because the page then waits for a click.
- The frame only grows: its measure is monotone, because a frame that shrinks to its body
  oscillates forever with absolutely positioned content. A short page keeps the 4:3 box, which is
  also what a full-window canvas game needs.
- `show` of code that loads a CDN is refused: the frame would run nothing.
- A page does not reach a channel that has no frame (Telegram): its file does.
- A page can still navigate to the two hosts the application frames, carrying data in that URL:
  Google Maps' embed path and Cloudflare's challenge host. It reaches no site of its choosing, which
  is what the FAQ says, and neither host hands the URL to anyone.
- Not measured: the Android and iOS WebViews (`task mobile:probe` needs their SDKs and must run
  after this CSP change).

## Measures (2026-11-05)

Routing, on the analyzer's production door with the real list of skills, strictly (a page with no
skill, a skill with no page, code with neither), 40 sentences in six languages:

| Model | Make | Code | Skill | Neighbour |
|---|---|---|---|---|
| claude-opus-5-5 | 14/14 | 11/11 | 8/8 | 7/7 |
| claude-sonnet-5-5 | 14/14 | 11/11 | 7/8 | 7/7 |
| claude-haiku-5-5 | 14/14 | 11/11 | 7/8 | 7/7 |
| deepseek-flash | 14/14 | 11/11 | 8/8 | 7/7 |
| gpt-5.4-mini | 5/14 | 4/11 | 8/8 | 6/7 |

The one miss of the Claude models is a unit conversion answered by the calculation tool. The
OpenAI model names the right domain but fills `skill_name` too, which the guards resolve, and sends
half of the code requests to a page. The Gemini family was not measured: the development image
carried an older SDK than the lockfile, and every call failed before any routing decision.

Writing, one page, by the model and depth of the slot:

| Model | `high` | `low` |
|---|---|---|
| claude-sonnet-5-5 | 44 to 67 s, 7 to 11 k tokens | 13 to 15 s, 2 k tokens |
| claude-haiku-5-5 | 109 to 127 s, 30 k tokens | 19 to 38 s, 5 to 10 k tokens |
| deepseek-flash | 95 to 172 s, 24 to 42 k tokens | 53 to 165 s, 13 to 40 k tokens |

The depth is worth a factor of three on two families and little on the third: what a person waits
for is the slot's MODEL first. Sixteen real pages from these models ran in the frame at 390 and
1100 px: no script error, no failure notice, no horizontal overflow, every control live.

## Alternatives rejected

- **Rendering the page in the bubble.** The sanitizer exists to refuse exactly this.
- **A dedicated origin for pages.** The sandbox's opaque origin gives the isolation with no second
  host, and a self-hosted instance has only one.
- **Reusing the skills' bridge.** It carries a request that opens a URL; see §3.
- **`allow-same-origin`, for a real `localStorage`.** It would hand the page the application's
  origin.
- **Running a restored page at once.** See §4.

## Key files

- `apps/api/src/domains/interactive_pages/` — `document.py` (policy, runtime, refusals),
  `service.py`, `schemas.py`
- `apps/api/src/domains/agents/interactive_page/` — manifests, `page_sources.py`
- `apps/api/src/domains/agents/tools/interactive_page_tools.py`
- `apps/api/src/domains/shared/frame_policy.py`
- `apps/api/alembic/versions/2026_11_05_2200-7c3e91a4d2f6_interactive_page_slot.py`
- `apps/api/src/domains/agents/nodes/react_context.py` (what the loop reads on a page turn)
- `apps/api/src/domains/agents/orchestration/step_timeouts.py` (the page's slot),
  `apps/api/src/domains/agents/services/analysis/skill_suppression.py`,
  `apps/api/src/domains/diagnostics/failure_context.py`
- `apps/web/src/components/chat/PageAppWidget.tsx`, `apps/web/src/hooks/usePageFrameBridge.ts`
- `apps/web/src/lib/markdown-source.ts`, `apps/web/src/lib/remark-literal-html.ts`

## References

- [INTERACTIVE_PAGES.md](../technical/INTERACTIVE_PAGES.md)
