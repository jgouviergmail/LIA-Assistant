/**
 * Firebase Cloud Messaging (FCM) configuration.
 *
 * Provides push notification support for:
 * - Web browsers (Chrome, Firefox, Safari 16.4+)
 * - Mobile PWA (when installed to home screen)
 *
 * Prerequisites:
 * - Firebase project configured
 * - VAPID key generated
 * - Service worker registered
 */

import { initializeApp, getApps, getApp, FirebaseApp } from 'firebase/app';
import { getMessaging, getToken, onMessage, Messaging, MessagePayload } from 'firebase/messaging';

// Firebase configuration from environment variables
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// VAPID key for web push
const VAPID_KEY = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY;

// Firebase app singleton
let app: FirebaseApp | null = null;
let messaging: Messaging | null = null;

/**
 * Check if Firebase is properly configured.
 */
export function isFirebaseConfigured(): boolean {
  return !!(
    firebaseConfig.apiKey &&
    firebaseConfig.projectId &&
    firebaseConfig.messagingSenderId &&
    VAPID_KEY
  );
}

/**
 * Check if notifications are supported in the current browser.
 */
export function areNotificationsSupported(): boolean {
  if (typeof window === 'undefined') return false;
  return 'Notification' in window && 'serviceWorker' in navigator;
}

/**
 * Check if running as installed PWA on iOS.
 */
export function isIOSPWA(): boolean {
  if (typeof window === 'undefined') return false;
  const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const isStandalone =
    (window.navigator as unknown as { standalone?: boolean }).standalone === true;
  return isIOS && isStandalone;
}

/**
 * Initialize Firebase app.
 */
function getFirebaseApp(): FirebaseApp | null {
  if (typeof window === 'undefined') return null;

  if (!isFirebaseConfigured()) {
    console.warn('[Firebase] Not configured - missing environment variables');
    return null;
  }

  if (app) return app;

  try {
    app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
    return app;
  } catch (error) {
    console.error('[Firebase] Initialization failed:', error);
    return null;
  }
}

/**
 * Get Firebase Messaging instance.
 */
function getFirebaseMessaging(): Messaging | null {
  if (typeof window === 'undefined') return null;

  if (!areNotificationsSupported()) {
    console.warn('[Firebase] Notifications not supported in this browser');
    return null;
  }

  if (messaging) return messaging;

  const firebaseApp = getFirebaseApp();
  if (!firebaseApp) return null;

  try {
    messaging = getMessaging(firebaseApp);
    return messaging;
  } catch (error) {
    console.error('[Firebase] Messaging initialization failed:', error);
    return null;
  }
}

/**
 * Request notification permission and get FCM token.
 *
 * IMPORTANT: This function MUST be called from a user interaction (click event)
 * to work properly on all browsers, especially iOS Safari.
 *
 * @returns FCM token if permission granted, null otherwise
 * @throws Error with detailed message for debugging
 */
export async function requestNotificationPermission(): Promise<string | null> {
  console.log('[Firebase] Starting permission request...');
  console.log('[Firebase] Config check:', {
    apiKey: firebaseConfig.apiKey ? 'SET' : 'MISSING',
    projectId: firebaseConfig.projectId ? 'SET' : 'MISSING',
    messagingSenderId: firebaseConfig.messagingSenderId ? 'SET' : 'MISSING',
    vapidKey: VAPID_KEY ? 'SET' : 'MISSING',
  });

  if (!areNotificationsSupported()) {
    const msg = '[Firebase] Notifications not supported in this browser';
    console.warn(msg);
    throw new Error(msg);
  }

  if (!isFirebaseConfigured()) {
    const msg = `[Firebase] Not configured - missing: ${[
      !firebaseConfig.apiKey && 'apiKey',
      !firebaseConfig.projectId && 'projectId',
      !firebaseConfig.messagingSenderId && 'messagingSenderId',
      !VAPID_KEY && 'vapidKey',
    ]
      .filter(Boolean)
      .join(', ')}`;
    console.warn(msg);
    throw new Error(msg);
  }

  try {
    // Request permission
    console.log('[Firebase] Requesting notification permission...');
    const permission = await Notification.requestPermission();
    console.log('[Firebase] Permission result:', permission);

    if (permission !== 'granted') {
      console.info('[Firebase] Notification permission denied');
      return null;
    }

    // Get messaging instance
    console.log('[Firebase] Getting messaging instance...');
    const messagingInstance = getFirebaseMessaging();
    if (!messagingInstance) {
      throw new Error('[Firebase] Messaging instance not available');
    }

    // Register service worker
    console.log('[Firebase] Registering service worker...');
    const registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js', {
      scope: '/',
    });
    console.log('[Firebase] Service worker registered:', registration.scope);

    // Wait for service worker to be ready
    console.log('[Firebase] Waiting for service worker to be ready...');
    await navigator.serviceWorker.ready;
    console.log('[Firebase] Service worker is ready');

    // Get FCM token
    console.log('[Firebase] Getting FCM token with VAPID key...');
    const token = await getToken(messagingInstance, {
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: registration,
    });

    if (token) {
      console.info('[Firebase] FCM token obtained:', token.substring(0, 20) + '...');
      return token;
    } else {
      throw new Error('[Firebase] No FCM token received from Firebase');
    }
  } catch (error) {
    console.error('[Firebase] Error getting FCM token:', error);
    throw error;
  }
}

/**
 * Get current notification permission status.
 */
export function getNotificationPermission(): NotificationPermission | 'unsupported' {
  if (!areNotificationsSupported()) {
    return 'unsupported';
  }
  return Notification.permission;
}

/**
 * Subscribe to foreground messages.
 *
 * These are messages received when the app is in the foreground (tab visible).
 * Background messages are handled by the service worker.
 *
 * @param callback Function to call when a message is received
 * @returns Unsubscribe function
 */
export function onForegroundMessage(
  callback: (payload: MessagePayload) => void
): (() => void) | null {
  const messagingInstance = getFirebaseMessaging();
  if (!messagingInstance) return null;

  return onMessage(messagingInstance, payload => {
    console.info('[Firebase] Foreground message received:', payload);
    callback(payload);
  });
}

/**
 * Get device type for FCM token registration.
 */
export function getDeviceType(): 'android' | 'ios' | 'web' {
  if (typeof window === 'undefined') return 'web';

  const userAgent = navigator.userAgent.toLowerCase();

  if (/android/.test(userAgent)) {
    return 'android';
  }

  if (/iphone|ipad|ipod/.test(userAgent)) {
    return 'ios';
  }

  return 'web';
}

export { firebaseConfig, VAPID_KEY };
