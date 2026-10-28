/** The chat page publishes phases; the persistent application avatar reads them. */
import { create } from 'zustand';
import type { ChatState, StreamPhase } from '@/types/chat-state';

export interface EyesChatState {
  chatStatus: ChatState['status'];
  streamPhase: StreamPhase;
  hitlAwaiting: boolean;
}

export const RESTING_CHAT: EyesChatState = {
  chatStatus: 'idle',
  streamPhase: 'answer',
  hitlAwaiting: false,
};

interface EyesChatStore {
  ownerId: string | null;
  state: EyesChatState;
  publish: (state: EyesChatState, ownerId?: string) => void;
  reset: () => void;
}

/** Ephemeral scalar signals only: no messages, persistence or second chat session. */
export const useEyesChatStore = create<EyesChatStore>(set => ({
  ownerId: null,
  state: RESTING_CHAT,
  publish: (state, ownerId) => set({ state, ownerId: ownerId ?? null }),
  reset: () => set({ state: RESTING_CHAT, ownerId: null }),
}));
