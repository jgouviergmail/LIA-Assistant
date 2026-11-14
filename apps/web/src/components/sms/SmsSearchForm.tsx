'use client';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type { DisclosureProps } from '@/components/ui/disclosure';
import { Input } from '@/components/ui/input';
import { civilDateInstant } from '@/lib/civil-date-instant';
import { SEARCH_DEBOUNCE_MS } from '@/lib/constants';
import { getIntlLocale, type Language } from '@/i18n/settings';
import type { SmsQuery } from '@/types/sms';
import { ListControls, ListField, ListFilters, ListSearch } from '@/components/ui/list-toolbar';

const BOUNDS = ['from', 'to'] as const;

/** A `YYYY-MM-DD` bound as the reader writes a date, never shifted by a zone. */
function civilDateLabel(day: string, locale: string): string {
  const [year, month, date] = day.split('-').map(Number);
  if (!year || !month || !date) return day;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(
    new Date(Date.UTC(year, month - 1, date))
  );
}

interface SearchValues {
  search: string;
  from: string;
  to: string;
}
export function SmsSearchForm({
  timezone,
  filtered,
  onChange,
  searchable = true,
  chips,
  surface,
}: {
  timezone: string;
  filtered: boolean;
  onChange: (query: SmsQuery) => void;
  searchable?: boolean;
  /** How the results are grouped: a view, not a narrowing, so it never folds. */
  chips?: ReactNode;
  /** The ground the phone fold alternates with: `nested` inside a hub section. */
  surface?: DisclosureProps['surface'];
}) {
  const { t, i18n } = useTranslation();
  const locale = getIntlLocale(i18n.language as Language);
  const id = useId();
  const [values, setValues] = useState<SearchValues>({ search: '', from: '', to: '' });
  const [invalid, setInvalid] = useState(false);
  function change(next: SearchValues) {
    setValues(next);
    const { search, from, to } = next;
    try {
      if (from && to && from >= to) throw new RangeError();
      onChange({
        ...(search.trim() ? { query: search.trim() } : {}),
        ...(from ? { from_ts: civilDateInstant(from, timezone) } : {}),
        ...(to ? { to_ts: civilDateInstant(to, timezone) } : {}),
      });
      setInvalid(false);
    } catch {
      setInvalid(true);
    }
  }
  return (
    <div role="search" className="space-y-3">
      {searchable && (
        <ListSearch
          query={values.search}
          onQuery={search => change({ ...values, search })}
          searchLabel={t('sms.search')}
          debounceMs={SEARCH_DEBOUNCE_MS}
        />
      )}
      <ListFilters
        surface={surface}
        active={BOUNDS.filter(bound => values[bound]).map(
          bound =>
            `${t(`sms.${bound}`)}${t('common.label_separator')}${civilDateLabel(values[bound], locale)}`
        )}
      >
        <ListControls>
          {BOUNDS.map(bound => (
            <ListField key={bound} htmlFor={`${id}-${bound}`} label={t(`sms.${bound}`)}>
              <Input
                id={`${id}-${bound}`}
                type="date"
                className="h-11 min-w-0 w-full"
                value={values[bound]}
                onChange={event => change({ ...values, [bound]: event.target.value })}
              />
            </ListField>
          ))}
        </ListControls>
      </ListFilters>
      {chips && <ListControls chips={chips} />}
      {invalid && (
        <p role="alert" className="text-sm text-destructive">
          {t('common.error')}
        </p>
      )}
      {(filtered || Object.values(values).some(Boolean)) && (
        <Button
          type="button"
          variant="ghost"
          onClick={() => change({ search: '', from: '', to: '' })}
        >
          {t('sms.clear_search')}
        </Button>
      )}
    </div>
  );
}
