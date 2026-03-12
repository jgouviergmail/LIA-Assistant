/**
 * Hook for monitoring OAuth connector health.
 *
 * SIMPLIFIED DESIGN:
 * - Only alerts on REAL problems (connector status=ERROR)
 * - Does NOT alert on normal token expiration (handled by proactive refresh)
 * - Shows modal only when re-authentication is truly required
 *
 * Why this design:
 * - Proactive refresh job runs every 15 min, refreshes tokens 30 min before expiry
 * - access_token.expires_at in past is NORMAL - on-demand refresh gets new token
 * - Only status=ERROR means refresh failed and manual re-auth is needed
 */

'use client';

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useApiQuery } from './useApiQuery';
import { logger } from '@/lib/logger';
import apiClient from '@/lib/api-client';
import {
  OAUTH_HEALTH_POLLING_INTERVAL_MS,
  OAUTH_HEALTH_TOAST_DEDUP_KEY,
  OAUTH_HEALTH_RECONNECT_PENDING_KEY,
} from '@/lib/constants';

// Types matching backend schemas
export type ConnectorHealthStatus = 'healthy' | 'expiring_soon' | 'expired' | 'error';
export type ConnectorHealthSeverity = 'info' | 'warning' | 'critical';

export interface ConnectorHealthItem {
  id: string;
  connector_type: string;
  display_name: string;
  health_status: ConnectorHealthStatus;
  severity: ConnectorHealthSeverity;
  expires_in_minutes: number | null;
  authorize_url: string;
}

export interface ConnectorHealthResponse {
  connectors: ConnectorHealthItem[];
  has_issues: boolean;
  critical_count: number;
  warning_count: number;
  checked_at: string;
}

/** Backend settings for health monitoring (simplified). */
export interface ConnectorHealthSettings {
  polling_interval_ms: number;
  critical_cooldown_ms: number;
}

export interface UseConnectorHealthOptions {
  /** Enable health check polling (default: true) */
  enabled?: boolean;
  /** Is user authenticated? Only poll when true */
  isAuthenticated?: boolean;
  /** Callback when critical connector detected (for modal) */
  onCritical?: (connectors: ConnectorHealthItem[]) => void;
}

export interface UseConnectorHealthResult {
  /** Full health response */
  health: ConnectorHealthResponse | null;
  /** Loading state */
  isLoading: boolean;
  /** Whether there are critical issues requiring action */
  hasIssues: boolean;
  /** Connectors with critical status (ERROR - needs re-auth) */
  criticalConnectors: ConnectorHealthItem[];
  /** Manually refetch health */
  refetch: () => Promise<void>;
  /** Dismiss a specific connector (hide from UI until next check) */
  dismissConnector: (connectorId: string) => void;
  /** Mark reconnection as pending (before OAuth redirect) */
  markReconnectPending: () => void;
}

/** Default polling interval (fallback if backend fetch fails). */
const DEFAULT_POLLING_INTERVAL_MS = OAUTH_HEALTH_POLLING_INTERVAL_MS;
const DEFAULT_CRITICAL_COOLDOWN_MS = 4 * 60 * 60 * 1000; // 4 hours

/**
 * Check if modal for this connector was shown recently (multi-tab dedup).
 */
function shouldShowModal(connectorId: string, cooldownMs: number): boolean {
  try {
    const key = `modal:${connectorId}`;
    const shown = JSON.parse(localStorage.getItem(OAUTH_HEALTH_TOAST_DEDUP_KEY) || '{}');
    const lastShown = shown[key];

    if (lastShown && Date.now() - lastShown < cooldownMs) {
      return false; // Already shown recently
    }

    // Mark as shown
    shown[key] = Date.now();
    localStorage.setItem(OAUTH_HEALTH_TOAST_DEDUP_KEY, JSON.stringify(shown));
    return true;
  } catch {
    return true;
  }
}

/**
 * Hook for monitoring OAuth connector health.
 * Only shows alerts for connectors with status=ERROR (real problems).
 */
