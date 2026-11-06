'use client';

/**
 * Searching the calendars (ADR-369, lot 5).
 *
 * The person's words are asked of the calendars shown, a year on each side of today;
 * what each provider understands by a word is its own. The answer takes the view's
 * place, the earliest first, each event opening as it does from the view. A calendar
 * that could not be read is said, and so is a cut (ADR-185). With no calendar shown
 * nothing is asked: there is nowhere to look, which is no failure.
 */
import { Search, X } from 'lucide-react';
import Link from 'next/link';
import { useState, type FormEvent, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useWorkbenchItem, type WorkbenchItemState } from '@/hooks/useWorkbenchItem';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { eventWhen } from '@/lib/workbench/calendar/format';
import type { CalendarEvent, CalendarSearchAnswer } from '@/lib/workbench/types';

const SEARCH_PATH = '/workbench/calendar/search';

export interface CalendarSearching {
  /** The words the answer is about; empty shows the view. */
  words: string;
  search: (words: string) => void;
  found: WorkbenchItemState<CalendarSearchAnswer>;
  /** No calendar is shown: there is nowhere to look. */
  nowhere: boolean;
}

/** @param calendarIds - The calendars shown: a search asks those alone. */
export function useCalendarSearch(calendarIds: readonly string[]): CalendarSearching {
  const [words, search] = useState('');
  const nowhere = calendarIds.length === 0;
  const found = useWorkbenchItem<CalendarSearchAnswer>(words && !nowhere ? SEARCH_PATH : null, {
    q: words,
    calendar_ids: calendarIds,
  });
  return { words, search, found, nowhere };
}

export function CalendarSearchBox({
  lng,
  searching,
}: {
  lng: Language;
  searching: CalendarSearching;
}) {
  const { t } = useTranslation(lng);
  const [typed, setTyped] = useState('');
  const submit = (event: FormEvent) => {
    event.preventDefault();
    searching.search(typed.trim());
  };
  return (
    <form role="search" onSubmit={submit} className="flex items-center gap-1">
      <div className="w-40 shrink-0">
        <Input
          type="search"
          value={typed}
          onChange={event => setTyped(event.target.value)}
          aria-label={t('workbench.calendar.search_label')}
          placeholder={t('workbench.calendar.search_label')}
          className="h-8 w-full"
        />
      </div>
      <Button
        type="submit"
        variant="outline"
        size="icon"
        aria-label={t('workbench.calendar.search_go')}
      >
        <Search className="h-4 w-4" aria-hidden="true" />
      </Button>
      {searching.words && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t('workbench.calendar.search_clear')}
          onClick={() => {
            setTyped('');
            searching.search('');
          }}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      )}
    </form>
  );
}

interface SearchShownProps {
  lng: Language;
  zone: string;
  hrefOf: (event: CalendarEvent) => string;
  linkRef: (key: string, link: HTMLAnchorElement | null) => void;
}

/** What a search found while there are words, else the view. */
export function SearchOrView({
  searching,
  children,
  ...shown
}: SearchShownProps & { searching: CalendarSearching; children: ReactNode }) {
  if (!searching.words) return children;
  return <CalendarSearchResults {...shown} found={searching.found} nowhere={searching.nowhere} />;
}

function CalendarSearchResults({
  lng,
  zone,
  found,
  nowhere,
  hrefOf,
  linkRef,
}: SearchShownProps & { found: WorkbenchItemState<CalendarSearchAnswer>; nowhere: boolean }) {
  const { t } = useTranslation(lng);
  const answer = found.item;
  if (nowhere) return <EmptyState description={t('workbench.calendar.search_none')} />;
  if (found.loading && !answer) {
    return (
      <div className="space-y-2 p-4" aria-busy="true">
        {[1, 2, 3].map(index => (
          <Skeleton key={index} className="h-10 w-full" />
        ))}
      </div>
    );
  }
  if (!answer) {
    return (
      <EmptyState
        className="flex-1"
        description={t('workbench.calendar.search_failed')}
        action={{ label: t('workbench.states.retry'), onClick: () => void found.refresh() }}
      />
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {answer.failed.length > 0 && (
        <p role="status" className="px-4 pt-3 text-sm text-destructive">
          {t('workbench.calendar.search_part_failed')}
        </p>
      )}
      {answer.events.length === 0 ? (
        <EmptyState description={t('workbench.calendar.search_none')} />
      ) : (
        <ul aria-label={t('workbench.calendar.search_results')} className="divide-y">
          {answer.events.map(event => (
            <li key={`${event.calendar_id}:${event.id}`}>
              <Link
                ref={link => linkRef(event.id, link)}
                href={hrefOf(event)}
                scroll={false}
                className="block px-4 py-2 text-sm hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="block font-medium text-foreground">
                  {event.summary || t('workbench.calendar.no_title')}
                </span>
                <span className="block text-xs text-muted-foreground">
                  {eventWhen(event, zone, lng, t('workbench.calendar.all_day'))}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {answer.truncated && (
        <p role="status" className="px-4 py-3 text-sm text-muted-foreground">
          {t('workbench.calendar.search_truncated', { count: answer.events.length })}
        </p>
      )}
    </div>
  );
}
