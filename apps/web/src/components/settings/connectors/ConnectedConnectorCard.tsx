/**
 * ConnectedConnectorCard component.
 * Displays a connected connector with disconnect button and optional preferences dropdown.
 */

'use client';

import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/format';
import { Clock, Unplug } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { ConnectorIcon } from './ConnectorIcon';
import { CONNECTOR_LABELS, isValidConnectorType } from '@/constants/connectors';
import { CONNECTORS_WITH_PREFERENCES, PREFERENCE_FIELDS } from './constants';
import { PreferenceDropdown } from './PreferenceDropdown';
import type { Language } from '@/i18n/settings';
import type { Connector, ConnectorPreferences } from './types';

interface ConnectedConnectorCardProps {
  connector: Connector;
  lng: Language;
  t: (key: string) => string;
  deleteLoading: boolean;
  onDisconnect: (connectorId: string) => void;
  // Preferences props (optional)
  savedPrefs?: ConnectorPreferences;
  savingPreference?: string | null;
  onSelectPreference?: (connectorId: string, connectorType: string, value: string) => void;
  // Children for additional settings (e.g., LocationSettings for google_places)
  children?: React.ReactNode;
}

function getConnectorLabel(type: string): string {
  // Handle legacy google_gmail -> gmail mapping
  const normalizedType = type === 'google_gmail' ? 'gmail' : type;
  if (isValidConnectorType(normalizedType)) {
    return CONNECTOR_LABELS[normalizedType];
  }
  // Fallback: format type as title case
  return type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function ConnectedConnectorCard({
  connector,
  lng,
  t,
  deleteLoading,
  onDisconnect,
  savedPrefs = {},
  savingPreference,
  onSelectPreference,
  children,
}: ConnectedConnectorCardProps) {
  const hasPreferences = CONNECTORS_WITH_PREFERENCES.includes(connector.connector_type);
  const prefField = PREFERENCE_FIELDS[connector.connector_type] || '';
  const isSaving = savingPreference === connector.id;

  return (
    <div className="p-4 bg-muted/50 rounded-lg border">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ConnectorIcon connectorType={connector.connector_type} />
          <div>
            <div className="font-medium">{getConnectorLabel(connector.connector_type)}</div>
            <div className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDate(connector.created_at, lng, { dateStyle: 'short' })}
            </div>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onDisconnect(connector.id)}
          disabled={deleteLoading}
          className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
          title={t('settings.connectors.google.disconnect')}
        >
          {deleteLoading ? <LoadingSpinner size="default" /> : <Unplug className="h-4 w-4" />}
        </Button>
      </div>

      {/* Preferences dropdown for Calendar and Tasks */}
      {hasPreferences && onSelectPreference && (
        <PreferenceDropdown
          connector={connector}
          savedValue={prefField ? savedPrefs[prefField] || '' : ''}
          saving={isSaving}
          t={t}
          onSelect={onSelectPreference}
        />
      )}

      {/* Additional settings (e.g., LocationSettings for google_places) */}
      {children}
    </div>
  );
}
