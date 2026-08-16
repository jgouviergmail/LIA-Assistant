import { useState, useEffect, useCallback } from 'react';
import { GEOLOCATION_CACHE_KEY, GEOLOCATION_ENABLED_KEY } from '@/lib/constants';
import { logger } from '@/lib/logger';

/**
 * Browser geolocation coordinates.
 */
export interface GeolocationCoordinates {
  lat: number;
  lon: number;
  accuracy: number | null;
  timestamp: number;
}

/**
 * Permission state for geolocation.
 */
export type GeolocationPermission = 'granted' | 'denied' | 'prompt' | 'unsupported';

/**
 * Geolocation hook state.
 */
export interface GeolocationState {
  /** Current coordinates (null if not available) */
  coordinates: GeolocationCoordinates | null;
  /** Current permission state */
  permission: GeolocationPermission;
  /** Whether geolocation is loading */
  isLoading: boolean;
  /** Error message if any */
  error: string | null;
  /** Whether geolocation is enabled by user preference */
  isEnabled: boolean;
}

/**
 * Cache validity duration in milliseconds (5 minutes).
 */
const CACHE_VALIDITY_MS = 5 * 60 * 1000;

/**
 * Auto-retry delay in milliseconds (3 seconds).
 */
const AUTO_RETRY_DELAY_MS = 3000;

/**
 * Maximum number of auto-retry attempts.
 */
const MAX_AUTO_RETRY_ATTEMPTS = 2;

/**
 * Custom hook for managing browser geolocation.
 *
 * Features:
 * - Automatic permission detection
 * - Opt-in/opt-out toggle with localStorage persistence
 * - Cached coordinates for quick access
 * - Error handling with user-friendly messages
 * - PWA lifecycle handling (2026-08-16): on return-to-foreground
 *   (`visibilitychange`/`pageshow`), a granted permission triggers a silent
 *   position refresh, and a permission that fell back to `prompt` (iOS
 *   standalone does this after inactivity) is surfaced as
 *   `needsReactivation` — the native sheet needs a user gesture, so the UI
 *   must offer one instead of the hook firing blindly.
 *
 * @returns Geolocation state and control functions
 *
 * @example
 * ```tsx
 * const { coordinates, permission, isEnabled, enable, disable, refresh } = useGeolocation();
 *
 * // Check if geolocation is available
 * if (coordinates) {
 *   console.log(`User is at ${coordinates.lat}, ${coordinates.lon}`);
 * }
 * ```
 */
