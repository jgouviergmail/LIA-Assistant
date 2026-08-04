'use client';

/**
 * `/dashboard/capabilities` — the constellation.
 *
 * A thin route shell, like the relations and notifications pages: the body
 * lives in `CapabilityMapView` so the page stays the routing concern and the
 * map stays testable without a router.
 */

import { Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { CapabilityMapView } from '@/components/capabilities/CapabilityMapView';
import { FeatureErrorBoundary } from '@/components/errors';
import { useLanguageParam } from '@/hooks/useLanguageParam';

export default function CapabilitiesPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  const { t } = useTranslation();

  return (
    <FeatureErrorBoundary feature="capabilities">
      {/* One column, the chart's own width: the heading is left-aligned and
          the square is centred, so on a wide screen they would otherwise sit
          on two different left edges. */}
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <Sparkles className="h-7 w-7 text-primary" aria-hidden="true" />
            {t('capabilities.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('capabilities.subtitle')}</p>
        </div>

        <CapabilityMapView lng={lng} />
      </div>
    </FeatureErrorBoundary>
  );
}
