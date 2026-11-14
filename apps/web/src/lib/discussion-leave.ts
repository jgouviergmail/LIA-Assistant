/**
 * Leaving the discussion on screen: when it is allowed, and where the history
 * search may lead (lot 12).
 *
 * ONE rule for every way out of a discussion — the switcher, and a history
 * search result found in another discussion: a turn keeps running in the
 * background only where the deployment runs it there; elsewhere, leaving
 * mid-turn is held. Unknown rules (an API that publishes none) hold too.
 */

import type { DiscussionSearchResult } from '@/hooks/useConversation';
import type {
  ConversationCatalogueConfig,
  ConversationCataloguePage,
  ConversationSummary,
} from '@/types/conversation';

export function leavingCancelsTurn(
  typing: boolean,
  rules: ConversationCatalogueConfig | undefined
): boolean {
  return typing && rules?.background_runs_enabled !== true;
}

export interface DiscussionReach {
  /** The discussion on screen; `null` for Main before its first message. */
  currentId: string | null;
  /** Whether the account holds discussions besides the one on screen. */
  hasOtherDiscussions: boolean;
  /** Opens the discussion holding a result; absent while leaving would cancel a turn. */
  openResult?: (row: DiscussionSearchResult) => void;
}

/**
 * How far the history search reaches beyond the discussion on screen.
 *
 * The other discussions are counted from the switcher's catalogue, which holds
 * the discussion on screen once it exists (Main before its first message does
 * not); an unread catalogue counts as « some », since the search is a read. A
 * result found elsewhere opens through the switcher's own door, `open`.
 */
export function discussionReach(args: {
  switcher: { rules: ConversationCatalogueConfig; page?: ConversationCataloguePage } | undefined;
  current: ConversationSummary | null;
  typing: boolean;
  open: (id: string | null) => void;
}): DiscussionReach {
  const { switcher, current, typing, open } = args;
  const currentId = current?.id ?? null;
  if (!switcher) return { currentId, hasOtherDiscussions: false };
  const total = switcher.page?.total_count;
  const hasOtherDiscussions = total === undefined || total > (current ? 1 : 0);
  if (leavingCancelsTurn(typing, switcher.rules)) return { currentId, hasOtherDiscussions };
  return {
    currentId,
    hasOtherDiscussions,
    openResult: row => open(row.conversation_kind === 'secondary' ? row.conversation_id : null),
  };
}
