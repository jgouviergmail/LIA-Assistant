'use client';

import { useEffect, useEffectEvent } from 'react';

/** Wake other world documents to verify their own cookie; never broadcast an account. */
export function useWorldIdentityNotice(ownerId: string, verify: () => Promise<void>) {
  const requestVerification = useEffectEvent(verify);
  useEffect(() => {
    if (typeof BroadcastChannel !== 'function') return;
    let channel: BroadcastChannel;
    try {
      channel = new BroadcastChannel('lia-world-identity-v1');
    } catch {
      // Storage-restricted browsers retain the existing focus/visibility check.
      return;
    }
    channel.onmessage = (event: MessageEvent<unknown>) => {
      const data = event.data;
      if (
        typeof data === 'object' &&
        data !== null &&
        'type' in data &&
        data.type === 'verify' &&
        'version' in data &&
        data.version === 1
      )
        void requestVerification();
    };
    channel.postMessage({ type: 'verify', version: 1 });
    return () => {
      channel.onmessage = null;
      channel.close();
    };
  }, [ownerId]);
}
