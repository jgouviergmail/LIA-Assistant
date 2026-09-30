'use client';

/**
 * The skills installed from a library, and whether each moved (ADR-327).
 *
 * Opening the tab asks GitHub, once per repository, whether the folder
 * changed since it was installed; « Review the update » reads the next
 * version before anything is replaced. Removing a skill stays in the skills
 * gallery, like every other skill.
 */
import type { TFunction } from 'i18next';
import { FolderGit2, RefreshCw, Sparkles } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useLibraryInstalled } from '@/hooks/useSkillLibrary';
import type { LibraryInstalledItem } from '@/lib/skill-library/types';
import { shortSha } from '@/lib/skill-library/types';
import { libraryUpdateTone } from '@/lib/status-tone';

function InstalledRow({
  item,
  t,
  onReview,
}: {
  item: LibraryInstalledItem;
  t: TFunction;
  onReview: (item: LibraryInstalledItem) => void;
}) {
  const location = item.path ? `${item.repository}/${item.path}` : item.repository;
  return (
    <li className="flex flex-col gap-2 rounded-lg border bg-card p-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="break-words text-sm font-medium">{item.name}</span>
          <Badge variant={libraryUpdateTone(item.update)} className="text-xs">
            {t(`settings.skills.library.installed.state.${item.update}`)}
          </Badge>
        </div>
        <p className="break-all text-xs text-muted-foreground">
          {location} · {shortSha(item.commit_sha)}
        </p>
      </div>
      {item.update === 'available' && (
        <Button
          size="sm"
          className="gap-1.5 self-start sm:self-center"
          onClick={() => onReview(item)}
          aria-label={t('settings.skills.library.installed.review_named', { name: item.name })}
        >
          <Sparkles className="h-4 w-4" aria-hidden />
          {t('settings.skills.library.installed.review')}
        </Button>
      )}
    </li>
  );
}

export function LibraryInstalledTab({
  t,
  onReview,
}: {
  t: TFunction;
  onReview: (item: LibraryInstalledItem) => void;
}) {
  const { data, loading, error, refetch } = useLibraryInstalled(true);
  const firstLoad = data === undefined && loading;
  const items = data?.items ?? [];

  if (firstLoad) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-16 w-full" label={t('settings.skills.library.installed.loading')} />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }
  return (
    <div className="space-y-3" aria-busy={loading}>
      <div className="flex items-center justify-between gap-2">
        <h4 className="flex items-center gap-2 text-sm font-medium">
          <FolderGit2 className="h-4 w-4 text-primary" aria-hidden />
          {t('settings.skills.library.installed.title', { count: items.length })}
        </h4>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void refetch()}>
          <RefreshCw className="h-4 w-4" aria-hidden />
          {t('settings.skills.library.installed.check')}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-muted-foreground">
          {t('settings.skills.library.errors.generic')}
        </p>
      )}
      {!error && items.length === 0 && (
        <EmptyState reason="no-data" description={t('settings.skills.library.installed.empty')} />
      )}
      {items.length > 0 && (
        <ul className="space-y-2">
          {items.map(item => (
            <InstalledRow key={item.skill_id} item={item} t={t} onReview={onReview} />
          ))}
        </ul>
      )}
    </div>
  );
}
