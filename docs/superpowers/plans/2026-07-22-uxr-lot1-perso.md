# UXR Lot 1 — PERSO: Bubble Action Row Implementation Plan

> **For agentic workers:** executed INLINE (program mandate — no subagents). Steps use
> checkbox syntax for tracking. Program doc:
> `docs/superpowers/specs/2026-07-22-ux-refinements-program.md` (Lot 1 spec + edge register).

**Goal:** move Copy + 👍/👎 from the top-right overlay of the assistant bubble into one
in-flow action row at the bubble's bottom (interest-notification pattern), fixing mobile
readability (<880px the overlay covers the first text lines).

**Architecture:** pure frontend layout refactor. `ChatMessage` renders one flex-wrap row
after `ExecutionTraceDisclosure`; `ResponseFeedbackButtons` loses its absolute wrapper and
becomes in-flow chips whose 👎 comment input wraps to a full-width second line
(`flex-wrap` + `w-full`). No backend, no endpoint, no i18n key change.

**Tech stack:** React 19, Tailwind v4, vitest + testing-library.

## Global constraints

- Behavioral tests keep passing untouched (roles/aria names unchanged).
- Always-visible row (interest pattern — the user's explicit reference); the ≥880px
  hover-reveal is dropped deliberately: an in-flow `opacity-0` row would reserve ghost
  space, and the reference pattern is always visible.
- **Deviation from program micro-decision, justified:** the action row (incl. Copy) is
  hidden while `isActiveStream` — an in-flow row at the growing edge of a streaming bubble
  would jitter on every token; the old absolute button did not. Copy of a partial answer
  is marginal. Program doc session log records this.
- Boy Scout (touched file): the `copied` reset `setTimeout` gets an unmount cleanup
  (timers rule, `apps/web/CLAUDE.md`).
- Gates: `task lint:frontend`, clean `tsc --noEmit --incremental false`,
  `pnpm test:coverage`, `a11y:ratchet`, `react-hooks:ratchet`, `cc:ratchet`; runtime
  browser proof (<880px + desktop) in the dev container.

---

### Task 1: New contract tests (fail first)

**Files:**
- Modify: `apps/web/src/components/chat/__tests__/ChatMessage.test.tsx`
- Modify: `apps/web/src/components/chat/__tests__/ResponseFeedbackButtons.test.tsx`

- [x] **Step 1: ChatMessage — action-row describe block** (streaming hides the row; chips
  + copy coexist in-flow for archived answers; copy-only without archived id; proactive
  rows keep the interest verdicts AND get the copy row; no `absolute` positioning class
  on the copy button).
- [x] **Step 2: ResponseFeedbackButtons — structural pins** (no overlay wrapper: chips are
  not inside an `absolute` container; the 👎 comment row carries `w-full`).
- [x] **Step 3: run — new tests FAIL on current implementation** (copy rendered while
  streaming today; copy button `absolute top-2 right-2`; chips wrapper `absolute`).

### Task 2: ResponseFeedbackButtons in-flow refactor

**Files:** `apps/web/src/components/chat/ResponseFeedbackButtons.tsx`

- [x] Replace the `absolute top-2 right-10 …` wrapper with an in-flow fragment: the two
  chip buttons stay identical (classes via `chipClass`, aria unchanged); the comment row
  becomes `w-full flex items-center gap-2 mt-1` (wraps under the row via parent
  `flex-wrap`; drops its own `border-t` — the row owns the separator). Header docstring
  updated (docstring-matches-behavior rule).

### Task 3: ChatMessage action row

**Files:** `apps/web/src/components/chat/ChatMessage.tsx`

- [x] Remove the absolute Copy `Tooltip` block (l.699-716); render after
  `ExecutionTraceDisclosure`, gated `!isActiveStream`:
  row `flex flex-wrap items-center gap-1 mt-2 pt-2 border-t border-border/30`,
  Copy chip (same chip idiom as the thumbs: `p-1.5 rounded-md border border-border/30
  bg-background/80 hover:bg-background transition-colors`) then
  `{feedbackProps && <ResponseFeedbackButtons …/>}`. Copy icon `h-3.5 w-3.5`.
- [x] `copied` timeout: store id in a ref, clear in an unmount effect.
- [x] Comment updates (QW-5 gate helper note: chips render **in the action row**).

### Task 4: Verify + gates

- [x] Full frontend suite green; updated tests still behavioral-first.
- [x] `task lint:frontend` + clean tsc + coverage + 3 ratchets.
- [x] Deep self-review pass (mandate) — then runtime browser proof (paired with Lot 2's
  session runtime slot): mobile viewport <880px shows the row under the answer, no
  overlay on text; desktop unchanged flows.
- [x] Program doc: tracker + session log updated (deviation recorded).
