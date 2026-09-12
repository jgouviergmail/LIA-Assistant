'use client';

/**
 * The « Bookmarks » tab of « My generated files » (ADR-282).
 *
 * A search over the answers and the requests, the EXACT total and the cap the
 * account may reach (ADR-185/184), one card per kept answer, the app's own
 * pagination. First load draws skeletons; a refetch keeps the cards under
 * `aria-busy` — never an unmount.
 */

import { Bookmark as BookmarkIcon } from 'lucide-react';
import { useState } from 'react';

import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Pagination } from '@/components/ui/pagination';
import { SearchInput } from '@/components/ui/search-input';
import { Skeleton } from '@/components/ui/skeleton';
import { useBookmarks } from '@/hooks/useBookmarks';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

import { BookmarkCard } from './BookmarkCard';

/** The API refuses a longer needle; the input stops there too. */
export const BOOKMARK_SEARCH_MAX_CHARS = 200;

export interface BookmarkListProps {
  lng: Language;
}

export function BookmarkList({ lng }: BookmarkListProps) {
  const { t } = useTranslation(lng);
  const [query, setQuery] = useState('');
  const list = useBookmarks(query, true);
  const searching = query.trim().length > 0;

  return (
    <div className="space-y-4">
      <SearchInput
        placeholder={t('settings.bookmarks.search')}
        aria-label={t('settings.bookmarks.search')}
        maxLength={BOOKMARK_SEARCH_MAX_CHARS}
        onSearchChange={setQuery}
      />

      <p className="text-sm text-muted-foreground">
        {/* Both figures are EXACT and published by the API: the count over
            the whole filtered set, and the cap the account may reach. */}
        {searching || list.maxPerUser === 0
          ? t('settings.bookmarks.total', { count: list.total })
          : t('settings.bookmarks.capacity', { count: list.total, max: list.maxPerUser })}
      </p>

      {list.firstLoad ? (
        <>
          <LoadingAnnouncement />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {[0, 1].map(index => (
              <Skeleton key={index} className="h-48 w-full" />
            ))}
          </div>
        </>
      ) : list.error ? (
        <EmptyState icon={BookmarkIcon} description={t('settings.bookmarks.load_error')} />
      ) : list.total === 0 ? (
        <EmptyState
          icon={BookmarkIcon}
          reason={searching ? 'no-match' : 'no-data'}
          title={
            searching
              ? t('settings.generated_assets.empty.filtered_title')
              : t('settings.generated_assets.empty.bookmarks_title')
          }
          description={
            searching
              ? t('settings.generated_assets.empty.filtered_description')
              : t('settings.generated_assets.empty.bookmarks_description')
          }
        />
      ) : (
        <div className="space-y-3" aria-busy={list.loading || undefined}>
          {/* `grid-cols-1` is not decoration: an implicit phone track sizes
              itself to the cards' min-content (measured 2026-09-11). */}
          <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {list.items.map(bookmark => (
              <BookmarkCard
                key={bookmark.id}
                lng={lng}
                bookmark={bookmark}
                onDeleted={list.refetch}
              />
            ))}
          </ul>
          {list.totalPages > 1 && (
            <Pagination
              currentPage={list.page}
              totalPages={list.totalPages}
              onPageChange={list.setPage}
              variant="centered"
              labels={{
                previous: t('common.previous'),
                next: t('common.next'),
                pageInfo: (current, count) =>
                  t('settings.bookmarks.page_info', { current, total: count }),
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
