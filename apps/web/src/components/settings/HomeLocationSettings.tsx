'use client';

import * as React from 'react';
import { Home, MapPin, Trash2, AlertCircle } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { SettingsSection } from '@/components/settings/SettingsSection';
import type { BaseSettingsProps } from '@/types/settings';

interface HomeLocation {
  address: string;
  lat: number;
  lon: number;
  place_id?: string | null;
}

interface Connector {
  id: string;
  connector_type: string;
  status: 'active' | 'inactive' | 'revoked';
}

interface ConnectorsResponse {
  connectors: Connector[];
}

export function HomeLocationSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const [addressInput, setAddressInput] = React.useState('');

  // Check if Google Places connector is active
  const { data: connectorsData, loading: loadingConnectors } = useApiQuery<ConnectorsResponse>(
    '/connectors',
    {
      componentName: 'HomeLocationSettings',
      initialData: { connectors: [] },
    }
  );

  const connectors = React.useMemo(() => connectorsData?.connectors || [], [connectorsData?.connectors]);

  const isPlacesActive = React.useMemo(() => {
    return connectors.some(c => c.connector_type === 'google_places' && c.status === 'active');
  }, [connectors]);

  // Get current home location
  const {
    data: homeLocation,
    loading: loadingHome,
    setData: setHomeData,
  } = useApiQuery<HomeLocation | null>('/users/me/home-location', {
    componentName: 'HomeLocationSettings',
    enabled: !!user,
  });

  // Set home location mutation
  const { mutate: setHomeLocation, loading: saving } = useApiMutation<HomeLocation, HomeLocation>({
    method: 'PUT',
    componentName: 'HomeLocationSettings',
    onSuccess: (result) => {
      toast.success(t('settings.location.home.saved'));
      // Optimistic update: update local state with API result
      if (result) {
        setHomeData(result);
      }
      setAddressInput('');
      logger.info('Home location saved', { component: 'HomeLocationSettings' });
    },
    onError: error => {
      toast.error(t('settings.location.home.save_error'));
      logger.error('Failed to save home location', error, { component: 'HomeLocationSettings' });
    },
  });

  // Clear home location mutation
  const { mutate: clearHomeLocation, loading: clearing } = useApiMutation<void, void>({
    method: 'DELETE',
    componentName: 'HomeLocationSettings',
    onSuccess: () => {
      toast.success(t('settings.location.home.cleared'));
      // Optimistic update: clear local state
      setHomeData(null);
      logger.info('Home location cleared', { component: 'HomeLocationSettings' });
    },
    onError: error => {
      toast.error(t('settings.location.home.clear_error'));
      logger.error('Failed to clear home location', error, { component: 'HomeLocationSettings' });
    },
  });

  const handleSaveLocation = async () => {
    if (!addressInput.trim()) {
      toast.error(t('settings.location.home.address_required'));
      return;
    }

    // For now, we'll use a simple geocoding approach
    // In production, this should use Google Places Autocomplete
    // The backend will validate and geocode the address
    await setHomeLocation('/users/me/home-location', {
      address: addressInput.trim(),
      lat: 0, // Will be geocoded by backend
      lon: 0, // Will be geocoded by backend
    });
  };

  const handleClearLocation = async () => {
    await clearHomeLocation('/users/me/home-location', undefined);
  };

  if (loadingConnectors || loadingHome) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoadingSpinner size="lg" spinnerColor="muted" />
      </div>
    );
  }

  const content = (
    <div className="space-y-4">
      {/* Connector status warning */}
      {!isPlacesActive && (
        <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3 space-y-2">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-yellow-600 dark:text-yellow-400 mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-yellow-900 dark:text-yellow-100">
                {t('settings.location.home.places_required')}
              </p>
              <p className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
                {t('settings.location.home.places_required_help')}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Current home location */}
      {homeLocation && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 space-y-2">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 space-y-1">
              <Label className="text-sm font-medium flex items-center gap-2">
                <Home className="h-4 w-4" />
                {t('settings.location.home.current')}
              </Label>
              <p className="text-sm text-foreground">{homeLocation.address}</p>
              <p className="text-xs text-muted-foreground font-mono">
                {homeLocation.lat.toFixed(6)}, {homeLocation.lon.toFixed(6)}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleClearLocation}
              disabled={clearing}
              className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
            >
              <Trash2 className="h-4 w-4 mr-1" />
              {t('settings.location.home.clear')}
            </Button>
          </div>
        </div>
      )}

      {/* Set new location */}
      {isPlacesActive && (
        <div className="space-y-3">
          <Label htmlFor="home-address">{t('settings.location.home.set_address')}</Label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="home-address"
                type="text"
                placeholder={t('settings.location.home.placeholder')}
                value={addressInput}
                onChange={e => setAddressInput(e.target.value)}
                className="pl-9"
                disabled={saving}
              />
            </div>
            <Button onClick={handleSaveLocation} disabled={saving || !addressInput.trim()}>
              {saving ? (
                <LoadingSpinner size="default" />
              ) : (
                t('settings.location.home.save')
              )}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">{t('settings.location.home.input_help')}</p>
        </div>
      )}

      {/* Usage info */}
      <InfoBox className="space-y-2">
        <p className="text-xs font-medium text-foreground">
          {t('settings.location.home.usage_title')}
        </p>
        <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
          <li>{t('settings.location.home.usage_weather')}</li>
          <li>{t('settings.location.home.usage_places')}</li>
          <li>{t('settings.location.home.usage_phrases')}</li>
        </ul>
      </InfoBox>

      {/* Privacy note */}
      <InfoBox>
        <p className="text-xs text-muted-foreground">{t('settings.location.home.privacy_note')}</p>
      </InfoBox>
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="home-location"
      title={t('settings.location.home.title')}
      description={t('settings.location.home.description')}
      icon={Home}
    >
      {content}
    </SettingsSection>
  );
}
