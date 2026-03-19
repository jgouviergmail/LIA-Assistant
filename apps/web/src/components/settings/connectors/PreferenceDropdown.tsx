/**
 * PreferenceDropdown component.
 * Replaces the free-text input for calendar/task list preferences
 * with a dropdown fetched from the connected provider.
 */

'use client';

import { Settings2, RefreshCw, AlertCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { PREFERENCE_FIELDS } from './constants';
import { useConnectorItems } from './hooks/useConnectorItems';
import type { Connector } from './types';

interface PreferenceDropdownProps {
  connector: Connector;
  savedValue: string;
  saving: boolean;
  t: (key: string) => string;
  onSelect: (connectorId: string, connectorType: string, value: string) => void;
}

/** Sentinel value for the "provider default" option (clear preference). */
const PROVIDER_DEFAULT_VALUE = '__provider_default__';

export function PreferenceDropdown({
  connector,
  savedValue,
  saving,
  t,
  onSelect,
}: PreferenceDropdownProps) {
  const prefField = PREFERENCE_FIELDS[connector.connector_type] || '';
  const isCalendar = prefField === 'default_calendar_name';

  const { items, loading, error, refetch } = useConnectorItems(
    connector.id,
    connector.connector_type
  );

  // Determine the current select value
  const defaultItem = items.find(item => item.isDefault);
  const currentValue = savedValue || defaultItem?.name || PROVIDER_DEFAULT_VALUE;

  const handleValueChange = (value: string) => {
    const effectiveValue = value === PROVIDER_DEFAULT_VALUE ? '' : value;
    onSelect(connector.id, connector.connector_type, effectiveValue);
  };

  const label = isCalendar
    ? t('settings.connectors.preferences.default_calendar')
    : t('settings.connectors.preferences.default_task_list');

  const helpText = isCalendar
    ? t('settings.connectors.preferences.calendar_help')
    : t('settings.connectors.preferences.tasks_help');

  const placeholder = isCalendar
    ? t('settings.connectors.preferences.select_calendar')
    : t('settings.connectors.preferences.select_task_list');

  return (
    <div className="mt-4 pt-4 border-t border-border/50">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Settings2 className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">{label}</span>
        </div>
        {!loading && !error && (
          <Button
            variant="ghost"
            size="icon"
            onClick={refetch}
            className="h-6 w-6 text-muted-foreground hover:text-foreground"
            title={t('settings.connectors.preferences.refresh')}
          >
            <RefreshCw className="h-3 w-3" />
          </Button>
        )}
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex items-center gap-2 p-3 rounded-lg border border-border/50">
          <LoadingSpinner size="default" />
          <span className="text-sm text-muted-foreground">
            {t('settings.connectors.preferences.loading_items')}
          </span>
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="flex items-center justify-between p-3 rounded-lg border border-destructive/30 bg-destructive/5">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive" />
            <span className="text-sm text-destructive">
              {t('settings.connectors.preferences.fetch_error')}
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={refetch}
            className="text-destructive hover:text-destructive"
          >
            <RefreshCw className="h-3 w-3 mr-1" />
            {t('settings.connectors.preferences.refresh')}
          </Button>
        </div>
      )}

      {/* Dropdown */}
      {!loading && !error && (
        <>
          <Select value={currentValue} onValueChange={handleValueChange} disabled={saving}>
            <SelectTrigger className="w-full">
              {saving ? (
                <div className="flex items-center gap-2">
                  <LoadingSpinner size="default" />
                </div>
              ) : (
                <SelectValue placeholder={placeholder} />
              )}
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={PROVIDER_DEFAULT_VALUE}>
                <span className="text-muted-foreground">
                  {t('settings.connectors.preferences.provider_default')}
                </span>
              </SelectItem>
              {items.map(item => (
                <SelectItem key={item.name} value={item.name}>
                  <div className="flex items-center gap-2">
                    <span>{item.name}</span>
                    {item.isDefault && (
                      <Badge variant="secondary" size="sm">
                        {t('settings.connectors.preferences.provider_default')}
                      </Badge>
                    )}
                    {isCalendar && item.accessRole === 'reader' && (
                      <Badge variant="outline" size="sm">
                        {t('settings.connectors.preferences.read_only')}
                      </Badge>
                    )}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="mt-1.5 text-xs text-muted-foreground">{helpText}</p>
        </>
      )}
    </div>
  );
}
