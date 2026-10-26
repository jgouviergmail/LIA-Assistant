/**
 * What the chat composer opens with — one priority, tested (ADR-210).
 *
 * The `?draft=` deep link wins (onboarding volet B / briefing intents), then a
 * REPLAYED intent (a consumed `?intent=` the browser resurrected — rule 4 in
 * `useDeepLinkParams`; shown as a draft so the arrival stays visible instead
 * of silently doing nothing: the persisted draft was read BEFORE the arrival
 * effect saved this text), then the persisted per-user draft (UXR Lot 2, A7).
 * Returns undefined when none applies so the input keeps its default empty
 * state. Never auto-sent.
 */

/** The single method this module needs from Next's ReadonlyURLSearchParams. */
import type { CardCompositionDraft } from '@/types/card-actions';

interface SearchParamsLike {
  get(name: string): string | null;
}

/** A newly chosen task starts without an older card's execution selection. */
export function resolveInitialComposition(
  composition: CardCompositionDraft | undefined,
  embedded: boolean | undefined,
  openingDraft: string | undefined
): CardCompositionDraft | undefined {
  return embedded && openingDraft !== undefined ? undefined : composition;
}

/**
 * Resolve the chat input's initial text.
 *
 * @param searchParams - The page's live search params (or null before hydration).
 * @param storedDraft - The persisted per-user draft, read once at mount.
 * @param replayedIntent - A resurrected intent degraded to a draft ('' = none).
 * @returns The initial composer text, or undefined for the default empty state.
 */
export function resolveInitialMessage(
  searchParams: SearchParamsLike | null,
  storedDraft: string | undefined,
  replayedIntent: string,
  embedded = false,
  openingDraft?: string
): string | undefined {
  if (embedded) return openingDraft ?? storedDraft;
  const draft = searchParams?.get('draft');
  if (draft && draft.trim()) return draft;
  if (replayedIntent) return replayedIntent;
  return storedDraft;
}
