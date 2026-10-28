'use client';

import { useEffect } from 'react';
import { useEyesChatStore, type EyesChatState } from '@/stores/eyesChatStore';
import { useCompanionActivityStore } from '@/stores/companionActivityStore';
import { useAuth } from '@/hooks/useAuth';

/** The native chat owns authentication; the renderer only reads scalar signals. */
export function useAuthenticatedEyesChatState(state: EyesChatState) {
  const { user } = useAuth();
  useEyesChatState(state, user?.id);
}

/** Publish phase changes without remounting the avatar or subscribing to tokens. */
export function useEyesChatState(
  { chatStatus, streamPhase, hitlAwaiting }: EyesChatState,
  ownerId?: string
) {
  useEffect(() => {
    if (ownerId) useCompanionActivityStore.getState().bindOwner(ownerId);
    useEyesChatStore.getState().publish({ chatStatus, streamPhase, hitlAwaiting }, ownerId);
  }, [chatStatus, streamPhase, hitlAwaiting, ownerId]);

  useEffect(
    () => () => {
      const store = useEyesChatStore.getState();
      if (store.ownerId === (ownerId ?? null)) store.reset();
    },
    [ownerId]
  );
}
