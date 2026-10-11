'use client';

import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationResourceSync } from '@/hooks/useApplicationResourceSync';
import { useApiMutation } from '@/hooks/useApiMutation';
import { publishApplicationResources } from '@/lib/application-resources';
import { useTranslation } from '@/i18n/client';
import type { BaseSettingsProps } from '@/types/settings';

/** Home data returned by the authenticated saved-location API. */
export interface HomeLocation {
  address: string;
  lat: number;
  lon: number;
  place_id?: string | null;
}

/** Saved-location state follows its owner; refresh never discards a typed address. */
export function useHomeLocationSettings(lng: BaseSettingsProps['lng']) {
  const { t } = useTranslation(lng);
  // Home location query
  const { data, ownerId, refetch } = useApplicationAccountQuery<HomeLocation | null>(
    '/users/me/home-location',
    'LocationSettings'
  );
  const { lifetime, isCurrent } = useApplicationAccountLifetime(ownerId);
  const [input, setInput] = useState<{ lifetime: typeof lifetime; value: string } | null>(null);
  const homeAddressInput = input?.lifetime === lifetime ? input.value : '';
  const setHomeAddressInput = (value: string) => {
    if (isCurrent()) setInput({ lifetime, value });
  };
  const [override, setOverride] = useState<{
    lifetime: typeof lifetime;
    value: HomeLocation | null;
  } | null>(null);
  const homeLocation = override?.lifetime === lifetime ? override.value : data;
  const setHomeLocationData = (value: HomeLocation | null) => setOverride({ lifetime, value });
  const releaseOverride = useCallback(() => setOverride(null), []);
  useApplicationResourceSync(ownerId, 'locations', refetch, releaseOverride);

  // Home location mutations (no refetch - optimistic update)
  const { mutate: setHomeLocationMutation, loading: savingHome } = useApiMutation<
    { address: string; lat: number; lon: number },
    HomeLocation
  >({
    method: 'PUT',
    componentName: 'LocationSettings',
  });

  const { mutate: clearHomeLocationMutation, loading: clearingHome } = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'LocationSettings',
  });

  const handleSaveHomeLocation = async () => {
    if (!isCurrent()) return;
    if (!homeAddressInput.trim()) {
      toast.error(t('settings.location.home.address_required'));
      return;
    }
    try {
      const result = await setHomeLocationMutation('/users/me/home-location', {
        address: homeAddressInput.trim(),
        lat: 0,
        lon: 0,
      });
      if (!isCurrent()) return;
      // Optimistic update: set the new home location
      if (result) {
        setHomeLocationData(result);
      }
      toast.success(t('settings.location.home.saved'));
      setHomeAddressInput('');
      if (ownerId) publishApplicationResources(ownerId, new Set(['locations']));
    } catch {
      if (isCurrent()) toast.error(t('settings.location.home.save_error'));
    }
  };

  const handleClearHomeLocation = async () => {
    if (!isCurrent()) return;
    try {
      await clearHomeLocationMutation('/users/me/home-location', undefined);
      if (!isCurrent()) return;
      // Optimistic update: clear the home location
      setHomeLocationData(null);
      if (ownerId) publishApplicationResources(ownerId, new Set(['locations']));
      toast.success(t('settings.location.home.cleared'));
    } catch {
      if (isCurrent()) toast.error(t('settings.location.home.clear_error'));
    }
  };

  return {
    homeLocation,
    homeAddressInput,
    setHomeAddressInput,
    savingHome,
    clearingHome,
    handleSaveHomeLocation,
    handleClearHomeLocation,
  };
}
