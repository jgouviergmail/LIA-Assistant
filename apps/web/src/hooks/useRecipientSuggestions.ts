'use client';

/**
 * The contacts suggested for the recipient being typed in « Send by e-mail »
 * (ADR-321 amendment).
 *
 * One request per pause in typing: the query is debounced, and it is only
 * asked once it has settled, so a fast typist sends one request, not one per
 * key. The answer carries the query it answers, and only the answer to the
 * query in the field NOW is returned: `useApiQuery` still holds the previous
 * key's data on the render where the key changes, and a suggestion list
 * belonging to an older query is one Enter away from the wrong address.
 */

import { useApiQuery } from './useApiQuery';
import { useDebounce } from './useDebounce';
import type { RecipientSuggestionsResponse } from '@/lib/email-share/share';

/** The pause after which what is typed is asked about. */
export const RECIPIENT_SUGGESTIONS_DEBOUNCE_MS = 250;

export interface RecipientSuggestionsState {
  suggestions: RecipientSuggestionsResponse['suggestions'];
  /** The address book was longer than the instance reads. */
  truncated: boolean;
}

/**
 * @param query - The recipient being typed (`activeRecipient(...).query`).
 * @param enabled - The options published suggestions for this account.
 * @param minChars - The published shortest query.
 * @returns The suggestions for exactly this query, or none.
 */
export function useRecipientSuggestions(
  query: string,
  enabled: boolean,
  minChars: number
): RecipientSuggestionsState {
  const settled = useDebounce(query, RECIPIENT_SUGGESTIONS_DEBOUNCE_MS);
  const ask = enabled && settled === query && settled.length >= minChars;
  const { data } = useApiQuery<RecipientSuggestionsResponse>('/email-share/recipients', {
    componentName: 'RecipientSuggestions',
    enabled: ask,
    params: { q: settled },
  });
  if (!enabled || data === undefined || data.query !== query) {
    return { suggestions: [], truncated: false };
  }
  return { suggestions: data.suggestions, truncated: data.truncated };
}
