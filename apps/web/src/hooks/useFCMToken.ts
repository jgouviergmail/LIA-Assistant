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

import { useState, useCallback, useEffect } from 'react';
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

export type FCMPermissionStatus = NotificationPermission | 'unsupported' | 'not-configured';

export interface RegisteredToken {
  id: string;
  device_type: 'android' | 'ios' | 'web';
  device_name: string | null;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

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
  /** Request permission and get FCM token */
  requestPermission: () => Promise<string | null>;
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
 *   const newToken = await requestPermission();
 *   if (newToken) {
 *     toast.success('Notifications enabled!');
 *   }
 * };
 * ```
 */
export function useFCMToken(): UseFCMTokenReturn {
  const [token, setToken] = useState<string | null>(null);
  const [permissionStatus, setPermissionStatus] = useState<FCMPermissionStatus>('default');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registeredTokens, setRegisteredTokens] = useState<RegisteredToken[]>([]);

  const isSupported = typeof window !== 'undefined' && areNotificationsSupported();
  const isConfigured = typeof window !== 'undefined' && isFirebaseConfigured();
  const isiOSPWA = typeof window !== 'undefined' && isIOSPWA();

  // Initialize permission status on mount
  useEffect(() => {
    if (typeof window === 'undefined') return;

    if (!isSupported) {
      setPermissionStatus('unsupported');
      return;
    }

    if (!isConfigured) {
      setPermissionStatus('not-configured');
      return;
    }

    const currentPermission = getNotificationPermission();
    setPermissionStatus(currentPermission);
  }, [isSupported, isConfigured]);

  /**
   * Fetch registered tokens from backend.
   * Also re-checks browser permission status to sync state across components.
   */
  const refreshTokens = useCallback(async (): Promise<void> => {
    try {
      // FIX 2025-12-29: Also refresh permission status from browser
      // This ensures state is synced when another component instance grants permission
      if (isSupported && isConfigured) {
        const currentPermission = getNotificationPermission();
        setPermissionStatus(currentPermission);
      }

      const response = await apiClient.get<{ tokens: RegisteredToken[] }>('/notifications/tokens');
      setRegisteredTokens(response.tokens || []);

      logger.debug('FCM: Tokens refreshed', {
        component: 'useFCMToken',
        count: response.tokens?.length || 0,
      });
    } catch (err) {
      // Don't set error state for refresh failures - it's not critical
      logger.warn('FCM: Failed to refresh tokens', {
        component: 'useFCMToken',
        error: err instanceof Error ? err.message : 'Unknown error',
      });
    }
  }, [isSupported, isConfigured]);

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
  const requestPermission = useCallback(async (): Promise<string | null> => {
    if (!isSupported) {
      setError('Notifications are not supported in this browser');
      logger.warn('FCM: Notifications not supported', { component: 'useFCMToken' });
      return null;
    }

    if (!isConfigured) {
      setError('Firebase is not configured');
      logger.warn('FCM: Firebase not configured', { component: 'useFCMToken' });
      return null;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Request permission and get token from Firebase
      const fcmToken = await requestNotificationPermission();

      // Update permission status
      const newPermission = getNotificationPermission();
      setPermissionStatus(newPermission);

      if (!fcmToken) {
        logger.info('FCM: Permission denied or token not obtained', {
          component: 'useFCMToken',
          permission: newPermission,
        });
        return null;
      }

      // Register token with backend
      const deviceType = getDeviceType();
      const deviceName = getDeviceName();

      await apiClient.post<void>('/notifications/register-token', {
        token: fcmToken,
        device_type: deviceType,
        device_name: deviceName,
      } as RegisterTokenRequest);

      setToken(fcmToken);

      logger.info('FCM: Token registered successfully', {
        component: 'useFCMToken',
        deviceType,
        tokenPrefix: fcmToken.substring(0, 20) + '...',
      });

      // Refresh token list after registration
      await refreshTokens();

      return fcmToken;
    } catch (err) {
      // Extract detailed error message for debugging
      const message = err instanceof Error ? err.message : 'Failed to enable notifications';
      setError(message);

      // Log full error details
      logger.error('FCM: Failed to register token', err as Error, {
        component: 'useFCMToken',
        errorMessage: message,
        errorStack: err instanceof Error ? err.stack : undefined,
      });

      // Also log to console for easier debugging
      console.error('[useFCMToken] Registration failed:', err);

      return null;
    } finally {
      setIsLoading(false);
    }
  }, [isSupported, isConfigured, refreshTokens]);

  /**
   * Unregister a token by ID from backend.
   */
  const unregisterToken = useCallback(async (tokenId: string): Promise<void> => {
    setIsLoading(true);
    setError(null);

    try {
      await apiClient.delete<void>(`/notifications/tokens/${tokenId}`);

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
  }, [token, registeredTokens, refreshTokens]);

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
