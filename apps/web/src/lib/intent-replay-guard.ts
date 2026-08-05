/**
 * One-shot chat intents — the consumed-intent ledger (ADR-210).
 *
 * The FOURTH failure mode of the `?intent=` deep link, paid for in production
 * on 2026-08-05: the URL is a replayable carrier. ADR-192 made deep links real
 * navigations (`window.location.assign`), which records the intent URL as a
 * first-class VISIT in the browser's history — and `history.replaceState`
 * rewrites the session ENTRY, never the visit database. The omnibox, a
 * most-visited tile, a session/tab restore, a bookmark, or the App Router's
 * own entry bookkeeping can therefore resurrect the URL long after its
 * consumption, and every resurrection re-executed the request (measured: the
 * same "Prépare une réponse au mail…" sent twice, 27 s apart, each followed by
 * the user cancelling it).
 *
 * The three earlier hardenings (read live, History-API clear, clear-once-
 * consumed — see `useDeepLinkParams`) all policed the CARRIER, and each was
 * bypassed by a new resurrection path. This module makes consumption
 * idempotent at the CONSUMER instead: every click mints a fresh `iid`
 * (`chatIntentHref`), and its consumption is recorded here. A resurrected URL
 * carries a consumed iid, whatever brought it back.
 *
 * `localStorage`, deliberately: shared across tabs (a replay in a second tab
 * is still a replay) and across sessions (the omnibox resurrects days later).
 * Bounded FIFO — the ledger only needs to outlive the browser history's
 * autocomplete relevance for chat URLs, not grow forever. Storage failures
 * fail OPEN (private mode degrades to the pre-ledger behavior): a re-executed
 * request is recoverable by the user, a silently dropped one is not — the
 * same doctrine as the hook's quota-wall fallback.
 *
 * Intents WITHOUT an iid are outside this contract on purpose: the backend
 * emits durable `?intent=` links ("Run it now" on a proposed scheduled
 * action, `scheduled_action_executor.py`) where each click IS a consent and
 * replay across days is the intended use.
 */

const STORAGE_KEY = 'lia.chat.consumed-intent-ids';

/** Ledger capacity — a few weeks of clicks, far beyond omnibox relevance. */
const MAX_CONSUMED_IDS = 50;

/** Mint the one-shot id a single click travels with. */
export function newIntentId(): string {
  return crypto.randomUUID();
}

/** The consumed ids, oldest first; [] when storage is unavailable/corrupt. */
function readLedger(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

/**
 * Whether this click id has already been consumed — i.e. the URL carrying it
 * is a resurrection, not the click itself.
 */
export function isIntentConsumed(intentId: string): boolean {
  return readLedger().includes(intentId);
}

/**
 * Record a click id as consumed. Call it at the same moment the URL params
 * are dropped (`clearIntent`): the two writes together are what "consumed"
 * means. Idempotent; oldest ids beyond the cap are evicted.
 */
export function markIntentConsumed(intentId: string): void {
  try {
    const ledger = readLedger().filter(id => id !== intentId);
    ledger.push(intentId);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ledger.slice(-MAX_CONSUMED_IDS)));
  } catch {
    // Fail open: without a ledger the intent behaves as before ADR-210.
  }
}
