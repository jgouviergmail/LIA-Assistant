/**
 * Hook for managing Firebase Cloud Messaging (FCM) token.
 *
 * Handles:
 * - Requesting notification permission
 * - Obtaining FCM token
 * - Registering/unregistering token with backend
 * - Tracking permission status
 */

'use client';

import { useHydrated } from '@/hooks/useHydrated';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useTranslation } from 'react-i18next';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import {
  requestNotificationPermission,
  getNotificationPermission,
  areNotificationsSupported,
  isFirebaseConfigured,
  getDeviceType,
  isIOSPWA,
} from '@/lib/firebase';
import { enrolNativePush, type NativeEnrolment } from '@/lib/native/push';
import { isNativeShell } from '@/lib/native/shell';

export type FCMPermissionStatus = NotificationPermission | 'unsupported' | 'not-configured';

export interface RegisteredToken {
  id: string;
  device_type: 'android' | 'ios' | 'web';
  device_name: string | null;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

/**
 * Outcome of an enrolment attempt.
 *
 * Discriminated on purpose. A refusal and a technical failure call for
 * different things from the user — re-allow notifications in the browser, or
 * report a bug — so the caller must be able to tell them apart from the return
 * value alone. The former shape (`string | null`) forced callers to re-read the
 * hook's `error` / `permissionStatus` state after an `await`, which in React
 * yields the values captured by the render that created the handler: always
 * stale. In production that surfaced as `Enable failed: null` while the hook
 * held the real cause (2026-07-24, CSP blocking `getToken()`).
 */
export type EnrollmentResult =
  | { status: 'enrolled'; token: string }
  | { status: 'denied' }
  | { status: 'failed'; error: string };

export interface UseFCMTokenReturn {
  /** Current FCM token (null if not obtained) */
  token: string | null;
  /** Current permission status */
  permissionStatus: FCMPermissionStatus;
  /** Whether notifications are supported */
  isSupported: boolean;
  /** Whether Firebase is configured */
  isConfigured: boolean;
  /** Whether running as iOS PWA */
  isIOSPWA: boolean;
  /** Whether loading (requesting permission or registering) */
  isLoading: boolean;
  /** Error message if any */
  error: string | null;
  /** List of registered tokens for the user */
  registeredTokens: RegisteredToken[];
  /** Request permission, get the FCM token and register it with the backend */
  requestPermission: () => Promise<EnrollmentResult>;
  /** Unregister a token by ID from backend */
  unregisterToken: (tokenId: string) => Promise<void>;
  /** Refresh the list of registered tokens */
  refreshTokens: () => Promise<void>;
}

interface RegisterTokenRequest {
  token: string;
  device_type: 'android' | 'ios' | 'web';
  device_name?: string;
}

/**
 * Hook for managing FCM token and notification permissions.
 *
 * @example
 * ```tsx
 * const { token, permissionStatus, requestPermission, isLoading } = useFCMToken();
 *
 * const handleEnable = async () => {
 *   const result = await requestPermission();
 *   if (result.status === 'enrolled') toast.success('Notifications enabled!');
 *   else if (result.status === 'denied') toast.error('You blocked notifications');
 *   else logger.error('enrolment_failed', undefined, { cause: result.error });
 * };
 * ```
 */
export function useFCMToken(): UseFCMTokenReturn {
  const { i18n } = useTranslation();
  const { user } = useAuth();
  const ownerId = user?.id;
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const [token, setToken] = useApplicationAccountState<string | null>(ownerId, null);
  const [reportedPermission, setPermissionStatus] = useState<FCMPermissionStatus | null>(null);
  const hydrated = useHydrated();
  const [isLoading, setIsLoading] = useApplicationAccountState(ownerId, false);
  const [error, setError] = useApplicationAccountState<string | null>(ownerId, null);
  const [registeredTokens, setRegisteredTokens] = useApplicationAccountState<RegisteredToken[]>(
    ownerId,
    []
  );
  const latestRead = useRef<{ sequence: number; result: Promise<boolean> | null }>({
    sequence: 0,
    result: null,
  });

  // A native shell has neither `Notification` nor a Firebase web config, and
  // both are the wrong question to ask it: it gets its token from its host and
  // its configuration from the server it is pointed at. Answering "unsupported"
  // here would hide the feature on the two platforms that now have it.
  const inShell = typeof window !== 'undefined' && isNativeShell();
  const isSupported = typeof window !== 'undefined' && (areNotificationsSupported() || inShell);
  const isConfigured = typeof window !== 'undefined' && (isFirebaseConfigured() || inShell);
  const isiOSPWA = typeof window !== 'undefined' && isIOSPWA();

  const browserPermission: FCMPermissionStatus = !hydrated
    ? 'default'
    : !isSupported
      ? 'unsupported'
      : !isConfigured
        ? 'not-configured'
        : inShell
          ? 'default'
          : getNotificationPermission();
  const permissionStatus = reportedPermission ?? browserPermission;

  /**
   * Fetch registered tokens from backend.
   * Also re-checks browser permission status to sync state across components.
   */
  const refreshTokensVerified = useCallback(async (): Promise<boolean> => {
    if (!isCurrent()) return false;
    const request = ++latestRead.current.sequence;
    const read = async (): Promise<boolean> => {
      try {
        // The shell owns its permission; browser reads must not overwrite it.
        if (isSupported && isConfigured && !inShell) {
          setPermissionStatus(getNotificationPermission());
        }
        const response = await apiClient.get<{ tokens: RegisteredToken[] }>(
          '/notifications/tokens'
        );
        if (!isCurrent()) return false;
        if (request !== latestRead.current.sequence)
          return (await latestRead.current.result) ?? false;
        const devices = response.tokens ?? [];
        setRegisteredTokens(devices);
        logger.debug('FCM: Tokens refreshed', {
          component: 'useFCMToken',
          count: devices.length,
        });
        return true;
      } catch (err) {
        if (!isCurrent()) return false;
        if (request !== latestRead.current.sequence)
          return (await latestRead.current.result) ?? false;
        // The existing manual refresh stays silent; addressed sync reports failure.
        logger.warn('FCM: Failed to refresh tokens', {
          component: 'useFCMToken',
          error: err instanceof Error ? err.message : 'Unknown error',
        });
        return false;
      }
    };
    const pending = read();
    latestRead.current.result = pending;
    return await pending;
  }, [isSupported, isConfigured, inShell, isCurrent, setRegisteredTokens]);
  const refreshTokens = useCallback(async (): Promise<void> => {
    await refreshTokensVerified();
  }, [refreshTokensVerified]);
  const refreshOwnedDevices = useCallback(async () => {
    if (!(await refreshTokensVerified())) throw new Error('Notification device refresh failed');
  }, [refreshTokensVerified]);
  const release = useCallback(() => {}, []);
  useApplicationResourceSync(ownerId, 'notification_devices', refreshOwnedDevices, release);

  // Fetch registered tokens when permission is granted
  useEffect(() => {
    if (permissionStatus === 'granted') {
      refreshTokens();
    }
  }, [permissionStatus, refreshTokens]);

  /**
   * Request notification permission and register FCM token.
   * MUST be called from a user interaction (click event).
   */
  const requestPermission = useCallback(async (): Promise<EnrollmentResult> => {
    if (!isCurrent())
      return { status: 'failed', error: 'Account changed during notification enrollment' };
    if (!isSupported) {
      const message = 'Notifications are not supported in this browser';
      setError(message);
      logger.warn('FCM: Notifications not supported', { component: 'useFCMToken' });
      return { status: 'failed', error: message };
    }

    if (!isConfigured) {
      const message = 'Firebase is not configured';
      setError(message);
      logger.warn('FCM: Firebase not configured', { component: 'useFCMToken' });
      return { status: 'failed', error: message };
    }

    setIsLoading(true);
    setError(null);

    try {
      // Only the ACQUISITION differs between a browser and a shell. Everything
      // below — registering with this server, tracking state, refreshing the
      // list — is the same work, and duplicating it into a second hook is how
      // the two paths would drift.
      const acquired = await acquireCurrentPush(i18n.language, isCurrent);
      if (acquired.status === 'stale')
        return { status: 'failed', error: 'Account changed during notification enrollment' };
      const { native, token: fcmToken, permission: newPermission } = acquired;
      setPermissionStatus(newPermission);

      if (!fcmToken) {
        logger.info('FCM: Permission denied or token not obtained', {
          component: 'useFCMToken',
          permission: newPermission,
          reason: native?.reason,
        });
        // A user's refusal and a server with no push configured call for
        // different things, so they must not collapse into one answer.
        return unavailablePushResult(native);
      }

      // Register token with backend
      const deviceType = native ? native.deviceType : getDeviceType();
      const deviceName = getDeviceName();

      await apiClient.post<void>('/notifications/register-token', {
        token: fcmToken,
        device_type: deviceType,
        device_name: deviceName,
      } satisfies RegisterTokenRequest);
      if (!isCurrent())
        return { status: 'failed', error: 'Account changed during notification enrollment' };

      setToken(fcmToken);

      logger.info('FCM: Token registered successfully', {
        component: 'useFCMToken',
        deviceType,
      });

      // Refresh token list after registration
      await refreshTokens();
      if (!isCurrent())
        return { status: 'failed', error: 'Account changed during notification enrollment' };
      return { status: 'enrolled', token: fcmToken };
    } catch (err) {
      if (!isCurrent())
        return { status: 'failed', error: 'Account changed during notification enrollment' };
      // Extract detailed error message for debugging
      const message = err instanceof Error ? err.message : 'Failed to enable notifications';
      setError(message);

      // Log full error details
      logger.error('FCM: Failed to register token', err as Error, {
        component: 'useFCMToken',
        errorMessage: message,
        errorStack: err instanceof Error ? err.stack : undefined,
      });

      // Also log to console: the structured logger only carries err.message
      // ("Failed to fetch"), while the raw object keeps the browser's
      // explanation (e.g. the CSP directive that refused the connection).
      console.error('[useFCMToken] Registration failed:', err);

      return { status: 'failed', error: message };
    } finally {
      setIsLoading(false);
    }
  }, [
    isSupported,
    isConfigured,
    refreshTokens,
    i18n.language,
    isCurrent,
    setIsLoading,
    setError,
    setToken,
  ]);

  /**
   * Unregister a token by ID from backend.
   */
  const unregisterToken = useCallback(
    async (tokenId: string): Promise<void> => {
      if (!isCurrent()) return;
      setIsLoading(true);
      setError(null);

      try {
        await apiClient.delete<void>(`/notifications/tokens/${tokenId}`);
        if (!isCurrent()) return;

        // Refresh token list after unregistration
        await refreshTokens();

        // Clear current token if it was the one unregistered
        const unregisteredToken = registeredTokens.find(t => t.id === tokenId);
        if (unregisteredToken && token) {
          // We can't directly compare, so just clear if any token was removed
          setToken(null);
        }

        logger.info('FCM: Token unregistered successfully', {
          component: 'useFCMToken',
          tokenId,
        });
      } catch (err) {
        if (!isCurrent()) return;
        const message = err instanceof Error ? err.message : 'Failed to unregister token';
        setError(message);

        logger.error('FCM: Failed to unregister token', err as Error, {
          component: 'useFCMToken',
          tokenId,
        });

        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [token, registeredTokens, refreshTokens, isCurrent, setIsLoading, setError, setToken]
  );

  return {
    token,
    permissionStatus,
    isSupported,
    isConfigured,
    isIOSPWA: isiOSPWA,
    isLoading,
    error,
    registeredTokens,
    requestPermission,
    unregisterToken,
    refreshTokens,
  };
}

type PushAcquisition =
  | { status: 'stale' }
  | {
      status: 'ready';
      native: NativeEnrolment | null;
      token: string | null;
      permission: FCMPermissionStatus;
    };

async function acquireCurrentPush(
  language: string,
  isCurrent: () => boolean
): Promise<PushAcquisition> {
  const native = await enrolNativePush(language);
  if (!isCurrent()) return { status: 'stale' };
  const token = native ? native.token : await requestNotificationPermission();
  if (!isCurrent()) return { status: 'stale' };
  const permission: FCMPermissionStatus = native
    ? token
      ? 'granted'
      : 'denied'
    : getNotificationPermission();
  return { status: 'ready', native, token, permission };
}

function unavailablePushResult(native: NativeEnrolment | null): EnrollmentResult {
  return native && native.reason !== 'permission_denied'
    ? { status: 'failed', error: native.reason ?? 'native_push_unavailable' }
    : { status: 'denied' };
}

/**
 * Get device name for token registration.
 */
function getDeviceName(): string {
  if (typeof window === 'undefined') return 'Unknown';

  const userAgent = navigator.userAgent;

  // Try to extract device/browser info
  if (/iPhone/.test(userAgent)) return 'iPhone';
  if (/iPad/.test(userAgent)) return 'iPad';
  if (/Android/.test(userAgent)) {
    const match = userAgent.match(/Android[^;]*;[^;]*;\s*([^)]+)/);
    return match ? match[1].trim() : 'Android Device';
  }

  // Browser detection for web
  if (/Chrome/.test(userAgent)) return 'Chrome Browser';
  if (/Firefox/.test(userAgent)) return 'Firefox Browser';
  if (/Safari/.test(userAgent)) return 'Safari Browser';
  if (/Edge/.test(userAgent)) return 'Edge Browser';

  return 'Web Browser';
}
