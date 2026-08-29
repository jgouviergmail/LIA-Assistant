/**
 * LIA unified Service Worker: push notifications + offline shell (D5).
 *
 * HISTORICAL NAME — this file keeps its `firebase-messaging-sw.js` URL so
 * existing registrations update in place (renaming would strand them at
 * scope `/`). It now owns BOTH concerns (arbitration A7, ADR-146):
 *   1. Push (standard Push API, works with FCM — unchanged below).
 *   2. Offline shell: precached branded offline page served as the
 *      navigation fallback + stale-while-revalidate for same-origin static
 *      assets. API traffic (`/api/`), non-GET, and SSE are NEVER cached —
 *      personal data must not land on disk.
 *
 * CACHE_VERSION must equal package.json version — enforced by
 * `src/__tests__/service-worker.test.ts`; bump it with every release.
 */

const CACHE_VERSION = '1.37.0';
const SHELL_CACHE = `lia-shell-v${CACHE_VERSION}`;
const OFFLINE_URL = '/offline.html';

const PRECACHE_ASSETS = [OFFLINE_URL, '/icon-192.png', '/icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('lia-shell-v') && key !== SHELL_CACHE)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

/**
 * Whether a request may go through the cache layer at all.
 * API calls, non-GET, cross-origin, and event streams are always network-only.
 */
function isCacheableRequest(request) {
  if (request.method !== 'GET') return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  if (url.pathname.startsWith('/api/')) return false;
  if (request.headers.get('accept')?.includes('text/event-stream')) return false;
  return true;
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (!isCacheableRequest(request)) return; // browser default handling

  // Navigations: network-first, branded offline page as the fallback.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  // Static assets: stale-while-revalidate (hashed /_next/static is immutable).
  const url = new URL(request.url);
  const isStaticAsset =
    url.pathname.startsWith('/_next/static/') ||
    /\.(png|svg|jpg|jpeg|webp|ico|woff2?)$/.test(url.pathname);
  if (!isStaticAsset) return;

  event.respondWith(
    caches.open(SHELL_CACHE).then(async (cache) => {
      const cached = await cache.match(request);
      const refresh = fetch(request)
        .then((response) => {
          if (response.ok) cache.put(request, response.clone());
          return response;
        })
        .catch(() => cached);
      return cached || refresh;
    })
  );
});

/**
 * Handle push events.
 *
 * This is called when a push message is received, regardless of whether
 * the app is in the foreground or background.
 */
self.addEventListener('push', (event) => {
  console.log('[SW] Push received:', event);

  let data = {};
  let title = 'Notification';
  let body = '';

  try {
    // Try to parse the push data
    if (event.data) {
      const payload = event.data.json();
      console.log('[SW] Push payload:', payload);

      // FCM sends data in different formats depending on the message type
      // Handle both notification and data messages
      if (payload.notification) {
        title = payload.notification.title || title;
        body = payload.notification.body || body;
      }

      if (payload.data) {
        data = payload.data;
        // Fallback to data fields if notification fields are empty
        if (!title || title === 'Notification') {
          title = payload.data.title || title;
        }
        if (!body) {
          body = payload.data.body || body;
        }
      }

      // Handle direct FCM format
      if (payload.title) {
        title = payload.title;
      }
      if (payload.body) {
        body = payload.body;
      }
    }
  } catch (error) {
    console.error('[SW] Error parsing push data:', error);
    // Try to get text content as fallback
    if (event.data) {
      body = event.data.text();
    }
  }

  const notificationOptions = {
    body: body,
    // Must name a file that actually exists in public/ — a 404 here does not
    // fail loudly, the browser just falls back to a generic bell, so every
    // push silently loses its branding (the previous '/icon-192x192.png' had
    // no such file and resolved to the HTML app shell). No `badge` is set:
    // LIA ships no monochrome badge asset, and naming a missing one is the
    // same silent lie. Guarded by src/__tests__/service-worker.test.ts.
    icon: '/icon-192.png',
    // Use reminder_id as tag to prevent duplicate notifications
    tag: data.reminder_id || 'lia-notification',
    // Keep notification visible until user interacts
    requireInteraction: true,
    // Store data for click handling
    data: {
      ...data,
      url: data.url || '/dashboard/chat',
    },
    // Vibration pattern for mobile
    vibrate: [200, 100, 200],
  };

  // Show notification
  event.waitUntil(
    self.registration.showNotification(title, notificationOptions)
  );
});

/**
 * Handle notification click.
 *
 * Opens the app when user clicks on a notification.
 */
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked:', event);

  // Close the notification
  event.notification.close();

  // Get URL to open
  const urlToOpen = event.notification.data?.url || '/dashboard/chat';

  // Focus existing window or open new one
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // Check if there's already a window/tab open
      for (const client of windowClients) {
        // If a window is already open, focus it
        if (client.url.includes('/dashboard') && 'focus' in client) {
          return client.focus();
        }
      }

      // If no window is open, open a new one
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});

/**
 * Handle notification close.
 */
self.addEventListener('notificationclose', (event) => {
  console.log('[SW] Notification closed:', event);
});

// NOTE: install/activate are declared ONCE, at the top of this file. A second
// pair used to live here — leftovers from the push-only service worker this
// file replaced when the offline shell moved in (ADR-146). They were dead
// weight: an install whose waitUntil rejects is discarded whatever a bare
// skipWaiting() says, and clients.claim() was already handled above.