export const useGeolocation = () => {
  const [state, setState] = useState<GeolocationState>({
    coordinates: null,
    permission: 'prompt',
    isLoading: false,
    error: null,
    isEnabled: false,
  });

  // Track retry attempts for auto-retry logic
  const [retryCount, setRetryCount] = useState(0);

  /**
   * Load cached coordinates from localStorage.
   */
  const loadCachedCoordinates = useCallback((): GeolocationCoordinates | null => {
    try {
      const cached = localStorage.getItem(GEOLOCATION_CACHE_KEY);
      if (cached) {
        const parsed = JSON.parse(cached) as GeolocationCoordinates;
        // Check if cache is still valid
        if (Date.now() - parsed.timestamp < CACHE_VALIDITY_MS) {
          return parsed;
        }
      }
    } catch {
      // Ignore parse errors
    }
    return null;
  }, []);

  /**
   * Save coordinates to localStorage cache.
   */
  const saveCachedCoordinates = useCallback((coords: GeolocationCoordinates) => {
    try {
      localStorage.setItem(GEOLOCATION_CACHE_KEY, JSON.stringify(coords));
    } catch {
      // Ignore storage errors
    }
  }, []);

  /**
   * Check and update permission state.
   */
  const checkPermission = useCallback(async (): Promise<GeolocationPermission> => {
    if (!navigator.geolocation) {
      return 'unsupported';
    }

    try {
      const result = await navigator.permissions.query({ name: 'geolocation' });
      return result.state as GeolocationPermission;
    } catch {
      // Fallback for browsers that don't support permissions API
      return 'prompt';
    }
  }, []);

  /**
   * Request geolocation from browser.
   */
  const requestGeolocation = useCallback(async (): Promise<GeolocationCoordinates | null> => {
    if (!navigator.geolocation) {
      setState(prev => ({
        ...prev,
        permission: 'unsupported',
        error: 'Geolocation not supported by browser',
      }));
      return null;
    }

    return new Promise(resolve => {
      setState(prev => ({ ...prev, isLoading: true, error: null }));

      navigator.geolocation.getCurrentPosition(
        position => {
          const coords: GeolocationCoordinates = {
            lat: position.coords.latitude,
            lon: position.coords.longitude,
            accuracy: position.coords.accuracy,
            timestamp: Date.now(),
          };

          saveCachedCoordinates(coords);

          setState(prev => ({
            ...prev,
            coordinates: coords,
            permission: 'granted',
            isLoading: false,
            error: null,
          }));

          logger.info('geolocation_obtained', {
            component: 'useGeolocation',
            accuracy: coords.accuracy,
          });

          resolve(coords);
        },
        error => {
          let errorMessage: string;
          let permission: GeolocationPermission = 'denied';

          switch (error.code) {
            case error.PERMISSION_DENIED:
              errorMessage = 'Permission denied';
              permission = 'denied';
              break;
            case error.POSITION_UNAVAILABLE:
              errorMessage = 'Position unavailable';
              permission = 'granted'; // Permission was granted but position failed
              break;
            case error.TIMEOUT:
              errorMessage = 'Request timeout';
              permission = 'granted';
              break;
            default:
              errorMessage = 'Unknown error';
          }

          setState(prev => ({
            ...prev,
            coordinates: null,
            permission,
            isLoading: false,
            error: errorMessage,
          }));

          logger.warn('geolocation_error', {
            component: 'useGeolocation',
            code: error.code,
            message: errorMessage,
          });

          resolve(null);
        },
        {
          enableHighAccuracy: false,
          timeout: 10000,
          maximumAge: CACHE_VALIDITY_MS,
        }
      );
    });
  }, [saveCachedCoordinates]);

  /**
   * Enable geolocation and request permission.
   * @returns The coordinates if successful, null if permission denied or error
   */
  const enable = useCallback(async (): Promise<GeolocationCoordinates | null> => {
    localStorage.setItem(GEOLOCATION_ENABLED_KEY, 'true');
    setState(prev => ({ ...prev, isEnabled: true }));
    const result = await requestGeolocation();
    return result;
  }, [requestGeolocation]);

  /**
   * Disable geolocation and clear cached data.
   */
  const disable = useCallback(() => {
    localStorage.setItem(GEOLOCATION_ENABLED_KEY, 'false');
    localStorage.removeItem(GEOLOCATION_CACHE_KEY);
    setState(prev => ({
      ...prev,
      isEnabled: false,
      coordinates: null,
      error: null,
    }));

    logger.info('geolocation_disabled', {
      component: 'useGeolocation',
    });
  }, []);

  /**
   * Refresh geolocation (request new position).
   */
  const refresh = useCallback(async () => {
    if (state.isEnabled) {
      await requestGeolocation();
    }
  }, [state.isEnabled, requestGeolocation]);

  /**
   * Initialize on mount.
   */
  useEffect(() => {
    const initialize = async () => {
      // Check if geolocation is enabled in preferences
      const enabled = localStorage.getItem(GEOLOCATION_ENABLED_KEY) === 'true';

      // Check permission state
      const permission = await checkPermission();

      // Load cached coordinates
      const cached = loadCachedCoordinates();

      setState(prev => ({
        ...prev,
        isEnabled: enabled,
        permission,
        coordinates: cached,
      }));

      // If enabled and permission granted, refresh coordinates
      if (enabled && permission === 'granted') {
        requestGeolocation();
      }
    };

    initialize();
  }, [checkPermission, loadCachedCoordinates, requestGeolocation]);

  /**
   * Listen for permission changes.
   */
  useEffect(() => {
    if (!navigator.permissions) return;

    let permissionStatus: PermissionStatus | null = null;
    let handleChange: (() => void) | null = null;

    const setupListener = async () => {
      try {
        permissionStatus = await navigator.permissions.query({ name: 'geolocation' });

        handleChange = () => {
          setState(prev => ({
            ...prev,
            permission: permissionStatus?.state as GeolocationPermission,
          }));

          // If permission was just granted and geolocation is enabled, refresh
          if (permissionStatus?.state === 'granted' && state.isEnabled) {
            requestGeolocation();
          }
        };

        permissionStatus.addEventListener('change', handleChange);
      } catch {
        // Permissions API not fully supported
      }
    };

    setupListener();

    return () => {
      // Properly cleanup event listener to prevent memory leaks
      if (permissionStatus && handleChange) {
        permissionStatus.removeEventListener('change', handleChange);
      }
    };
  }, [state.isEnabled, requestGeolocation]);

  /**
   * PWA lifecycle: react to the app returning to the foreground.
   *
   * A frozen-then-resumed PWA keeps the mounted hook state forever: the
   * cached position expires, nothing ever refreshes, and every chat request
   * ships a null geolocation (measured on Android/iOS, 2026-08-16). On
   * `visibilitychange`→visible and `pageshow` (bfcache restore):
   * - permission re-checked (iOS standalone can silently drop a grant);
   * - `granted` + no fresh cache → silent getCurrentPosition (no prompt);
   * - `prompt` → no call (the native sheet requires a user gesture — the
   *   proactive banner owns that), the state update flips `needsReactivation`.
   *
   * The enabled flag is read from localStorage, not from the closure state:
   * the listener is registered once and must see the CURRENT preference.
   */
  useEffect(() => {
    if (typeof document === 'undefined') return;

    const handleReturnToForeground = async () => {
      if (document.visibilityState !== 'visible') return;
      if (localStorage.getItem(GEOLOCATION_ENABLED_KEY) !== 'true') return;

      const permission = await checkPermission();
      setState(prev => (prev.permission === permission ? prev : { ...prev, permission }));

      if (permission !== 'granted') {
        if (permission === 'prompt') {
          logger.info('geolocation_foreground_needs_reactivation', {
            component: 'useGeolocation',
          });
        }
        return;
      }

      // Fresh cache → the position is already good enough; skip the GPS.
      if (loadCachedCoordinates()) return;

      logger.info('geolocation_foreground_refresh', { component: 'useGeolocation' });
      await requestGeolocation();
    };

    const onVisibilityChange = () => {
      void handleReturnToForeground();
    };
    // `pageshow` also fires on every NORMAL load (persisted=false), where the
    // mount effect already refreshes — reacting there would double the GPS
    // request at startup. Only bfcache restores (persisted=true) matter: the
    // mount effect does not re-run for them.
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) void handleReturnToForeground();
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pageshow', onPageShow);
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pageshow', onPageShow);
    };
  }, [checkPermission, loadCachedCoordinates, requestGeolocation]);

  /**
   * Auto-retry logic: if enabled but no coordinates and not denied, retry automatically.
   * This handles cases like:
   * - GPS temporarily unavailable
   * - Network timeout
   * - Cache expired
   */
  useEffect(() => {
    // Only retry if:
    // - Geolocation is enabled by user preference
    // - No coordinates available
    // - Permission not denied (can still retry)
    // - Not currently loading
    // - Haven't exceeded max retry attempts
    const shouldRetry =
      state.isEnabled &&
      !state.coordinates &&
      state.permission !== 'denied' &&
      state.permission !== 'unsupported' &&
      !state.isLoading &&
      retryCount < MAX_AUTO_RETRY_ATTEMPTS;

    if (!shouldRetry) return;

    logger.debug('geolocation_auto_retry_scheduled', {
      component: 'useGeolocation',
      retryCount: retryCount + 1,
      maxRetries: MAX_AUTO_RETRY_ATTEMPTS,
      permission: state.permission,
      error: state.error,
    });

    const timeoutId = setTimeout(async () => {
      setRetryCount(prev => prev + 1);

      logger.info('geolocation_auto_retry_attempt', {
        component: 'useGeolocation',
        attempt: retryCount + 1,
      });

      await requestGeolocation();
    }, AUTO_RETRY_DELAY_MS);

    return () => clearTimeout(timeoutId);
  }, [
    state.isEnabled,
    state.coordinates,
    state.permission,
    state.isLoading,
    state.error,
    retryCount,
    requestGeolocation,
  ]);

  /**
   * Reset retry count when coordinates are successfully obtained.
   */
  useEffect(() => {
    if (state.coordinates) {
      setRetryCount(0);
    }
  }, [state.coordinates]);

  return {
    ...state,
    /**
     * The user opted in but the browser permission fell back to `prompt`
     * (typical iOS-standalone behavior after inactivity): only a user
     * gesture can reopen the native sheet, so the UI must offer one.
     * Derived, never stored — it is a pure function of the state.
     */
    needsReactivation: state.isEnabled && state.permission === 'prompt',
    enable,
    disable,
    refresh,
  };
};

export default useGeolocation;
