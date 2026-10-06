import type { ChatAction, ChatState } from '@/types/chat-state';
import { initialHitlCardState } from '@/types/hitl';

/** An authoritative read applies only to the card it started reading. */
export function syncPendingHitl(
  state: ChatState,
  action: Extract<ChatAction, { type: 'HITL_SYNC' }>
): ChatState {
  const { expected, payload } = action.payload;
  if (state.hitl !== expected || !['idle', 'error'].includes(state.status)) return state;
  if (state.hitl.status === 'submitting' || state.hitl.status === 'resolved') return state;
  if (!payload) {
    return state.hitl.status === 'awaiting' ? { ...state, hitl: initialHitlCardState } : state;
  }
  // A repeated read must preserve the card's edit/focus and expired state.
  if (payload.messageId === state.hitl.payload?.messageId) return state;
  return {
    ...state,
    hitl: { status: 'awaiting', payload, resolution: null, submittedAction: null },
  };
}
