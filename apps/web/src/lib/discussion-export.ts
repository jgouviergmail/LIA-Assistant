import { apiEndpointUrl } from '@/lib/api-client';
import type { ConversationSummary } from '@/types/conversation';

/**
 * Where one discussion downloads as a Markdown document.
 *
 * A URL the BROWSER follows, so it goes through the API origin
 * (`apiEndpointUrl`), never a path relative to the page.
 *
 * An annex is named by its identity AND the generation the person is looking
 * at: a discussion reset meanwhile is refused rather than exported under the
 * title of what it used to hold. Main is asked for with no selection — the
 * server resolves its current generation itself, and the list does not hold
 * Main's row on every page.
 *
 * @param target - The annex, or Main (its row, or `null` when the page shown
 *   does not list it).
 * @returns The download address.
 */
export function discussionExportUrl(target: ConversationSummary | null): string {
  if (target?.kind !== 'secondary') return apiEndpointUrl('/conversations/me/export');
  const selection = new URLSearchParams({
    conversation_id: target.id,
    conversation_revision: String(target.revision),
  });
  return apiEndpointUrl(`/conversations/me/export?${selection}`);
}
