'use client';

/**
 * useSettingsAvailability — the flags that decide which settings sections
 * exist for THIS account on THIS instance, resolved once for every surface
 * that lists sections: the settings shell (rail, overview, search) and the
 * « my shortcuts » picker (ADR-277). Extracted from the settings page so the
 * picker can never offer a section the shell would not show.
 */

import { useMemo } from 'react';

import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import { useDebugPanelEnabled } from '@/hooks/useDebugPanelEnabled';
import type { SettingsSearchAvailability } from '@/lib/settings-search';

export function useSettingsAvailability(): SettingsSearchAvailability {
  const { user } = useAuth();
  const { userAccessAvailable } = useDebugPanelEnabled();
  // The one instance flag family a settings section actually reads before
  // rendering (`OpenLoopsSection` and its siblings). The other `/config`
  // flags are NOT consulted: the sections they name render regardless, and
  // filtering the shell on them would hide something the pane can show.
  const { config } = useAppConfig();

  // Stable identity: `SettingsSearch` memoizes its whole index on this
  // object, and a fresh one per render would rebuild fifty entries every
  // keystroke. While `/config` is in flight the gated sections are genuinely
  // absent, and every consumer rebuilds by itself when the answer lands.
  return useMemo<SettingsSearchAvailability>(
    () => ({
      isSuperuser: !!user?.is_superuser,
      openLoopsEnabled: !!config?.features?.open_loops_enabled,
      habitsEnabled: !!config?.features?.habits_enabled,
      peersEnabled: !!config?.features?.peers_enabled,
      debugUserAccess: userAccessAvailable,
    }),
    [
      user?.is_superuser,
      config?.features?.open_loops_enabled,
      config?.features?.habits_enabled,
      config?.features?.peers_enabled,
      userAccessAvailable,
    ]
  );
}
