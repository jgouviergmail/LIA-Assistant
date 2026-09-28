'use client';

/**
 * The radio's page (ADR-324): start the station, or follow what it says.
 */

import { RadioPage } from '@/components/radio/RadioPage';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { radioAvailable } from '@/lib/radio/availability';

interface RadioRouteProps {
  params: Promise<{ lng: string }>;
}

export default function RadioRoute({ params }: RadioRouteProps) {
  const lng = useLanguageParam(params);
  const { config } = useAppConfig();
  return <RadioPage lng={lng} available={config === null ? null : radioAvailable(config)} />;
}
