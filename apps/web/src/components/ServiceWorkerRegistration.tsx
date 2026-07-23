'use client';

import { useEffect } from 'react';

/**
 * Unconditional service-worker registration (D5, ADR-146).
 *
 * Historically the SW was only registered inside the FCM permission flow —
 * users without push had NO service worker and therefore no offline shell.
 * Registration is idempotent: the FCM flow reuses this same registration.
 * Development is excluded (a caching SW on `next dev` poisons the workflow).
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') return;
    if (!('serviceWorker' in navigator)) return;
    navigator.serviceWorker
      .register('/firebase-messaging-sw.js', { scope: '/' })
      .catch(() => {
        // Offline shell is progressive enhancement — never break the app.
      });
  }, []);

  return null;
}
