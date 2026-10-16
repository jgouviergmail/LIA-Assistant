/**
 * LocationSettings — the standalone "Location" settings section.
 *
 * The three sources of the location cascade (ADR-219), in cascade order:
 * live browser position > remembered last-known position > home address.
 *
 * Standalone section since 2026-08 (moved out of the Google Places connector
 * card): the data lives on the user — `/users/me/home-location`,
 * `use_last_known_location` — not on any connector, and the cascade serves
 * weather, "where am I" and scheduled actions whether or not Places is
 * connected. Nesting it under a Google card also read as "shared with
 * Google", which it never was.
 */

'use client';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { InfoBox } from '@/components/ui/info-box';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Navigation, Home, MapPin, History, Info, Save, Trash2 } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useGeolocation } from '@/hooks/useGeolocation';
import { useTranslation } from '@/i18n/client';
import { logger } from '@/lib/logger';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';
import { LastKnownLocationSection } from './LastKnownLocationSection';

import { useHomeLocationSettings } from '@/hooks/useHomeLocationSettings';
export type { HomeLocation } from '@/hooks/useHomeLocationSettings';

function geolocationState({
  isEnabled,
  permission,
  error,
}: Pick<ReturnType<typeof useGeolocation>, 'isEnabled' | 'permission' | 'error'>) {
  if (error) return 'error';
  if (!isEnabled) return 'inactive';
  if (permission === 'granted') return 'active';
  return permission === 'prompt' ? 'inactive' : 'error';
}
const GEO_STATE_TONE = { error: 'destructive', active: 'success', inactive: 'secondary' } as const;

export function LocationSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const {
    permission,
    isEnabled,
    isLoading: geoLoading,
    error: geoError,
    enable,
    disable,
  } = useGeolocation();
  const geoState = geolocationState({ isEnabled, permission, error: geoError });

  const {
    homeLocation,
    homeAddressInput,
    setHomeAddressInput,
    savingHome,
    clearingHome,
    handleSaveHomeLocation,
    handleClearHomeLocation,
  } = useHomeLocationSettings(lng);

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

  return (
    <SettingsSection
      value="location"
      title={t('settings.location.title')}
      description={t('settings.location.description')}
      icon={MapPin}
    >
      <div className="space-y-6">
        {/* Geolocation Settings */}
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <Navigation className="h-4 w-4 text-primary" />
              <Label id="geolocation-label" className="text-sm text-muted-foreground">
                {t('settings.location.geolocation.title')}
              </Label>
              <Badge variant={GEO_STATE_TONE[geoState]} role="status">
                {t(geoLoading ? 'common.loading' : `common.${geoState}`)}
              </Badge>
            </div>
            <Switch
              checked={isEnabled}
              onCheckedChange={handleGeoToggle}
              disabled={geoLoading || permission === 'unsupported'}
              aria-labelledby="geolocation-label"
            />
          </div>

          {/* Geolocation error */}
          {geoError && (
            <InfoBox variant="error">
              <p className="text-sm text-red-700 dark:text-red-400">{geoError}</p>
            </InfoBox>
          )}

          {permission === 'unsupported' && (
            <p className="text-xs text-muted-foreground">
              {t('settings.location.geolocation.unsupported')}
            </p>
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

        {/* Last-known location memory (generalized opt-in, cascade middle step) */}
        <div className="space-y-3 pt-4 border-t border-border/50">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-primary" />
            <Label className="text-sm text-muted-foreground">
              {t('settings.location.last_known.title')}
            </Label>
          </div>
          <LastKnownLocationSection t={t} />
        </div>

        {/* Home Location Settings */}
        <div className="space-y-3 pt-4 border-t border-border/50">
          <div className="flex items-center gap-2">
            <Home className="h-4 w-4 text-primary" />
            <Label className="text-sm text-muted-foreground">
              {t('settings.location.home.title')}
            </Label>
          </div>

          {/* If saved value exists, show it with delete button */}
          {homeLocation && (
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
              <div className="flex items-center justify-between gap-4">
                <p className="min-w-0 flex-1 break-words text-sm text-foreground">
                  {homeLocation.address}
                </p>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleClearHomeLocation}
                  disabled={clearingHome}
                  className="text-destructive hover:text-destructive"
                  title={t('common.delete')}
                >
                  {clearingHome ? (
                    <LoadingSpinner size="default" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
          )}
          {(!homeLocation || homeAddressInput.length > 0) && (
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
    </SettingsSection>
  );
}
