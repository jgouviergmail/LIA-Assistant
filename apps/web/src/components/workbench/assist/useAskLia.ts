'use client';

/**
 * The door from the section to the chat (ADR-369, ADR-372): words left in its input, unsent.
 *
 * Apart from `useToolBridges`, because the shell's own search reads it and `useToolBridges` reads
 * the shell: one more import there would close a cycle.
 */
import { useAuth } from '@/hooks/useAuth';
import { seedInputDraft } from '@/hooks/useInputDraft';
import type { Language } from '@/i18n/settings';
import { chatDraftHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';

/** @returns What opens the chat on words: the person reads them and goes on from there. */
export function useAskLia(lng: Language): (words: string) => void {
  const { user } = useAuth();
  return words => {
    if (user) seedInputDraft(user.id, words);
    openChatDeepLink(chatDraftHref(lng));
  };
}
