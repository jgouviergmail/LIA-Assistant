'use client';

import { MapPin, Navigation, Check, X, Info } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import { useGeolocation } from '@/hooks/useGeolocation';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

export function GeolocationSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { coordinates, permission, isEnabled, isLoading, error, enable, disable, refresh } =
    useGeolocation();

  const handleToggle = async (checked: boolean) => {
    if (checked) {
      // enable() returns coordinates if successful, null if denied/error
      const result = await enable();
      if (result) {
        toast.success(t('settings.location.geolocation.enabled'));
      } else {
        // Permission denied or error - check current error state for details
        toast.error(t('settings.location.geolocation.permission_denied'));
      }
    } else {
      disable();
      toast.info(t('settings.location.geolocation.disabled'));
    }

    logger.info('Geolocation toggled', {
      component: 'GeolocationSettings',
      enabled: checked,
      permission,
    });
  };

  const handleRefresh = async () => {
    await refresh();
    if (coordinates) {
      toast.success(t('settings.location.geolocation.refreshed'));
    }
  };

  const getPermissionBadge = () => {
    switch (permission) {
      case 'granted':
        return (
          <div className="rounded-md bg-green-500/10 px-2 py-1 text-xs text-green-700 dark:text-green-400 flex items-center gap-1">
            <Check className="h-3 w-3" />
            {t('settings.location.geolocation.permission_granted')}
          </div>
        );
      case 'denied':
        return (
          <div className="rounded-md bg-red-500/10 px-2 py-1 text-xs text-red-700 dark:text-red-400 flex items-center gap-1">
            <X className="h-3 w-3" />
            {t('settings.location.geolocation.permission_denied')}
          </div>
        );
      case 'unsupported':
        return (
          <div className="rounded-md bg-yellow-500/10 px-2 py-1 text-xs text-yellow-700 dark:text-yellow-400">
            {t('settings.location.geolocation.unsupported')}
          </div>
        );
      default:
        return null;
    }
  };

  const content = (
    <div className="space-y-4">
      {/* Toggle and status */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label className="text-sm font-medium">
            {t('settings.location.geolocation.auto_label')}
          </Label>
          <p className="text-xs text-muted-foreground">
            {t('settings.location.geolocation.auto_description')}
          </p>
        </div>
        <Switch
          checked={isEnabled}
          onCheckedChange={handleToggle}
          disabled={isLoading || permission === 'unsupported'}
        />
      </div>

      {/* Permission status */}
      {permission !== 'prompt' && (
        <div className="flex items-center justify-between">
          <Label className="text-xs text-muted-foreground">
            {t('settings.location.geolocation.permission_status')}
          </Label>
          {getPermissionBadge()}
        </div>
      )}

      {/* Current position display */}
      {isEnabled && coordinates && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-2">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 space-y-1">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Navigation className="h-4 w-4" />
                {t('settings.location.geolocation.current_position')}
              </Label>
              <p className="text-sm text-muted-foreground font-mono">
                {coordinates.lat.toFixed(6)}, {coordinates.lon.toFixed(6)}
              </p>
              {coordinates.accuracy && (
                <p className="text-xs text-muted-foreground">
                  {t('settings.location.geolocation.accuracy', {
                    meters: Math.round(coordinates.accuracy),
                  })}
                </p>
              )}
            </div>
            <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isLoading}>
              {t('settings.location.geolocation.refresh')}
            </Button>
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <InfoBox variant="error">
          <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
        </InfoBox>
      )}

      {/* Permission denied help */}
      {permission === 'denied' && (
        <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3 space-y-2">
          <div className="flex items-start gap-2">
            <Info className="h-4 w-4 text-yellow-600 dark:text-yellow-400 mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-yellow-900 dark:text-yellow-100">
                {t('settings.location.geolocation.denied_help')}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Info note */}
      <InfoBox>
        <p className="text-xs text-muted-foreground">
          {t('settings.location.geolocation.info_note')}
        </p>
      </InfoBox>
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="geolocation"
      title={t('settings.location.geolocation.title')}
      description={t('settings.location.geolocation.description')}
      icon={MapPin}
    >
      {content}
    </SettingsSection>
  );
}
