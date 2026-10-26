'use client';

import { useEffect, useState, type ReactElement } from 'react';
import type { Language } from '@/i18n/settings';
import type { SettingsSectionToken } from '@/lib/settings-sections';
import { SETTINGS_SECTION_REGISTRY } from './settings-section-registry';

interface LoadedSection {
  key: string;
  element: ReactElement | null;
  failed: boolean;
}
/** A late module may not replace the section selected since its load began. */
export function useSettingsSection(token: SettingsSectionToken, lng: Language, enabled: boolean) {
  const key = token + ':' + lng;
  const [loaded, setLoaded] = useState<LoadedSection | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let current = true;
    void SETTINGS_SECTION_REGISTRY[token].render(lng).then(
      element => {
        if (current) setLoaded({ key, element, failed: false });
      },
      () => {
        if (current) setLoaded({ key, element: null, failed: true });
      }
    );
    return () => {
      current = false;
    };
  }, [key, token, lng, enabled]);
  const accepted = enabled && loaded?.key === key ? loaded : null;
  return {
    element: accepted?.element ?? null,
    failed: accepted?.failed ?? false,
    loading: enabled && accepted === null,
  };
}
