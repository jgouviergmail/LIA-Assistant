'use client';

import { useEffect } from 'react';
import { useEyesChatStore, type EyesChatState } from '@/stores/eyesChatStore';

/** Publish phase changes without remounting the avatar or subscribing to tokens. */
export function useEyesChatState({ chatStatus, streamPhase, hitlAwaiting }: EyesChatState) {
  useEffect(() => {
    useEyesChatStore.getState().publish({ chatStatus, streamPhase, hitlAwaiting });
  }, [chatStatus, streamPhase, hitlAwaiting]);

  useEffect(() => () => useEyesChatStore.getState().reset(), []);
}
