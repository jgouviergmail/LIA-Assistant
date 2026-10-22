'use client';

import { useEffect, useRef, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { discussionSourceSchema } from '@/types/proactive-discussions';

/** How long typing must pause before the search applies itself: one read per search. */
export const DISCUSSION_SEARCH_DELAY_MS = 400;

/** The filters a read carries: blank values dropped, the search trimmed. */
export function appliedFilters(draft: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(draft)
      .map(([key, value]) => [key, key === 'query' ? value.trim() : value] as const)
      .filter(([, value]) => value)
  );
}

function sameFilters(left: Record<string, string>, right: Record<string, string>): boolean {
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every(key => left[key] === right[key]);
}

// The field primitives' own look (`Input`), on a native list a test can drive.
const SELECT_CLASS =
  'h-10 w-full min-w-0 rounded-lg border border-input ' +
  'bg-[color:var(--lia-field-background,var(--color-background))] px-3 text-sm shadow-sm ' +
  'transition-colors hover:border-primary/50 focus-visible:outline-none ' +
  'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ' +
  'focus-visible:border-primary';

/** The context filters: each applies as soon as it changes, the search once typing pauses. */
export function DiscussionContextFilters({
  lng,
  filters,
  onChange,
}: {
  lng: Language;
  filters: Record<string, string>;
  onChange: (filters: Record<string, string>) => void;
}) {
  const { t } = useTranslation(lng);
  const [draft, setDraft] = useState(filters);
  const latest = useRef(filters);
  const applied = useRef(appliedFilters(filters));
  const pending = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(pending.current), []);
  function apply(next: Record<string, string>) {
    clearTimeout(pending.current);
    const value = appliedFilters(next);
    // The same selection read again would only reset the page the person is on.
    if (sameFilters(value, applied.current)) return;
    applied.current = value;
    onChange(value);
  }
  function change(key: string, value: string) {
    const next = { ...latest.current, [key]: value };
    latest.current = next;
    setDraft(next);
    if (key !== 'query') {
      apply(next);
      return;
    }
    clearTimeout(pending.current);
    pending.current = setTimeout(() => apply(next), DISCUSSION_SEARCH_DELAY_MS);
  }
  return (
    <form
      className="grid min-w-0 gap-4 sm:grid-cols-2"
      onSubmit={event => {
        // Enter applies the search at once, without waiting for the pause.
        event.preventDefault();
        apply(latest.current);
      }}
    >
      <div className="min-w-0 sm:col-span-2">
        <Input
          id="discussion-context-query"
          label={t('discussions.filters.search')}
          type="search"
          maxLength={160}
          value={draft.query ?? ''}
          onChange={event => change('query', event.target.value)}
        />
      </div>
      <div className="min-w-0 space-y-3">
        <Label htmlFor="discussion-context-source">{t('discussions.filters.source')}</Label>
        <select
          id="discussion-context-source"
          className={SELECT_CLASS}
          value={draft.source ?? ''}
          onChange={event => change('source', event.target.value)}
        >
          <option value="">{t('discussions.filters.all')}</option>
          {discussionSourceSchema.options.map(source => (
            <option key={source} value={source}>
              {t(`discussions.sources.${source}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="min-w-0 space-y-3">
        <Label htmlFor="discussion-context-kind">{t('discussions.filters.kind')}</Label>
        <select
          id="discussion-context-kind"
          className={SELECT_CLASS}
          value={draft.kind ?? ''}
          onChange={event => change('kind', event.target.value)}
        >
          <option value="">{t('discussions.filters.all')}</option>
          {['observation', 'episode', 'pattern'].map(kind => (
            <option key={kind} value={kind}>
              {t(`discussions.kinds.${kind}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="min-w-0 space-y-3">
        <Label htmlFor="discussion-context-use">{t('discussions.filters.usability')}</Label>
        <select
          id="discussion-context-use"
          className={SELECT_CLASS}
          value={draft.usable ?? ''}
          onChange={event => change('usable', event.target.value)}
        >
          <option value="">{t('discussions.filters.all')}</option>
          <option value="true">{t('discussions.usable')}</option>
          <option value="false">{t('discussions.excluded')}</option>
        </select>
      </div>
      <div className="min-w-0">
        <Input
          id="discussion-context-created"
          label={t('discussions.filters.created_from')}
          type="date"
          value={draft.created_from?.slice(0, 10) ?? ''}
          onChange={event =>
            change('created_from', event.target.value ? `${event.target.value}T00:00:00Z` : '')
          }
        />
      </div>
      <div className="flex flex-wrap gap-2 sm:col-span-2">
        <Button
          variant="outline"
          size="sm"
          type="button"
          onClick={() => {
            latest.current = {};
            setDraft({});
            apply({});
          }}
        >
          {t('discussions.filters.reset')}
        </Button>
      </div>
    </form>
  );
}
