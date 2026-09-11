'use client';

/**
 * « Mes fichiers générés » — what LIA produced, kept where a person can find it
 * (ADR-279).
 *
 * Images and documents used to live in the conversation that produced them and
 * nowhere else: nothing listed them, nothing let one be downloaded back a day
 * later, and resetting the conversation deleted the lot. Three galleries now
 * hold them — images, documents, browser screenshots — each with a search, two
 * date windows, an ordering, and the EXACT total behind the page (ADR-185).
 *
 * The shape follows the section conventions already in place:
 *
 * - the filters FOLD below `lg`, like the workboard's (the reader came to look
 *   at their files, not at the controls) and the folded summary says what it
 *   holds — the count and the words of the controls;
 * - every expiry is STATED rather than implied: a file's deadline is on its
 *   card, because a file that vanishes without warning is the defect the
 *   expiry notice was written for;
 * - a bulk delete reports what it removed AND what it skipped: a file that
 *   expired between the listing and the click must not be counted as deleted.
 */

import { useMemo, useState } from 'react';
import { Camera, FileText, FolderOpen, ImageIcon, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

import { GeneratedAssetGrid } from '@/components/settings/generated-assets/GeneratedAssetGrid';
import { GeneratedAssetFiltersBar } from '@/components/settings/generated-assets/GeneratedAssetFiltersBar';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useConfirm } from '@/components/ui/use-confirm';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useGeneratedAssets } from '@/hooks/useGeneratedAssets';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatFileSize } from '@/lib/format';
import { activeAssetFilterCount } from '@/lib/generated-assets/filters';
import type {
  GeneratedAssetFamily,
  GeneratedAssetFilters,
  GeneratedAssetsDeleteResult,
} from '@/types/generated-assets';

const FAMILIES: readonly { key: GeneratedAssetFamily; icon: typeof ImageIcon }[] = [
  { key: 'images', icon: ImageIcon },
  { key: 'documents', icon: FileText },
  { key: 'screenshots', icon: Camera },
];

const NO_FILTERS: GeneratedAssetFilters = {};

export interface GeneratedAssetsSettingsProps {
  lng: Language;
}

export function GeneratedAssetsSettings({ lng }: GeneratedAssetsSettingsProps) {
  const { t } = useTranslation(lng);
  const [family, setFamily] = useState<GeneratedAssetFamily>('images');

  return (
    <SettingsSection
      value="generated-assets"
      title={t('settings.generated_assets.title')}
      description={t('settings.generated_assets.description')}
      icon={FolderOpen}
    >
      <Tabs value={family} onValueChange={value => setFamily(value as GeneratedAssetFamily)}>
        <TabsList className="grid w-full grid-cols-3">
          {/* Three equal columns are ~80 px each at 320 px: the mark yields to
              the word below `sm` (the `SkillGuideModal` precedent), because a
              tab reading « Docu… » names nothing. */}
          {FAMILIES.map(({ key, icon: Icon }) => (
            <TabsTrigger key={key} value={key} className="gap-1.5 px-2 text-xs sm:px-3 sm:text-sm">
              <Icon className="hidden h-4 w-4 shrink-0 sm:block" aria-hidden="true" />
              <span className="truncate">{t(`settings.generated_assets.family.${key}`)}</span>
            </TabsTrigger>
          ))}
        </TabsList>
        {FAMILIES.map(({ key, icon: Icon }) => (
          <TabsContent key={key} value={key} className="mt-4">
            {/* Mounted only while its tab is open: three galleries fetching at
                once would open three pages nobody is looking at. */}
            {family === key && <Gallery lng={lng} family={key} icon={Icon} />}
          </TabsContent>
        ))}
      </Tabs>
    </SettingsSection>
  );
}