export function useConnectorHealth(options: UseConnectorHealthOptions = {}): UseConnectorHealthResult {
  const { enabled = true, isAuthenticated = false, onCritical } = options;

  const [dismissedConnectors, setDismissedConnectors] = useState<Set<string>>(new Set());
  const [pollingIntervalMs, setPollingIntervalMs] = useState(DEFAULT_POLLING_INTERVAL_MS);
  const [criticalCooldownMs, setCriticalCooldownMs] = useState(DEFAULT_CRITICAL_COOLDOWN_MS);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastCriticalIdsRef = useRef<string[]>([]);

  // Fetch settings from backend
  useEffect(() => {
    if (!enabled || !isAuthenticated) return;

    const fetchSettings = async () => {
      try {
        const response = await apiClient.get<ConnectorHealthSettings>('/connectors/health/settings');
        setPollingIntervalMs(response.polling_interval_ms);
        setCriticalCooldownMs(response.critical_cooldown_ms);
        logger.debug('Connector health settings loaded', {
          component: 'useConnectorHealth',
          pollingIntervalMs: response.polling_interval_ms,
        });
      } catch (error) {
        logger.warn('Failed to fetch health settings, using defaults', {
          component: 'useConnectorHealth',
          error: error instanceof Error ? error.message : 'Unknown error',
        });
      } finally {
        setSettingsLoaded(true);
      }
    };

    fetchSettings();
  }, [enabled, isAuthenticated]);

  // Use the generic API query hook
  const { data, loading, refetch: apiRefetch } = useApiQuery<ConnectorHealthResponse>(
    '/connectors/health',
    {
      componentName: 'useConnectorHealth',
      enabled: enabled && isAuthenticated && settingsLoaded,
      onSuccess: (response) => {
        logger.debug('Connector health check completed', {
          component: 'useConnectorHealth',
          criticalCount: response.critical_count,
        });
      },
      onError: (error) => {
        logger.warn('Connector health check failed', {
          component: 'useConnectorHealth',
          error: error.message,
        });
      },
    }
  );

  // Filter critical connectors (status=ERROR, excluding dismissed)
  const criticalConnectors = useMemo(
    () =>
      (data?.connectors || []).filter(
        (c) => c.severity === 'critical' && !dismissedConnectors.has(c.id)
      ),
    [data?.connectors, dismissedConnectors]
  );

  const hasIssues = criticalConnectors.length > 0;

  // Handle critical notifications (modal) - only for NEW critical connectors
  useEffect(() => {
    if (!onCritical) return;
    if (criticalConnectors.length === 0) return;

    // Check if critical connectors changed
    const currentIds = criticalConnectors.map((c) => c.id).sort().join(',');
    const lastIds = lastCriticalIdsRef.current.sort().join(',');

    if (currentIds !== lastIds) {
      // Filter to only show connectors not recently shown
      const connectorsToShow = criticalConnectors.filter((c) =>
        shouldShowModal(c.id, criticalCooldownMs)
      );

      if (connectorsToShow.length > 0) {
        lastCriticalIdsRef.current = criticalConnectors.map((c) => c.id);
        onCritical(connectorsToShow);
      }
    }
  }, [criticalConnectors, onCritical, criticalCooldownMs]);

  // Setup polling interval
  useEffect(() => {
    if (!enabled || !isAuthenticated || !settingsLoaded) return;

    pollingIntervalRef.current = setInterval(() => {
      apiRefetch();
    }, pollingIntervalMs);

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [enabled, isAuthenticated, settingsLoaded, pollingIntervalMs, apiRefetch]);

  // Check for OAuth return (post-reconnection)
  useEffect(() => {
    const checkOAuthReturn = () => {
      try {
        if (sessionStorage.getItem(OAUTH_HEALTH_RECONNECT_PENDING_KEY)) {
          sessionStorage.removeItem(OAUTH_HEALTH_RECONNECT_PENDING_KEY);
          apiRefetch();
          setDismissedConnectors(new Set());
          // Clear the modal dedup so it can show again if still broken
          localStorage.removeItem(OAUTH_HEALTH_TOAST_DEDUP_KEY);
        }
      } catch {
        // sessionStorage not available
      }
    };

    checkOAuthReturn();

    window.addEventListener('storage', checkOAuthReturn);
    return () => window.removeEventListener('storage', checkOAuthReturn);
  }, [apiRefetch]);

  const dismissConnector = useCallback((connectorId: string) => {
    setDismissedConnectors((prev) => new Set([...prev, connectorId]));
  }, []);

  const markReconnectPending = useCallback(() => {
    try {
      sessionStorage.setItem(OAUTH_HEALTH_RECONNECT_PENDING_KEY, 'true');
    } catch {
      // sessionStorage not available
    }
  }, []);

  const refetch = useCallback(async () => {
    await apiRefetch();
  }, [apiRefetch]);

  return {
    health: data || null,
    isLoading: loading,
    hasIssues,
    criticalConnectors,
    refetch,
    dismissConnector,
    markReconnectPending,
  };
}
