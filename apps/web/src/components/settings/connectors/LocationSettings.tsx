/**
 * LocationSettings component.
 * Handles geolocation and home location settings for Google Places connector.
 */

'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Navigation, Home, MapPin, Info, Save, Trash2 } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useGeolocation } from '@/hooks/useGeolocation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useApiMutation } from '@/hooks/useApiMutation';
import { logger } from '@/lib/logger';
import type { HomeLocation } from './types';

interface LocationSettingsProps {
  t: (key: string) => string;
}

export function LocationSettings({ t }: LocationSettingsProps) {
  const {
    permission,
    isEnabled,
    isLoading: geoLoading,
    error: geoError,
    enable,
    disable,
  } = useGeolocation();

  const [homeAddressInput, setHomeAddressInput] = useState('');

  // Home location query
  const { data: homeLocation, setData: setHomeLocationData } = useApiQuery<HomeLocation | null>(
    '/users/me/home-location',
    {
      componentName: 'LocationSettings',
      enabled: true,
    }
  );

  // Home location mutations (no refetch - optimistic update)
  const { mutate: setHomeLocationMutation, loading: savingHome } = useApiMutation<
    { address: string; lat: number; lon: number },
    { address: string; lat: number; lon: number }
  >({
    method: 'PUT',
    componentName: 'LocationSettings',
  });

  const { mutate: clearHomeLocationMutation, loading: clearingHome } = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'LocationSettings',
  });

  // Geolocation handlers
  const handleGeoToggle = async (checked: boolean) => {
    if (checked) {
      const result = await enable();
      if (result) {
        toast.success(t('settings.location.geolocation.enabled'));
      } else {
        toast.error(t('settings.location.geolocation.permission_denied'));
      }
    } else {
      disable();
      toast.info(t('settings.location.geolocation.disabled'));
    }
    logger.info('Geolocation toggled', {
      component: 'LocationSettings',
      enabled: checked,
      permission,
    });
  };

  const handleSaveHomeLocation = async () => {
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
      // Optimistic update: set the new home location
      if (result) {
        setHomeLocationData(result);
      }
      toast.success(t('settings.location.home.saved'));
      setHomeAddressInput('');
    } catch {
      toast.error(t('settings.location.home.save_error'));
    }
  };

  const handleClearHomeLocation = async () => {
    try {
      await clearHomeLocationMutation('/users/me/home-location', undefined);
      // Optimistic update: clear the home location
      setHomeLocationData(null);
      toast.success(t('settings.location.home.cleared'));
    } catch {
      toast.error(t('settings.location.home.clear_error'));
    }
  };

  return (
    <div className="mt-4 pt-4 border-t border-border/50 space-y-6">
      {/* Geolocation Settings */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Navigation className="h-4 w-4 text-muted-foreground" />
            <Label className="text-sm text-muted-foreground">
              {t('settings.location.geolocation.title')}
            </Label>
          </div>
          <Switch
            checked={isEnabled}
            onCheckedChange={handleGeoToggle}
            disabled={geoLoading || permission === 'unsupported'}
          />
        </div>

        {/* Permission status - simple colored circle */}
        {permission !== 'prompt' && (
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">
              {t('settings.location.geolocation.permission_status')}
            </Label>
            <span
              className="text-base"
              title={
                permission === 'granted'
                  ? t('settings.location.geolocation.permission_granted')
                  : permission === 'denied'
                    ? t('settings.location.geolocation.permission_denied')
                    : t('settings.location.geolocation.unsupported')
              }
            >
              {permission === 'granted' ? '🟢' : permission === 'denied' ? '🔴' : '🟡'}
            </span>
          </div>
        )}

        {/* Geolocation error */}
        {geoError && (
          <InfoBox variant="error">
            <p className="text-sm text-red-700 dark:text-red-400">{geoError}</p>
          </InfoBox>
        )}

        {/* Permission denied help */}
        {permission === 'denied' && (
          <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-yellow-600 dark:text-yellow-400 mt-0.5 shrink-0" />
              <p className="text-sm text-yellow-900 dark:text-yellow-100">
                {t('settings.location.geolocation.denied_help')}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Home Location Settings */}
      <div className="space-y-3 pt-4 border-t border-border/50">
        <div className="flex items-center gap-2">
          <Home className="h-4 w-4 text-muted-foreground" />
          <Label className="text-sm text-muted-foreground">
            {t('settings.location.home.title')}
          </Label>
        </div>

        {/* If saved value exists, show it with delete button */}
        {homeLocation ? (
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm text-foreground">{homeLocation.address}</p>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleClearHomeLocation}
                disabled={clearingHome}
                className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
                title={t('common.delete')}
              >
                {clearingHome ? <LoadingSpinner size="default" /> : <Trash2 className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        ) : (
          /* No saved value, show input with save button */
          <div className="flex gap-2">
            <div className="relative flex-1">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="home-address-input"
                type="text"
                placeholder={t('settings.location.home.placeholder')}
                value={homeAddressInput}
                onChange={e => setHomeAddressInput(e.target.value)}
                className="pl-9"
                disabled={savingHome}
              />
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleSaveHomeLocation}
              disabled={savingHome || !homeAddressInput.trim()}
              className="text-primary hover:text-primary hover:bg-primary/10"
              title={t('common.save')}
            >
              {savingHome ? <LoadingSpinner size="default" /> : <Save className="h-4 w-4" />}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
