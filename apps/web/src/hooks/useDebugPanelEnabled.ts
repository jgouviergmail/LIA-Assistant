/**
 * Hook to check if the debug panel is enabled for the current user.
 *
 * The debug panel visibility is determined by a 2-level system:
 * - Admin: enabled = system_setting.debug_panel_enabled
 * - Non-admin: enabled = system_setting.debug_panel_user_access_enabled AND user.debug_panel_enabled
 *
 * Also exposes `userAccessAvailable` for the settings page to conditionally
 * show the debug panel toggle in user preferences.
 *
 * Uses useApiQuery for consistency with codebase patterns (abort on unmount, etc.).
 */

import { useApiQuery } from '@/hooks/useApiQuery';

interface DebugPanelStatusResponse {
  enabled: boolean;
  user_access_available: boolean;
}

interface UseDebugPanelEnabledReturn {
  /** Whether debug panel should be shown for this user */
  isEnabled: boolean;
  /** Whether admin has enabled user-level debug panel access (for preferences UI) */
  userAccessAvailable: boolean;
  /** Whether the setting is still loading */
  isLoading: boolean;
  /** Force refresh the setting */
  refresh: () => Promise<void>;
}

/** Public endpoint for debug panel status (authenticated) */
const DEBUG_PANEL_ENDPOINT = '/system-settings/debug-panel-status';

/** Safe initial state when setting hasn't been fetched yet */
const INITIAL_DATA: DebugPanelStatusResponse = {
  enabled: false,
  user_access_available: false,
};

/**
 * Hook to check if debug panel should be displayed.
 *
 * Returns the effective enabled state and whether user-level access is available.
 * Fetches from public endpoint (all authenticated users).
 */
export function useDebugPanelEnabled(): UseDebugPanelEnabledReturn {
  const { data, loading, refetch } = useApiQuery<DebugPanelStatusResponse>(DEBUG_PANEL_ENDPOINT, {
    componentName: 'useDebugPanelEnabled',
    initialData: INITIAL_DATA,
  });

  // During loading, default to false (no flash of debug panel)
  const isEnabled = loading ? false : (data?.enabled ?? false);
  const userAccessAvailable = loading ? false : (data?.user_access_available ?? false);

  return {
    isEnabled,
    userAccessAvailable,
    isLoading: loading,
    refresh: refetch,
  };
}
