'use client';

import { LightsTool } from '@/components/workbench/lights/LightsTool';
import { useLanguageParam } from '@/hooks/useLanguageParam';

/** `/dashboard/tools/lights`: the account's Hue bridge, by hand (ADR-369). */
export default function LightsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  return <LightsTool lng={lng} />;
}
