/**
 * LastKnownLocationSection component.
 *
 * Generalized last-known location opt-in (moved from the weather-scoped block
 * in proactive-notifications settings, 2026-08-16). The persisted position is
 * used by ALL features — chat tools, scheduled actions, proactive
 * notifications, briefing — whenever the live browser position is
 * unavailable, with the home address as the final fallback.
 *
 * The throttled backend push does NOT live here: it belongs to the global
 * `useLastKnownLocationSync` hook so the position keeps flowing regardless of
 * which page is open.
 */

'use client';

import { useCallback, useEffect, useState } from 'react';
import { Info, Trash2 } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { useAuth } from '@/hooks/useAuth';
import { useGeolocation } from '@/hooks/useGeolocation';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { toast } from 'sonner';

/**
 * Last-known location view returned by GET /auth/me/last-location.
 */
interface LastLocationView {
  stored: boolean;
  lat: number | null;
  lon: number | null;
  accuracy: number | null;
  updated_at: string | null;
  stale: boolean;
}

interface LastKnownLocationSectionProps {
  t: (key: string) => string;
}

export function LastKnownLocationSection({ t }: LastKnownLocationSectionProps) {
  const { user, refreshUser } = useAuth();
  const { isEnabled: geolocEnabled } = useGeolocation();

  const optedIn = user?.use_last_known_location ?? false;

  const [updating, setUpdating] = useState(false);
  const [stored, setStored] = useState<LastLocationView | null>(null);

  const fetchStored = useCallback(async () => {
    if (!user) return;
    try {
      const data = await apiClient.get<LastLocationView>('/auth/me/last-location');
      setStored(data);
    } catch (err) {
      logger.warn('last_known_location_stored_fetch_failed', {
        component: 'LastKnownLocationSection',
        error: String(err),
      });
    }
  }, [user]);

  // Initial fetch + refresh after toggle.
  useEffect(() => {
    if (optedIn) {
      fetchStored();
    } else {
      setStored(null);
    }
  }, [optedIn, fetchStored]);

  const handleToggle = async (checked: boolean) => {
    if (!user || updating) return;
    setUpdating(true);
    try {
      await apiClient.patch('/auth/me/location-preference', {
        enabled: checked,
      });
      await refreshUser();
      if (!checked) {
        setStored(null);
      }
      toast.success(
        checked
          ? t('settings.location.last_known.enabled_success')
          : t('settings.location.last_known.disabled_success')
      );
    } catch (err) {
      logger.error('last_known_location_toggle_failed', undefined, {
        component: 'LastKnownLocationSection',
        error: String(err),
      });
      toast.error(t('common.error'));
    } finally {
      setUpdating(false);
    }
  };

  const handleClearNow = async () => {
    // Disabling triggers a backend wipe — reuse that path for idempotency.
    await handleToggle(false);
  };

  const formatUpdatedAt = (iso: string | null) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <p className="text-sm font-medium">{t('settings.location.last_known.toggle_label')}</p>
          <p className="text-xs text-muted-foreground">
            {t('settings.location.last_known.toggle_description')}
          </p>
        </div>
        <Switch
          checked={optedIn}
          onCheckedChange={handleToggle}
          disabled={updating}
          aria-label={t('settings.location.last_known.toggle_label')}
        />
      </div>

      {optedIn && (
        <>
          <InfoBox variant="default">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 shrink-0 mt-0.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">
                {t('settings.location.last_known.privacy_note')}
              </p>
            </div>
          </InfoBox>

          {!geolocEnabled && (
            <InfoBox variant="warning">
              <p className="text-xs text-yellow-700 dark:text-yellow-400">
                {t('settings.location.last_known.geoloc_required_hint')}
              </p>
            </InfoBox>
          )}

          <div className="rounded-lg border bg-muted/30 p-3 space-y-2">
            <p className="text-xs font-medium">{t('settings.location.last_known.stored_title')}</p>
            {stored?.stored ? (
              <div className="space-y-1 text-xs text-muted-foreground">
                <div className="flex justify-between gap-4">
                  <span>{t('settings.location.last_known.stored_coords')}</span>
                  <span className="font-mono">
                    {stored.lat?.toFixed(4)}, {stored.lon?.toFixed(4)}
                  </span>
                </div>
                <div className="flex justify-between gap-4">
                  <span>{t('settings.location.last_known.stored_updated_at')}</span>
                  <span>{formatUpdatedAt(stored.updated_at)}</span>
                </div>
                {stored.stale && (
                  <p className="text-amber-600 dark:text-amber-500">
                    {t('settings.location.last_known.stored_stale')}
                  </p>
                )}
                <div className="pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={handleClearNow}
                    disabled={updating}
                  >
                    <Trash2 className="mr-2 h-3 w-3" />
                    {t('settings.location.last_known.clear_button')}
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                {t('settings.location.last_known.no_stored')}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
