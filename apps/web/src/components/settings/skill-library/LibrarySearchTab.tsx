'use client';

/**
 * Searching the portal (ADR-327): the debounced text, the portal's ranking.
 *
 * Each row names the skill, where the portal says it lives and how often it
 * was installed; « Read » opens it before anything is installed. A skill the
 * portal lists on a website instead of a GitHub repository is shown, and said
 * not installable — hiding it would make the portal look emptier than it is.
 */
import { useState } from 'react';
import type { TFunction } from 'i18next';
import { BookOpenText, PackageSearch } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { SearchInput } from '@/components/ui/search-input';
import { LIBRARY_QUERY_MIN_CHARS, useLibrarySearch } from '@/hooks/useSkillLibrary';
import type { LibrarySearchItem } from '@/lib/skill-library/types';

function ResultRow({
  item,
  t,
  onRead,
}: {
  item: LibrarySearchItem;
  t: TFunction;
  onRead: (item: LibrarySearchItem) => void;
}) {
  return (
    <li className="flex flex-col gap-2 rounded-lg border bg-card p-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="break-words text-sm font-medium">{item.name}</span>
          {item.installed && (
            <Badge variant="success" className="text-xs">
              {t('settings.skills.library.search.installed')}
            </Badge>
          )}
          {!item.supported && (
            <Badge variant="outline" className="text-xs">
              {t('settings.skills.library.search.unsupported')}
            </Badge>
          )}
        </div>
        <p className="break-all text-xs text-muted-foreground">
          {item.source} ·{' '}
          <span className="tabular-nums">
            {t('settings.skills.library.search.installs', { count: item.installs })}
          </span>
        </p>
      </div>
      {item.supported ? (
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5 self-start sm:self-center"
          onClick={() => onRead(item)}
          aria-label={t('settings.skills.library.search.read_named', { name: item.name })}
        >
          <BookOpenText className="h-4 w-4" aria-hidden />
          {t('settings.skills.library.search.read')}
        </Button>
      ) : (
        <p className="text-xs text-muted-foreground sm:max-w-[14rem]">
          {t('settings.skills.library.search.unsupported_hint')}
        </p>
      )}
    </li>
  );
}

export function LibrarySearchTab({
  t,
  revision,
  onRead,
}: {
  t: TFunction;
  /** Moves after an install or an update: the results are read again. */
  revision: number;
  /** Reads a skill, naming the portal that listed it. */
  onRead: (item: LibrarySearchItem, portal: string) => void;
}) {
  const [query, setQuery] = useState('');
  const { data, loading, error, refetch } = useLibrarySearch(query, revision);
  const long = query.trim().length >= LIBRARY_QUERY_MIN_CHARS;
  const items = long ? (data?.items ?? []) : [];

  return (
    <div className="space-y-3">
      <SearchInput
        onSearchChange={setQuery}
        loading={loading}
        placeholder={t('settings.skills.library.search.placeholder')}
        aria-label={t('settings.skills.library.search.label')}
      />
      {!long && (
        <p className="text-xs text-muted-foreground">
          {t('settings.skills.library.search.idle', { min: LIBRARY_QUERY_MIN_CHARS })}
        </p>
      )}
      {long && error && (
        <div role="alert" className="flex items-center gap-3 text-sm">
          <p className="text-muted-foreground">{t('settings.skills.library.errors.generic')}</p>
          <Button size="sm" variant="outline" onClick={() => void refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      )}
      {long && !error && !loading && data && items.length === 0 && (
        <EmptyState
          icon={PackageSearch}
          reason="no-match"
          description={t('settings.skills.library.search.empty')}
        />
      )}
      {items.length > 0 && (
        <ul className="space-y-2" aria-busy={loading}>
          {items.map(item => (
            <ResultRow
              key={item.registry_id}
              item={item}
              t={t}
              onRead={picked => onRead(picked, data?.portal ?? 'skills_sh')}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
