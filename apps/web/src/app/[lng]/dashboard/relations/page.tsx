'use client';

/**
 * Relations — the personal CRM page (N-09 + favorites).
 *
 * A first-class nav destination since 2026-07-30 (it took the header slot
 * `spaces` held — the spaces page keeps its one-click door through the chat
 * indicator, which now always renders). Overview ⇄ detail in one page
 * (selected name in local state; the URL stays `/dashboard/relations`).
 * Reads are aggregations; the ONE write is the favorites star, toggled
 * optimistically through the overview hook — the detail panel receives the
 * star state from here so both surfaces always agree. A failed toggle rolls
 * back and toasts.
 */

import { useState } from 'react';
import { Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { RelationCardList } from '@/components/relations/RelationCardList';
import { RelationDetailPanel } from '@/components/relations/RelationDetailPanel';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { FeatureErrorBoundary } from '@/components/errors';
import { useRelationsOverview } from '@/hooks/useRelations';
import { useLanguageParam } from '@/hooks/useLanguageParam';

export default function RelationsPage({ params }: { params: Promise<{ lng: string }> }) {
  const lng = useLanguageParam(params);
  const { t } = useTranslation();
  const { relations, relationsTotal, loading, initialLoading, toggleFavorite } =
    useRelationsOverview();
  const [selected, setSelected] = useState<string | null>(null);

  const handleToggleFavorite = async (name: string, nextValue: boolean) => {
    const { ok } = await toggleFavorite(name, nextValue);
    if (!ok) toast.error(t('relations.favorite_error'));
  };

  const selectedIsFavorite = selected
    ? (relations.find(relation => relation.display_name === selected)?.is_favorite ?? false)
    : false;

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
          <RelationDetailPanel
            name={selected}
            lng={lng}
            isFavorite={selectedIsFavorite}
            onToggleFavorite={handleToggleFavorite}
            onBack={() => setSelected(null)}
          />
        ) : initialLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner className="h-6 w-6" />
          </div>
        ) : (
          // `initialLoading`, never `loading`: starring refetches the overview,
          // and staging a spinner then would unmount the toolbar mid-use —
          // the user's search text, sort choice and filters, gone on a star.
          <div aria-busy={loading}>
            <RelationCardList
              relations={relations}
              relationsTotal={relationsTotal}
              onOpen={setSelected}
              onToggleFavorite={handleToggleFavorite}
            />
          </div>
        )}
      </div>
    </FeatureErrorBoundary>
  );
}
