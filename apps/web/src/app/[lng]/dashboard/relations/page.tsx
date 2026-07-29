'use client';

/**
 * Relations — the personal CRM page (N-09).
 *
 * Overview ⇄ detail in one page (selected name in local state; the URL stays
 * `/dashboard/relations`). Read-only: every action is a chat deep link
 * (ADR-173). Reached from settings search and a briefing-card shortcut — not
 * a 6th nav destination (the header already clips at 5, R01).
 */

import { useState } from 'react';
import { Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { RelationCardList } from '@/components/relations/RelationCardList';
import { RelationDetailPanel } from '@/components/relations/RelationDetailPanel';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { FeatureErrorBoundary } from '@/components/errors';
import { useRelationsOverview } from '@/hooks/useRelations';
import { useLanguageParam } from '@/hooks/useLanguageParam';

export default function RelationsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  const { t } = useTranslation();
  const { relations, loading } = useRelationsOverview();
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <FeatureErrorBoundary feature="relations">
      <div className="space-y-6">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <Users className="h-7 w-7 text-primary" aria-hidden="true" />
            {t('relations.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('relations.subtitle')}</p>
        </div>

        {selected ? (
          <RelationDetailPanel name={selected} lng={lng} onBack={() => setSelected(null)} />
        ) : loading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner className="h-6 w-6" />
          </div>
        ) : (
          <RelationCardList relations={relations} onOpen={setSelected} />
        )}
      </div>
    </FeatureErrorBoundary>
  );
}
