'use client';

/**
 * Relations — the personal CRM page (N-09 + favorites).
 *
 * A first-class nav destination. Overview ⇄ detail in one page
 * (selected name in local state; the URL stays `/dashboard/relations` — a
 * `?name=` opens on that person, the « See the relationship » of a contact).
 * Reads are aggregations; the ONE write is the favorites star, toggled
 * optimistically through the overview hook — the detail panel receives the
 * star state from here so both surfaces always agree. A failed toggle rolls
 * back and toasts.
 */

import { useSearchParams } from 'next/navigation';
import { SectionHeader } from '@/components/ui/section-header';
import { useRef, useState } from 'react';
import type { Language } from '@/i18n/settings';
import { useAuth } from '@/hooks/useAuth';
import { Users } from '@/lib/icons';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { RelationCardList } from '@/components/relations/RelationCardList';
import { RelationSmsSourceNotice } from '@/components/relations/RelationSmsSection';
import { RelationDetailPanel } from '@/components/relations/RelationDetailPanel';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { FeatureErrorBoundary } from '@/components/errors';
import { useRelationsOverview } from '@/hooks/useRelations';

export interface RelationsScrollPort {
  read(): number;
  write(top: number): void;
}

export function RelationsWorkspace({
  lng,
  scrollPort,
}: {
  lng: Language;
  scrollPort?: RelationsScrollPort;
}) {
  const { user } = useAuth();
  return <AccountRelationsPage key={user?.id ?? 'signed-out'} lng={lng} scrollPort={scrollPort} />;
}

function AccountRelationsPage({
  lng,
  scrollPort,
}: {
  lng: Language;
  scrollPort?: RelationsScrollPort;
}) {
  const { t } = useTranslation();
  const {
    relations,
    relationsTotal,
    smsAvailable,
    loading,
    initialLoading,
    toggleFavorite,
    refetch,
    debriefEnabled,
    setDebriefEnabled,
  } = useRelationsOverview();
  const params = useSearchParams();
  const [selected, setSelected] = useState<string | null>(() => params.get('name'));
  const listRef = useRef<HTMLDivElement>(null);
  const returnRef = useRef<{ element: HTMLElement | null; scroll: number }>({
    element: null,
    scroll: 0,
  });
  const openRelation = (name: string) => {
    returnRef.current = {
      element: document.activeElement instanceof HTMLElement ? document.activeElement : null,
      scroll: scrollPort?.read() ?? window.scrollY,
    };
    setSelected(name);
    if (scrollPort) scrollPort.write(0);
    else window.scrollTo({ top: 0 });
  };
  const closeRelation = () => {
    setSelected(null);
    requestAnimationFrame(() => {
      const previous = returnRef.current;
      const target = previous.element?.isConnected
        ? previous.element
        : listRef.current?.querySelector<HTMLElement>('button');
      target?.focus({ preventScroll: true });
      if (scrollPort) scrollPort.write(previous.scroll);
      else window.scrollTo({ top: previous.scroll });
    });
  };

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
        <SectionHeader
          level={1}
          icon={Users}
          title={t('relations.title')}
          description={t('relations.subtitle')}
        />

        {selected && (
          <RelationDetailPanel
            name={selected}
            lng={lng}
            isFavorite={selectedIsFavorite}
            onToggleFavorite={handleToggleFavorite}
            // Same single-source rule as the star: the overview owns the
            // switch, and the panel never re-reads it.
            debriefEnabled={debriefEnabled}
            onDebriefToggle={next => void setDebriefEnabled(next)}
            // The merge candidates come from the overview the page already
            // holds: a second read would be a second opinion on which
            // relationships exist.
            candidates={relations.map(relation => relation.display_name)}
            onMerged={refetch}
            onBack={closeRelation}
          />
        )}
        {initialLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner className="h-6 w-6" />
          </div>
        ) : (
          // `initialLoading`, never `loading`: starring refetches the overview,
          // and staging a spinner then would unmount the toolbar mid-use —
          // the user's search text, sort choice and filters, gone on a star.
          <div ref={listRef} hidden={selected !== null} aria-busy={loading}>
            <RelationSmsSourceNotice available={smsAvailable} />
            <RelationCardList
              relations={relations}
              relationsTotal={relationsTotal}
              onOpen={openRelation}
              onToggleFavorite={handleToggleFavorite}
            />
          </div>
        )}
      </div>
    </FeatureErrorBoundary>
  );
}
