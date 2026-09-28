'use client';

/**
 * useRadioStationName — the name the listener gave their station (ADR-324), or
 * `null` for the name their language gives it. Read from their settings, and
 * only where the radio is offered: a surface that cannot show the station asks
 * nothing about it.
 */

import { useApiQuery } from '@/hooks/useApiQuery';
import { RADIO_ENDPOINTS } from '@/lib/radio/api';
import type { RadioPreferences } from '@/lib/radio/types';

export function useRadioStationName(enabled: boolean): string | null {
  const { data } = useApiQuery<RadioPreferences>(RADIO_ENDPOINTS.preferences, {
    componentName: 'useRadioStationName',
    enabled,
  });
  return data?.station_name ?? null;
}
