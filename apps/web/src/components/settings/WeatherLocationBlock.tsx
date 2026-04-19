'use client';

import { useCallback, useEffect, useState } from 'react';
import { Info, Trash2 } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { useTranslation } from '@/i18n/client';
import { useAuth } from '@/hooks/useAuth';
import { useGeolocation } from '@/hooks/useGeolocation';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { toast } from 'sonner';
import type { Language } from '@/i18n/settings';

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

const BACKEND_SYNC_THROTTLE_MS = 30 * 60 * 1000; // 30 minutes
const LAST_PUSH_STORAGE_KEY = 'smart_weather_last_push_ms';

interface WeatherLocationBlockProps {
  /** Current language for translations. */
  lng: Language;
}

/**
 * Inline block rendering the Phase 3 "smart weather location" controls:
 * opt-in toggle, transparency view, clear button, and geolocation hint.
 *
 * Embedded inside HeartbeatSettings ("Proactive notifications") because
 * it only affects the weather source of proactive notifications. Does not
 * wrap itself in SettingsSection — the parent section provides the card.
 */
export function WeatherLocationBlock({ lng }: WeatherLocationBlockProps) {
  const { t } = useTranslation(lng);
  const { user, refreshUser } = useAuth();
  const { coordinates, isEnabled: geolocEnabled } = useGeolocation();

  const optedIn = user?.weather_use_last_known_location ?? false;

  const [updating, setUpdating] = useState(false);
  const [stored, setStored] = useState<LastLocationView | null>(null);

  const fetchStored = useCallback(async () => {
    if (!user) return;
    try {
      const data = await apiClient.get<LastLocationView>('/auth/me/last-location');
      setStored(data);
    } catch (err) {
      logger.warn('weather_location_stored_fetch_failed', {
        component: 'WeatherLocationBlock',
        error: String(err),
      });
    }
  }, [user]);

  // Initial fetch + refresh after toggle/push.
  useEffect(() => {
    if (optedIn) {
      fetchStored();
    } else {
      setStored(null);
    }
  }, [optedIn, fetchStored]);

  // Background throttled push: when opt-in + fresh coordinates, PUT to backend
  // at most once per 30 minutes.
  useEffect(() => {
    if (!optedIn || !geolocEnabled || !coordinates) return;

    const lastPushRaw = localStorage.getItem(LAST_PUSH_STORAGE_KEY);
    const lastPush = lastPushRaw ? Number.parseInt(lastPushRaw, 10) : 0;
    const elapsed = Date.now() - lastPush;
    if (elapsed < BACKEND_SYNC_THROTTLE_MS) return;

    (async () => {
      try {
        await apiClient.put('/auth/me/last-location', {
          lat: coordinates.lat,
          lon: coordinates.lon,
          accuracy: coordinates.accuracy,
        });
        localStorage.setItem(LAST_PUSH_STORAGE_KEY, String(Date.now()));
        await fetchStored();
      } catch (err) {
        logger.debug('weather_location_push_failed', {
          component: 'WeatherLocationBlock',
          error: String(err),
        });
      }
    })();
  }, [optedIn, geolocEnabled, coordinates, fetchStored]);

  const handleToggle = async (checked: boolean) => {
    if (!user || updating) return;
    setUpdating(true);
    try {
      await apiClient.patch('/auth/me/weather-location-preference', {
        enabled: checked,
      });
      await refreshUser();
      if (!checked) {
        localStorage.removeItem(LAST_PUSH_STORAGE_KEY);
        setStored(null);
      }
      toast.success(
        checked
          ? t('heartbeat.weather_location.enabled_success')
          : t('heartbeat.weather_location.disabled_success')
      );
    } catch (err) {
      logger.error('weather_location_toggle_failed', undefined, {
        component: 'WeatherLocationBlock',
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
          <p className="text-sm font-medium">
            {t('heartbeat.weather_location.toggle_label')}
          </p>
          <p className="text-xs text-muted-foreground">
            {t('heartbeat.weather_location.toggle_description')}
          </p>
        </div>
        <Switch
          checked={optedIn}
          onCheckedChange={handleToggle}
          disabled={updating}
          aria-label={t('heartbeat.weather_location.toggle_label')}
        />
      </div>

      {optedIn && (
        <>
          <InfoBox variant="default">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 shrink-0 mt-0.5 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">
                {t('heartbeat.weather_location.privacy_note')}
              </p>
            </div>
          </InfoBox>

          {!geolocEnabled && (
            <InfoBox variant="warning">
              <p className="text-xs text-yellow-700 dark:text-yellow-400">
                {t('heartbeat.weather_location.geoloc_required_hint')}
              </p>
            </InfoBox>
          )}

          <div className="rounded-lg border bg-muted/30 p-3 space-y-2">
            <p className="text-xs font-medium">
              {t('heartbeat.weather_location.stored_title')}
            </p>
            {stored?.stored ? (
              <div className="space-y-1 text-xs text-muted-foreground">
                <div className="flex justify-between gap-4">
                  <span>{t('heartbeat.weather_location.stored_coords')}</span>
                  <span className="font-mono">
                    {stored.lat?.toFixed(4)}, {stored.lon?.toFixed(4)}
                  </span>
                </div>
                <div className="flex justify-between gap-4">
                  <span>{t('heartbeat.weather_location.stored_updated_at')}</span>
                  <span>{formatUpdatedAt(stored.updated_at)}</span>
                </div>
                {stored.stale && (
                  <p className="text-amber-600 dark:text-amber-500">
                    {t('heartbeat.weather_location.stored_stale')}
                  </p>
                )}
                <div className="pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleClearNow}
                    disabled={updating}
                  >
                    <Trash2 className="mr-2 h-3 w-3" />
                    {t('heartbeat.weather_location.clear_button')}
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                {t('heartbeat.weather_location.no_stored')}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
