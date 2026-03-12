/**
 * Firebase Cloud Messaging Service Worker.
 *
 * Handles push notifications when the app is in the background or closed.
 *
 * This service worker uses the standard Push API which works with FCM.
 * The Firebase client SDK handles token management, while this SW
 * handles receiving and displaying push notifications.
 *
 * IMPORTANT:
 * - This file MUST be at the root of the public folder
 * - Works with FCM without needing Firebase SDK in the service worker
 */

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
    icon: '/icon-192x192.png',
    badge: '/badge-72x72.png',
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

/**
 * Handle service worker installation.
 */
self.addEventListener('install', (event) => {
  console.log('[SW] Installing...');
  // Skip waiting to activate immediately
  self.skipWaiting();
});

/**
 * Handle service worker activation.
 */
self.addEventListener('activate', (event) => {
  console.log('[SW] Activated');
  // Claim all clients immediately
  event.waitUntil(clients.claim());
});