/** One family: its filters, its page, and what it holds. */
function Gallery({
  lng,
  family,
  icon,
}: {
  lng: Language;
  family: GeneratedAssetFamily;
  /** The family's own mark, so an empty documents gallery is not headed by a
      picture — the tab and the empty state name the same thing. */
  icon: typeof ImageIcon;
}) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const wide = useMediaQuery('(min-width: 1024px)');
  const [filters, setFilters] = useState<GeneratedAssetFilters>(NO_FILTERS);
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const gallery = useGeneratedAssets(family, filters, true);
  const { mutate: removeMany, loading: removing } = useApiMutation<
    { ids: string[] },
    GeneratedAssetsDeleteResult
  >({ method: 'POST', componentName: 'GeneratedAssetsSettings' });

  const activeCount = useMemo(() => activeAssetFilterCount(filters), [filters]);
  const chosen = useMemo(
    () => gallery.items.filter(item => selected.has(item.id)).map(item => item.id),
    [gallery.items, selected]
  );

  const deleteChosen = async () => {
    if (chosen.length === 0 || removing) return;
    const ok = await confirm({
      title: t('settings.generated_assets.confirm_delete_title'),
      description: t('settings.generated_assets.confirm_delete_description', {
        count: chosen.length,
      }),
      confirmLabel: t('settings.generated_assets.delete_selected', { count: chosen.length }),
      destructive: true,
    });
    if (!ok) return;
    const result = await removeMany('/generated-assets/delete', { ids: chosen });
    if (!result) {
      toast.error(t('common.error'));
      return;
    }
    setSelected(new Set());
    // What actually went, and what did not: a file the cleanup removed between
    // the listing and the click is skipped, never counted as deleted.
    if (result.deleted.length > 0) {
      toast.success(
        t('settings.generated_assets.deleted', { count: result.deleted.length })
      );
    }
    if (result.skipped.length > 0) {
      toast.info(t('settings.generated_assets.skipped', { count: result.skipped.length }));
    }
    gallery.refetch();
  };

  return (
    <div className="space-y-4">
      {confirmDialog}

      {/* Below `lg` the block folds behind a summary saying what it holds: the
          reader came to look at their files, not at four fields and a button. */}
      <GeneratedAssetFiltersBar
        filters={filters}
        onChange={setFilters}
        collapsible={!wide}
      />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {/* Both figures are EXACT over the whole filtered set, never over the
              page: a gallery says how many files it holds and how much room
              they take (ADR-185). */}
          {t('settings.generated_assets.total', { count: gallery.total })}
          {gallery.totalBytes > 0 && ` · ${formatFileSize(gallery.totalBytes)}`}
        </p>
        {chosen.length > 0 && (
          <Button variant="destructive" size="sm" onClick={() => void deleteChosen()}>
            <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            {t('settings.generated_assets.delete_selected', { count: chosen.length })}
          </Button>
        )}
      </div>

      {gallery.firstLoad ? (
        <>
          <LoadingAnnouncement />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2].map(index => (
              <Skeleton key={index} className="h-40 w-full" />
            ))}
          </div>
        </>
      ) : gallery.error ? (
        <EmptyState icon={icon} description={t('settings.generated_assets.load_error')} />
      ) : gallery.total === 0 ? (
        <EmptyState
          icon={icon}
          reason={activeCount > 0 ? 'no-match' : 'no-data'}
          title={
            activeCount > 0
              ? t('settings.generated_assets.empty.filtered_title')
              : t(`settings.generated_assets.empty.${family}_title`)
          }
          description={
            activeCount > 0
              ? t('settings.generated_assets.empty.filtered_description')
              : t(`settings.generated_assets.empty.${family}_description`)
          }
        />
      ) : (
        <GeneratedAssetGrid
          lng={lng}
          items={gallery.items}
          selected={selected}
          onToggle={id =>
            setSelected(previous => {
              const next = new Set(previous);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            })
          }
          page={gallery.page}
          totalPages={gallery.totalPages}
          onPage={gallery.setPage}
          onDeleted={gallery.refetch}
        />
      )}
    </div>
  );
}
