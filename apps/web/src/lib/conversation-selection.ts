/** One serialization for the public discussion coordinate on all HTTP doors. */
import type { ConversationSelection, ConversationSummary } from '@/types/conversation';

export function discussionSelection(target: ConversationSummary | null): ConversationSelection | undefined {
  if (target === null) return undefined;
  return { conversation_id: target.id, conversation_revision: target.revision };
}

export function conversationParams(
  selection?: ConversationSelection
): Record<string, string | number> {
  return selection
    ? {
        conversation_id: selection.conversation_id,
        conversation_revision: selection.conversation_revision,
      }
    : {};
}

export function conversationQuery(selection?: ConversationSelection): string {
  if (!selection) return '';
  return `?${new URLSearchParams({ conversation_id: selection.conversation_id, conversation_revision: String(selection.conversation_revision) })}`;
}

export function conversationScopeKey(
  ownerId: string | undefined,
  selection?: ConversationSelection
): string {
  return JSON.stringify([
    ownerId ?? null,
    selection?.conversation_id ?? 'main',
    selection?.conversation_revision ?? 0,
  ]);
}

/** Explicit coordinates never attach to another generation's stream. */
export function isSelectedRun(
  run: {
    conversation_id?: string | null;
    conversation_revision?: number | null;
    conversation_kind?: 'main' | 'secondary' | null;
    can_resume?: boolean;
  },
  selection?: ConversationSelection
): boolean {
  if (!selection) return run.conversation_kind !== 'secondary' && run.can_resume !== false;
  return (
    run.can_resume === true &&
    run.conversation_id === selection.conversation_id &&
    run.conversation_revision === selection.conversation_revision
  );
}
