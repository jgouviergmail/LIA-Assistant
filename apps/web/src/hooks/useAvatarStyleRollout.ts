'use client';

import { useEffect } from 'react';
import { readPublicUiJson } from '@/lib/api-client';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import { avatarStyleRolloutIdFromConfig } from '@/lib/runtime-ui';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';

/** The authenticated host applies an explicit operator campaign once per browser. */
export function useAvatarStyleRollout(): void {
  useEffect(() => {
    const controller = new AbortController();
    const synchronize = () => {
      void useEyesWidgetStore.persist?.rehydrate();
    };
    const onStorage = (event: StorageEvent) => {
      try {
        if (event.storageArea === localStorage && event.key === EYES_WIDGET_PREFS_KEY)
          synchronize();
      } catch {
        // Privacy settings can make browser storage unavailable.
      }
    };
    window.addEventListener('storage', onStorage);

    const apply = (id: string) => {
      if (controller.signal.aborted) return;
      // This store uses synchronous localStorage: rehydrate reads the latest
      // marker and any later user choice before the atomic style+marker write.
      synchronize();
      if (controller.signal.aborted || !useEyesWidgetStore.persist?.hasHydrated()) return;
      useEyesWidgetStore.getState().applyAvatarStyleRollout(id);
    };
    const read = async () => {
      try {
        const config = await readPublicUiJson<unknown>('/api/runtime-ui', {
          signal: controller.signal,
        });
        const id = avatarStyleRolloutIdFromConfig(config);
        if (!id || controller.signal.aborted) return;
        // Web Locks serialize simultaneous first visits of this same origin.
        // Older browsers still re-read the stored marker immediately before applying.
        if (navigator.locks) {
          await navigator.locks.request(
            `${EYES_WIDGET_PREFS_KEY}:avatar-style-rollout`,
            { signal: controller.signal },
            () => apply(id)
          );
        } else apply(id);
      } catch {
        // Unavailable configuration/storage must leave the person's choice alone.
      }
    };
    // StrictMode's cancelled probe never sends a request.
    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) return read();
    });
    return () => {
      controller.abort();
      window.removeEventListener('storage', onStorage);
    };
  }, []);
}
