import { useEffectRequest } from '@/hooks/useEffectRequest';
/**
 * Hook for fetching available calendars or task lists from a connected provider.
 * Used by PreferenceDropdown to populate the selection dropdown.
 */

import { useState, useCallback } from 'react';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { PREFERENCE_FIELDS } from '../constants';

export interface ConnectorItem {
  name: string;
  isDefault: boolean;
  accessRole?: string;
}

interface CalendarApiItem {
  name: string;
  is_default: boolean;
  access_role: string;
}

interface TaskListApiItem {
  name: string;
  is_default: boolean;
}

interface UseConnectorItemsReturn {
  items: ConnectorItem[];
  loading: boolean;
  error: boolean;
  refetch: () => void;
}

function isCalendarConnector(connectorType: string): boolean {
  const prefField = PREFERENCE_FIELDS[connectorType] || '';
  return prefField === 'default_calendar_name';
}

export function useConnectorItems(
  connectorId: string,
  connectorType: string
): UseConnectorItemsReturn {
  const [items, setItems] = useState<ConnectorItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const isCalendar = isCalendarConnector(connectorType);

  // The automatic read and the retry share one generation (`useEffectRequest`):
  // a newer read, or the unmount, aborts the one in flight at its transport.
  const fetchItems = useCallback(
    async (signal: AbortSignal) => {
      setLoading(true);
      setError(false);

      try {
        if (isCalendar) {
          const response = await apiClient.get<{ items: CalendarApiItem[] }>(
            `/connectors/${connectorId}/calendars`,
            { signal }
          );
          if (signal.aborted) return;
          setItems(
            (response.items || []).map(item => ({
              name: item.name,
              isDefault: item.is_default,
              accessRole: item.access_role,
            }))
          );
        } else {
          const response = await apiClient.get<{ items: TaskListApiItem[] }>(
            `/connectors/${connectorId}/task-lists`,
            { signal }
          );
          if (signal.aborted) return;
          setItems(
            (response.items || []).map(item => ({
              name: item.name,
              isDefault: item.is_default,
            }))
          );
        }
      } catch (err) {
        if (signal.aborted) return;
        logger.error('Failed to fetch connector items', err as Error, {
          component: 'useConnectorItems',
          connectorId,
          connectorType,
        });
        setError(true);
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [connectorId, connectorType, isCalendar]
  );

  const rerun = useEffectRequest(fetchItems);
  const refetch = useCallback(() => void rerun(), [rerun]);
  return { items, loading, error, refetch };
}
