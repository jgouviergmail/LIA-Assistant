'use client';

import { useApiQuery } from './useApiQuery';

/**
 * One grounded suggestion for the empty chat.
 *
 * The backend sends an id and parameters, never a sentence: the wording is
 * resolved here from the locale, like every other contract in this app.
 */
export interface ChatSuggestion {
  /** `next_event` | `important_mails` | `close_loop` — also the i18n suffix. */
  id: string;
  /** Interpolation values (an event title, a commitment subject). */
  params?: Record<string, string>;
}

interface ChatSuggestionsResponse {
  suggestions: ChatSuggestion[];
}

/**
 * Suggestions backed by what the briefing cache already holds.
 *
 * The endpoint never fetches a connector: a cold cache answers with an empty
 * list, which is the ordinary cold-start case rather than a failure. The
 * caller then shows the generic starters — the same fallback as before this
 * feature existed.
 *
 * @param enabled - Fetch only where the suggestions can be shown (an empty
 *   conversation); a busy chat must not pay for a list nobody will read.
 */
export function useChatSuggestions(enabled: boolean) {
  const { data, error } = useApiQuery<ChatSuggestionsResponse>('/chat/suggestions', {
    componentName: 'useChatSuggestions',
    enabled,
  });

  // An error is indistinguishable from "nothing to suggest" for the reader:
  // both mean the generic starters are shown. Surfacing it would be noise on
  // the one screen a newcomer is already unsure about.
  return { suggestions: error ? [] : (data?.suggestions ?? []) };
}
